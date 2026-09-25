from datetime import datetime
from enum import Enum
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr

from db.models import Action, JobBoard, JobType


# ---------- agents (apis/reposetories/agents.py) ----------

class RunStatus(str, Enum):
    """Lifecycle of a graph run: queued -> running -> succeeded | failed."""
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"


class AgentRunRequest(BaseModel):
    """Body of POST /agents/runs: which portals to search and which sandbox to use."""
    # Portal names from portals.yml; None or empty = all enabled portals.
    portals: Optional[list[str]] = None
    sandbox: Literal["sandbox", "sandbox-cpu"] = "sandbox"


class AgentRunSummary(BaseModel):
    """What a finished run did: portal_search -> qualification_check -> db_ingestion."""
    positions: int = 0
    scored: int = 0
    ingested: int = 0  # rows written by the graph's db_ingestion node
    portal_errors: list[dict] = []
    qualification_errors: list[dict] = []
    ingestion_errors: list[dict] = []


class AgentRun(BaseModel):
    """Returned by POST /agents/runs, GET /agents/runs and GET /agents/runs/{run_id};
    the frontend polls it until status is succeeded or failed."""
    id: UUID
    status: RunStatus
    portals: list[str]
    sandbox: str
    created_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    summary: Optional[AgentRunSummary] = None
    error: Optional[str] = None


# ---------- job board queries (apis/reposetories/jobs.py) ----------

class JobOut(BaseModel):
    """One job_board_table row, as returned by GET /jobs and GET /jobs/{job_id}."""
    model_config = ConfigDict(from_attributes=True)  # built straight from JobBoard rows

    id: UUID
    company_name: str
    position: str
    description: Optional[str] = None
    link: Optional[str] = None
    update_at: datetime
    job_type: JobType
    compatibility: int
    action: Action


class JobPage(BaseModel):
    """Response of GET /jobs: one page of filtered jobs plus the total match count."""
    total: int
    limit: int
    offset: int
    items: list[JobOut]


class JobActionUpdate(BaseModel):
    """Body of PATCH /jobs/{job_id}/action: set the application status of a job."""
    action: Action
