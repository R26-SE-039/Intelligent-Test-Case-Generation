"""
SQLAlchemy ORM models for Component 2.

Tables:
  - projects          : top-level project container
  - user_stories      : stories received from C1 (or entered manually), scoped to a project
  - gherkin_scenarios : AI-generated Gherkin for each story
"""

from sqlalchemy import Column, String, Boolean, Text, DateTime, ForeignKey, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
import enum

from app.database import Base


class Priority(str, enum.Enum):
    high = "high"
    medium = "medium"
    low = "low"


class Status(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    done = "done"


class Project(Base):
    """
    Top-level container.  Every user story belongs to exactly one project.
    Deleting a project cascades to its stories and their Gherkin scenarios.
    """
    __tablename__ = "projects"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(200), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class UserStory(Base):
    """
    Represents a user story (from C1 or manually entered).
    Mirrors the JSON structure Component 1 outputs.
    Scoped to a Project — the same story ID (e.g. US-001) can exist in multiple projects.
    """
    __tablename__ = "user_stories"

    id = Column(String(50), primary_key=True)          # composite PK with project_id
    project_id = Column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        primary_key=True,                               # composite PK
    )
    actor = Column(String(200), nullable=False)
    action = Column(String(500), nullable=False)
    goal = Column(String(500), nullable=False)
    priority = Column(SAEnum(Priority), default=Priority.medium)
    status = Column(SAEnum(Status), default=Status.pending)
    source = Column(String(20), default="manual")       # "C1" or "manual"
    acceptance_criteria = Column(Text, default="[]")    # JSON array stored as text
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class GherkinScenario(Base):
    """
    AI-generated Gherkin feature file content for a user story.
    One story can have multiple iterations (edited by QA).
    """
    __tablename__ = "gherkin_scenarios"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    story_id = Column(String(50), nullable=False)
    project_id = Column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    feature_name = Column(String(255), nullable=False)
    gherkin_text = Column(Text, nullable=False)         # full .feature file content
    generator = Column(String(20), default="jinja2")    # "jinja2" | "llm"
    llm_model = Column(String(100), nullable=True)      # e.g. "gpt-4o", "codellama"
    edited_by_qa = Column(Boolean, default=False)
    approved = Column(Boolean, default=False)           # QA approved this scenario
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
