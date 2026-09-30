import fastapi
import typing
import logging
import uuid
import datetime
import functools
import threading

from db.models import Action, JobBoard
from apis.schemas import (AgentRun, AgentRunRequest, AgentRunSummary, AnalyticsReport, AnalyticsRun,
                          AnalyticsRunRequest, ResumeReport, RunStatus)
from agents.analytics.agent import build_tables, load_jobs
from agents.resume_builder.agent import run_resume_builder
from agents.graph.analytic_graph import build_analytic_graph
from agents.graph.graph import build_graph
from agents.portal_search.agent import load_portals
from agents.sandbox import SandboxConfig

AGENTS_ROUTER: typing.Final = fastapi.APIRouter(prefix="/agents", tags=["agents"])

logger = logging.getLogger(__name__)

# Runs are kept in memory: they are lost when the API restarts, but the jobs they
# found are already in job_board_table (written by the graph's db_ingestion node).
RUNS: dict[uuid.UUID, AgentRun] = {}
ANALYTICS_RUNS: dict[uuid.UUID, AnalyticsRun] = {}
# One run at a time: every run shares the local LLM and a sandbox container.
RUN_LOCK = threading.Lock()


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


def _run_graph(run_id: uuid.UUID, portals: list[dict]) -> None:
    """Background task: portal_search -> qualification_check -> db_ingestion, then records the outcome."""
    run = RUNS[run_id]
    try:
        run.status, run.started_at = RunStatus.running, _now()
        state = _graph(run.sandbox).invoke({"portals": portals})
        scored = state.get("scored_positions")  # None when no positions were found
        run.summary = AgentRunSummary(
            positions=len(state.get("positions", [])),
            scored=int(scored["score"].notna().sum()) if scored is not None and "score" in scored else 0,
            ingested=state.get("ingested", 0),
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
    """Spins off the agents: searches the portals, scores the positions and saves them to the DB.
    Returns immediately with a run id; poll GET /agents/runs/{run_id} for the result."""
    portals = load_portals()
    if body.portals:
        wanted = {name.strip().lower() for name in body.portals}
        portals = [p for p in portals if p["name"].lower() in wanted]
        if not portals:
            raise fastapi.HTTPException(status_code=404, detail=f"no enabled portal matches {body.portals}")

    if not RUN_LOCK.acquire(blocking=False):
        raise fastapi.HTTPException(status_code=409, detail="an agent run is already in progress")

    run = AgentRun(
        id=uuid.uuid4(),
        status=RunStatus.queued,
        portals=[p["name"] for p in portals],
        sandbox=body.sandbox,
        created_at=_now(),
    )
    RUNS[run.id] = run
    background_tasks.add_task(_run_graph, run.id, portals)  # releases RUN_LOCK when done
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


@AGENTS_ROUTER.post("/resume/{job_id}", response_model=ResumeReport)
def build_resume(job_id: uuid.UUID):
    """Builds a Markdown resume tailored to a saved job from the user's knowledge base and
    projects, plus side-project ideas for the skills the job asks for that the user lacks.
    Takes a minute or two (two LLM calls); nothing is saved."""
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
    return ResumeReport(
        job_id=job["id"],
        company_name=job["company_name"],
        position=job["position"],
        resume=report["resume"],
        side_projects=report["side_projects"],
        generated_at=_now(),
    )


@AGENTS_ROUTER.get("/portals", response_model=list[str])
def list_portals():
    """Names of the enabled portals in portals.yml, for the frontend's portal picker."""
    return [p["name"] for p in load_portals()]
