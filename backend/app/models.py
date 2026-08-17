"""
SQLAlchemy ORM models for Component 2.

Tables:
  - projects          : top-level project container
  - user_stories      : stories received from C1 (or entered manually), scoped to a project
  - gherkin_scenarios : AI-generated Gherkin for each story
  - test_suites       : persisted LLM-generated test code, one row per (project, framework)
  - dom_elements      : selectors extracted from the live staging DOM, editable by QA
  - test_runs         : execution log of each test scenario, used as labels for ML risk prediction
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

    The id mirrors the auth-service project UUID (get-or-create), and
    organization_id references the auth-service organization. The auth
    service (user_db) stays the system of record for both — this table
    only stores the UUIDs, never copies of their data.
    """
    __tablename__ = "projects"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    organization_id = Column(UUID(as_uuid=True), nullable=True, index=True)
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
    # Auth-service iteration UUID (set on C1 imports). Reference only — the
    # auth service owns iterations; RTM can trace story → iteration with it.
    iteration_id = Column(UUID(as_uuid=True), nullable=True, index=True)
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

    History model — each (project, framework) is a chain of versions:
      - `version` is a 1-based incrementing counter per (project, framework).
      - `is_active=True` marks the head of the chain (the latest version that
        autosaves apply to; appears in the Code Review list).
      - `selected_for_run=True` marks the one suite (across the whole project)
        that the next CI/CD run should execute. At most one row per project
        carries this flag.

    Regeneration INSERTs a fresh row at version+1, flips the prior head to
    inactive. QA edits autosave into the active row. "Save as new version"
    snapshots the active row. "Restore" copies an old version's code into a
    new head row, so history is never destructive.

    source_scenarios_hash fingerprints the Gherkin inputs that produced this
    suite, so the UI can detect when scenarios have drifted and prompt the
    user to regenerate (instead of silently burning LLM tokens on every page
    load).
    """
    __tablename__ = "test_suites"
    __table_args__ = (
        UniqueConstraint(
            "project_id", "framework", "version",
            name="uq_test_suites_project_framework_version",
        ),
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
    version = Column(Integer, nullable=False, default=1)
    is_active = Column(Boolean, nullable=False, default=True)
    selected_for_run = Column(Boolean, nullable=False, default=False)
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


class TestRun(Base):
    """
    One row per executed test scenario. Accumulating these rows over time is
    what turns the risk prediction model from synthetic-only into a real
    supervised classifier (failure rate per flow becomes the label).

    `flow_name` groups runs into the buckets the UI surfaces ("login_flow",
    "cart_ops", "checkout", "search"). It is derived from the scenario name
    on insertion so the model can aggregate without a join.
    """
    __tablename__ = "test_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    suite_id = Column(
        UUID(as_uuid=True),
        ForeignKey("test_suites.id", ondelete="SET NULL"),
        nullable=True,
    )
    scenario_name = Column(String(255), nullable=False)
    flow_name = Column(String(64), nullable=False, index=True)
    framework = Column(String(40), nullable=False)
    status = Column(String(20), nullable=False)         # passed | failed | error
    duration_ms = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)
    executed_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)


class TestRunExecution(Base):
    """
    One row per "Run Tests" click — captures the whole CI/CD execution.

    Two execution paths share this schema:
      - `mode='github'`  → GitHub Actions workflow_dispatch was triggered.
        `github_run_id` and `github_run_url` link out to the live run.
      - `mode='local'`   → A subprocess Playwright run on the FastAPI host.
        Used as the demo-safe fallback when GITHUB_TOKEN is not configured.

    `raw_log_text` is the full stdout/stderr capture (or GitHub Actions log
    fetched via REST after the run finished) — this is the "log file saved
    in DB" deliverable. Per-scenario rows still land in `test_runs` so the
    ML risk model keeps its training signal.

    `artifacts_json` stores the structured screenshot / video / Allure links
    so we don't need a JOIN to render the dashboard.
    """
    __tablename__ = "test_run_executions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    suite_id = Column(
        UUID(as_uuid=True),
        ForeignKey("test_suites.id", ondelete="SET NULL"),
        nullable=True,
    )
    framework = Column(String(40), nullable=False)
    mode = Column(String(20), nullable=False)            # github | local
    status = Column(String(20), nullable=False, default="queued")
                                                          # queued | running | passed | failed | error
    github_run_id = Column(String(64), nullable=True)    # numeric ID returned by GH API
    github_run_url = Column(Text, nullable=True)         # https://github.com/owner/repo/actions/runs/...
    github_branch = Column(String(120), nullable=True)   # runs/{uuid}

    started_at = Column(DateTime(timezone=True), server_default=func.now())
    finished_at = Column(DateTime(timezone=True), nullable=True)
    duration_ms = Column(Integer, nullable=True)

    total_count = Column(Integer, nullable=False, default=0)
    passed_count = Column(Integer, nullable=False, default=0)
    failed_count = Column(Integer, nullable=False, default=0)

    raw_log_text = Column(Text, nullable=True)            # full execution log captured at run end
    artifacts_json = Column(JSONB, nullable=False, default=dict)
                                                          # {screenshots, video, allure_url, ...}
    pdf_path = Column(Text, nullable=True)                # local filesystem path to generated PDF
    error_message = Column(Text, nullable=True)


class TestRunScreenshot(Base):
    """
    Per-scenario screenshot persisted to disk and indexed in the DB so the
    dashboard's screenshot grid can be rendered with a single query. The
    image bytes live under `./reports/{run_id}/screenshots/`; `image_path`
    is the relative path served via the static-file endpoint.
    """
    __tablename__ = "test_run_screenshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id = Column(
        UUID(as_uuid=True),
        ForeignKey("test_run_executions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    scenario = Column(String(255), nullable=False)
    label = Column(String(255), nullable=False)
    status = Column(String(20), nullable=False)            # passed | failed
    image_path = Column(Text, nullable=False)              # relative path under ./reports/
    captured_at = Column(DateTime(timezone=True), server_default=func.now())


class ProjectGitHubConnection(Base):
    """
    Per-project GitHub credential + target repo. One row per project (PK is
    project_id) so users can wire different projects to different repos.

    The token is encrypted at rest with Fernet (symmetric AES-128-CBC + HMAC)
    using a key from NEXTGENQA_CRYPTO_KEY in .env. We never return the
    decrypted token to the frontend — the dashboard shows a masked preview.

    `workflow_installed_at` is stamped after we successfully PUT the workflow
    YAML to the repo's default branch. If null, the connection exists but
    the workflow is missing (e.g. install failed; UI offers a "Reinstall"
    button).
    """
    __tablename__ = "project_github_connections"

    project_id = Column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        primary_key=True,
    )
    encrypted_token = Column(Text, nullable=False)        # Fernet ciphertext
    token_preview = Column(String(20), nullable=False)    # e.g. "ghp_****wxyz"
    owner = Column(String(120), nullable=False)
    repo = Column(String(120), nullable=False)
    default_branch = Column(String(120), nullable=False, default="main")
    github_user_login = Column(String(120), nullable=True)
    github_user_avatar_url = Column(Text, nullable=True)
    workflow_installed_at = Column(DateTime(timezone=True), nullable=True)
    last_validated_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
