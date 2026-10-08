from db.connector import DBConnector
from db import models
from db.documents import delete_description, read_description
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
import datetime
import uuid

UUID = uuid.UUID

db = DBConnector()


def add_job(id: UUID, company_name: str, position: str, description_path: str, link: str,
            compatibility: int, job_type: str = "unknown", action: str = "searched"):
    """
        Adds a new job to the job board. description_path points at the
        description's .md file (see db.documents.write_description).
        @return: the id of the new job
    """
    conn, session = db.connect()
    try:
        new_job = models.JobBoard(
            id=id,
            company_name=company_name,
            position=position,
            description_path=description_path,
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
        Deletes the job with the given id, and its description file.
        @return: True if a job was deleted, False if no job was found
    """
    conn, session = db.connect()
    try:
        job = session.get(models.JobBoard, id)
        if job is None:
            return False
        path = job.description_path
        session.delete(job)
        session.commit()
        delete_description(path)
        return True
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        conn.close()


def update_job(id: UUID, company_name: str = None, position: str = None, description_path: str = None,
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
        if description_path is not None:
            job.description_path = description_path
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
                "description_path": stmt.excluded.description_path,
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
        # ORM bulk inserts report rowcount -1, so count the returned ids instead
        upserted = len(session.execute(stmt.returning(models.JobBoard.id)).all())
        session.commit()
        return upserted
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        conn.close()


def all_jobs(with_description: bool = False):
    """
        Fetches every job, for analytics over the whole board.
        Descriptions are read from their .md files only if with_description (they are large).
        @return: list of dicts with the JobBoard columns except description_path, plus
                 "description" if with_description; enums as their values
    """
    conn, session = db.connect()
    try:
        rows = session.execute(select(*models.JobBoard.__table__.columns)).mappings().all()
        jobs = []
        for row in rows:
            job = {k: v.value if isinstance(v, (models.Action, models.JobType)) else v
                   for k, v in row.items() if k != "description_path"}
            if with_description:
                job["description"] = read_description(row["description_path"])
            jobs.append(job)
        return jobs
    finally:
        session.close()
        conn.close()


def known_links():
    """
        Links of every saved job, so the search can skip postings it already scanned.
        @return: set of link strings
    """
    conn, session = db.connect()
    try:
        return set(session.scalars(select(models.JobBoard.link).where(models.JobBoard.link.is_not(None))))
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
        company is a case-insensitive exact match; search matches company or position
        (descriptions are files, see db/documents.py).
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
                           | models.JobBoard.position.ilike(pattern))

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


# ---------- resume drafts (agents/resume_builder) ----------

def _now_iso():
    return datetime.datetime.now(datetime.UTC).isoformat()


def _draft_dict(draft: models.ResumeDraft, job: models.JobBoard = None):
    return {
        "id": draft.id,
        "job_id": draft.job_id,
        "company_name": job.company_name if job else None,
        "position": job.position if job else None,
        "resume": draft.resume,
        "side_projects": draft.side_projects,
        "messages": list(draft.messages or []),
        "versions": list(draft.versions or []),
        "created_at": draft.created_at,
        "update_at": draft.update_at,
    }


def create_draft(job_id: UUID, resume: str, side_projects: str):
    """
        Saves a freshly built resume and side-project ideas for a job.
        @return: the new draft as a dict (see get_draft)
    """
    conn, session = db.connect()
    try:
        draft = models.ResumeDraft(job_id=job_id, resume=resume, side_projects=side_projects,
                                   messages=[], versions=[])
        session.add(draft)
        session.commit()
        return _draft_dict(draft, session.get(models.JobBoard, job_id))
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        conn.close()


def get_draft(id: UUID):
    """
        Fetches one resume draft with its job's company and position.
        @return: dict with the ResumeDraft columns plus company_name/position, or None if not found
    """
    conn, session = db.connect()
    try:
        draft = session.get(models.ResumeDraft, id)
        if draft is None:
            return None
        return _draft_dict(draft, session.get(models.JobBoard, draft.job_id))
    finally:
        session.close()
        conn.close()


def list_drafts(job_id: UUID = None):
    """
        Lists resume drafts, most recently edited first; only one job's when job_id is given.
        @return: list of draft dicts (see get_draft)
    """
    conn, session = db.connect()
    try:
        stmt = (select(models.ResumeDraft, models.JobBoard)
                .join(models.JobBoard, models.JobBoard.id == models.ResumeDraft.job_id)
                .order_by(models.ResumeDraft.update_at.desc()))
        if job_id is not None:
            stmt = stmt.where(models.ResumeDraft.job_id == job_id)
        return [_draft_dict(draft, job) for draft, job in session.execute(stmt).all()]
    finally:
        session.close()
        conn.close()


def update_draft(id: UUID, resume: str = None, side_projects: str = None, note: str = "",
                 messages: list[dict] = None):
    """
        Edits a draft. If resume or side_projects change, the old content is first pushed
        onto versions (with note saying what changed it). messages are appended to the chat.
        @return: the updated draft dict, or None if not found
    """
    conn, session = db.connect()
    try:
        draft = session.get(models.ResumeDraft, id)
        if draft is None:
            return None
        changed = (resume is not None and resume != draft.resume) or \
                  (side_projects is not None and side_projects != draft.side_projects)
        if changed:
            # Reassign the JSON lists: in-place mutation isn't tracked.
            draft.versions = list(draft.versions or []) + [{
                "resume": draft.resume, "side_projects": draft.side_projects, "note": note, "at": _now_iso(),
            }]
            if resume is not None:
                draft.resume = resume
            if side_projects is not None:
                draft.side_projects = side_projects
        if messages:
            draft.messages = list(draft.messages or []) + [{**m, "at": m.get("at") or _now_iso()} for m in messages]
        if changed or messages:
            draft.update_at = datetime.datetime.now(datetime.UTC)
        session.commit()
        return _draft_dict(draft, session.get(models.JobBoard, draft.job_id))
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        conn.close()


def clear_draft_messages(id: UUID):
    """
        Empties a draft's chat history (the context the chat sends back to the model);
        its resume, side projects and versions are kept.
        @return: the updated draft dict, or None if not found
    """
    conn, session = db.connect()
    try:
        draft = session.get(models.ResumeDraft, id)
        if draft is None:
            return None
        draft.messages = []
        draft.update_at = datetime.datetime.now(datetime.UTC)
        session.commit()
        return _draft_dict(draft, session.get(models.JobBoard, draft.job_id))
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        conn.close()


def revert_draft(id: UUID, version: int):
    """
        Restores versions[version] of a draft; the current content becomes a new version first.
        @return: the updated draft dict, or None if not found; IndexError if no such version
    """
    draft = get_draft(id)
    if draft is None:
        return None
    old = draft["versions"][version]
    return update_draft(id, resume=old["resume"], side_projects=old["side_projects"],
                        note=f"before revert to version {version}")
