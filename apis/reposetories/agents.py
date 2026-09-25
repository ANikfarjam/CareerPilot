import fastapi
import typing
import logging
import uuid
import datetime
import functools
import threading

from db.models import Action, JobBoard
from apis.schemas import AgentRun, AgentRunRequest, AgentRunSummary, RunStatus
from agents.graph.graph import build_graph
from agents.portal_search.agent import load_portals
from agents.sandbox import SandboxConfig

AGENTS_ROUTER: typing.Final = fastapi.APIRouter(prefix="/agents", tags=["agents"])

logger = logging.getLogger(__name__)

# Runs are kept in memory: they are lost when the API restarts, but the jobs they
# found are already in job_board_table (written by the graph's db_ingestion node).
RUNS: dict[uuid.UUID, AgentRun] = {}
# One run at a time: every run shares the local LLM and a sandbox container.
RUN_LOCK = threading.Lock()


@functools.lru_cache(maxsize=2)
def _graph(sandbox: str):
    """Compiled graph per sandbox service; built once because it loads the local LLM."""
    return build_graph(sandbox_config=SandboxConfig(service=sandbox))


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


@AGENTS_ROUTER.get("/portals", response_model=list[str])
def list_portals():
    """Names of the enabled portals in portals.yml, for the frontend's portal picker."""
    return [p["name"] for p in load_portals()]
