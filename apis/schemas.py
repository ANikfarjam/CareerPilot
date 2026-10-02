from datetime import datetime
from enum import Enum
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr

from db.models import Action, JobBoard, JobType


class Schema(BaseModel):
    """Base of every API schema. A field with a default is still always in a response, so
    the OpenAPI spec marks it required there; the generated frontend types
    (fronts/careerai/lib/client) then match what the API sends. Request bodies are unaffected."""
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)


# ---------- agents (apis/reposetories/agents.py) ----------

class RunStatus(str, Enum):
    """Lifecycle of a graph run: queued -> running -> succeeded | failed."""
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"


class AgentRunRequest(Schema):
    """Body of POST /agents/runs: which portals to search and which sandbox to use."""
    # Portal names from portals.yml; None or empty = all enabled portals.
    portals: Optional[list[str]] = None
    sandbox: Literal["sandbox", "sandbox-cpu"] = "sandbox"


class AgentRunSummary(Schema):
    """What a finished run did: portal_search -> qualification_check -> db_ingestion."""
    positions: int = 0
    scored: int = 0
    ingested: int = 0  # rows written by the graph's db_ingestion node
    portal_errors: list[dict] = []
    qualification_errors: list[dict] = []
    ingestion_errors: list[dict] = []


class AgentRun(Schema):
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


class SideProject(Schema):
    """A side project the analytics agent recommends to close skill gaps from the near-miss jobs."""
    title: str
    skills: list[str]  # skill gaps it covers, as named in AnalyticsReport.skill_gaps
    description: str
    why: str  # which near-miss jobs / companies it helps with
    effort: Literal["weekend", "1-2 weeks", "1 month+"]


class ActionRow(Schema):
    """Row of AnalyticsTables.by_action: how many jobs have each status, zeros included."""
    action: Action
    count: int


class FunnelRow(Schema):
    """Row of AnalyticsTables.funnel: found -> applied -> interview -> interview_done."""
    stage: Literal["found", "applied", "interview", "interview_done"]
    count: int
    rate: float  # share of found jobs, 0-1


class JobTypeRow(Schema):
    """Row of AnalyticsTables.by_job_type: jobs found, applied to and interviewed per work type."""
    job_type: JobType
    found: int
    applied: int
    interview: int


class CompanyRow(Schema):
    """Row of AnalyticsTables.by_company, most found first."""
    company_name: str
    found: int
    applied: int
    interview: int
    avg_compatibility: Optional[float] = None


class CompatibilityRow(Schema):
    """Row of AnalyticsTables.compatibility: the 0-10 compatibility score histogram."""
    compatibility: int
    found: int
    applied: int


class WeeklyRow(Schema):
    """Row of AnalyticsTables.weekly: jobs by week of their last update, one count per action."""
    week: datetime  # start of the week
    searched: int = 0
    applied: int = 0
    drop: int = 0
    interview_scheduled: int = 0
    interview_inprogress: int = 0
    interview_done: int = 0
    denied: int = 0


class AnalyticsTables(Schema):
    """The chart tables of AnalyticsReport, built by agents/analytics/agent.py build_tables()."""
    by_action: list[ActionRow]
    funnel: list[FunnelRow]
    by_job_type: list[JobTypeRow]
    by_company: list[CompanyRow]
    compatibility: list[CompatibilityRow]
    weekly: list[WeeklyRow]


class NearMissJob(Schema):
    """Row of AnalyticsReport.near_miss_jobs: a job you're broadly qualified for that misses
    at least one required skill (agents/analytics/agent.py NEAR_MISS_COLUMNS)."""
    company_name: str
    position: str
    compatibility: int
    action: Action
    link: Optional[str] = None
    missing_required: Optional[str] = None  # skills joined with "; "


class SkillGap(Schema):
    """Row of AnalyticsReport.skill_gaps: a skill missing across the near-miss jobs
    (agents/analytics/agent.py SKILL_GAP_COLUMNS)."""
    skill: str
    jobs: int
    required_in: int
    avg_compatibility: Optional[float] = None
    companies: Optional[str] = None  # joined with "; "


class AnalyticsReport(Schema):
    """Analytics over every saved job. GET /agents/analytics returns only `tables` (host
    pandas, fast); a finished analytics run (agents/graph/analytic_graph.py) fills the rest.
    The tables are built by agents/analytics/agent.py build_tables()."""
    total_jobs: int
    tables: AnalyticsTables
    # Jobs you're broadly qualified for but missing crucial (required) skills.
    near_miss_jobs: list[NearMissJob] = []
    skill_gaps: list[SkillGap] = []  # missing skills across near_miss_jobs, most required first
    analysis: str = ""
    conclusion: str = ""
    projects: list[SideProject] = []
    errors: list[str] = []  # the tables are still valid when the agent failed
    generated_at: datetime


class AnalyticsRunRequest(Schema):
    """Body of POST /agents/analytics/runs: which sandbox the analytics agent runs its code in.
    It only needs pandas, so sandbox-cpu is enough."""
    sandbox: Literal["sandbox", "sandbox-cpu"] = "sandbox"


class AnalyticsRun(Schema):
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


class ResumeReport(Schema):
    """Response of POST /agents/resume/{job_id}: a Markdown resume tailored to the saved
    job, plus Markdown side-project ideas that close its skill gaps. Saved as the resume
    draft draft_id, which the resume chat edits."""
    draft_id: UUID
    job_id: UUID
    company_name: str
    position: str
    resume: str
    side_projects: str
    generated_at: datetime



class ChatMessage(Schema):
    """One message of a resume draft's chat; assistant messages hold only the reply text,
    the doc edits they made are in ResumeDraftOut.versions."""
    role: Literal["user", "assistant"]
    content: str
    at: datetime


class DraftVersion(Schema):
    """A resume draft's content before one edit (a chat edit, a manual save or a revert)."""
    resume: str
    side_projects: str
    note: str  # what replaced it, e.g. the chat message that changed it
    at: datetime


class ResumeDraftSummary(Schema):
    """One row of GET /agents/resume/drafts: a saved resume draft without its content."""
    id: UUID
    job_id: UUID
    company_name: Optional[str] = None
    position: Optional[str] = None
    created_at: datetime
    update_at: datetime


class ResumeDraftOut(ResumeDraftSummary):
    """A saved resume draft, as returned by GET/PUT /agents/resume/drafts/{draft_id}, the revert
    route and the chat websocket's "done" event: the current docs, the chat and older versions."""
    resume: str
    side_projects: str
    messages: list[ChatMessage] = []
    versions: list[DraftVersion] = []  # oldest first; index is the revert route's {version}


class ResumeDraftUpdate(Schema):
    """Body of PUT /agents/resume/drafts/{draft_id}: a manual edit from the UI.
    Fields left out are not changed; the old content is kept as a version."""
    resume: Optional[str] = None
    side_projects: Optional[str] = None


# ---------- job board queries (apis/reposetories/jobs.py) ----------

class JobOut(Schema):
    """One job_board_table row, as returned by GET /jobs and GET /jobs/{job_id}."""
    model_config = ConfigDict(from_attributes=True, json_schema_serialization_defaults_required=True)  # built straight from JobBoard rows

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


class JobPage(Schema):
    """Response of GET /jobs: one page of filtered jobs plus the total match count."""
    total: int
    limit: int
    offset: int
    items: list[JobOut]


class JobActionUpdate(Schema):
    """Body of PATCH /jobs/{job_id}/action: set the application status of a job."""
    action: Action
