import fastapi
import typing
import logging
import uuid

from db import dbOps
from db.documents import read_description
from db.models import Action, JobType
from apis.schemas import JobActionUpdate, JobOut, JobPage

JOBS_ROUTER: typing.Final = fastapi.APIRouter(prefix="/jobs", tags=["jobs"])

logger = logging.getLogger(__name__)


@JOBS_ROUTER.get("", response_model=JobPage)
def list_jobs(
    action: typing.Optional[Action] = None,
    job_type: typing.Optional[JobType] = None,
    min_compatibility: typing.Optional[int] = fastapi.Query(None, ge=0, le=100),
    company: typing.Optional[str] = None,
    search: typing.Optional[str] = fastapi.Query(None, description="matches company or position"),
    sort_by: typing.Literal["update_at", "compatibility", "company_name", "position"] = "update_at",
    order: typing.Literal["asc", "desc"] = "desc",
    limit: int = fastapi.Query(50, ge=1, le=200),
    offset: int = fastapi.Query(0, ge=0),
):
    """Job board for the frontend: filters, sorts and paginates the jobs the agents saved.
    e.g. GET /jobs?action=searched&min_compatibility=70&sort_by=compatibility"""
    total, rows = dbOps.list_jobs(
        action=action.value if action else None,
        job_type=job_type.value if job_type else None,
        min_compatibility=min_compatibility,
        company=company,
        search=search,
        sort_by=sort_by,
        descending=order == "desc",
        limit=limit,
        offset=offset,
    )
    return JobPage(total=total, limit=limit, offset=offset, items=rows)


@JOBS_ROUTER.get("/{job_id}", response_model=JobOut)
def get_job(job_id: uuid.UUID):
    """One job with its full description (read from its .md file), for the job detail page."""
    job = dbOps.get_job(job_id)
    if job is None:
        raise fastapi.HTTPException(status_code=404, detail="job not found")
    return JobOut.model_validate(job).model_copy(update={"description": read_description(job.description_path)})


@JOBS_ROUTER.patch("/{job_id}/action", response_model=JobOut)
def update_job_action(job_id: uuid.UUID, body: JobActionUpdate):
    """Sets the application status of a job (applied, interview_scheduled, ...).
    Re-running the agents keeps this status (see dbOps.upsert_jobs)."""
    if not dbOps.update_action(job_id, body.action.value):
        raise fastapi.HTTPException(status_code=404, detail="job not found")
    return dbOps.get_job(job_id)
