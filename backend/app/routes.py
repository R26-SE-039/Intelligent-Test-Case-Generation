"""
API routes for Projects, User Stories, and Gherkin generation.

Project endpoints:
  POST   /api/v1/projects                              — Create project
  GET    /api/v1/projects                              — List all projects
  DELETE /api/v1/projects/{project_id}                 — Delete project + cascade

Story endpoints (project-scoped):
  GET    /api/v1/projects/{project_id}/stories         — List stories for project
  POST   /api/v1/projects/{project_id}/stories/bulk   — Upsert stories into project
  POST   /api/v1/projects/{project_id}/stories         — Add single story
  DELETE /api/v1/projects/{project_id}/stories/{id}   — Delete a story

Gherkin endpoints:
  POST   /api/v1/gherkin/generate                      — Generate Gherkin for story IDs
  GET    /api/v1/gherkin/{project_id}/{story_id}       — Get Gherkin for a story
  PUT    /api/v1/gherkin/{gherkin_id}                  — Update Gherkin text (QA edit)
  PUT    /api/v1/gherkin/{gherkin_id}/approve          — Toggle approval status
  POST   /api/v1/gherkin/{project_id}/{story_id}/regenerate — Force regenerate
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from pydantic import BaseModel
from typing import Optional
import hashlib
import json
import uuid

from app.database import get_db
from app.models import Project, UserStory, GherkinScenario, TestSuite, DomElement, Priority, Status
from app.gherkin.generator import generate_gherkin
from app.code_gen.generator import generate_test_suite
from app.dom_crawler import crawl_url, probe_url

router = APIRouter(prefix="/api/v1", tags=["pipeline"])


# ─── Pydantic schemas ─────────────────────────────────────────────────────────

class ProjectIn(BaseModel):
    name: str
    description: Optional[str] = None


class ProjectOut(BaseModel):
    id: str
    name: str
    description: Optional[str]
    created_at: Optional[str]

    class Config:
        from_attributes = True


class UserStoryIn(BaseModel):
    id: str
    actor: str
    action: str
    goal: str
    priority: str = "medium"
    status: str = "pending"
    source: str = "manual"
    acceptance_criteria: list[str] = []


class UserStoryOut(BaseModel):
    id: str
    project_id: str
    actor: str
    action: str
    goal: str
    priority: str
    status: str
    source: str
    acceptance_criteria: list[str]

    class Config:
        from_attributes = True


class GenerateRequest(BaseModel):
    story_ids: list[str]
    project_id: str


class GherkinOut(BaseModel):
    id: str
    story_id: str
    project_id: str
    feature_name: str
    gherkin_text: str
    generator: str
    edited_by_qa: bool
    approved: bool

    class Config:
        from_attributes = True


class GherkinUpdateIn(BaseModel):
    gherkin_text: str


# ─── Helper ───────────────────────────────────────────────────────────────────

def _story_out(s: UserStory) -> UserStoryOut:
    return UserStoryOut(
        id=s.id,
        project_id=str(s.project_id),
        actor=s.actor,
        action=s.action,
        goal=s.goal,
        priority=s.priority.value,
        status=s.status.value,
        source=s.source,
        acceptance_criteria=json.loads(s.acceptance_criteria or "[]"),
    )


def _gherkin_out(g: GherkinScenario) -> GherkinOut:
    return GherkinOut(
        id=str(g.id),
        story_id=g.story_id,
        project_id=str(g.project_id),
        feature_name=g.feature_name,
        gherkin_text=g.gherkin_text,
        generator=g.generator,
        edited_by_qa=g.edited_by_qa,
        approved=g.approved,
    )


# ─── Project endpoints ────────────────────────────────────────────────────────

@router.post("/projects", response_model=ProjectOut)
async def create_project(body: ProjectIn, db: AsyncSession = Depends(get_db)):
    """Create a new project (blank workspace)."""
    # Check name uniqueness
    result = await db.execute(select(Project).where(Project.name == body.name))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"Project '{body.name}' already exists")

    project = Project(
        id=uuid.uuid4(),
        name=body.name,
        description=body.description,
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)

    return ProjectOut(
        id=str(project.id),
        name=project.name,
        description=project.description,
        created_at=project.created_at.isoformat() if project.created_at else None,
    )


@router.get("/projects", response_model=list[ProjectOut])
async def list_projects(db: AsyncSession = Depends(get_db)):
    """List all projects ordered by most recent first."""
    result = await db.execute(select(Project).order_by(Project.created_at.desc()))
    projects = result.scalars().all()
    return [
        ProjectOut(
            id=str(p.id),
            name=p.name,
            description=p.description,
            created_at=p.created_at.isoformat() if p.created_at else None,
        )
        for p in projects
    ]


@router.delete("/projects/{project_id}", status_code=204)
async def delete_project(project_id: str, db: AsyncSession = Depends(get_db)):
    """Delete a project and all its stories + Gherkin scenarios (cascade)."""
    result = await db.execute(
        select(Project).where(Project.id == project_id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    await db.execute(delete(Project).where(Project.id == project_id))
    await db.commit()


# ─── Story endpoints (project-scoped) ────────────────────────────────────────

@router.get("/projects/{project_id}/stories", response_model=list[UserStoryOut])
async def list_stories(project_id: str, db: AsyncSession = Depends(get_db)):
    """List all user stories for a project."""
    result = await db.execute(
        select(UserStory)
        .where(UserStory.project_id == project_id)
        .order_by(UserStory.created_at.asc())
    )
    stories = result.scalars().all()
    return [_story_out(s) for s in stories]


@router.post("/projects/{project_id}/stories/bulk", response_model=list[UserStoryOut])
async def save_stories_bulk(
    project_id: str,
    stories: list[UserStoryIn],
    db: AsyncSession = Depends(get_db),
):
    """
    Upsert multiple user stories into a project.
    If a story with the same id already exists in the project, it is updated.
    """
    # Verify project exists
    proj = await db.execute(select(Project).where(Project.id == project_id))
    if not proj.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Project not found")

    saved = []
    for s in stories:
        result = await db.execute(
            select(UserStory).where(
                UserStory.id == s.id,
                UserStory.project_id == project_id,
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            existing.actor = s.actor
            existing.action = s.action
            existing.goal = s.goal
            existing.priority = Priority(s.priority)
            existing.status = Status(s.status)
            existing.source = s.source
            existing.acceptance_criteria = json.dumps(s.acceptance_criteria)
            db.add(existing)
            saved.append(existing)
        else:
            story = UserStory(
                id=s.id,
                project_id=project_id,
                actor=s.actor,
                action=s.action,
                goal=s.goal,
                priority=Priority(s.priority),
                status=Status(s.status),
                source=s.source,
                acceptance_criteria=json.dumps(s.acceptance_criteria),
            )
            db.add(story)
            saved.append(story)

    await db.commit()
    for story in saved:
        await db.refresh(story)

    return [_story_out(s) for s in saved]


@router.post("/projects/{project_id}/stories", response_model=UserStoryOut)
async def add_story(
    project_id: str,
    story: UserStoryIn,
    db: AsyncSession = Depends(get_db),
):
    """Add a single user story to a project."""
    proj = await db.execute(select(Project).where(Project.id == project_id))
    if not proj.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Project not found")

    # Auto-generate an ID if not provided or already taken
    result = await db.execute(
        select(UserStory).where(
            UserStory.id == story.id,
            UserStory.project_id == project_id,
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        # Update
        existing.actor = story.actor
        existing.action = story.action
        existing.goal = story.goal
        existing.priority = Priority(story.priority)
        existing.status = Status(story.status)
        existing.source = story.source
        existing.acceptance_criteria = json.dumps(story.acceptance_criteria)
        db.add(existing)
        await db.commit()
        await db.refresh(existing)
        return _story_out(existing)

    new_story = UserStory(
        id=story.id,
        project_id=project_id,
        actor=story.actor,
        action=story.action,
        goal=story.goal,
        priority=Priority(story.priority),
        status=Status(story.status),
        source=story.source,
        acceptance_criteria=json.dumps(story.acceptance_criteria),
    )
    db.add(new_story)
    await db.commit()
    await db.refresh(new_story)
    return _story_out(new_story)


@router.delete("/projects/{project_id}/stories/{story_id}", status_code=204)
async def delete_story(
    project_id: str,
    story_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Delete a story and its Gherkin scenario from a project."""
    # Delete associated Gherkin first
    await db.execute(
        delete(GherkinScenario).where(
            GherkinScenario.story_id == story_id,
            GherkinScenario.project_id == project_id,
        )
    )
    # Delete story
    result = await db.execute(
        select(UserStory).where(
            UserStory.id == story_id,
            UserStory.project_id == project_id,
        )
    )
    story = result.scalar_one_or_none()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")

    await db.execute(
        delete(UserStory).where(
            UserStory.id == story_id,
            UserStory.project_id == project_id,
        )
    )
    await db.commit()


# ─── Gherkin endpoints ────────────────────────────────────────────────────────

@router.post("/gherkin/generate", response_model=list[GherkinOut])
async def generate_gherkin_for_stories(
    body: GenerateRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Generate (or regenerate) Gherkin scenarios for a list of story IDs within a project.
    """
    if not body.story_ids:
        raise HTTPException(status_code=400, detail="No story IDs provided")

    results = []

    for story_id in body.story_ids:
        result = await db.execute(
            select(UserStory).where(
                UserStory.id == story_id,
                UserStory.project_id == body.project_id,
            )
        )
        story = result.scalar_one_or_none()

        if not story:
            raise HTTPException(
                status_code=404,
                detail=f"Story {story_id} not found in project {body.project_id}"
            )

        story_dict = {
            "id": story.id,
            "actor": story.actor,
            "action": story.action,
            "goal": story.goal,
            "priority": story.priority.value,
            "acceptance_criteria": json.loads(story.acceptance_criteria or "[]"),
        }

        gherkin_text, generator_name = await generate_gherkin(story_dict)

        existing_q = await db.execute(
            select(GherkinScenario).where(
                GherkinScenario.story_id == story_id,
                GherkinScenario.project_id == body.project_id,
            )
        )
        existing_gherkin = existing_q.scalar_one_or_none()

        if existing_gherkin and not existing_gherkin.edited_by_qa:
            existing_gherkin.gherkin_text = gherkin_text
            existing_gherkin.generator = generator_name
            db.add(existing_gherkin)
            gherkin_row = existing_gherkin
        elif not existing_gherkin:
            feature_name = story.action.title()
            gherkin_row = GherkinScenario(
                id=uuid.uuid4(),
                story_id=story.id,
                project_id=body.project_id,
                feature_name=feature_name,
                gherkin_text=gherkin_text,
                generator=generator_name,
            )
            db.add(gherkin_row)
        else:
            gherkin_row = existing_gherkin

        story.status = Status.done  # Mark as done after successful generation
        db.add(story)
        results.append(gherkin_row)

    await db.commit()
    for g in results:
        await db.refresh(g)

    return [_gherkin_out(g) for g in results]


@router.get("/gherkin/{project_id}/{story_id}", response_model=Optional[GherkinOut])
async def get_gherkin_for_story(
    project_id: str,
    story_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get the Gherkin scenario for a story within a project."""
    result = await db.execute(
        select(GherkinScenario).where(
            GherkinScenario.story_id == story_id,
            GherkinScenario.project_id == project_id,
        )
    )
    gherkin = result.scalar_one_or_none()
    if not gherkin:
        return None
    return _gherkin_out(gherkin)


@router.put("/gherkin/{gherkin_id}", response_model=GherkinOut)
async def update_gherkin(
    gherkin_id: str,
    body: GherkinUpdateIn,
    db: AsyncSession = Depends(get_db),
):
    """Save QA edits to a Gherkin scenario. Sets edited_by_qa=True."""
    result = await db.execute(
        select(GherkinScenario).where(GherkinScenario.id == gherkin_id)
    )
    gherkin = result.scalar_one_or_none()
    if not gherkin:
        raise HTTPException(status_code=404, detail="Gherkin scenario not found")

    gherkin.gherkin_text = body.gherkin_text
    gherkin.edited_by_qa = True
    db.add(gherkin)
    await db.commit()
    await db.refresh(gherkin)
    return _gherkin_out(gherkin)


@router.put("/gherkin/{gherkin_id}/approve", response_model=GherkinOut)
async def toggle_approve_gherkin(
    gherkin_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Toggle the approved status of a Gherkin scenario (persisted to DB)."""
    result = await db.execute(
        select(GherkinScenario).where(GherkinScenario.id == gherkin_id)
    )
    gherkin = result.scalar_one_or_none()
    if not gherkin:
        raise HTTPException(status_code=404, detail="Gherkin scenario not found")

    gherkin.approved = not gherkin.approved
    db.add(gherkin)
    await db.commit()
    await db.refresh(gherkin)
    return _gherkin_out(gherkin)


@router.post("/gherkin/{project_id}/{story_id}/regenerate", response_model=GherkinOut)
async def regenerate_gherkin(
    project_id: str,
    story_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Force-regenerate Gherkin for a story, even if QA has edited it.
    Clears the edited_by_qa and approved flags.
    """
    result = await db.execute(
        select(UserStory).where(
            UserStory.id == story_id,
            UserStory.project_id == project_id,
        )
    )
    story = result.scalar_one_or_none()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")

    story_dict = {
        "id": story.id,
        "actor": story.actor,
        "action": story.action,
        "goal": story.goal,
        "priority": story.priority.value,
        "acceptance_criteria": json.loads(story.acceptance_criteria or "[]"),
    }

    gherkin_text, generator_name = await generate_gherkin(story_dict)

    existing_q = await db.execute(
        select(GherkinScenario).where(
            GherkinScenario.story_id == story_id,
            GherkinScenario.project_id == project_id,
        )
    )
    existing = existing_q.scalar_one_or_none()

    if existing:
        existing.gherkin_text = gherkin_text
        existing.generator = generator_name
        existing.edited_by_qa = False
        existing.approved = False
        db.add(existing)
        gherkin_row = existing
    else:
        gherkin_row = GherkinScenario(
            id=uuid.uuid4(),
            story_id=story.id,
            project_id=project_id,
            feature_name=story.action.title(),
            gherkin_text=gherkin_text,
            generator=generator_name,
        )
        db.add(gherkin_row)

    story.status = Status.done
    db.add(story)
    await db.commit()
    await db.refresh(gherkin_row)
    return _gherkin_out(gherkin_row)


# ─── Code Generation endpoints ────────────────────────────────────────────────

class CodeGenRequest(BaseModel):
    project_id: str
    url: str
    mode: str
    frameworks: list[str]  # e.g., ["playwright"] or ["selenium", "playwright", "cypress"]


class TestSuiteOut(BaseModel):
    id: str
    project_id: str
    framework: str
    language: str
    filename: str
    code: str
    mode: str
    url: str
    llm_model: Optional[str] = None
    source_scenarios_hash: str
    source_scenario_count: int
    is_stale: bool                      # current scenarios hash differs from stored
    updated_at: Optional[str] = None

    class Config:
        from_attributes = True


def _framework_meta(framework: str) -> tuple[str, str]:
    """Return (language, filename) for a framework name."""
    if framework == "cypress":
        return "javascript", "test_suite_cypress.cy.js"
    return "python", f"test_suite_{framework}.py"


def _scenarios_fingerprint(scenarios: list[GherkinScenario]) -> tuple[str, list[str], int]:
    """
    Deterministic fingerprint of the Gherkin inputs.
    Returns (sha256_hex, sorted_scenario_ids, count).
    Sorting by id makes the hash insensitive to row order.
    """
    pairs = sorted(
        ((str(s.id), s.gherkin_text or "") for s in scenarios),
        key=lambda p: p[0],
    )
    h = hashlib.sha256()
    for sid, text in pairs:
        h.update(sid.encode())
        h.update(b"\x00")
        h.update(text.encode())
        h.update(b"\x00")
    return h.hexdigest(), [sid for sid, _ in pairs], len(pairs)


def _suite_out(s: TestSuite, current_hash: str) -> TestSuiteOut:
    return TestSuiteOut(
        id=str(s.id),
        project_id=str(s.project_id),
        framework=s.framework,
        language=s.language,
        filename=s.filename,
        code=s.code,
        mode=s.mode,
        url=s.url,
        llm_model=s.llm_model,
        source_scenarios_hash=s.source_scenarios_hash,
        source_scenario_count=s.source_scenario_count,
        is_stale=s.source_scenarios_hash != current_hash,
        updated_at=s.updated_at.isoformat() if s.updated_at else None,
    )


@router.post("/code/generate", response_model=list[TestSuiteOut])
async def generate_code(
    body: CodeGenRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Generate executable test code from the project's Gherkin scenarios and
    upsert one TestSuite row per framework. Idempotent per (project, framework).
    """
    result = await db.execute(
        select(GherkinScenario).where(GherkinScenario.project_id == body.project_id)
    )
    scenarios = result.scalars().all()

    if not scenarios:
        raise HTTPException(status_code=404, detail="No Gherkin scenarios found for this project.")

    gherkin_texts = [s.gherkin_text for s in scenarios if s.gherkin_text]
    if not gherkin_texts:
        raise HTTPException(status_code=400, detail="Gherkin scenarios are empty.")

    current_hash, scenario_ids, scenario_count = _scenarios_fingerprint(scenarios)

    saved: list[TestSuite] = []
    for framework in body.frameworks:
        try:
            generated_code = await generate_test_suite(
                gherkin_texts=gherkin_texts,
                url=body.url,
                mode=body.mode,
                framework=framework,
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to generate code for {framework}: {str(e)}")

        if not generated_code:
            raise HTTPException(status_code=500, detail=f"Failed to generate code for {framework}: LLM returned None")

        language, filename = _framework_meta(framework)

        existing_q = await db.execute(
            select(TestSuite).where(
                TestSuite.project_id == body.project_id,
                TestSuite.framework == framework,
            )
        )
        existing = existing_q.scalar_one_or_none()

        if existing:
            existing.code = generated_code
            existing.language = language
            existing.filename = filename
            existing.mode = body.mode
            existing.url = body.url
            existing.source_scenarios_hash = current_hash
            existing.source_scenario_ids = scenario_ids
            existing.source_scenario_count = scenario_count
            db.add(existing)
            saved.append(existing)
        else:
            suite = TestSuite(
                id=uuid.uuid4(),
                project_id=body.project_id,
                framework=framework,
                language=language,
                filename=filename,
                code=generated_code,
                mode=body.mode,
                url=body.url,
                source_scenarios_hash=current_hash,
                source_scenario_ids=scenario_ids,
                source_scenario_count=scenario_count,
            )
            db.add(suite)
            saved.append(suite)

    await db.commit()
    for s in saved:
        await db.refresh(s)

    return [_suite_out(s, current_hash) for s in saved]


@router.get("/code/suites", response_model=list[TestSuiteOut])
async def list_test_suites(
    project_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Load persisted test suites for a project — no LLM calls.
    Each suite carries an `is_stale` flag set when the project's current
    Gherkin scenarios no longer match the inputs that produced the suite.
    """
    suites_q = await db.execute(
        select(TestSuite)
        .where(TestSuite.project_id == project_id)
        .order_by(TestSuite.framework.asc())
    )
    suites = suites_q.scalars().all()

    if not suites:
        return []

    scenarios_q = await db.execute(
        select(GherkinScenario).where(GherkinScenario.project_id == project_id)
    )
    current_hash, _, _ = _scenarios_fingerprint(scenarios_q.scalars().all())

    return [_suite_out(s, current_hash) for s in suites]


@router.put("/code/suites/{suite_id}", response_model=TestSuiteOut)
async def update_test_suite_code(
    suite_id: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
):
    """Persist QA edits to a suite's code without regenerating."""
    new_code = body.get("code")
    if not isinstance(new_code, str):
        raise HTTPException(status_code=400, detail="`code` (string) is required")

    result = await db.execute(select(TestSuite).where(TestSuite.id == suite_id))
    suite = result.scalar_one_or_none()
    if not suite:
        raise HTTPException(status_code=404, detail="Test suite not found")

    suite.code = new_code
    db.add(suite)
    await db.commit()
    await db.refresh(suite)

    scenarios_q = await db.execute(
        select(GherkinScenario).where(GherkinScenario.project_id == suite.project_id)
    )
    current_hash, _, _ = _scenarios_fingerprint(scenarios_q.scalars().all())
    return _suite_out(suite, current_hash)


# ─── DOM crawler endpoints ────────────────────────────────────────────────────

class ProbeRequest(BaseModel):
    url: str


class ProbeResponse(BaseModel):
    ok: bool
    status: int
    title: Optional[str] = None
    error: Optional[str] = None


class DomCrawlRequest(BaseModel):
    project_id: str
    url: str


class DomElementOut(BaseModel):
    id: str
    project_id: str
    url: str
    selector: str
    tag: str
    text: Optional[str] = None
    attributes: dict
    role: str
    source_step: Optional[str] = None
    confidence: Optional[float] = None
    edited_by_qa: bool
    approved: bool
    updated_at: Optional[str] = None

    class Config:
        from_attributes = True


class DomElementUpsertIn(BaseModel):
    project_id: str
    url: str
    selector: str
    tag: str = "DIV"
    text: Optional[str] = None
    attributes: dict = {}
    role: str
    source_step: Optional[str] = "manual"
    confidence: Optional[float] = 1.0


class DomElementUpdateIn(BaseModel):
    selector: Optional[str] = None
    tag: Optional[str] = None
    text: Optional[str] = None
    attributes: Optional[dict] = None
    role: Optional[str] = None
    approved: Optional[bool] = None


class DomCrawlResponse(BaseModel):
    project_id: str
    url: str
    elements: list[DomElementOut]
    logs: list[str]
    extracted_count: int


def _dom_out(d: DomElement) -> DomElementOut:
    return DomElementOut(
        id=str(d.id),
        project_id=str(d.project_id),
        url=d.url,
        selector=d.selector,
        tag=d.tag,
        text=d.text,
        attributes=d.attributes or {},
        role=d.role,
        source_step=d.source_step,
        confidence=d.confidence,
        edited_by_qa=bool(d.edited_by_qa),
        approved=bool(d.approved),
        updated_at=d.updated_at.isoformat() if d.updated_at else None,
    )


@router.post("/dom/probe", response_model=ProbeResponse)
async def probe_dom_url(body: ProbeRequest):
    """
    Reachability check used by the wizard's Validate button.
    Plain HTTP GET — no browser, no DB write.
    """
    if not body.url or not body.url.startswith(("http://", "https://")):
        return ProbeResponse(ok=False, status=0, error="URL must start with http:// or https://")
    result = await probe_url(body.url)
    return ProbeResponse(
        ok=result.ok,
        status=result.status,
        title=result.title,
        error=result.error,
    )


@router.post("/dom/crawl", response_model=DomCrawlResponse)
async def crawl_dom(body: DomCrawlRequest, db: AsyncSession = Depends(get_db)):
    """
    Run the Playwright crawler against a URL and persist extracted elements.
    Idempotent per (project_id, url): existing rows for the same page that
    were NOT edited by QA are replaced; edited rows are preserved.
    """
    proj_q = await db.execute(select(Project).where(Project.id == body.project_id))
    if not proj_q.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Project not found")

    if not body.url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="URL must start with http:// or https://")

    try:
        extracted, logs = await crawl_url(body.url)
    except NotImplementedError:
        raise HTTPException(
            status_code=500,
            detail=(
                "Crawler failed: asyncio subprocess unsupported on this event loop. "
                "Restart the backend so the Proactor loop policy in app/main.py takes effect."
            ),
        )
    except Exception as e:
        msg = str(e).strip() or repr(e)
        raise HTTPException(status_code=500, detail=f"Crawler failed: {type(e).__name__}: {msg}")

    # Drop only auto-generated rows for this (project, url) so QA edits survive a re-crawl.
    await db.execute(
        delete(DomElement).where(
            DomElement.project_id == body.project_id,
            DomElement.url == body.url,
            DomElement.edited_by_qa == False,  # noqa: E712
        )
    )

    # Existing edited rows hold their roles — skip those role names so we don't
    # collide on the unique (project, url, role) constraint.
    edited_q = await db.execute(
        select(DomElement.role).where(
            DomElement.project_id == body.project_id,
            DomElement.url == body.url,
            DomElement.edited_by_qa == True,  # noqa: E712
        )
    )
    reserved = {r for (r,) in edited_q.all()}

    saved: list[DomElement] = []
    for el in extracted:
        if el.role in reserved:
            continue
        row = DomElement(
            id=uuid.uuid4(),
            project_id=body.project_id,
            url=body.url,
            selector=el.selector,
            tag=el.tag,
            text=el.text,
            attributes=el.attributes,
            role=el.role,
            source_step=el.source_step,
            confidence=el.confidence,
        )
        db.add(row)
        saved.append(row)

    await db.commit()
    for r in saved:
        await db.refresh(r)

    # Return the full current set (saved + preserved edits) sorted by role
    full_q = await db.execute(
        select(DomElement)
        .where(DomElement.project_id == body.project_id, DomElement.url == body.url)
        .order_by(DomElement.role.asc())
    )
    full = full_q.scalars().all()

    return DomCrawlResponse(
        project_id=body.project_id,
        url=body.url,
        elements=[_dom_out(d) for d in full],
        logs=logs,
        extracted_count=len(extracted),
    )


@router.get("/dom/elements", response_model=list[DomElementOut])
async def list_dom_elements(
    project_id: str,
    url: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """List DOM elements for a project, optionally filtered to a single URL."""
    stmt = select(DomElement).where(DomElement.project_id == project_id)
    if url:
        stmt = stmt.where(DomElement.url == url)
    stmt = stmt.order_by(DomElement.url.asc(), DomElement.role.asc())
    result = await db.execute(stmt)
    return [_dom_out(d) for d in result.scalars().all()]


@router.post("/dom/elements", response_model=DomElementOut)
async def add_dom_element(body: DomElementUpsertIn, db: AsyncSession = Depends(get_db)):
    """
    Manually add (or upsert by role) a DOM element. Marked edited_by_qa=True so
    re-crawling won't overwrite it.
    """
    proj_q = await db.execute(select(Project).where(Project.id == body.project_id))
    if not proj_q.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Project not found")

    existing_q = await db.execute(
        select(DomElement).where(
            DomElement.project_id == body.project_id,
            DomElement.url == body.url,
            DomElement.role == body.role,
        )
    )
    existing = existing_q.scalar_one_or_none()

    if existing:
        existing.selector = body.selector
        existing.tag = body.tag
        existing.text = body.text
        existing.attributes = body.attributes or {}
        existing.source_step = body.source_step
        existing.confidence = body.confidence
        existing.edited_by_qa = True
        db.add(existing)
        await db.commit()
        await db.refresh(existing)
        return _dom_out(existing)

    row = DomElement(
        id=uuid.uuid4(),
        project_id=body.project_id,
        url=body.url,
        selector=body.selector,
        tag=body.tag,
        text=body.text,
        attributes=body.attributes or {},
        role=body.role,
        source_step=body.source_step,
        confidence=body.confidence,
        edited_by_qa=True,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return _dom_out(row)


@router.put("/dom/elements/{element_id}", response_model=DomElementOut)
async def update_dom_element(
    element_id: str,
    body: DomElementUpdateIn,
    db: AsyncSession = Depends(get_db),
):
    """Edit one DOM element. Always sets edited_by_qa=True."""
    result = await db.execute(select(DomElement).where(DomElement.id == element_id))
    el = result.scalar_one_or_none()
    if not el:
        raise HTTPException(status_code=404, detail="DOM element not found")

    if body.selector is not None:
        el.selector = body.selector
    if body.tag is not None:
        el.tag = body.tag
    if body.text is not None:
        el.text = body.text
    if body.attributes is not None:
        el.attributes = body.attributes
    if body.role is not None:
        el.role = body.role
    if body.approved is not None:
        el.approved = body.approved
    el.edited_by_qa = True

    db.add(el)
    await db.commit()
    await db.refresh(el)
    return _dom_out(el)


@router.delete("/dom/elements/{element_id}", status_code=204)
async def delete_dom_element(element_id: str, db: AsyncSession = Depends(get_db)):
    """Delete one DOM element."""
    result = await db.execute(select(DomElement).where(DomElement.id == element_id))
    el = result.scalar_one_or_none()
    if not el:
        raise HTTPException(status_code=404, detail="DOM element not found")
    await db.execute(delete(DomElement).where(DomElement.id == element_id))
    await db.commit()
