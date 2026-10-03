"""
One-off schema migrations; create_all (db/connector.py) only creates missing tables.

  migrate_descriptions_to_files(): job_board_table.description (the full text)
  -> description_path (a .md file under db.documents.DOCUMENTS_DIR). Running it
  again does nothing once the description column is gone.

Run it:
    python -m db.migrations      # or: just migrate
"""

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text

from db.documents import write_description

TABLE = "job_board_table"


def migrate_descriptions_to_files(engine) -> int:
    """
        Moves every stored description into its .md file and drops the description column.
        @return: the number of descriptions written (0 if already migrated)
    """
    insp = inspect(engine)
    if not insp.has_table(TABLE):
        return 0
    columns = {c["name"] for c in insp.get_columns(TABLE)}
    if "description" not in columns:
        return 0
    written = 0
    with engine.begin() as conn:  # one transaction: the column is only dropped if every file was written
        conn.execute(text(f"ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS description_path VARCHAR"))
        rows = conn.execute(text(f"SELECT id, description FROM {TABLE} WHERE description IS NOT NULL")).all()
        for job_id, description in rows:
            path = write_description(job_id, description)
            conn.execute(text(f"UPDATE {TABLE} SET description_path = :path WHERE id = :id"),
                         {"path": path, "id": job_id})
            written += 1
        conn.execute(text(f"ALTER TABLE {TABLE} DROP COLUMN description"))
    return written


def main() -> None:
    load_dotenv()
    engine = create_engine(os.getenv("DATABASE_URL"))
    written = migrate_descriptions_to_files(engine)
    print(f"{written} job descriptions moved to files" if written else "nothing to migrate")


if __name__ == "__main__":
    main()
