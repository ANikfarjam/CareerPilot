"""
This agent search all the portals from the portals.yaml. Then extracts all the available postions.
Ther result afterword is passed to avluation agent via lang graph.

How it works (code-as-action agent):
  The local LLM (gpt-oss-20b served by Ollama) isn't relied on for native
  tool calls, so instead of tools it writes shell commands. Each turn,
  the ```bash block in its reply runs in the sandbox container (`docker exec
  ... bash -s`, see agents/sandbox) and the stdout/stderr/exit code is sent back
  as the next message, so the model fixes its script from what it echoes.
  Nothing lives in memory between turns; state is files in /workspace.
  One container serves the whole sweep, so scripts written for one portal
  (e.g. a Greenhouse fetcher) can be reused for the next.
  For each portal the model writes results/<slug>.csv with the columns in
  COLUMNS and replies DONE; `finalize` reads and validates that CSV directly,
  so the LLM never has to re-type hundreds of postings.

Orchestration:
  - `build_portal_search_agent()` returns the compiled per-portal graph
    (input {"portal": {...}}, output adds "positions" as a list of row dicts).
    Needs a SandboxSession in the run context.
  - `search_portals()` runs it over many portals in one sandbox and returns a
    pandas DataFrame with COLUMNS (plus the per-portal errors). Postings whose
    link is in `known` (already saved, see agents/utils/known_jobs.py) are
    listed in the sandbox's known_links.txt and dropped from the DataFrame.
  - `make_portal_search_node()` returns a plain LangGraph node for the parent
    graph: reads `portals` from the parent state (default: all enabled
    tracked_companies in portals.yml; [] searches none) plus any
    `manual_positions` the user added by hand, and returns {"positions": DataFrame,
    "portal_errors", "skipped_known"}; skip_known=False rescans saved postings. A DataFrame is not JSON-serializable, so convert it
    (`df.to_dict("records")`) if the parent graph uses a checkpointer.
"""

import io
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal, TypedDict

import pandas as pd
import yaml
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.runtime import Runtime
from langgraph.types import Command

from agents.sandbox import SandboxConfig, SandboxSession
from agents.utils.known_jobs import KNOWN_LINKS_FILE, drop_known, known_links_file, load_known_links
from agents.utils.progress import Log, no_log, stage_logger

PORTALS_FILE = Path(__file__).resolve().parents[1] / "utils" / "portals.yml"
MAX_STEPS = 12  # model turns per portal

COLUMNS = ["company", "position", "descrition", "post_id", "link", "jobType"]
JOB_TYPES = ("onsite", "remote", "hybrid", "unknown")


def load_portals(path: Path = PORTALS_FILE) -> list[dict]:
    data = yaml.safe_load(path.read_text())
    return [c for c in data.get("tracked_companies", []) if c.get("enabled", True)]


def load_target_positions(path: Path = PORTALS_FILE) -> list[str]:
    """The title_filter's positive keywords: the positions the search targets."""
    data = yaml.safe_load(path.read_text())
    return list((data.get("title_filter") or {}).get("positive") or [])


# ─────────────────────────────────────────────────────────
# PROMPTS
# ─────────────────────────────────────────────────────────

SYSTEM_PROMPT = f"""You are a job-portal scraping agent working in a Linux bash shell.

Each turn, reply with exactly one ```bash code block. It runs in /workspace and you
get its stdout, stderr and exit code in the next message. Nothing stays in memory
between turns: save anything you need later to files. Write Python to a file and
run it with python3, e.g.

```bash
cat > fetch.py <<'EOF'
import json, requests
portal = json.load(open("portals/acme.json"))
...
EOF
python3 fetch.py
```

Output longer than a few thousand characters is truncated, so print/echo summaries
(counts, keys, a few samples), never whole responses.
Available: python3 with requests, httpx, bs4, lxml, pandas, pyyaml; curl is not
installed. Network access is allowed. Files in /workspace persist across portals,
so reuse scripts you wrote for earlier portals.

Goal: collect every open position listed by the portal into the CSV file named in
the task, with exactly these columns: {", ".join(COLUMNS)}
  company  - company name
  position - job title
  descrition - full job description as plain text (HTML tags stripped); it is
             used to extract the job's requirements, so don't leave it empty
  post_id  - the portal's own id for the posting (e.g. Greenhouse/Lever/Ashby job
             id); leave it empty if the portal has none
  link     - URL of the posting
  jobType  - one of: {", ".join(JOB_TYPES)} (infer from location/workplace fields;
             "unknown" if the posting doesn't say)
Write it with pandas: pd.DataFrame(rows, columns={COLUMNS}).to_csv(path, index=False)

Prefer the ATS JSON API over HTML when the portal has one:
  - Greenhouse: GET https://boards-api.greenhouse.io/v1/boards/<slug>/jobs?content=true
                ("content" is HTML-escaped: html.unescape it, then strip the tags)
  - Ashby:      GET https://api.ashbyhq.com/posting-api/job-board/<api_slug>
                (if that 404s, POST the GraphQL endpoint in portal["api"])
  - Lever:      GET https://api.lever.co/v0/postings/<slug>?mode=json
Otherwise fetch portal["careers_url"] and parse the HTML.

{KNOWN_LINKS_FILE} lists the links of postings already saved, one per line: skip them
(don't fetch their descriptions, leave them out of the CSV).

When the CSV is complete (or the portal has no open positions: write just the
header row), reply with the single word DONE and no code block."""

TASK_PROMPT = """Collect the open positions for this portal (also saved as {portal_file}):
{portal}

Write the results to {result_file}.
Files already in /workspace:
{files}"""


# ─────────────────────────────────────────────────────────
# GRAPH
# ─────────────────────────────────────────────────────────

class PortalSearchState(TypedDict, total=False):
    portal: dict
    messages: Annotated[list[AnyMessage], add_messages]
    steps: int
    positions: list[dict]


@dataclass
class PortalSearchContext:
    # Lives in the run context, not the state, so the state stays serializable
    # for LangGraph checkpointers.
    sandbox: SandboxSession


def build_portal_search_agent(model: BaseChatModel | None = None):
    if model is None:
        from agents.utils.langchainConfig import chat_model as model  # loads the local LLM

    def setup(state: PortalSearchState, runtime: Runtime[PortalSearchContext]):
        portal = state["portal"]
        sbx = runtime.context.sandbox
        portal_file, result_file = _paths(portal)
        sbx.run(
            f"mkdir -p portals results && rm -f {result_file}\n"
            f"cat > {portal_file} <<'PORTAL_EOF'\n{json.dumps(portal, indent=2)}\nPORTAL_EOF"
        )
        files = sbx.run("find . -maxdepth 2 -type f | sort")["stdout"].strip()
        return {
            "messages": [
                SystemMessage(SYSTEM_PROMPT),
                HumanMessage(TASK_PROMPT.format(
                    portal=json.dumps(portal, indent=2),
                    portal_file=portal_file,
                    result_file=result_file,
                    files=files or "(none)",
                )),
            ],
            "steps": 0,
            "positions": [],
        }

    def agent(state: PortalSearchState):
        reply = model.invoke(state["messages"])
        return {
            "messages": [AIMessage(_final_channel(reply.text))],
            "steps": state["steps"] + 1,
        }

    def route(state: PortalSearchState) -> Literal["execute", "finalize"]:
        if _extract_code(state["messages"][-1].text) and state["steps"] < MAX_STEPS:
            return "execute"
        return "finalize"

    def execute(state: PortalSearchState, runtime: Runtime[PortalSearchContext]):
        lang, code = _extract_code(state["messages"][-1].text)
        sbx = runtime.context.sandbox
        out = sbx.run_python(code) if lang in ("python", "py") else sbx.run(code)
        return {"messages": [HumanMessage(_format_observation(out))]}

    def finalize(
        state: PortalSearchState, runtime: Runtime[PortalSearchContext]
    ) -> Command[Literal["agent", "__end__"]]:
        _, result_file = _paths(state["portal"])
        problem, positions = None, []
        try:
            df = pd.read_csv(io.StringIO(runtime.context.sandbox.read_file(result_file)), dtype=str)
        except Exception as e:
            problem = f"Could not read {result_file} as CSV: {e}"
        else:
            missing = [c for c in COLUMNS if c not in df.columns]
            if missing:
                problem = f"{result_file} is missing columns {missing}; it has {list(df.columns)}."
            else:
                df = _clean(df[COLUMNS], state["portal"])
                bad = df["position"].isna() | df["link"].isna()
                if bad.any():
                    problem = f"{int(bad.sum())} rows in {result_file} have an empty position or link."
                positions = df[~bad].to_dict("records")

        if problem and state["steps"] < MAX_STEPS:
            return Command(
                update={"messages": [HumanMessage(f"{problem}\nFix the CSV, then reply DONE.")]},
                goto="agent",
            )
        return Command(update={"positions": positions}, goto=END)

    graph = StateGraph(PortalSearchState, context_schema=PortalSearchContext)
    graph.add_node("setup", setup)
    graph.add_node("agent", agent)
    graph.add_node("execute", execute)
    graph.add_node("finalize", finalize)
    graph.add_edge(START, "setup")
    graph.add_edge("setup", "agent")
    graph.add_conditional_edges("agent", route)
    graph.add_edge("execute", "agent")
    return graph.compile()


def search_portals(
    agent,
    portals: list[dict],
    sandbox_config: SandboxConfig | None = None,
    known: set[str] = frozenset(),
    log: Log = no_log,
) -> tuple[pd.DataFrame, list[dict], int]:
    """Run the agent on every portal in one shared sandbox container.

    Returns (DataFrame with COLUMNS minus the known links, [{"portal", "error"}, ...],
    number of known postings dropped). log(level, message) reports each portal's progress.
    """
    rows, errors = [], []
    if portals:  # no container needed when only manual positions are run
        with SandboxSession(sandbox_config) as sbx:
            sbx.run(f"cat > {KNOWN_LINKS_FILE} <<'KNOWN_EOF'\n{known_links_file(known)}KNOWN_EOF")
            for n, portal in enumerate(portals, 1):
                name = portal.get("name")
                log("info", f"Searching {name} ({n}/{len(portals)})")
                try:
                    out = agent.invoke(
                        {"portal": portal},
                        context=PortalSearchContext(sandbox=sbx),
                        config={"recursion_limit": 4 * MAX_STEPS + 10},
                    )
                    rows += out["positions"]
                    log("success", f"{name}: {len(out['positions'])} matching postings")
                except Exception as e:  # one broken portal shouldn't stop the sweep
                    errors.append({"portal": name, "error": str(e)})
                    log("error", f"{name} failed: {e}")
    df = pd.DataFrame(rows, columns=COLUMNS).drop_duplicates("link", ignore_index=True)
    df, skipped = drop_known(df, known)
    if skipped:
        log("info", f"Skipped {skipped} postings already saved")
    return df, errors, skipped


def manual_rows(manual_positions: list[dict]) -> pd.DataFrame:
    """Postings the user added by hand (apis.schemas.ManualPosition dicts) as COLUMNS rows."""
    rows = [{
        "company": p["company"],
        "position": p["position"],
        "descrition": p["description"],
        "post_id": p.get("post_id"),
        "link": p["link"],
        "jobType": _job_type(p.get("job_type")),
    } for p in manual_positions]
    return pd.DataFrame(rows, columns=COLUMNS)


def make_portal_search_node(
    model: BaseChatModel | None = None, sandbox_config: SandboxConfig | None = None, skip_known: bool = True
):
    """LangGraph node for the parent (orchestrator) graph; skip_known drops postings already in the DB.
    The state's manual_positions are added after the search and never dropped as known, so they get re-scored."""
    agent = build_portal_search_agent(model)

    def portal_search(state: dict) -> dict:
        log = stage_logger("portal_search")
        portals = state["portals"] if state.get("portals") is not None else load_portals()  # [] = only manual positions
        known = load_known_links() if skip_known and portals else set()
        df, errors, skipped = search_portals(agent, portals, sandbox_config, known, log)
        if manual := state.get("manual_positions"):
            df = pd.concat([df, manual_rows(manual)], ignore_index=True).drop_duplicates("link", keep="last", ignore_index=True)
            log("info", f"Added {len(manual)} manual position{'s' if len(manual) != 1 else ''}")
        found = f"Found {len(df)} new position{'s' if len(df) != 1 else ''}" if len(df) else "No new positions; nothing to score"
        log("success" if len(df) else "info", found)
        return {"positions": df, "portal_errors": errors, "skipped_known": skipped}

    return portal_search


# ─────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────

def _paths(portal: dict) -> tuple[str, str]:
    slug = re.sub(r"[^a-z0-9]+", "-", str(portal.get("name", "portal")).lower()).strip("-") or "portal"
    return f"portals/{slug}.json", f"results/{slug}.csv"


def _clean(df: pd.DataFrame, portal: dict) -> pd.DataFrame:
    df = df.apply(lambda col: col.str.strip()).replace("", None)
    df["company"] = df["company"].fillna(portal.get("name"))
    df["jobType"] = df["jobType"].map(_job_type)
    return df


def _job_type(value) -> str:
    v = re.sub(r"[^a-z]", "", str(value).lower()) if isinstance(value, str) else ""
    if "hybrid" in v:
        return "hybrid"
    if "remote" in v:
        return "remote"
    if v in ("onsite", "inoffice", "office", "inperson"):
        return "onsite"
    return "unknown"


def _final_channel(text: str) -> str:
    # Ollama already strips gpt-oss's analysis channel (reasoning=True in
    # langchainConfig); this guards against a raw harmony "analysis...assistantfinal..."
    # reply so reasoning doesn't pile up in the history.
    return text.rsplit("assistantfinal", 1)[-1].strip()


def _extract_code(text: str) -> tuple[str, str] | None:
    """(language, code) of the first code block in a reply; bash unless tagged python."""
    m = re.search(r"```([a-z]*)[ \t]*\n(.*?)```", text, re.DOTALL)
    return (m.group(1) or "bash", m.group(2).strip()) if m else None


def _format_observation(out: dict) -> str:
    parts = [f"exit code: {out['exit_code']}"] + [
        f"{key}:\n{out[key]}" for key in ("stdout", "stderr") if out[key]
    ]
    return "Execution output:\n" + "\n\n".join(parts)
