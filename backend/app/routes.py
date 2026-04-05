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
import json
import uuid

from app.database import get_db
from app.models import Project, UserStory, GherkinScenario, Priority, Status
from app.gherkin.generator import generate_gherkin

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
