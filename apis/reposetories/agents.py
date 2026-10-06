import fastapi
import typing
import logging
import uuid
import datetime
import functools
import threading

from db.models import Action, JobBoard
from starlette.concurrency import iterate_in_threadpool, run_in_threadpool

from db import dbOps
from apis.schemas import (AgentRun, AgentRunRequest, AgentRunSummary, AnalyticsReport, AnalyticsRun,
                          AnalyticsRunRequest, KnowledgeRun, KnowledgeRunRequest, PortalChanges, PortalCreate,
                          ResumeDraftOut, ResumeDraftSummary, ResumeDraftUpdate, ResumeReport, RunLog, RunStatus,
                          TargetPositionCreate, UserDocs)
from agents.analytics.agent import build_tables, load_jobs
from agents.knowledge_base.agent import (KINDS, KNOWLEDGE_FILE, USER_DOCS_DIR, apply_portal_changes, create_folders,
                                        run_knowledge_base, scan_user_docs)
from agents.resume_builder.agent import load_job, run_resume_builder
from agents.resume_builder.chat import stream_chat
from agents.graph.analytic_graph import build_analytic_graph
from agents.graph.graph import build_graph
from agents.portal_search.agent import load_portals, load_target_positions
from agents.sandbox import SandboxConfig

AGENTS_ROUTER: typing.Final = fastapi.APIRouter(prefix="/agents", tags=["agents"])

logger = logging.getLogger(__name__)

# Runs are kept in memory: they are lost when the API restarts, but the jobs they
# found are already in job_board_table (written by the graph's db_ingestion node).
RUNS: dict[uuid.UUID, AgentRun] = {}
ANALYTICS_RUNS: dict[uuid.UUID, AnalyticsRun] = {}
KNOWLEDGE_RUNS: dict[uuid.UUID, KnowledgeRun] = {}
# One run at a time: every run shares the local LLM and a sandbox container.
RUN_LOCK = threading.Lock()
MAX_ACTIVITY_LOGS = 300  # AgentRun.logs keeps every progress line but only the newest detail lines


@functools.lru_cache(maxsize=2)
def _graph(sandbox: str):
    """Compiled graph per sandbox service; built once because it loads the local LLM."""
    return build_graph(sandbox_config=SandboxConfig(service=sandbox))


@functools.lru_cache(maxsize=2)
def _analytic_graph(sandbox: str):
    """Compiled analytics graph per sandbox service; built once because it loads the local LLM."""
    return build_analytic_graph(sandbox_config=SandboxConfig(service=sandbox))


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def _run_graph(run_id: uuid.UUID, portals: list[dict], manual_positions: list[dict]) -> None:
    """Background task: portal_search -> qualification_check -> db_ingestion, then records the outcome.
    The nodes' progress and live-activity lines (agents/utils/progress.py) are collected into
    run.logs as they stream and echoed to the API's log."""
    run = RUNS[run_id]
    try:
        run.status, run.started_at = RunStatus.running, _now()
        state: dict = {}
        stream = _graph(run.sandbox).stream({"portals": portals, "manual_positions": manual_positions},
                                            stream_mode=["custom", "values"])
        for mode, chunk in stream:
            if mode == "values":
                state = chunk
            else:
                run.stage = chunk["stage"]
                line = RunLog(**chunk, at=_now())
                logger.info("[%s] %s", line.stage, line.message)
                logs = run.logs + [line]
                if line.detail and sum(l.detail for l in logs) > MAX_ACTIVITY_LOGS:
                    oldest = next(i for i, l in enumerate(logs) if l.detail)
                    logs = logs[:oldest] + logs[oldest + 1:]
                run.logs = logs
        scored = state.get("scored_positions")  # None when no positions were found
        run.summary = AgentRunSummary(
            positions=len(state.get("positions", [])),
            scored=int(scored["score"].notna().sum()) if scored is not None and "score" in scored else 0,
            ingested=state.get("ingested", 0),
            skipped_known=state.get("skipped_known", 0),
            portal_errors=state.get("portal_errors", []),
            qualification_errors=state.get("qualification_errors", []),
            ingestion_errors=state.get("ingestion_errors", []),
        )
        run.status = RunStatus.succeeded
    except Exception as e:
        logger.exception("agent run %s failed", run_id)
        run.status, run.error = RunStatus.failed, str(e)
    finally:
        run.finished_at = _now()
        RUN_LOCK.release()


@AGENTS_ROUTER.post("/runs", response_model=AgentRun, status_code=fastapi.status.HTTP_202_ACCEPTED)
def start_run(body: AgentRunRequest, background_tasks: fastapi.BackgroundTasks):
    """Spins off the agents: searches the portals, scores the positions (plus any manual_positions)
    and saves them to the DB. portals None searches every enabled portal, [] none (then
    manual_positions must be given). Returns immediately with a run id; poll
    GET /agents/runs/{run_id} for its stage, logs and result."""
    portals = load_portals()
    if body.portals is not None:
        wanted = {name.strip().lower() for name in body.portals}
        portals = [p for p in portals if p["name"].lower() in wanted]
        if body.portals and not portals:
            raise fastapi.HTTPException(status_code=404, detail=f"no enabled portal matches {body.portals}")
    if not portals and not body.manual_positions:
        raise fastapi.HTTPException(status_code=422, detail="choose at least one portal or add a position manually")

    if not RUN_LOCK.acquire(blocking=False):
        raise fastapi.HTTPException(status_code=409, detail="an agent run is already in progress")

    manual = [p.model_dump(mode="json") for p in body.manual_positions]
    run = AgentRun(
        id=uuid.uuid4(),
        status=RunStatus.queued,
        portals=[p["name"] for p in portals] + [f"{p['company']} (manual)" for p in manual],
        sandbox=body.sandbox,
        created_at=_now(),
    )
    RUNS[run.id] = run
    background_tasks.add_task(_run_graph, run.id, portals, manual)  # releases RUN_LOCK when done
    return run


@AGENTS_ROUTER.get("/runs", response_model=list[AgentRun])
def list_runs():
    """Lists the runs started since the API came up, newest first."""
    return sorted(RUNS.values(), key=lambda r: r.created_at, reverse=True)


@AGENTS_ROUTER.get("/runs/{run_id}", response_model=AgentRun)
def get_run(run_id: uuid.UUID):
    """Status of one run; summary (positions found, scored, ingested, errors) is set once it finishes."""
    run = RUNS.get(run_id)
    if run is None:
        raise fastapi.HTTPException(status_code=404, detail="run not found")
    return run


def _analytics_report(state: dict) -> AnalyticsReport:
    """AnalyticsReport from the analytic graph's state (or just load_data's jobs + tables)."""
    return AnalyticsReport(
        total_jobs=len(state["jobs"]),
        tables={name: df.to_dict("records") for name, df in state["tables"].items()},
        near_miss_jobs=state.get("near_miss_jobs") or [],
        skill_gaps=state.get("skill_gaps") or [],
        analysis=state.get("analysis") or "",
        conclusion=state.get("conclusion") or "",
        projects=state.get("projects") or [],
        errors=state.get("analytics_errors") or [],
        generated_at=_now(),
    )


def _run_analytics(run_id: uuid.UUID) -> None:
    """Background task: load_data -> analytics_agent (sandbox), then records the report."""
    run = ANALYTICS_RUNS[run_id]
    try:
        run.status, run.started_at = RunStatus.running, _now()
        run.report = _analytics_report(_analytic_graph(run.sandbox).invoke({}))
        run.status = RunStatus.succeeded
    except Exception as e:
        logger.exception("analytics run %s failed", run_id)
        run.status, run.error = RunStatus.failed, str(e)
    finally:
        run.finished_at = _now()
        RUN_LOCK.release()


@AGENTS_ROUTER.get("/analytics", response_model=AnalyticsReport)
def get_analytics():
    """Chart tables over every saved job (status counts, funnel, work type, company,
    compatibility, weekly activity). Fast: host pandas only, no LLM or sandbox.
    For near-miss jobs, skill gaps, the written analysis and side projects, start
    POST /agents/analytics/runs."""
    jobs = load_jobs()
    return _analytics_report({"jobs": jobs, "tables": build_tables(jobs)})


@AGENTS_ROUTER.post("/analytics/runs", response_model=AnalyticsRun, status_code=fastapi.status.HTTP_202_ACCEPTED)
def start_analytics_run(body: AnalyticsRunRequest, background_tasks: fastapi.BackgroundTasks):
    """Spins off the analytics agent: it runs code in a sandbox to find the near-miss jobs
    and skill gaps, writes the analysis and recommends side projects. Takes a few minutes.
    Returns immediately with a run id; poll GET /agents/analytics/runs/{run_id} for the report."""
    # Shares the local LLM with the search runs.
    if not RUN_LOCK.acquire(blocking=False):
        raise fastapi.HTTPException(status_code=409, detail="an agent run is already in progress")
    run = AnalyticsRun(id=uuid.uuid4(), status=RunStatus.queued, sandbox=body.sandbox, created_at=_now())
    ANALYTICS_RUNS[run.id] = run
    background_tasks.add_task(_run_analytics, run.id)  # releases RUN_LOCK when done
    return run


@AGENTS_ROUTER.get("/analytics/runs/{run_id}", response_model=AnalyticsRun)
def get_analytics_run(run_id: uuid.UUID):
    """Status of one analytics run; report is set once it succeeds."""
    run = ANALYTICS_RUNS.get(run_id)
    if run is None:
        raise fastapi.HTTPException(status_code=404, detail="analytics run not found")
    return run


def _user_docs() -> UserDocs:
    exists = KNOWLEDGE_FILE.exists()
    return UserDocs(
        root=str(USER_DOCS_DIR),
        folders=scan_user_docs(),
        knowledge_file=str(KNOWLEDGE_FILE),
        knowledge=KNOWLEDGE_FILE.read_text() if exists else "",
        knowledge_updated_at=(datetime.datetime.fromtimestamp(KNOWLEDGE_FILE.stat().st_mtime, datetime.UTC)
                              if exists else None),
    )


@AGENTS_ROUTER.get("/knowledge/documents", response_model=UserDocs)
def get_user_docs():
    """The Docs/user_docs folders the knowledge base agent reads (resumes, education, projects,
    papers, achievements, other): whether each exists, how many documents it holds and a tree
    of its files, plus the current knowledge base."""
    return _user_docs()


@AGENTS_ROUTER.post("/knowledge/folders", response_model=UserDocs)
def create_user_docs_folders():
    """Creates Docs/user_docs and any of its document folders that are missing, so a new user
    has the layout to drop files into. Returns the updated listing."""
    create_folders()
    return _user_docs()


def _run_knowledge(run_id: uuid.UUID) -> None:
    """Background task: rebuilds user_knowledge.md and (optionally) tunes portals.yml, then records the outcome."""
    run = KNOWLEDGE_RUNS[run_id]
    try:
        run.status, run.started_at = RunStatus.running, _now()
        result = run_knowledge_base(kinds=run.kinds, update_portals=run.update_portals)
        run.documents = result["documents"]
        run.portals = PortalChanges(**result["portals"]) if result["portals"] is not None else None
        run.status = RunStatus.succeeded
    except Exception as e:
        logger.exception("knowledge run %s failed", run_id)
        run.status, run.error = RunStatus.failed, str(e)
    finally:
        run.finished_at = _now()
        RUN_LOCK.release()


@AGENTS_ROUTER.post("/knowledge/runs", response_model=KnowledgeRun, status_code=fastapi.status.HTTP_202_ACCEPTED)
def start_knowledge_run(body: KnowledgeRunRequest, background_tasks: fastapi.BackgroundTasks):
    """Spins off the knowledge base agent: it rebuilds Docs/user_docs/user_knowledge.md from the
    chosen kinds of documents and adjusts portals.yml's title keywords and companies to it.
    Takes several minutes (one LLM call per section and project). 422 if none of the chosen
    folders has a document. Returns immediately; poll GET /agents/knowledge/runs/{run_id}."""
    kinds = body.kinds or list(KINDS)
    counts = {f["kind"]: f["documents"] for f in scan_user_docs()}
    if not any(counts[kind] for kind in kinds):
        raise fastapi.HTTPException(status_code=422, detail=f"no documents in the chosen folders ({', '.join(kinds)})")
    # Shares the local LLM with the other agents.
    if not RUN_LOCK.acquire(blocking=False):
        raise fastapi.HTTPException(status_code=409, detail="an agent run is already in progress")
    run = KnowledgeRun(id=uuid.uuid4(), status=RunStatus.queued, kinds=kinds,
                       update_portals=body.update_portals, created_at=_now())
    KNOWLEDGE_RUNS[run.id] = run
    background_tasks.add_task(_run_knowledge, run.id)  # releases RUN_LOCK when done
    return run


@AGENTS_ROUTER.get("/knowledge/runs", response_model=list[KnowledgeRun])
def list_knowledge_runs():
    """Lists the knowledge base runs started since the API came up, newest first."""
    return sorted(KNOWLEDGE_RUNS.values(), key=lambda r: r.created_at, reverse=True)


@AGENTS_ROUTER.get("/knowledge/runs/{run_id}", response_model=KnowledgeRun)
def get_knowledge_run(run_id: uuid.UUID):
    """Status of one knowledge base run; documents and portal changes are set once it succeeds."""
    run = KNOWLEDGE_RUNS.get(run_id)
    if run is None:
        raise fastapi.HTTPException(status_code=404, detail="knowledge run not found")
    return run


@AGENTS_ROUTER.post("/resume/{job_id}", response_model=ResumeReport)
def build_resume(job_id: uuid.UUID):
    """Builds a Markdown resume tailored to a saved job from the user's knowledge base and
    projects, plus side-project ideas for the skills the job asks for that the user lacks.
    Takes a minute or two (two LLM calls). The result is saved as a new resume draft
    (draft_id) that GET /agents/resume/drafts/{draft_id} and the resume chat work on."""
    # The resume shares the local LLM with the search runs.
    if not RUN_LOCK.acquire(blocking=False):
        raise fastapi.HTTPException(status_code=409, detail="an agent run is using the model; try again later")
    try:
        report = run_resume_builder(job_id)
    except LookupError as e:
        raise fastapi.HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise fastapi.HTTPException(status_code=422, detail=str(e))
    finally:
        RUN_LOCK.release()
    job = report["job"]
    draft = dbOps.create_draft(job["id"], report["resume"], report["side_projects"])
    return ResumeReport(
        draft_id=draft["id"],
        job_id=job["id"],
        company_name=job["company_name"],
        position=job["position"],
        resume=report["resume"],
        side_projects=report["side_projects"],
        generated_at=_now(),
    )



def _draft_or_404(draft_id: uuid.UUID) -> dict:
    draft = dbOps.get_draft(draft_id)
    if draft is None:
        raise fastapi.HTTPException(status_code=404, detail="resume draft not found")
    return draft


@AGENTS_ROUTER.get("/resume/drafts", response_model=list[ResumeDraftSummary])
def list_resume_drafts(job_id: typing.Optional[uuid.UUID] = None):
    """Lists saved resume drafts, most recently edited first; only one job's when job_id is given."""
    return dbOps.list_drafts(job_id)


@AGENTS_ROUTER.get("/resume/drafts/{draft_id}", response_model=ResumeDraftOut)
def get_resume_draft(draft_id: uuid.UUID):
    """One resume draft: its current resume and side projects, chat history and older versions."""
    return _draft_or_404(draft_id)


@AGENTS_ROUTER.put("/resume/drafts/{draft_id}", response_model=ResumeDraftOut)
def update_resume_draft(draft_id: uuid.UUID, body: ResumeDraftUpdate):
    """Saves a manual edit of a draft's resume and/or side projects; the old content becomes a version."""
    draft = dbOps.update_draft(draft_id, resume=body.resume, side_projects=body.side_projects, note="manual edit")
    if draft is None:
        raise fastapi.HTTPException(status_code=404, detail="resume draft not found")
    return draft


@AGENTS_ROUTER.post("/resume/drafts/{draft_id}/revert/{version}", response_model=ResumeDraftOut)
def revert_resume_draft(draft_id: uuid.UUID, version: int):
    """Restores versions[version] of a draft; the current content is kept as a new version first."""
    if version < 0 or version >= len(_draft_or_404(draft_id)["versions"]):
        raise fastapi.HTTPException(status_code=404, detail="no such version")
    return dbOps.revert_draft(draft_id, version)


def _chat_model():
    from agents.utils.langchainConfig import chat_model  # loads the local LLM on first use
    return chat_model


async def _chat_turn(ws: fastapi.WebSocket, draft: dict, job: dict, content: str) -> dict:
    """Streams one reply's events to the socket, then saves the messages and doc edits.
    Returns the updated draft dict. The caller holds RUN_LOCK."""
    model = await run_in_threadpool(_chat_model)
    result = None
    async for event in iterate_in_threadpool(stream_chat(model, draft, job, content)):
        if event["type"] == "result":
            result = event
        else:
            await ws.send_json(event)
    note = f"chat: {content[:200]}"
    return await run_in_threadpool(
        dbOps.update_draft, draft["id"], resume=result.get("resume"), side_projects=result.get("side_projects"),
        note=note, messages=[{"role": "user", "content": content},
                             {"role": "assistant", "content": result["reply"]}])


@AGENTS_ROUTER.websocket("/resume/drafts/{draft_id}/chat")
async def resume_chat(ws: fastapi.WebSocket, draft_id: uuid.UUID):
    """Chat that edits a resume draft, streamed over a websocket.

    Client sends {"type": "message", "content": "<request>"}. Server replies with
    {"type": "status", "state": "thinking" | "writing"}, then
    {"type": "token", "target": "chat" | "resume" | "side_projects", "text"} as the reply streams,
    then {"type": "done", "draft": ResumeDraftOut} once the messages and edits are saved.
    Errors arrive as {"type": "error", "detail"} and leave the socket open, e.g. "model busy"
    while another agent run is using the local LLM. Closes with 4404 if the draft doesn't exist."""
    await ws.accept()
    draft = await run_in_threadpool(dbOps.get_draft, draft_id)
    if draft is None:
        await ws.close(code=4404, reason="resume draft not found")
        return
    job = await run_in_threadpool(load_job, draft["job_id"])
    try:
        while True:
            data = await ws.receive_json()
            content = str(data.get("content") or "").strip() if isinstance(data, dict) else ""
            if not (isinstance(data, dict) and data.get("type") == "message" and content):
                await ws.send_json({"type": "error", "detail": 'expected {"type": "message", "content": "..."}'})
                continue
            # Shares the local LLM with the search, analytics and resume runs.
            if not RUN_LOCK.acquire(blocking=False):
                await ws.send_json({"type": "error", "detail": "model busy: an agent run is using it; try again later"})
                continue
            try:
                draft = await _chat_turn(ws, draft, job, content)
            except fastapi.WebSocketDisconnect:
                raise
            except Exception as e:
                logger.exception("resume chat on draft %s failed", draft_id)
                await ws.send_json({"type": "error", "detail": str(e)})
                continue
            finally:
                RUN_LOCK.release()
            await ws.send_json({"type": "done", "draft": ResumeDraftOut(**draft).model_dump(mode="json")})
    except fastapi.WebSocketDisconnect:
        pass


@AGENTS_ROUTER.get("/portals", response_model=list[str])
def list_portals():
    """Names of the enabled portals in portals.yml, for the frontend's portal picker."""
    return [p["name"] for p in load_portals()]


@AGENTS_ROUTER.get("/portals/positions", response_model=list[str])
def list_target_positions():
    """Positive title_filter keywords in portals.yml: the positions the portal search targets."""
    return load_target_positions()


def _edit_portals(changes: dict) -> dict:
    """Applies changes to portals.yml (knowledge_base.apply_portal_changes, which keeps its comments).
    409 while an agent run is using portals.yml, 422 if the edit is invalid."""
    if not RUN_LOCK.acquire(blocking=False):
        raise fastapi.HTTPException(status_code=409, detail="an agent run is in progress; edit portals when it finishes")
    try:
        return apply_portal_changes(changes, by="the user (search page)")
    except ValueError as e:
        raise fastapi.HTTPException(status_code=422, detail=str(e))
    finally:
        RUN_LOCK.release()


@AGENTS_ROUTER.post("/portals", response_model=list[str])
def add_portal(body: PortalCreate):
    """Adds a company careers page to portals.yml's tracked_companies (or re-enables it if it was
    dropped) so the next search covers it. Returns the enabled portal names."""
    _edit_portals({"companies_add": [{"name": body.name.strip(), "careers_url": body.careers_url.strip()}]})
    return list_portals()


@AGENTS_ROUTER.delete("/portals/{name}", response_model=list[str])
def remove_portal(name: str):
    """Drops a portal from the search: its portals.yml entry is kept but set to enabled: false.
    404 if no enabled portal has that name. Returns the enabled portal names."""
    if not _edit_portals({"companies_drop": [name]})["companies_disabled"]:
        raise fastapi.HTTPException(status_code=404, detail=f"no enabled portal named {name!r}")
    return list_portals()


@AGENTS_ROUTER.post("/portals/positions", response_model=list[str])
def add_target_position(body: TargetPositionCreate):
    """Adds a keyword to portals.yml's title_filter.positive: postings whose title contains it are
    searched for. Returns the target positions."""
    _edit_portals({"positive_add": [body.keyword.strip()]})
    return load_target_positions()


@AGENTS_ROUTER.delete("/portals/positions/{keyword:path}", response_model=list[str])
def remove_target_position(keyword: str):
    """Removes a keyword from portals.yml's title_filter.positive (422 if it is the last one,
    404 if it isn't there). Returns the target positions."""
    if not _edit_portals({"positive_remove": [keyword]})["positive_removed"]:
        raise fastapi.HTTPException(status_code=404, detail=f"no target position {keyword!r}")
    return load_target_positions()
