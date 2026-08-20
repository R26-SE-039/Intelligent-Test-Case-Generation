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
from sqlalchemy import select, delete, func as sa_func, update
from pydantic import BaseModel
from typing import Literal, Optional
import hashlib
import json
import re
import uuid

from app.database import get_db
from app.models import Project, UserStory, GherkinScenario, TestSuite, DomElement, Priority, Status
from app.gherkin.generator import generate_gherkin
from app.code_gen.generator import generate_test_suite
from app.dom_crawler import crawl_url, probe_url, build_auth_plan, AuthPlan, log_broker
from app.ml.predict import predict_for_project

router = APIRouter(prefix="/api/v1", tags=["pipeline"])


# ─── Pydantic schemas ─────────────────────────────────────────────────────────

class ProjectIn(BaseModel):
    name: str
    description: Optional[str] = None
    # Optional client-supplied UUID. The merged NextGenQA frontend passes the
    # auth-service project id here so both services share one project id.
    id: Optional[uuid.UUID] = None
    # Auth-service organization UUID (reference only — auth owns orgs).
    organization_id: Optional[uuid.UUID] = None


class ProjectOut(BaseModel):
    id: str
    name: str
    description: Optional[str]
    organization_id: Optional[str] = None
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
    # Auth-service iteration UUID, set when importing from C1.
    iteration_id: Optional[uuid.UUID] = None


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
    iteration_id: Optional[str] = None

    class Config:
        from_attributes = True


class GenerateRequest(BaseModel):
    story_ids: list[str]
    project_id: str
    scenario_mode: Literal["lean", "full"] = "lean"


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
        iteration_id=str(s.iteration_id) if s.iteration_id else None,
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
    """Create a new project (blank workspace).

    When `id` is supplied the call is a get-or-create: an existing project with
    that id is returned as-is, so external services (the auth service) can keep
    a single shared project id without a mapping table.
    """
    if body.id is not None:
        existing = await db.get(Project, body.id)
        if existing:
            # Backfill the org reference on projects created before the
            # auth-flow alignment migration.
            if body.organization_id and existing.organization_id != body.organization_id:
                existing.organization_id = body.organization_id
                db.add(existing)
                await db.commit()
                await db.refresh(existing)
            return ProjectOut(
                id=str(existing.id),
                name=existing.name,
                description=existing.description,
                organization_id=str(existing.organization_id) if existing.organization_id else None,
                created_at=existing.created_at.isoformat() if existing.created_at else None,
            )

    # Check name uniqueness
    result = await db.execute(select(Project).where(Project.name == body.name))
    conflicting = result.scalar_one_or_none()
    if conflicting is not None:
        if body.id is None:
            raise HTTPException(status_code=409, detail=f"Project '{body.name}' already exists")
        # id is the real key for bridged projects — dedupe the display name
        # instead of failing so get-or-create stays idempotent.
        body.name = f"{body.name} ({str(body.id)[:8]})"

    project = Project(
        id=body.id or uuid.uuid4(),
        name=body.name,
        description=body.description,
        organization_id=body.organization_id,
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)

    return ProjectOut(
        id=str(project.id),
        name=project.name,
        description=project.description,
        organization_id=str(project.organization_id) if project.organization_id else None,
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
            organization_id=str(p.organization_id) if p.organization_id else None,
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
async def list_stories(
    project_id: str,
    iteration_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """List all user stories for a project, optionally scoped to one iteration."""
    query = select(UserStory).where(UserStory.project_id == project_id)
    if iteration_id:
        query = query.where(UserStory.iteration_id == iteration_id)
    result = await db.execute(query.order_by(UserStory.created_at.asc()))
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
            existing.iteration_id = s.iteration_id
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
                iteration_id=s.iteration_id,
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
        existing.iteration_id = story.iteration_id
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
        iteration_id=story.iteration_id,
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

        gherkin_text, generator_name = await generate_gherkin(
            story_dict,
            body.scenario_mode,
        )

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
    scenario_mode: Literal["lean", "full"] = "lean",
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

    gherkin_text, generator_name = await generate_gherkin(story_dict, scenario_mode)

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
    version: int
    is_active: bool
    selected_for_run: bool
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
    scenario_block_count = 0
    for _, text in pairs:
        scenario_block_count += len(
            re.findall(r"^\s*Scenario(?: Outline)?:\s*.+$", text or "", flags=re.M)
        )
    count = scenario_block_count if scenario_block_count > 0 else len(pairs)
    return h.hexdigest(), [sid for sid, _ in pairs], count


def _dom_elements_fingerprint(elements: list[DomElement]) -> str:
    """
    Deterministic fingerprint of (role, selector) tuples for the elements
    actually used during code generation. Combined with the scenarios hash so
    the Code Review staleness banner fires when QA edits selectors too.
    """
    pairs = sorted(((e.role, e.selector or "") for e in elements), key=lambda p: p[0])
    h = hashlib.sha256()
    for role, sel in pairs:
        h.update(role.encode())
        h.update(b"\x00")
        h.update(sel.encode())
        h.update(b"\x00")
    return h.hexdigest()


def _combined_inputs_hash(scenarios_hash: str, dom_hash: str) -> str:
    """One hash that covers both Gherkin scenarios and DOM elements."""
    return hashlib.sha256(f"{scenarios_hash}:{dom_hash}".encode()).hexdigest()


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
        version=s.version,
        is_active=s.is_active,
        selected_for_run=s.selected_for_run,
        updated_at=s.updated_at.isoformat() if s.updated_at else None,
    )


async def _current_combined_hash(db: AsyncSession, project_id: str, url: str) -> str:
    """
    Compute the combined fingerprint of the inputs that would be used to
    regenerate test code right now. Used by both POST /code/generate (to store
    in the new suite row) and GET /code/suites (to mark older rows stale).
    """
    sc_q = await db.execute(
        select(GherkinScenario).where(
            GherkinScenario.project_id == project_id,
            GherkinScenario.approved.is_(True),
        )
    )
    scenarios_hash, _, _ = _scenarios_fingerprint(sc_q.scalars().all())

    el_q = await db.execute(
        select(DomElement).where(
            DomElement.project_id == project_id,
            DomElement.url == url,
        )
    )
    dom_hash = _dom_elements_fingerprint(el_q.scalars().all())

    return _combined_inputs_hash(scenarios_hash, dom_hash)


@router.post("/code/generate", response_model=list[TestSuiteOut])
async def generate_code(
    body: CodeGenRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Generate executable test code from the project's Gherkin scenarios +
    crawled DOM elements. Each framework gets a *new* TestSuite row at
    version+1 — the prior head of that chain is deactivated but kept on disk
    so the QA can restore it from the dedicated editor's version dropdown.
    """
    result = await db.execute(
        select(GherkinScenario).where(
            GherkinScenario.project_id == body.project_id,
            GherkinScenario.approved.is_(True),
        )
    )
    scenarios = result.scalars().all()

    if not scenarios:
        raise HTTPException(status_code=404, detail="No approved Gherkin scenarios found for this project.")

    gherkin_texts = [s.gherkin_text for s in scenarios if s.gherkin_text]
    if not gherkin_texts:
        raise HTTPException(status_code=400, detail="Gherkin scenarios are empty.")

    scenarios_hash, scenario_ids, scenario_count = _scenarios_fingerprint(scenarios)

    # Pull DOM elements for this URL (Mode B). All extracted elements feed the
    # LLM — `approved` is a QA quality marker, not a filter, so partial approval
    # doesn't silently drop the unapproved ones.
    elements: list[DomElement] = []
    dom_payload: list[dict] = []
    if body.mode == "dom":
        el_q = await db.execute(
            select(DomElement)
            .where(DomElement.project_id == body.project_id, DomElement.url == body.url)
            .order_by(DomElement.role.asc())
        )
        elements = list(el_q.scalars().all())
        dom_payload = [
            {
                "role": e.role,
                "selector": e.selector,
                "tag": e.tag,
                "text": e.text or "",
            }
            for e in elements
        ]

    dom_hash = _dom_elements_fingerprint(elements)
    combined_hash = _combined_inputs_hash(scenarios_hash, dom_hash)

    # Fan out one LLM call per framework. Wall-clock = max(call_i) instead
    # of sum(call_i); for "Generate All" that's roughly 3x faster.
    import asyncio as _asyncio
    try:
        generated_codes = await _asyncio.gather(
            *(
                generate_test_suite(
                    gherkin_texts=gherkin_texts,
                    url=body.url,
                    mode=body.mode,
                    framework=fw,
                    dom_elements=dom_payload or None,
                )
                for fw in body.frameworks
            ),
            return_exceptions=True,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Code generation failed: {e}")

    saved: list[TestSuite] = []
    for framework, generated_code in zip(body.frameworks, generated_codes):
        if isinstance(generated_code, Exception):
            raise HTTPException(
                status_code=500,
                detail=f"Failed to generate code for {framework}: {generated_code}",
            )
        if not generated_code:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to generate code for {framework}: LLM returned None",
            )

        language, filename = _framework_meta(framework)

        # Mark every prior version of this (project, framework) as inactive.
        # The new row inserted below becomes the head of the chain.
        await db.execute(
            update(TestSuite)
            .where(
                TestSuite.project_id == body.project_id,
                TestSuite.framework == framework,
                TestSuite.is_active == True,  # noqa: E712
            )
            .values(is_active=False, selected_for_run=False)
        )

        next_version_q = await db.execute(
            select(sa_func.coalesce(sa_func.max(TestSuite.version), 0)).where(
                TestSuite.project_id == body.project_id,
                TestSuite.framework == framework,
            )
        )
        next_version = int(next_version_q.scalar() or 0) + 1

        suite = TestSuite(
            id=uuid.uuid4(),
            project_id=body.project_id,
            framework=framework,
            language=language,
            filename=filename,
            code=generated_code,
            mode=body.mode,
            url=body.url,
            source_scenarios_hash=combined_hash,
            source_scenario_ids=scenario_ids,
            source_scenario_count=scenario_count,
            version=next_version,
            is_active=True,
            selected_for_run=False,
        )
        db.add(suite)
        saved.append(suite)

    await db.commit()
    for s in saved:
        await db.refresh(s)

    return [_suite_out(s, combined_hash) for s in saved]


@router.get("/code/suites", response_model=list[TestSuiteOut])
async def list_test_suites(
    project_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Load the active head of each (project, framework) chain — no LLM calls.
    `is_stale` fires when EITHER the Gherkin scenarios OR the crawled DOM
    elements (for the suite's recorded URL) have changed since generation.

    Past versions are accessed via /code/suites/{suite_id}/history.
    """
    suites_q = await db.execute(
        select(TestSuite)
        .where(
            TestSuite.project_id == project_id,
            TestSuite.is_active == True,  # noqa: E712
        )
        .order_by(TestSuite.framework.asc())
    )
    suites = suites_q.scalars().all()

    if not suites:
        return []

    # Cache per-URL hash so we don't re-query DOM elements once per suite when
    # they all share a URL (the common case).
    hash_cache: dict[str, str] = {}
    out: list[TestSuiteOut] = []
    for s in suites:
        if s.url not in hash_cache:
            hash_cache[s.url] = await _current_combined_hash(db, project_id, s.url)
        out.append(_suite_out(s, hash_cache[s.url]))
    return out


@router.get("/code/suites/{suite_id}", response_model=TestSuiteOut)
async def get_test_suite(
    suite_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Fetch one specific suite version (used by the dedicated editor page)."""
    result = await db.execute(select(TestSuite).where(TestSuite.id == suite_id))
    suite = result.scalar_one_or_none()
    if not suite:
        raise HTTPException(status_code=404, detail="Test suite not found")
    current_hash = await _current_combined_hash(db, str(suite.project_id), suite.url)
    return _suite_out(suite, current_hash)


@router.get("/code/suites/{suite_id}/history", response_model=list[TestSuiteOut])
async def get_test_suite_history(
    suite_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Every version of the (project, framework) chain that `suite_id` belongs to,
    newest first. Powers the version dropdown in the dedicated editor.
    """
    anchor_q = await db.execute(select(TestSuite).where(TestSuite.id == suite_id))
    anchor = anchor_q.scalar_one_or_none()
    if not anchor:
        raise HTTPException(status_code=404, detail="Test suite not found")

    rows_q = await db.execute(
        select(TestSuite)
        .where(
            TestSuite.project_id == anchor.project_id,
            TestSuite.framework == anchor.framework,
        )
        .order_by(TestSuite.version.desc())
    )
    rows = rows_q.scalars().all()

    current_hash = await _current_combined_hash(db, str(anchor.project_id), anchor.url)
    return [_suite_out(s, current_hash) for s in rows]


@router.put("/code/suites/{suite_id}", response_model=TestSuiteOut)
async def update_test_suite_code(
    suite_id: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
):
    """
    Autosave QA edits into the active head version. Editing a historical
    (is_active=False) row is rejected — the dedicated editor must "Restore"
    first, which copies that version forward as a new head.
    """
    new_code = body.get("code")
    if not isinstance(new_code, str):
        raise HTTPException(status_code=400, detail="`code` (string) is required")

    result = await db.execute(select(TestSuite).where(TestSuite.id == suite_id))
    suite = result.scalar_one_or_none()
    if not suite:
        raise HTTPException(status_code=404, detail="Test suite not found")
    if not suite.is_active:
        raise HTTPException(
            status_code=409,
            detail="Cannot edit a historical version. Restore it to a new head first.",
        )

    suite.code = new_code
    db.add(suite)
    await db.commit()
    await db.refresh(suite)

    current_hash = await _current_combined_hash(db, str(suite.project_id), suite.url)
    return _suite_out(suite, current_hash)


@router.post("/code/suites/{suite_id}/save-as-new-version", response_model=TestSuiteOut)
async def save_suite_as_new_version(
    suite_id: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
):
    """
    Snapshot the current code into a fresh row at version+1. Used by the
    "Save as new version" button so QA can branch instead of overwriting the
    current head. The new row becomes the active head; the prior head goes
    inactive (its code is preserved as a historical version).
    """
    new_code = body.get("code")
    if not isinstance(new_code, str):
        raise HTTPException(status_code=400, detail="`code` (string) is required")

    anchor_q = await db.execute(select(TestSuite).where(TestSuite.id == suite_id))
    anchor = anchor_q.scalar_one_or_none()
    if not anchor:
        raise HTTPException(status_code=404, detail="Test suite not found")

    # Deactivate the current head of the chain.
    await db.execute(
        update(TestSuite)
        .where(
            TestSuite.project_id == anchor.project_id,
            TestSuite.framework == anchor.framework,
            TestSuite.is_active == True,  # noqa: E712
        )
        .values(is_active=False, selected_for_run=False)
    )

    next_version_q = await db.execute(
        select(sa_func.coalesce(sa_func.max(TestSuite.version), 0)).where(
            TestSuite.project_id == anchor.project_id,
            TestSuite.framework == anchor.framework,
        )
    )
    next_version = int(next_version_q.scalar() or 0) + 1

    new_row = TestSuite(
        id=uuid.uuid4(),
        project_id=anchor.project_id,
        framework=anchor.framework,
        language=anchor.language,
        filename=anchor.filename,
        code=new_code,
        mode=anchor.mode,
        url=anchor.url,
        llm_model=anchor.llm_model,
        source_scenarios_hash=anchor.source_scenarios_hash,
        source_scenario_ids=anchor.source_scenario_ids,
        source_scenario_count=anchor.source_scenario_count,
        version=next_version,
        is_active=True,
        selected_for_run=False,
    )
    db.add(new_row)
    await db.commit()
    await db.refresh(new_row)

    current_hash = await _current_combined_hash(db, str(new_row.project_id), new_row.url)
    return _suite_out(new_row, current_hash)


@router.post("/code/suites/{suite_id}/restore", response_model=TestSuiteOut)
async def restore_suite_version(
    suite_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Restore an old version by copying its code into a brand-new head row
    (version = max+1). The historical row is left in place; the prior head
    is deactivated. This keeps history strictly append-only.
    """
    anchor_q = await db.execute(select(TestSuite).where(TestSuite.id == suite_id))
    anchor = anchor_q.scalar_one_or_none()
    if not anchor:
        raise HTTPException(status_code=404, detail="Test suite not found")

    await db.execute(
        update(TestSuite)
        .where(
            TestSuite.project_id == anchor.project_id,
            TestSuite.framework == anchor.framework,
            TestSuite.is_active == True,  # noqa: E712
        )
        .values(is_active=False, selected_for_run=False)
    )

    next_version_q = await db.execute(
        select(sa_func.coalesce(sa_func.max(TestSuite.version), 0)).where(
            TestSuite.project_id == anchor.project_id,
            TestSuite.framework == anchor.framework,
        )
    )
    next_version = int(next_version_q.scalar() or 0) + 1

    restored = TestSuite(
        id=uuid.uuid4(),
        project_id=anchor.project_id,
        framework=anchor.framework,
        language=anchor.language,
        filename=anchor.filename,
        code=anchor.code,
        mode=anchor.mode,
        url=anchor.url,
        llm_model=anchor.llm_model,
        source_scenarios_hash=anchor.source_scenarios_hash,
        source_scenario_ids=anchor.source_scenario_ids,
        source_scenario_count=anchor.source_scenario_count,
        version=next_version,
        is_active=True,
        selected_for_run=False,
    )
    db.add(restored)
    await db.commit()
    await db.refresh(restored)

    current_hash = await _current_combined_hash(db, str(restored.project_id), restored.url)
    return _suite_out(restored, current_hash)


@router.post("/code/suites/{suite_id}/select-for-run", response_model=TestSuiteOut)
async def select_suite_for_run(
    suite_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Mark this suite as the one CI/CD should execute. Only one suite per
    project carries the flag — selecting a new one clears every other suite
    in the same project. Only the active head of a framework chain can be
    selected (older versions must be restored first).
    """
    anchor_q = await db.execute(select(TestSuite).where(TestSuite.id == suite_id))
    anchor = anchor_q.scalar_one_or_none()
    if not anchor:
        raise HTTPException(status_code=404, detail="Test suite not found")
    if not anchor.is_active:
        raise HTTPException(
            status_code=409,
            detail="Only the active version of a framework can be selected for a run.",
        )

    # Clear every other suite in the project first, then mark this one.
    await db.execute(
        update(TestSuite)
        .where(
            TestSuite.project_id == anchor.project_id,
            TestSuite.id != anchor.id,
        )
        .values(selected_for_run=False)
    )
    anchor.selected_for_run = True
    db.add(anchor)
    await db.commit()
    await db.refresh(anchor)

    current_hash = await _current_combined_hash(db, str(anchor.project_id), anchor.url)
    return _suite_out(anchor, current_hash)


# ─── DOM crawler endpoints ────────────────────────────────────────────────────

class ProbeRequest(BaseModel):
    url: str


class ProbeResponse(BaseModel):
    ok: bool
    status: int
    title: Optional[str] = None
    error: Optional[str] = None


class ManualAuthConfig(BaseModel):
    """Phase 6 fallback: explicit selectors + creds when Background can't drive login."""
    login_url: Optional[str] = None
    username_selector: Optional[str] = None
    username_value: Optional[str] = None
    password_selector: Optional[str] = None
    password_value: Optional[str] = None
    submit_selector: Optional[str] = None


class DomCrawlRequest(BaseModel):
    project_id: str
    url: str
    auth_strategy: str = "background"     # background | none | manual | storage_state
    manual_auth: Optional[ManualAuthConfig] = None
    storage_state: Optional[dict] = None  # Playwright storageState JSON
    run_id: Optional[str] = None          # frontend-supplied; matches /ws/dom/crawl/{id} subscriber


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
    auth_strategy_used: str = "none"
    auth_steps_replayed: int = 0
    unmatched_background_steps: list[str] = []


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


def _manual_auth_to_plan(cfg: ManualAuthConfig) -> AuthPlan:
    """
    Translate the Phase-6 manual auth form into the same Action sequence the
    Background parser produces, so the crawler's replay loop is unchanged.

    Empty selectors fall back to the generic universal locators used by the
    Background path — so the user can supply just username + password values
    and the crawler will find the form fields itself.
    """
    from app.dom_crawler.auth import (
        Action, USERNAME_LOCATOR, PASSWORD_LOCATOR, LOGIN_BUTTON_LOCATOR,
    )
    actions: list = []
    if cfg.login_url:
        actions.append(Action("goto", cfg.login_url, None, f"goto {cfg.login_url}"))
    if cfg.username_value:
        sel = (cfg.username_selector or "").strip() or USERNAME_LOCATOR
        actions.append(Action(
            "fill", sel, cfg.username_value,
            f"fill username '{cfg.username_value}'",
        ))
    if cfg.password_value:
        sel = (cfg.password_selector or "").strip() or PASSWORD_LOCATOR
        actions.append(Action("fill", sel, cfg.password_value, "fill password"))
    sub_sel = (cfg.submit_selector or "").strip() or LOGIN_BUTTON_LOCATOR
    actions.append(Action("click", sub_sel, None, "click submit"))
    plan = AuthPlan()
    plan.actions = actions
    plan.raw_steps = [a.description for a in actions]
    return plan


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

    # Assemble the auth strategy.
    auth_plan: Optional[AuthPlan] = None
    storage_state = None
    strategy_used = body.auth_strategy

    if body.auth_strategy == "background":
        sc_q = await db.execute(
            select(GherkinScenario).where(GherkinScenario.project_id == body.project_id)
        )
        gherkin_texts = [s.gherkin_text for s in sc_q.scalars().all() if s.gherkin_text]
        plan = build_auth_plan(gherkin_texts)
        if not plan.is_empty:
            auth_plan = plan
        else:
            strategy_used = "none"  # no Background found
    elif body.auth_strategy == "manual":
        if not body.manual_auth:
            raise HTTPException(status_code=400, detail="manual_auth config is required for strategy 'manual'")
        auth_plan = _manual_auth_to_plan(body.manual_auth)
    elif body.auth_strategy == "storage_state":
        if not body.storage_state:
            raise HTTPException(status_code=400, detail="storage_state JSON is required for strategy 'storage_state'")
        storage_state = body.storage_state
    elif body.auth_strategy == "none":
        pass
    else:
        raise HTTPException(status_code=400, detail=f"Unknown auth_strategy '{body.auth_strategy}'")

    try:
        extracted, logs = await crawl_url(
            body.url,
            auth_plan=auth_plan,
            storage_state=storage_state,
            run_id=body.run_id,
        )
    except NotImplementedError:
        if body.run_id:
            log_broker.close(body.run_id)
        raise HTTPException(
            status_code=500,
            detail=(
                "Crawler failed: asyncio subprocess unsupported on this event loop. "
                "Restart the backend so the Proactor loop policy in app/main.py takes effect."
            ),
        )
    except Exception as e:
        if body.run_id:
            log_broker.close(body.run_id)
        msg = str(e).strip() or repr(e)
        raise HTTPException(status_code=500, detail=f"Crawler failed: {type(e).__name__}: {msg}")
    finally:
        # Sentinel — tells the WS subscriber the run is over so it can close cleanly.
        if body.run_id:
            log_broker.close(body.run_id)

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
        auth_strategy_used=strategy_used,
        auth_steps_replayed=len(auth_plan.actions) if auth_plan else 0,
        unmatched_background_steps=auth_plan.unmatched_steps if auth_plan else [],
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


class BulkApproveIn(BaseModel):
    project_id: str
    url: Optional[str] = None
    approved: bool = True


@router.post("/dom/elements/bulk-approve", response_model=list[DomElementOut])
async def bulk_approve_dom_elements(
    body: BulkApproveIn,
    db: AsyncSession = Depends(get_db),
):
    """Toggle approval for every element in a project (optionally scoped to a URL)."""
    stmt = select(DomElement).where(DomElement.project_id == body.project_id)
    if body.url:
        stmt = stmt.where(DomElement.url == body.url)
    result = await db.execute(stmt.order_by(DomElement.role.asc()))
    rows = result.scalars().all()
    for r in rows:
        r.approved = body.approved
        db.add(r)
    await db.commit()
    for r in rows:
        await db.refresh(r)
    return [_dom_out(r) for r in rows]


# ─── ML Risk Prediction endpoint ──────────────────────────────────────────────

class RiskPrediction(BaseModel):
    flow: str
    label: str
    risk: str
    confidence: float
    probabilities: dict[str, float]
    features: dict[str, float]


class RiskResponse(BaseModel):
    project_id: str
    source: str                        # "model" | "heuristic"
    model_classes: list[str]
    feature_columns: list[str]
    predictions: list[RiskPrediction]


@router.get("/projects/{project_id}/risk", response_model=RiskResponse)
async def get_risk_predictions(
    project_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Score the four flow buckets (Login, Cart, Checkout, Search) for this
    project. Uses the trained RandomForest if `app/ml/data/model.pkl` exists;
    otherwise falls back to a deterministic heuristic so the UI keeps working
    before the model has been trained for the first time.
    """
    proj_q = await db.execute(select(Project).where(Project.id == project_id))
    if not proj_q.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Project not found")

    result = await predict_for_project(db, project_id)
    return RiskResponse(project_id=project_id, **result)
