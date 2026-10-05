"""
Orchestrator: the parent LangGraph that chains the agents.

    START -> portal_search -> qualification_check -> db_ingestion -> END
                    \\__ (no positions found) _________________________/

  - portal_search       searches every portal in one sandbox container and
                        returns `positions` (DataFrame, portal_search COLUMNS),
                        minus postings already in the DB (`skipped_known`).
  - qualification_check scores each position against user_knowledge.md on the
                        host (no sandbox) and returns `scored_positions`
                        (positions + SCORE_COLUMNS, best score first).
  - db_ingestion        upserts the scored positions into job_board_table
                        (DATABASE_URL), writes their descriptions to
                        Docs/job_descriptions/*.md and returns `ingested` (row count).

Both agents share one chat model, so the local LLM is loaded once.
The state holds DataFrames, so the graph is compiled without a checkpointer.

Run it:
    python -m agents.graph.graph                         # all enabled portals
    python -m agents.graph.graph --portals Anthropic,Modal --sandbox sandbox-cpu
    python -m agents.graph.graph --rescan                # also re-score saved postings
"""

import argparse
import json
from pathlib import Path
from typing import Literal, TypedDict

import pandas as pd
from langchain_core.language_models import BaseChatModel
from langgraph.graph import END, START, StateGraph

from agents.portal_search.agent import load_portals, make_portal_search_node
from agents.qualification_check.agent import KNOWLEDGE_FILE, make_qualification_node
from agents.sandbox import SandboxConfig
from agents.sandbox.config import PROJECT_ROOT
from agents.utils.dbingestion import make_db_ingestion_node

OUTPUT_DIR = PROJECT_ROOT / "results"


class CareerState(TypedDict, total=False):
    portals: list[dict]  # input; missing = all enabled tracked_companies in portals.yml, [] = none
    manual_positions: list[dict]  # input; postings added by hand (apis.schemas.ManualPosition), scored and saved too
    positions: pd.DataFrame
    portal_errors: list[dict]
    skipped_known: int  # postings already in the DB, dropped before scoring
    scored_positions: pd.DataFrame
    qualification_errors: list[dict]
    ingested: int
    ingestion_errors: list[dict]


def build_graph(
    model: BaseChatModel | None = None,
    sandbox_config: SandboxConfig | None = None,
    knowledge_file: Path = KNOWLEDGE_FILE,
    skip_known: bool = True,
):
    if model is None:
        from agents.utils.langchainConfig import chat_model as model  # loads the local LLM

    def route(state: CareerState) -> Literal["qualification_check", "__end__"]:
        return "qualification_check" if len(state["positions"]) else END

    graph = StateGraph(CareerState)
    graph.add_node("portal_search", make_portal_search_node(model, sandbox_config, skip_known))
    graph.add_node("qualification_check", make_qualification_node(model, knowledge_file))
    graph.add_edge(START, "portal_search")
    graph.add_conditional_edges("portal_search", route)
    graph.add_node("db_ingestion", make_db_ingestion_node())
    graph.add_edge("qualification_check", "db_ingestion")
    graph.add_edge("db_ingestion", END)
    return graph.compile()


def main() -> None:
    parser = argparse.ArgumentParser(description="Search job portals and score positions against the user's profile.")
    parser.add_argument("--portals", help="comma-separated portal names from portals.yml (default: all enabled)")
    parser.add_argument("--sandbox", default="sandbox", choices=["sandbox", "sandbox-cpu"], help="sandbox service")
    parser.add_argument("--rescan", action="store_true", help="also scan and score postings already in the database")
    parser.add_argument("--out", type=Path, default=OUTPUT_DIR, help="output directory")
    args = parser.parse_args()

    portals = load_portals()
    if args.portals:
        wanted = {name.strip().lower() for name in args.portals.split(",")}
        portals = [p for p in portals if p["name"].lower() in wanted]
        if not portals:
            parser.error(f"no enabled portal matches {args.portals!r}")

    app = build_graph(sandbox_config=SandboxConfig(service=args.sandbox), skip_known=not args.rescan)
    state = app.invoke({"portals": portals})

    args.out.mkdir(parents=True, exist_ok=True)
    scored = state.get("scored_positions")
    if scored is None:  # nothing found, qualification_check was skipped
        scored = state["positions"]
    scored.to_csv(args.out / "scored_positions.csv", index=False)
    errors = {
        "portal_errors": state.get("portal_errors", []),
        "qualification_errors": state.get("qualification_errors", []),
        "ingestion_errors": state.get("ingestion_errors", []),
    }
    (args.out / "errors.json").write_text(json.dumps(errors, indent=2))

    print(f"{len(state['positions'])} new positions from {len(portals)} portals -> {args.out / 'scored_positions.csv'}"
          f" ({state.get('skipped_known', 0)} already saved, skipped)")
    print(f"{len(errors['portal_errors'])} portal errors, {len(errors['qualification_errors'])} scoring errors")
    print(f"{state.get('ingested', 0)} positions saved to the database, {len(errors['ingestion_errors'])} not saved")
    if "score" in scored:
        print(scored[["score", "company", "position", "link"]].head(10).to_string(index=False))


if __name__ == "__main__":
    main()
