from db.connector import DBConnector
from db import models
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
import datetime
import uuid

UUID = uuid.UUID

db = DBConnector()


def add_job(id: UUID, company_name: str, position: str, description: str, link: str,
            compatibility: int, job_type: str = "unknown", action: str = "searched"):
    """
        Adds a new job to the job board.
        @return: the id of the new job
    """
    conn, session = db.connect()
    try:
        new_job = models.JobBoard(
            id=id,
            company_name=company_name,
            position=position,
            description=description,
            link=link,
            compatibility=compatibility,
            job_type=models.JobType(job_type),
            action=models.Action(action),
        )
        session.add(new_job)
        session.commit()
        return new_job.id
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        conn.close()


def delete_job(id: UUID):
    """
        Deletes the job with the given id.
        @return: True if a job was deleted, False if no job was found
    """
    conn, session = db.connect()
    try:
        job = session.get(models.JobBoard, id)
        if job is None:
            return False
        session.delete(job)
        session.commit()
        return True
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        conn.close()


def update_job(id: UUID, company_name: str = None, position: str = None, description: str = None,
               link: str = None, compatibility: int = None, job_type: str = None, action: str = None):
    """
        Updates the given fields of a job. Fields left as None are not changed.
        @return: True if the job was updated, False if no job was found
    """
    conn, session = db.connect()
    try:
        job = session.get(models.JobBoard, id)
        if job is None:
            return False
        if company_name is not None:
            job.company_name = company_name
        if position is not None:
            job.position = position
        if description is not None:
            job.description = description
        if link is not None:
            job.link = link
        if compatibility is not None:
            job.compatibility = compatibility
        if job_type is not None:
            job.job_type = models.JobType(job_type)
        if action is not None:
            job.action = models.Action(action)
        session.commit()
        return True
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        conn.close()


def update_action(id: UUID, action: str):
    """
        Updates the action (application status) of a job.
        @return: True if the job was updated, False if no job was found
    """
    return update_job(id, action=action)


def upsert_jobs(jobs: list[dict]):
    """
        Inserts many jobs in one statement. A job whose id already exists gets its
        posting fields and compatibility refreshed; its action (application status) is kept.
        @return: the number of rows inserted or updated
    """
    if not jobs:
        return 0
    conn, session = db.connect()
    try:
        stmt = insert(models.JobBoard).values(jobs)
        stmt = stmt.on_conflict_do_update(
            index_elements=[models.JobBoard.id],
            set_={
                "company_name": stmt.excluded.company_name,
                "position": stmt.excluded.position,
                "description": stmt.excluded.description,
                "post_id": stmt.excluded.post_id,
                "link": stmt.excluded.link,
                "job_type": stmt.excluded.job_type,
                "compatibility": stmt.excluded.compatibility,
                "requirements": stmt.excluded.requirements,
                "matched": stmt.excluded.matched,
                "missing": stmt.excluded.missing,
                "reasoning": stmt.excluded.reasoning,
                "update_at": datetime.datetime.now(datetime.UTC),
            },
        )
        result = session.execute(stmt)
        session.commit()
        return result.rowcount
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        conn.close()


def all_jobs(with_description: bool = False):
    """
        Fetches every job, for analytics over the whole board.
        Descriptions are left out unless with_description (they are most of the row size).
        @return: list of dicts with the JobBoard columns; enums as their values
    """
    conn, session = db.connect()
    try:
        columns = [c for c in models.JobBoard.__table__.columns
                   if with_description or c.name != "description"]
        rows = session.execute(select(*columns)).mappings().all()
        return [{k: v.value if isinstance(v, (models.Action, models.JobType)) else v
                 for k, v in row.items()} for row in rows]
    finally:
        session.close()
        conn.close()


def get_job(id: UUID):
    """
        Fetches one job by id.
        @return: the JobBoard row, or None if no job was found
    """
    conn, session = db.connect()
    try:
        return session.get(models.JobBoard, id)
    finally:
        session.close()
        conn.close()


def list_jobs(action: str = None, job_type: str = None, min_compatibility: int = None,
              company: str = None, search: str = None, sort_by: str = "update_at",
              descending: bool = True, limit: int = 50, offset: int = 0):
    """
        Lists jobs matching the given filters. Filters left as None are not applied.
        company is a case-insensitive exact match; search matches company, position or description.
        @return: (total number of matching jobs, JobBoard rows of the requested page)
    """
    conn, session = db.connect()
    try:
        filters = []
        if action is not None:
            filters.append(models.JobBoard.action == models.Action(action))
        if job_type is not None:
            filters.append(models.JobBoard.job_type == models.JobType(job_type))
        if min_compatibility is not None:
            filters.append(models.JobBoard.compatibility >= min_compatibility)
        if company is not None:
            filters.append(func.lower(models.JobBoard.company_name) == company.lower())
        if search:
            pattern = f"%{search}%"
            filters.append(models.JobBoard.company_name.ilike(pattern)
                           | models.JobBoard.position.ilike(pattern)
                           | models.JobBoard.description.ilike(pattern))

        total = session.scalar(select(func.count()).select_from(models.JobBoard).where(*filters))
        column = getattr(models.JobBoard, sort_by)
        rows = session.scalars(
            select(models.JobBoard)
            .where(*filters)
            .order_by(column.desc() if descending else column.asc(), models.JobBoard.id)
            .limit(limit)
            .offset(offset)
        ).all()
        return total, rows
    finally:
        session.close()
        conn.close()
