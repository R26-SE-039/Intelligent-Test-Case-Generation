"""
SQLAlchemy ORM models for Component 2.

Tables:
  - projects          : top-level project container
  - user_stories      : stories received from C1 (or entered manually), scoped to a project
  - gherkin_scenarios : AI-generated Gherkin for each story
  - test_suites       : persisted LLM-generated test code, one row per (project, framework)
  - dom_elements      : selectors extracted from the live staging DOM, editable by QA
"""

from sqlalchemy import (
    Column, String, Boolean, Text, DateTime, Integer, Float,
    ForeignKey, Enum as SAEnum, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
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


class TestSuite(Base):
    """
    Persisted test code generated from approved Gherkin scenarios.
    One row per (project_id, framework) — regeneration upserts.

    source_scenarios_hash fingerprints the Gherkin inputs that produced this
    suite, so the UI can detect when scenarios have drifted and prompt the
    user to regenerate (instead of silently burning LLM tokens on every page
    load).
    """
    __tablename__ = "test_suites"
    __table_args__ = (
        UniqueConstraint("project_id", "framework", name="uq_test_suites_project_framework"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    framework = Column(String(40), nullable=False)      # selenium | playwright | cypress
    language = Column(String(40), nullable=False)       # python | javascript
    filename = Column(String(255), nullable=False)
    code = Column(Text, nullable=False)
    mode = Column(String(40), nullable=False)           # abstract | dom
    url = Column(Text, nullable=False)
    llm_model = Column(String(100), nullable=True)
    source_scenarios_hash = Column(String(64), nullable=False)
    source_scenario_ids = Column(JSONB, nullable=False, default=list)
    source_scenario_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class DomElement(Base):
    """
    A real CSS selector extracted from the staging DOM by the Playwright crawler,
    or manually added/edited by QA. Used as ground truth at code-generation time
    so the LLM emits real selectors instead of <<PLACEHOLDER>>s.

    Uniqueness is per (project, url, role): each named role on a page exists at
    most once, so re-crawling can upsert cleanly.
    """
    __tablename__ = "dom_elements"
    __table_args__ = (
        UniqueConstraint("project_id", "url", "role", name="uq_dom_elements_project_url_role"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    url = Column(Text, nullable=False)              # the page URL where this element lives
    selector = Column(Text, nullable=False)         # CSS selector, e.g. "#user-name"
    tag = Column(String(40), nullable=False)        # INPUT, BUTTON, A, ...
    text = Column(Text, nullable=True)              # visible text / value
    attributes = Column(JSONB, nullable=False, default=dict)  # id, name, type, placeholder, aria-label, ...
    role = Column(String(120), nullable=False)      # semantic label: username_input, login_button, ...
    source_step = Column(Text, nullable=True)       # the Gherkin step (or heuristic) that produced it
    confidence = Column(Float, nullable=True)       # 0..1 — how sure the crawler is about the role mapping
    edited_by_qa = Column(Boolean, default=False)
    approved = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
