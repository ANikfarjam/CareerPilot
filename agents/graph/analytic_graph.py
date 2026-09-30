"""
Analytics orchestrator: the LangGraph that analyzes the saved jobs. Separate from
the search graph (graph.py): it only reads what that pipeline saved to job_board_table.

    START -> load_data -> analytics_agent -> END
                  \\__ (no jobs saved) ______/

  - load_data         reads every job (with descriptions and qualification_check's
                      requirements / matched / missing) and builds the fixed chart
                      tables on the host with pandas. Returns `jobs` (DataFrame)
                      and `tables` ({name: DataFrame}, see analytics build_tables).
  - analytics_agent   starts a sandbox container and runs the code-as-action
                      analytics agent in it: finds the near-miss jobs, ranks the
                      skill gaps, writes the analysis + conclusion and recommends
                      side projects. Returns `near_miss_jobs`, `skill_gaps`,
                      `analysis`, `conclusion`, `projects` and `analytics_errors`
                      (on failure only the errors, so the tables are still usable).

The state holds DataFrames, so the graph is compiled without a checkpointer.

Run it:
    python -m agents.graph.analytic_graph
    python -m agents.graph.analytic_graph --sandbox sandbox-cpu
"""

import argparse
import json
from pathlib import Path
from typing import Literal, TypedDict

import pandas as pd
from langchain_core.language_models import BaseChatModel
from langgraph.graph import END, START, StateGraph

from agents.analytics.agent import build_tables, load_jobs, make_analytics_node
from agents.qualification_check.agent import KNOWLEDGE_FILE
from agents.sandbox import SandboxConfig
from agents.graph.graph import OUTPUT_DIR


class AnalyticsState(TypedDict, total=False):
    jobs: pd.DataFrame
    tables: dict[str, pd.DataFrame]
    near_miss_jobs: list[dict]
    skill_gaps: list[dict]
    analysis: str
    conclusion: str
    projects: list[dict]
    analytics_errors: list[str]


def load_data(state: AnalyticsState) -> dict:
    jobs = load_jobs(with_description=True)
    return {"jobs": jobs, "tables": build_tables(jobs)}


def build_analytic_graph(
    model: BaseChatModel | None = None,
    sandbox_config: SandboxConfig | None = None,
    knowledge_file: Path = KNOWLEDGE_FILE,
):
    def route(state: AnalyticsState) -> Literal["analytics_agent", "__end__"]:
        return "analytics_agent" if len(state["jobs"]) else END

    graph = StateGraph(AnalyticsState)
    graph.add_node("load_data", load_data)
    graph.add_node("analytics_agent", make_analytics_node(model, sandbox_config, knowledge_file))
    graph.add_edge(START, "load_data")
    graph.add_conditional_edges("load_data", route)
    graph.add_edge("analytics_agent", END)
    return graph.compile()


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze the saved jobs and recommend side projects.")
    parser.add_argument("--sandbox", default="sandbox", choices=["sandbox", "sandbox-cpu"], help="sandbox service")
    parser.add_argument("--out", type=Path, default=OUTPUT_DIR, help="output directory")
    args = parser.parse_args()

    app = build_analytic_graph(sandbox_config=SandboxConfig(service=args.sandbox))
    state = app.invoke({})

    print(f"{len(state['jobs'])} jobs\n")
    for name, df in state["tables"].items():
        print(f"== {name} ==\n{df.to_string(index=False)}\n")
    for name in ("near_miss_jobs", "skill_gaps"):
        print(f"== {name} ==\n{pd.DataFrame(state.get(name, [])).to_string(index=False)}\n")
    for name in ("analysis", "conclusion"):
        if state.get(name):
            print(f"== {name} ==\n{state[name]}\n")
    for p in state.get("projects", []):
        print(f"* {p['title']} ({p['effort']}): {', '.join(p['skills'])}\n  {p['description']}\n  why: {p['why']}")
    for error in state.get("analytics_errors", []):
        print(f"error: {error}")

    args.out.mkdir(parents=True, exist_ok=True)
    report = {k: v for k, v in state.items() if k not in ("jobs", "tables")}
    report["tables"] = {name: df.to_dict("records") for name, df in state["tables"].items()}
    (args.out / "analytics.json").write_text(json.dumps(report, indent=2, default=str))
    print(f"\n-> {args.out / 'analytics.json'}")


if __name__ == "__main__":
    main()
