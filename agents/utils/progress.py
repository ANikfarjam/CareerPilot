"""
Progress lines of the orchestrator graph's nodes, for the frontend's live run log.

  A node calls `stage_logger(stage)` and passes the returned `log(level, message)`
  to the functions it runs (search_portals, evaluate_positions, ...). The lines go
  to LangGraph's custom stream (graph.stream(..., stream_mode="custom")), which
  apis/reposetories/agents.py collects into AgentRun.logs. With .invoke() nothing
  listens and they are dropped.

  log(level, message, detail=True) marks a live-activity line (each step of an
  agent's loop: the model call, the command it runs, its exit code) instead of a
  progress line (which portal, how many found); the frontend shows them apart.
"""

from typing import Literal, Protocol

from langgraph.config import get_stream_writer

Level = Literal["info", "success", "error"]


class Log(Protocol):
    def __call__(self, level: Level, message: str, *, detail: bool = False) -> None: ...


def no_log(level: Level, message: str, *, detail: bool = False) -> None:
    """Default `log` of functions called outside the graph."""


def stage_logger(stage: str) -> Log:
    """`log(level, message, detail=False)` that streams {"stage", "level", "message", "detail"};
    call it inside a graph node."""
    writer = get_stream_writer()

    def log(level: Level, message: str, *, detail: bool = False) -> None:
        writer({"stage": stage, "level": level, "message": message, "detail": detail})

    return log
