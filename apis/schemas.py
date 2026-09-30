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


class SideProject(BaseModel):
    """A side project the analytics agent recommends to close skill gaps from the near-miss jobs."""
    title: str
    skills: list[str]  # skill gaps it covers, as named in AnalyticsReport.skill_gaps
    description: str
    why: str  # which near-miss jobs / companies it helps with
    effort: Literal["weekend", "1-2 weeks", "1 month+"]


class AnalyticsReport(BaseModel):
    """Analytics over every saved job. GET /agents/analytics returns only `tables` (host
    pandas, fast); a finished analytics run (agents/graph/analytic_graph.py) fills the rest.
    Each table is a list of row dicts (agents/analytics/agent.py documents the columns):
    by_action, funnel, by_job_type, by_company, compatibility, weekly."""
    total_jobs: int
    tables: dict[str, list[dict]]
    # Jobs you're broadly qualified for but missing crucial (required) skills.
    near_miss_jobs: list[dict] = []
    skill_gaps: list[dict] = []  # missing skills across near_miss_jobs, most required first
    analysis: str = ""
    conclusion: str = ""
    projects: list[SideProject] = []
    errors: list[str] = []  # the tables are still valid when the agent failed
    generated_at: datetime


class AnalyticsRunRequest(BaseModel):
    """Body of POST /agents/analytics/runs: which sandbox the analytics agent runs its code in.
    It only needs pandas, so sandbox-cpu is enough."""
    sandbox: Literal["sandbox", "sandbox-cpu"] = "sandbox"


class AnalyticsRun(BaseModel):
    """Returned by POST /agents/analytics/runs and GET /agents/analytics/runs/{run_id};
    the frontend polls it until status is succeeded or failed, then reads `report`."""
    id: UUID
    status: RunStatus
    sandbox: str
    created_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    report: Optional[AnalyticsReport] = None
    error: Optional[str] = None


class ResumeReport(BaseModel):
    """Response of POST /agents/resume/{job_id}: a Markdown resume tailored to the saved
    job, plus Markdown side-project ideas that close its skill gaps. Not saved anywhere."""
    job_id: UUID
    company_name: str
    position: str
    resume: str
    side_projects: str
    generated_at: datetime


# ---------- job board queries (apis/reposetories/jobs.py) ----------

class JobOut(BaseModel):
    """One job_board_table row, as returned by GET /jobs and GET /jobs/{job_id}."""
    model_config = ConfigDict(from_attributes=True)  # built straight from JobBoard rows

    id: UUID
    company_name: str
    position: str
    description: Optional[str] = None
    post_id: Optional[str] = None  # the portal's own id for the posting
    link: Optional[str] = None
    update_at: datetime
    job_type: JobType
    compatibility: int
    action: Action
    # qualification_check's breakdown of the score; None for jobs saved before it was stored.
    requirements: Optional[list[dict]] = None
    matched: Optional[list[str]] = None
    missing: Optional[list[str]] = None
    reasoning: Optional[str] = None


class JobPage(BaseModel):
    """Response of GET /jobs: one page of filtered jobs plus the total match count."""
    total: int
    limit: int
    offset: int
    items: list[JobOut]


class JobActionUpdate(BaseModel):
    """Body of PATCH /jobs/{job_id}/action: set the application status of a job."""
    action: Action
