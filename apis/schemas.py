from datetime import datetime
from enum import Enum
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from db.models import Action, JobBoard, JobType


class Schema(BaseModel):
    """Base of every API schema. A field with a default is still always in a response, so
    the OpenAPI spec marks it required there; the generated frontend types
    (fronts/careerpilot/lib/client) then match what the API sends. Request bodies are unaffected."""
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)


# ---------- agents (apis/reposetories/agents.py) ----------

class RunStatus(str, Enum):
    """Lifecycle of a graph run: queued -> running -> succeeded | failed."""
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"


class ManualPosition(Schema):
    """A posting the user adds by hand (AgentRunRequest.manual_positions, POST /agents/runs).
    It skips portal_search but is scored by qualification_check and saved by db_ingestion,
    so it needs a description to score."""
    company: str = Field(min_length=1)
    position: str = Field(min_length=1)
    link: str = Field(min_length=1)  # also the job's id (uuid5 of the link), see dbingestion.job_id
    job_type: JobType = JobType.unknown
    description: str = Field(min_length=1)
    post_id: Optional[str] = None


class AgentRunRequest(Schema):
    """Body of POST /agents/runs: which portals to search, postings to add by hand and which sandbox to use."""
    # Portal names from portals.yml; None = all enabled portals, [] = none (only manual_positions).
    portals: Optional[list[str]] = None
    manual_positions: list[ManualPosition] = []
    # Scraping needs no GPU (and Ollama holds the VRAM); "sandbox" needs the NVIDIA Container Toolkit.
    sandbox: Literal["sandbox", "sandbox-cpu"] = "sandbox-cpu"


RunStage = Literal["portal_search", "qualification_check", "db_ingestion"]


class RunLog(Schema):
    """One line of a graph node's log (AgentRun.logs). detail False: a progress line, e.g. which
    portal is being searched; detail True: a live-activity line, one step of the agent's loop
    (waiting on the model, the command it runs, its exit code)."""
    stage: RunStage
    level: Literal["info", "success", "error"]
    message: str
    detail: bool = False
    at: datetime


class AgentRunSummary(Schema):
    """What a finished run did: portal_search -> qualification_check -> db_ingestion."""
    positions: int = 0
    scored: int = 0
    ingested: int = 0  # rows written by the graph's db_ingestion node
    skipped_known: int = 0  # postings already in the DB, not re-scored
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
    stage: Optional[RunStage] = None  # graph node currently running (the last one once finished)
    logs: list[RunLog] = []  # oldest first: every progress line, the last MAX_ACTIVITY_LOGS detail lines
    summary: Optional[AgentRunSummary] = None
    error: Optional[str] = None


class PortalCreate(Schema):
    """Body of POST /agents/portals: a company careers page to add to portals.yml's tracked_companies."""
    name: str = Field(min_length=1)
    careers_url: str = Field(pattern=r"^https?://")


class TargetPositionCreate(Schema):
    """Body of POST /agents/target-positions: a title keyword to add to portals.yml's title_filter.positive."""
    keyword: str = Field(min_length=1)


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
    sandbox: Literal["sandbox", "sandbox-cpu"] = "sandbox-cpu"


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


DocKind = Literal["resumes", "education", "projects", "papers", "achievements", "other"]


class DocNode(Schema):
    """A file or folder under Docs/user_docs, for the knowledge base page's tree view."""
    name: str
    path: str  # relative to Docs/user_docs
    is_dir: bool
    size: Optional[int] = None  # bytes; None for folders
    usable: bool  # a .md/.txt/.pdf the knowledge base agent reads (images etc. are listed but ignored)
    children: list["DocNode"] = []


class DocFolder(Schema):
    """One kind of document the knowledge base agent reads: where to drop it and what's there now."""
    kind: DocKind
    folder: str  # relative to Docs/user_docs; "" for other (files placed directly in it)
    label: str
    description: str
    exists: bool
    documents: int  # files in it the agent would read
    tree: list[DocNode]


class UserDocs(Schema):
    """Response of GET /agents/knowledge/documents: the Docs/user_docs layout, what each folder
    holds, and the current knowledge base (empty until it is first generated)."""
    root: str  # absolute path of Docs/user_docs
    folders: list[DocFolder]
    knowledge_file: str
    knowledge: str = ""
    knowledge_updated_at: Optional[datetime] = None


class KnowledgeRunRequest(Schema):
    """Body of POST /agents/knowledge/runs: which kinds of documents to build the knowledge base
    from (default: every kind) and whether to tune portals.yml to it afterwards."""
    kinds: Optional[list[DocKind]] = None
    update_portals: bool = True


class PortalChanges(Schema):
    """What the knowledge base agent changed in portals.yml (title_filter keywords and tracked companies)."""
    positive_added: list[str] = []
    positive_removed: list[str] = []
    negative_added: list[str] = []
    negative_removed: list[str] = []
    companies_added: list[dict] = []  # {"name", "careers_url"}
    companies_enabled: list[str] = []
    companies_disabled: list[str] = []
    reasoning: str = ""


class KnowledgeRun(Schema):
    """Returned by POST /agents/knowledge/runs and GET /agents/knowledge/runs/{run_id}; the
    frontend polls it until status is succeeded or failed."""
    id: UUID
    status: RunStatus
    kinds: list[DocKind]
    update_portals: bool
    created_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    documents: list[str] = []  # files the knowledge base was built from, relative to Docs/user_docs
    portals: Optional[PortalChanges] = None
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
    description: Optional[str] = None  # read from the job's .md file; only filled by GET /jobs/{job_id}
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
