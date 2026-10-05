"""
This agent extract key technical requirements from each posted job. Then it compare it to the
user skills and rate compatibility from 10.

How it works:
  The user's qualifications come from Docs/user_docs/user_knowledge.md (the
  agent's knowledge base); it's read once per run and sent as the system prompt.
  For each posting, the model gets the title + description and replies with one
  JSON object: the extracted requirements, which of them the user meets / misses,
  a 0-10 score and a short reason. `finalize` parses and validates that JSON and
  sends the model back to fix it (up to MAX_ATTEMPTS) if it's malformed.

  No sandbox: unlike portal_search, nothing here runs model-written code; it's
  pure text-in / JSON-out, so it runs on the host next to the LLM. It can run in
  the same parent graph right after portal_search, reading its `positions`.

Orchestration:
  - `build_qualification_agent()` returns the compiled per-posting graph
    (input {"job": {...row with portal_search COLUMNS...}}, output adds "result").
  - `evaluate_positions()` runs it over a positions DataFrame and returns it with
    the SCORE_COLUMNS added, sorted by score (plus the per-posting errors).
  - `make_qualification_node()` returns a plain LangGraph node for the parent
    graph: reads `positions` (DataFrame or list of row dicts) from the parent
    state and returns {"scored_positions": DataFrame, "qualification_errors"}.
"""

import json
from pathlib import Path
from typing import Annotated, Literal, TypedDict

import pandas as pd
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.types import Command

from agents.portal_search.agent import COLUMNS, _final_channel
from agents.utils.progress import Log, no_log, stage_logger

KNOWLEDGE_FILE = Path(__file__).resolve().parents[2] / "Docs" / "user_docs" / "user_knowledge.md"
MAX_ATTEMPTS = 3  # model turns per posting (first try + fixes)
MAX_DESCRIPTION_CHARS = 8000  # long postings are mostly benefits/boilerplate at the end

SCORE_COLUMNS = ["score", "requirements", "matched", "missing", "reasoning"]
LEVELS = ("required", "preferred")


def load_knowledge(path: Path = KNOWLEDGE_FILE) -> str:
    return path.read_text()


# ─────────────────────────────────────────────────────────
# PROMPTS
# ─────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a technical recruiter screening job postings for one candidate.

For each posting you get, do two things:
1. Extract the key technical requirements: languages, frameworks, tools, platforms,
   domain knowledge, degrees and years of experience. Skip soft skills, benefits
   and company boilerplate. Mark each one "required" or "preferred" (nice-to-have,
   bonus, "a plus"); if the posting doesn't say, it's "required".
2. Compare them to the candidate's knowledge base below and rate compatibility
   from 0 to 10.

Only count a requirement as matched if the knowledge base shows evidence for it
(work experience, projects, coursework or listed skills). A related skill is not
a match (GCP is not AWS), but you may mention it as transferable in the reasoning.
Years of experience and seniority count: the candidate is early career.

Scoring rubric:
  9-10  meets nearly all required and most preferred requirements; seniority fits
  7-8   meets most required requirements; the gaps are small or quick to learn
  5-6   meets about half of the required requirements, or seniority is a stretch
  3-4   major gaps in core requirements
  0-2   different field, or far more senior than the candidate

Reply with only this JSON object, no other text:
{{
  "requirements": [{{"skill": "<requirement>", "level": "required" | "preferred"}}, ...],
  "matched": ["<requirement the candidate meets>", ...],
  "missing": ["<requirement the candidate lacks>", ...],
  "score": <integer 0-10>,
  "reasoning": "<1-3 sentences: why this score>"
}}
Every item in "matched" and "missing" must be a "skill" from "requirements".

# Candidate knowledge base

{knowledge}"""

TASK_PROMPT = """Company: {company}
Position: {position}
Work type: {jobType}

Job description:
{description}"""


# ─────────────────────────────────────────────────────────
# GRAPH
# ─────────────────────────────────────────────────────────

class QualificationState(TypedDict, total=False):
    job: dict
    messages: Annotated[list[AnyMessage], add_messages]
    attempts: int
    result: dict | None


def build_qualification_agent(model: BaseChatModel | None = None, knowledge: str | None = None):
    if model is None:
        from agents.utils.langchainConfig import chat_model as model  # loads the local LLM
    system = SystemMessage(SYSTEM_PROMPT.format(knowledge=knowledge or load_knowledge()))

    def setup(state: QualificationState):
        job = state["job"]
        description = _text(job.get("descrition"))
        if len(description) > MAX_DESCRIPTION_CHARS:
            description = description[:MAX_DESCRIPTION_CHARS] + "\n...[truncated]"
        return {
            "messages": [
                system,
                HumanMessage(TASK_PROMPT.format(
                    company=_text(job.get("company")) or "unknown",
                    position=_text(job.get("position")) or "unknown",
                    jobType=_text(job.get("jobType")) or "unknown",
                    description=description,
                )),
            ],
            "attempts": 0,
            "result": None,
        }

    def agent(state: QualificationState):
        reply = model.invoke(state["messages"])
        return {
            "messages": [AIMessage(_final_channel(reply.text))],
            "attempts": state["attempts"] + 1,
        }

    def finalize(state: QualificationState) -> Command[Literal["agent", "__end__"]]:
        try:
            result = _parse_result(state["messages"][-1].text)
        except ValueError as e:
            if state["attempts"] < MAX_ATTEMPTS:
                return Command(
                    update={"messages": [HumanMessage(f"{e}\nReply again with only the corrected JSON object.")]},
                    goto="agent",
                )
            raise
        return Command(update={"result": result}, goto=END)

    graph = StateGraph(QualificationState)
    graph.add_node("setup", setup)
    graph.add_node("agent", agent)
    graph.add_node("finalize", finalize)
    graph.add_edge(START, "setup")
    graph.add_edge("setup", "agent")
    graph.add_edge("agent", "finalize")
    return graph.compile()


def evaluate_positions(agent, positions: pd.DataFrame, log: Log = no_log) -> tuple[pd.DataFrame, list[dict]]:
    """Score every posting with the agent.

    Returns (positions + SCORE_COLUMNS sorted by score, best first; [{"link", "error"}, ...]).
    Postings without a description, or that fail, keep an empty score.
    log(level, message) reports each posting's progress.
    """
    results, errors = [], []
    jobs = positions.to_dict("records")
    for n, job in enumerate(jobs, 1):
        result = {}
        title = f"{_text(job.get('position')) or 'Untitled'} @ {_text(job.get('company')) or 'unknown'}"
        if not _text(job.get("descrition")):
            errors.append({"link": job.get("link"), "error": "no job description to extract requirements from"})
            log("error", f"{title}: no description, skipped ({n}/{len(jobs)})")
        else:
            log("info", f"Scoring {title} ({n}/{len(jobs)})")
            try:
                out = agent.invoke({"job": job}, config={"recursion_limit": 3 * MAX_ATTEMPTS + 5})
                result = out["result"]
                log("success", f"{title}: {result.get('score')}/10")
            except Exception as e:  # one bad posting shouldn't stop the run
                errors.append({"link": job.get("link"), "error": str(e)})
                log("error", f"{title} failed: {e}")
        results.append({c: result.get(c) for c in SCORE_COLUMNS})

    scored = pd.concat([positions.reset_index(drop=True), pd.DataFrame(results, columns=SCORE_COLUMNS)], axis=1)
    scored["score"] = scored["score"].astype("Int64")
    return scored.sort_values("score", ascending=False, na_position="last", ignore_index=True), errors


def make_qualification_node(model: BaseChatModel | None = None, knowledge_file: Path = KNOWLEDGE_FILE):
    """LangGraph node for the parent (orchestrator) graph; runs after portal_search."""
    agent = build_qualification_agent(model, load_knowledge(knowledge_file))

    def qualification_check(state: dict) -> dict:
        positions = state.get("positions")
        if not isinstance(positions, pd.DataFrame):  # list of row dicts (checkpointed parent graph)
            positions = pd.DataFrame(positions or [], columns=COLUMNS)
        df, errors = evaluate_positions(agent, positions, stage_logger("qualification_check"))
        return {"scored_positions": df, "qualification_errors": errors}

    return qualification_check


# ─────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────

def _parse_result(text: str) -> dict:
    """Validated result dict from the model's reply; ValueError says what to fix."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end < start:
        raise ValueError("Your reply has no JSON object.")
    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError as e:
        raise ValueError(f"Your JSON is invalid: {e}.") from e

    requirements = []
    for req in data.get("requirements") or []:
        if isinstance(req, str):
            req = {"skill": req}
        if isinstance(req, dict) and _text(req.get("skill")):
            level = _text(req.get("level")).lower()
            requirements.append({"skill": _text(req["skill"]), "level": level if level in LEVELS else "required"})
    if not requirements:
        raise ValueError('"requirements" is empty; list the technical requirements from the posting.')

    try:
        score = round(float(data.get("score")))
    except (TypeError, ValueError):
        raise ValueError(f'"score" must be an integer from 0 to 10, got {data.get("score")!r}.') from None
    if not 0 <= score <= 10:
        raise ValueError(f'"score" must be from 0 to 10, got {score}.')

    return {
        "score": score,
        "requirements": requirements,
        "matched": [_text(s) for s in data.get("matched") or [] if _text(s)],
        "missing": [_text(s) for s in data.get("missing") or [] if _text(s)],
        "reasoning": _text(data.get("reasoning")),
    }


def _text(value) -> str:
    # CSV-loaded rows have NaN/None for empty cells.
    return value.strip() if isinstance(value, str) else ""
