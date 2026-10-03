"""
Skips postings the search already scanned, so they aren't scraped or scored again.

  A posting is known when its link is in job_board_table (a job's id is a
  uuid5 of its link, see agents/utils/dbingestion.py, so link and id match 1:1).
  Known postings are dropped from portal_search's output before
  qualification_check, which saves one LLM call per posting.

  - `load_known_links()` reads the links from the database.
  - `known_links_file()` is the text of known_links.txt, written into the
    sandbox so the scraping scripts can skip those postings up front.
  - `drop_known()` removes them from the positions DataFrame, whether or not
    the scripts honored known_links.txt.
"""

import logging

import pandas as pd

KNOWN_LINKS_FILE = "known_links.txt"

logger = logging.getLogger(__name__)


def load_known_links() -> set[str]:
    """Links of every saved job; empty (nothing skipped) if the database can't be read."""
    try:
        from db.dbOps import known_links  # imported here: db.dbOps needs DATABASE_URL at import

        return known_links()
    except Exception as e:  # a down DB shouldn't stop the search
        logger.warning("could not load known jobs, scanning everything: %s", e)
        return set()


def known_links_file(known: set[str]) -> str:
    """Content of known_links.txt: one link per line, sorted."""
    return "".join(f"{link}\n" for link in sorted(known))


def drop_known(positions: pd.DataFrame, known: set[str]) -> tuple[pd.DataFrame, int]:
    """Returns (positions whose link isn't known, number of known postings dropped)."""
    if not known or positions.empty:
        return positions, 0
    is_known = positions["link"].isin(known)
    return positions[~is_known].reset_index(drop=True), int(is_known.sum())
