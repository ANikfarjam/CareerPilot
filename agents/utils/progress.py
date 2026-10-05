"""
Progress lines of the orchestrator graph's nodes, for the frontend's live run log.

  A node calls `stage_logger(stage)` and passes the returned `log(level, message)`
  to the functions it runs (search_portals, evaluate_positions, ...). The lines go
  to LangGraph's custom stream (graph.stream(..., stream_mode="custom")), which
  apis/reposetories/agents.py collects into AgentRun.logs. With .invoke() nothing
  listens and they are dropped.
"""

from typing import Callable, Literal

from langgraph.config import get_stream_writer

Level = Literal["info", "success", "error"]
Log = Callable[[Level, str], None]


def no_log(level: Level, message: str) -> None:
    """Default `log` of functions called outside the graph."""


def stage_logger(stage: str) -> Log:
    """`log(level, message)` that streams {"stage", "level", "message"}; call it inside a graph node."""
    writer = get_stream_writer()
    return lambda level, message: writer({"stage": stage, "level": level, "message": message})
