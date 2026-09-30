"""
This agent queries all the jobs searched, applied and within the interview process
and generates dataframes for visualization as well as a paragraph or two
analyzing this data and a conclusion summary. It also finds the near-miss jobs
(you have the general knowledge but miss some crucial skills) and recommends
side projects that close those skill gaps.

How it works (code-as-action agent, same loop as portal_search):
  The chart tables are fixed pandas on the host (`build_tables()`, no LLM), so
  the charts are always right. The exploratory part runs in the sandbox: the
  jobs (with descriptions and qualification_check's requirements / matched /
  missing), the chart tables and the candidate's background are written to
  /workspace/data, and each turn the ```python block in the model's reply runs
  there (`docker exec ... python3 -`, see agents/sandbox) and its output is sent
  back so the model can fix its script. The model writes:
    results/near_miss_jobs.csv  NEAR_MISS_COLUMNS
    results/skill_gaps.csv      SKILL_GAP_COLUMNS
    results/report.json         {"analysis", "conclusion", "projects": [...]}
  and replies DONE; `finalize` reads and validates those files and sends the
  model back to fix them if they're wrong.

Orchestration:
  - `build_analytics_agent()` returns the compiled REPL graph
    (input {"jobs": [...], "tables": {...}, "background": str}, output adds the
    results above). Needs a SandboxSession in the run context.
  - `analyze()` runs it in its own sandbox container.
  - `make_analytics_node()` returns a plain LangGraph node for the parent graph
    (agents/graph/analytic_graph.py): reads `jobs` and `tables` (DataFrames)
    and returns the results plus `analytics_errors`.
"""

import io
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal, TypedDict

import pandas as pd
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.runtime import Runtime
from langgraph.types import Command

from agents.portal_search.agent import _extract_code, _final_channel, _format_observation
from agents.qualification_check.agent import KNOWLEDGE_FILE
from agents.resume_builder.agent import load_background
from agents.sandbox import SandboxConfig, SandboxSession
from db.dbOps import all_jobs
from db.models import Action, JobType

ACTIONS = [a.value for a in Action]
JOB_TYPES = [t.value for t in JobType]
INTERVIEW = ["interview_scheduled", "interview_inprogress", "interview_done"]
# Statuses that mean the job was applied to. A denial is counted as applied:
# you only get denied after applying.
APPLIED = ["applied", *INTERVIEW, "denied"]

JOB_COLUMNS = ["id", "company_name", "position", "link", "update_at", "job_type", "compatibility", "action",
               "requirements", "matched", "missing", "reasoning"]

MAX_STEPS = 12  # model turns per analysis
NEAR_MISS = (5, 8)  # compatibility band: 5-6 meets about half, 7-8 small gaps (qualification_check rubric)
NEAR_MISS_COLUMNS = ["company_name", "position", "compatibility", "action", "link", "missing_required"]
SKILL_GAP_COLUMNS = ["skill", "jobs", "required_in", "avg_compatibility", "companies"]
PROJECT_KEYS = ["title", "skills", "description", "why", "effort"]
EFFORTS = ("weekend", "1-2 weeks", "1 month+")
NUM_PROJECTS = (3, 5)

NEAR_MISS_FILE = "results/near_miss_jobs.csv"
SKILL_GAPS_FILE = "results/skill_gaps.csv"
REPORT_FILE = "results/report.json"


def load_jobs(with_description: bool = False) -> pd.DataFrame:
    """Every job in job_board_table, one row per job (descriptions only if asked for)."""
    columns = JOB_COLUMNS + (["description"] if with_description else [])
    jobs = pd.DataFrame(all_jobs(with_description), columns=columns)
    jobs["update_at"] = pd.to_datetime(jobs["update_at"], utc=True)
    return jobs


# ─────────────────────────────────────────────────────────
# TABLES (host, for the charts)
# ─────────────────────────────────────────────────────────

def _flags(jobs: pd.DataFrame) -> pd.DataFrame:
    return jobs.assign(
        applied=jobs["action"].isin(APPLIED),
        interview=jobs["action"].isin(INTERVIEW),
        denied=jobs["action"] == "denied",
    )


def build_tables(jobs: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Aggregates the jobs into chart-ready DataFrames:

      by_action      action, count                          (every status, zeros included)
      funnel         stage, count, rate                     (found -> applied -> interview -> interview_done)
      by_job_type    job_type, found, applied, interview
      by_company     company_name, found, applied, interview, avg_compatibility (most found first)
      compatibility  compatibility, found, applied          (score 0-10 histogram)
      weekly         week, <one column per action>          (jobs by week of their last update)
    """
    jobs = _flags(jobs)
    total = len(jobs)

    by_action = (jobs["action"].value_counts().reindex(ACTIONS, fill_value=0)
                 .rename_axis("action").reset_index(name="count"))

    stages = {
        "found": total,
        "applied": int(jobs["applied"].sum()),
        "interview": int(jobs["interview"].sum()),
        "interview_done": int((jobs["action"] == "interview_done").sum()),
    }
    funnel = pd.DataFrame({"stage": list(stages), "count": list(stages.values())})
    funnel["rate"] = (funnel["count"] / total).round(3) if total else 0.0  # share of found jobs

    counts = {"found": ("id", "size"), "applied": ("applied", "sum"), "interview": ("interview", "sum")}
    by_job_type = (jobs.groupby("job_type").agg(**counts)
                   .reindex(JOB_TYPES, fill_value=0).rename_axis("job_type").reset_index())

    by_company = (jobs.groupby("company_name")
                  .agg(**counts, avg_compatibility=("compatibility", "mean"))
                  .round({"avg_compatibility": 1})
                  .sort_values(["found", "applied"], ascending=False).reset_index())

    compatibility = (jobs.groupby("compatibility").agg(found=("id", "size"), applied=("applied", "sum"))
                     .reindex(range(11), fill_value=0).rename_axis("compatibility").reset_index())

    weeks = jobs["update_at"].dt.tz_localize(None).dt.to_period("W").dt.start_time
    weekly = (pd.crosstab(weeks, jobs["action"]).reindex(columns=ACTIONS, fill_value=0)
              .rename_axis("week").rename_axis(None, axis=1).reset_index())

    return {
        "by_action": by_action,
        "funnel": funnel,
        "by_job_type": by_job_type,
        "by_company": by_company,
        "compatibility": compatibility,
        "weekly": weekly,
    }


# ─────────────────────────────────────────────────────────
# PROMPTS
# ─────────────────────────────────────────────────────────

SYSTEM_PROMPT = f"""You are a data analyst and career coach reviewing one candidate's job search.
You work in a Linux sandbox with python3 (pandas, numpy available; no network needed).

Each turn, reply with exactly one ```python code block. It runs in /workspace and you
get its stdout, stderr and exit code in the next message. Nothing stays in memory
between turns: every script must load what it needs from files, and save anything
you need later to files. Output longer than a few thousand characters is
truncated, so print summaries (shapes, value_counts, head()), never whole files.

Data (read-only):
  data/jobs.json        every job the search agents saved, a list of objects with:
                        company_name, position, description, link, job_type, action,
                        compatibility (0-10 fit score), requirements ([{{"skill", "level":
                        "required" | "preferred"}}]), matched and missing (lists of
                        requirement skills the candidate meets / lacks), reasoning.
                        requirements/matched/missing may be null for older jobs.
  data/tables/*.csv     chart tables already computed from jobs.json (status counts,
                        funnel, work type, company, compatibility histogram, weekly).
  data/background.md    the candidate's knowledge base and full project write-ups.

Statuses (action): searched (found, not acted on), applied, drop (candidate passed),
interview_scheduled, interview_inprogress, interview_done, denied (rejected after applying).

Tasks:
1. Near-miss jobs: jobs with compatibility {NEAR_MISS[0]}-{NEAR_MISS[1]} that miss at least one
   REQUIRED skill (a skill in "missing" whose level in "requirements" is "required").
   The candidate has the general knowledge for these but lacks crucial skills.
   Write {NEAR_MISS_FILE} with columns: {", ".join(NEAR_MISS_COLUMNS)}
   (missing_required = the missing required skills joined with "; "), best score first.
2. Skill gaps: count the missing skills across the near-miss jobs. Merge spellings of
   the same skill (e.g. "k8s" and "Kubernetes", "AWS" and "Amazon Web Services").
   Write {SKILL_GAPS_FILE} with columns: {", ".join(SKILL_GAP_COLUMNS)}
     jobs              near-miss jobs missing the skill at any level
     required_in       of those, how many list it as required
     avg_compatibility mean compatibility of those jobs, 1 decimal
     companies         the companies, joined with "; "
   sorted by required_in, then jobs, descending. If there are no near-miss jobs,
   write both CSVs with just the header row.
3. Write {REPORT_FILE}, a JSON object:
   {{
     "analysis": "<one or two paragraphs, second person ('you'): how far jobs get
                  through the funnel, which companies, work types and compatibility
                  scores lead to applications and interviews, how activity changed
                  over the weeks, and what the near-miss jobs have in common>",
     "conclusion": "<two to four sentences: the main takeaway and next steps>",
     "projects": [
       {{"title": "...",
         "skills": ["<skill exactly as written in {SKILL_GAPS_FILE}>", ...],
         "description": "<what to build, concretely>",
         "why": "<which near-miss jobs / companies it helps with>",
         "effort": "{'" | "'.join(EFFORTS)}"}}
     ]
   }}
   Give {NUM_PROJECTS[0]}-{NUM_PROJECTS[1]} side projects that together cover the top skill gaps.
   Build each on what data/background.md shows the candidate already knows, and don't
   repeat a project they have already done. Use only numbers you computed. If there are
   no skill gaps, "projects" is an empty list.
   Write it with json.dump(report, open("{REPORT_FILE}", "w"), indent=2).

When all three files are written, reply with the single word DONE and no code block."""

TASK_PROMPT = """Analyze this job search: {total} jobs saved, {scored} with a requirements breakdown,
{band} with compatibility {low}-{high}.

Files in /workspace:
{files}"""


# ─────────────────────────────────────────────────────────
# GRAPH
# ─────────────────────────────────────────────────────────

class AnalyticsAgentState(TypedDict, total=False):
    jobs: list[dict]  # load_jobs(with_description=True) rows
    tables: dict[str, list[dict]]  # build_tables() rows
    background: str  # knowledge base + project write-ups
    messages: Annotated[list[AnyMessage], add_messages]
    steps: int
    near_miss_jobs: list[dict]
    skill_gaps: list[dict]
    analysis: str
    conclusion: str
    projects: list[dict]
    error: str | None  # set when the results were still invalid after MAX_STEPS


@dataclass
class AnalyticsContext:
    # Lives in the run context, not the state, so the state stays serializable
    # for LangGraph checkpointers.
    sandbox: SandboxSession


def build_analytics_agent(model: BaseChatModel | None = None):
    if model is None:
        from agents.utils.langchainConfig import chat_model as model  # loads the local LLM

    def setup(state: AnalyticsAgentState, runtime: Runtime[AnalyticsContext]):
        sbx = runtime.context.sandbox
        jobs = state["jobs"]
        sbx.run("rm -rf data results && mkdir -p data/tables results")
        _write(sbx, "data/jobs.json", json.dumps(jobs, indent=1, default=str))
        for name, rows in state["tables"].items():
            _write(sbx, f"data/tables/{name}.csv", pd.DataFrame(rows).to_csv(index=False))
        _write(sbx, "data/background.md", state["background"])
        files = sbx.run("find . -type f | sort")["stdout"].strip()
        return {
            "messages": [
                SystemMessage(SYSTEM_PROMPT),
                HumanMessage(TASK_PROMPT.format(
                    total=len(jobs),
                    scored=sum(1 for j in jobs if j.get("requirements")),
                    band=sum(1 for j in jobs if NEAR_MISS[0] <= j["compatibility"] <= NEAR_MISS[1]),
                    low=NEAR_MISS[0],
                    high=NEAR_MISS[1],
                    files=files,
                )),
            ],
            "steps": 0,
            "error": None,
        }

    def agent(state: AnalyticsAgentState):
        reply = model.invoke(state["messages"])
        return {
            "messages": [AIMessage(_final_channel(reply.text))],
            "steps": state["steps"] + 1,
        }

    def route(state: AnalyticsAgentState) -> Literal["execute", "finalize"]:
        if _extract_code(state["messages"][-1].text) and state["steps"] < MAX_STEPS:
            return "execute"
        return "finalize"

    def execute(state: AnalyticsAgentState, runtime: Runtime[AnalyticsContext]):
        # Always python: the prompt asks for python blocks, and _extract_code reports
        # an untagged block as bash.
        _, code = _extract_code(state["messages"][-1].text)
        out = runtime.context.sandbox.run_python(code)
        return {"messages": [HumanMessage(_format_observation(out))]}

    def finalize(
        state: AnalyticsAgentState, runtime: Runtime[AnalyticsContext]
    ) -> Command[Literal["agent", "__end__"]]:
        results = {"near_miss_jobs": [], "skill_gaps": [], "analysis": "", "conclusion": "", "projects": []}
        try:
            results.update(_read_results(runtime.context.sandbox))
            problem = None
        except ValueError as e:
            problem = str(e)

        if problem and state["steps"] < MAX_STEPS:
            return Command(
                update={"messages": [HumanMessage(f"{problem}\nFix it, then reply DONE.")]},
                goto="agent",
            )
        return Command(update={**results, "error": problem}, goto=END)

    graph = StateGraph(AnalyticsAgentState, context_schema=AnalyticsContext)
    graph.add_node("setup", setup)
    graph.add_node("agent", agent)
    graph.add_node("execute", execute)
    graph.add_node("finalize", finalize)
    graph.add_edge(START, "setup")
    graph.add_edge("setup", "agent")
    graph.add_conditional_edges("agent", route)
    graph.add_edge("execute", "agent")
    return graph.compile()


def analyze(
    agent, jobs: pd.DataFrame, tables: dict[str, pd.DataFrame], background: str,
    sandbox_config: SandboxConfig | None = None,
) -> dict:
    """Run the agent in its own sandbox container.

    Returns {"near_miss_jobs", "skill_gaps", "analysis", "conclusion", "projects", "error"}.
    """
    with SandboxSession(sandbox_config) as sbx:
        out = agent.invoke(
            {
                "jobs": _records(jobs),
                "tables": {name: _records(df) for name, df in tables.items()},
                "background": background,
            },
            context=AnalyticsContext(sandbox=sbx),
            config={"recursion_limit": 4 * MAX_STEPS + 10},
        )
    return {k: out.get(k) for k in ("near_miss_jobs", "skill_gaps", "analysis", "conclusion", "projects", "error")}


def make_analytics_node(
    model: BaseChatModel | None = None,
    sandbox_config: SandboxConfig | None = None,
    knowledge_file: Path = KNOWLEDGE_FILE,
):
    """LangGraph node for the parent graph (agents/graph/analytic_graph.py); runs after load_data."""
    agent = build_analytics_agent(model)

    def analytics_agent(state: dict) -> dict:
        try:
            background = load_background(knowledge_file, knowledge_file.parent / "projects")
            out = analyze(agent, state["jobs"], state["tables"], background, sandbox_config)
        except Exception as e:  # keep the host tables even if the sandbox or model fails
            return {"analytics_errors": [f"analytics agent failed: {e}"]}
        error = out.pop("error")
        return {**out, "analytics_errors": [error] if error else []}

    return analytics_agent


# ─────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────

def _write(sbx: SandboxSession, path: str, content: str) -> None:
    out = sbx.run(f"cat > {path} <<'CAREERAI_DATA_EOF'\n{content}\nCAREERAI_DATA_EOF")
    if out["exit_code"] != 0:
        raise RuntimeError(f"could not write {path} to the sandbox: {out['stderr']}")


def _records(df: pd.DataFrame) -> list[dict]:
    """Row dicts with None instead of NaN, so they serialize as JSON."""
    return df.astype(object).where(df.notna(), None).to_dict("records")


def _read_csv(sbx: SandboxSession, path: str, columns: list[str]) -> pd.DataFrame:
    try:
        df = pd.read_csv(io.StringIO(sbx.read_file(path)))
    except Exception as e:
        raise ValueError(f"Could not read {path} as CSV: {e}") from e
    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise ValueError(f"{path} is missing columns {missing}; it has {list(df.columns)}.")
    return df[columns]


def _read_results(sbx: SandboxSession) -> dict:
    """Validated results from the sandbox files; ValueError says what to fix."""
    near_miss = _read_csv(sbx, NEAR_MISS_FILE, NEAR_MISS_COLUMNS)
    gaps = _read_csv(sbx, SKILL_GAPS_FILE, SKILL_GAP_COLUMNS)

    try:
        report = json.loads(sbx.read_file(REPORT_FILE))
    except Exception as e:
        raise ValueError(f"Could not read {REPORT_FILE} as JSON: {e}") from e
    if not isinstance(report, dict):
        raise ValueError(f"{REPORT_FILE} must be a JSON object.")
    for key in ("analysis", "conclusion"):
        if not isinstance(report.get(key), str) or not report[key].strip():
            raise ValueError(f'"{key}" in {REPORT_FILE} must be a non-empty string.')

    projects = report.get("projects")
    if not isinstance(projects, list):
        raise ValueError(f'"projects" in {REPORT_FILE} must be a list.')
    low, high = NUM_PROJECTS if len(gaps) else (0, 0)
    if not low <= len(projects) <= high:
        raise ValueError(f'"projects" must have {low}-{high} items, it has {len(projects)}.')
    gap_skills = {str(s).strip().lower() for s in gaps["skill"]}
    for i, p in enumerate(projects):
        if not isinstance(p, dict) or any(k not in p for k in PROJECT_KEYS):
            raise ValueError(f"project {i} must be an object with keys {PROJECT_KEYS}.")
        if not isinstance(p["skills"], list) or not p["skills"]:
            raise ValueError(f'project {i} "skills" must be a non-empty list.')
        unknown = [s for s in p["skills"] if str(s).strip().lower() not in gap_skills]
        if unknown:
            raise ValueError(f"project {i} skills {unknown} are not in {SKILL_GAPS_FILE}; "
                             "use the skill names exactly as written there.")
        if p["effort"] not in EFFORTS:
            raise ValueError(f'project {i} "effort" must be one of {list(EFFORTS)}, got {p["effort"]!r}.')

    return {
        "near_miss_jobs": _records(near_miss),
        "skill_gaps": _records(gaps),
        "analysis": report["analysis"].strip(),
        "conclusion": report["conclusion"].strip(),
        "projects": [{k: p[k] for k in PROJECT_KEYS} for p in projects],
    }
