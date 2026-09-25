from sqlalchemy import String, DateTime, Integer, Column, ForeignKey
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
    link = Column(String, nullable=True)
    update_at = Column(DateTime(timezone=True), nullable=False,
                       default=lambda: datetime.datetime.now(datetime.UTC),
                       onupdate=lambda: datetime.datetime.now(datetime.UTC))
    job_type = Column(SAEnum(JobType,values_callable=lambda x: [e.value for e in x]), nullable=False, default=JobType.unknown)
    compatibility = Column(Integer, nullable=False)
    action = Column(SAEnum(Action,values_callable=lambda x: [e.value for e in x]), nullable=False, default=Action.searched)