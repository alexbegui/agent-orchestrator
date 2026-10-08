import uuid
from datetime import datetime, timezone
from enum import Enum
from sqlalchemy import Column, String, Text, DateTime, JSON, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import relationship
from app.core.database import Base


class TaskStatus(str, Enum):
    DRAFT = "DRAFT"
    SPEC_READY = "SPEC_READY"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    REVIEW_READY = "REVIEW_READY"
    DONE = "DONE"
    FAILED = "FAILED"


class RunnerType(str, Enum):
    SUBPROCESS_CLI = "SUBPROCESS_CLI"
    DIRECT_API = "DIRECT_API"


class Task(Base):
    __tablename__ = "tasks"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False)
    title = Column(String(255), nullable=False)
    raw_prompt = Column(Text, nullable=False)
    refined_spec = Column(Text, nullable=True)
    status = Column(SQLEnum(TaskStatus), default=TaskStatus.DRAFT, nullable=False)
    runner_type = Column(SQLEnum(RunnerType), default=RunnerType.SUBPROCESS_CLI, nullable=False)
    runner_config = Column(JSON, default=dict)
    worktree_path = Column(String(1024), nullable=True)
    git_branch = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    project = relationship("Project", back_populates="tasks")
    messages = relationship("Message", back_populates="task", cascade="all, delete-orphan")
