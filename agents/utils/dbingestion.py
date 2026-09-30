"""
Writes the scored postings from qualification_check into job_board_table.

  Each posting's id is a uuid5 of its link, so running the graph again updates
  the postings already stored (description, score, ...) instead of duplicating
  them, and keeps their action (application status) as you set it.
  Postings without a score (no description, or scoring failed) are skipped:
  compatibility is required in the table.

Orchestration:
  - `positions_to_jobs()` maps a scored DataFrame to job_board_table rows.
  - `make_db_ingestion_node()` returns a plain LangGraph node for the parent
    graph: reads `scored_positions` and returns {"ingested": count,
    "ingestion_errors": [...]}.
"""

import uuid

import pandas as pd

from agents.portal_search.agent import JOB_TYPES
from agents.qualification_check.agent import _text
from db.dbOps import upsert_jobs


def job_id(link: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, link)


def positions_to_jobs(scored: pd.DataFrame) -> tuple[list[dict], list[dict]]:
    """Returns (job_board_table rows, [{"link", "error"}, ...] for skipped postings)."""
    jobs, skipped = {}, []
    for row in scored.to_dict("records"):
        link = _text(row.get("link"))
        if not link:
            skipped.append({"link": None, "error": "posting has no link"})
        elif pd.isna(row.get("score")):
            skipped.append({"link": link, "error": "posting has no compatibility score"})
        else:
            job_type = _text(row.get("jobType")).lower()
            jobs[link] = {  # keyed by link: one statement can't upsert the same id twice
                "id": job_id(link),
                "company_name": _text(row.get("company")) or "unknown",
                "position": _text(row.get("position")) or "unknown",
                "description": _text(row.get("descrition")) or None,
                "post_id": _text(row.get("post_id")) or None,
                "link": link,
                "job_type": job_type if job_type in JOB_TYPES else "unknown",
                "compatibility": int(row["score"]),
                **{c: row.get(c) if isinstance(row.get(c), list) else None  # CSV-loaded rows have str/NaN
                   for c in ("requirements", "matched", "missing")},
                "reasoning": _text(row.get("reasoning")) or None,
            }
    return list(jobs.values()), skipped


def make_db_ingestion_node():
    """LangGraph node for the parent (orchestrator) graph; runs after qualification_check."""

    def db_ingestion(state: dict) -> dict:
        scored = state.get("scored_positions")
        if not isinstance(scored, pd.DataFrame):  # list of row dicts (checkpointed parent graph)
            scored = pd.DataFrame(scored or [])
        jobs, errors = positions_to_jobs(scored)
        try:
            ingested = upsert_jobs(jobs)
        except Exception as e:  # keep the run's results (CSV) even if the DB is down
            ingested, errors = 0, errors + [{"link": None, "error": f"database write failed: {e}"}]
        return {"ingested": ingested, "ingestion_errors": errors}

    return db_ingestion
