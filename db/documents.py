"""
Job descriptions live as Markdown files on disk, not in the database.

  Descriptions are long, so job_board_table only keeps description_path: the
  file's path relative to the project root (e.g. Docs/job_descriptions/<id>.md),
  which keeps the DB valid if the repo is cloned elsewhere. Docs/ is gitignored,
  so the files stay local like the rest of the user's documents.
  Set DOCUMENTS_DIR to store them somewhere else.
"""

import os
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOCUMENTS_DIR = Path(os.getenv("DOCUMENTS_DIR") or PROJECT_ROOT / "Docs" / "job_descriptions")


def _resolve(path: str) -> Path:
    p = Path(path)
    return p if p.is_absolute() else PROJECT_ROOT / p


def write_description(job_id: uuid.UUID, text: str) -> str:
    """
        Writes a job's description to <DOCUMENTS_DIR>/<job_id>.md, replacing any older one.
        @return: the path to store in description_path (relative to the project root when inside it)
    """
    DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)
    path = DOCUMENTS_DIR / f"{job_id}.md"
    path.write_text(text, encoding="utf-8")
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:  # DOCUMENTS_DIR outside the project
        return str(path)


def read_description(path: str | None) -> str | None:
    """
        Reads a description file.
        @return: its text, or None if path is None or the file is missing
    """
    if not path:
        return None
    try:
        return _resolve(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        return None


def delete_description(path: str | None) -> None:
    """Removes a description file; a missing file is fine."""
    if path:
        _resolve(path).unlink(missing_ok=True)
