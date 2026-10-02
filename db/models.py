from sqlalchemy import String, DateTime, Integer, Column, ForeignKey, JSON
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.types import Uuid
import uuid
import datetime
from enum import Enum

class Base(DeclarativeBase):
    pass

class JobType(Enum):
    onsite = "onsite"
    remote = "remote"
    hybrid = "hybrid"
    unknown = "unknown"

class Action(Enum):
    searched = "searched"
    applied = "applied"
    drop = "drop"
    interview_scheduled = "interview_scheduled"
    interview_inprogress = "interview_inprogress"
    interview_done = "interview_done"
    denied = "denied"

class JobBoard(Base):
    __tablename__="job_board_table"
    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    company_name = Column(String, nullable=False)
    position = Column(String, nullable=False)
    description = Column(String, nullable=True)
    post_id = Column(String, nullable=True)
    link = Column(String, nullable=True)
    update_at = Column(DateTime(timezone=True), nullable=False,
                       default=lambda: datetime.datetime.now(datetime.UTC),
                       onupdate=lambda: datetime.datetime.now(datetime.UTC))
    job_type = Column(SAEnum(JobType,values_callable=lambda x: [e.value for e in x]), nullable=False, default=JobType.unknown)
    compatibility = Column(Integer, nullable=False)
    action = Column(SAEnum(Action,values_callable=lambda x: [e.value for e in x]), nullable=False, default=Action.searched)
    # From qualification_check, so analytics can find the skills you're missing.
    requirements = Column(JSON, nullable=True)  # [{"skill", "level": "required" | "preferred"}, ...]
    matched = Column(JSON, nullable=True)  # requirement skills you meet
    missing = Column(JSON, nullable=True)  # requirement skills you lack
    reasoning = Column(String, nullable=True)  # why the model gave this compatibility score

class ResumeDraft(Base):
    """A resume_builder result for one job, edited over time by the resume chat."""
    __tablename__="resume_drafts"
    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    job_id = Column(Uuid, ForeignKey("job_board_table.id", ondelete="CASCADE"), nullable=False, index=True)
    resume = Column(String, nullable=False)  # Markdown
    side_projects = Column(String, nullable=False)  # Markdown
    messages = Column(JSON, nullable=False, default=list)  # [{"role": "user" | "assistant", "content", "at"}, ...]
    # Snapshot taken before each edit, oldest first: [{"resume", "side_projects", "note", "at"}, ...]
    versions = Column(JSON, nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), nullable=False,
                        default=lambda: datetime.datetime.now(datetime.UTC))
    update_at = Column(DateTime(timezone=True), nullable=False,
                       default=lambda: datetime.datetime.now(datetime.UTC),
                       onupdate=lambda: datetime.datetime.now(datetime.UTC))
