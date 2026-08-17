"""
REST endpoints driving the dashboard's "Connect this project to GitHub" flow.

POST  /api/v1/github/validate                         — verify a PAT, return user + repos
GET   /api/v1/projects/{pid}/github/connection        — current connection (or 404)
POST  /api/v1/projects/{pid}/github/connect           — save token + repo, install workflow
POST  /api/v1/projects/{pid}/github/reinstall-workflow — re-PUT the YAML (used after conflict)
POST  /api/v1/projects/{pid}/github/test-ping         — smoke check using the stored token
DELETE /api/v1/projects/{pid}/github/connection       — disconnect (deletes row)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Project, ProjectGitHubConnection

from .crypto import decrypt_token, encrypt_token, mask_token
from .workflow_installer import (
    GITHUB_API,
    install_workflow,
    InstallResult,
    WORKFLOW_PATH,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["github-connection"])


# ─── Pydantic ────────────────────────────────────────────────────────────────


class ValidateRequest(BaseModel):
    token: str = Field(..., min_length=10)


class GitHubRepoOut(BaseModel):
    full_name: str
    name: str
    owner: str
    default_branch: str
    private: bool
    html_url: str


class ValidateResponse(BaseModel):
    login: str
    name: Optional[str]
    avatar_url: Optional[str]
    repos: list[GitHubRepoOut]
    repo_count: int


class ConnectRequest(BaseModel):
    token: str = Field(..., min_length=10)
    owner: str
    repo: str
    default_branch: str = "main"
    force_workflow_overwrite: bool = False


class ConnectionOut(BaseModel):
    project_id: str
    owner: str
    repo: str
    repo_full: str
    default_branch: str
    token_preview: str
    github_user_login: Optional[str]
    github_user_avatar_url: Optional[str]
    workflow_installed: bool
    workflow_installed_at: Optional[str]
    last_validated_at: Optional[str]
    updated_at: Optional[str]


class ConnectResponse(BaseModel):
    connection: ConnectionOut
    workflow_status: str           # installed | already_present | conflict
    workflow_message: str


class PingResponse(BaseModel):
    ok: bool
    login: Optional[str] = None
    rate_limit_remaining: Optional[int] = None
    workflow_present: bool = False
    detail: Optional[str] = None


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _connection_out(row: ProjectGitHubConnection) -> ConnectionOut:
    return ConnectionOut(
        project_id=str(row.project_id),
        owner=row.owner,
        repo=row.repo,
        repo_full=f"{row.owner}/{row.repo}",
        default_branch=row.default_branch,
        token_preview=row.token_preview,
        github_user_login=row.github_user_login,
        github_user_avatar_url=row.github_user_avatar_url,
        workflow_installed=row.workflow_installed_at is not None,
        workflow_installed_at=row.workflow_installed_at.isoformat() if row.workflow_installed_at else None,
        last_validated_at=row.last_validated_at.isoformat() if row.last_validated_at else None,
        updated_at=row.updated_at.isoformat() if row.updated_at else None,
    )


async def _ensure_project(db: AsyncSession, project_id: str) -> None:
    q = await db.execute(select(Project).where(Project.id == project_id))
    if not q.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Project not found")


# ─── Endpoints ───────────────────────────────────────────────────────────────


@router.post("/github/validate", response_model=ValidateResponse)
async def validate_token(body: ValidateRequest):
    """
    Step 1 of the connect flow. Verifies the PAT by calling GET /user and
    GET /user/repos. Returns the user identity + owned repos so the UI can
    populate the repo dropdown.

    The token is not persisted here — only the user's choice from the next
    screen is. If validation fails (401), we surface the message verbatim
    so the user knows why (expired token, missing scopes, etc).
    """
    async with httpx.AsyncClient(headers=_headers(body.token), timeout=20.0) as client:
        user_resp = await client.get(f"{GITHUB_API}/user")
        if user_resp.status_code == 401:
            raise HTTPException(
                status_code=400,
                detail="Token rejected by GitHub (401). Check that it hasn't expired and has the `repo` + `workflow` scopes.",
            )
        user_resp.raise_for_status()
        user = user_resp.json()

        # Fetch up to 100 repos the user can push to (owner + collaborator
        # so org repos show up too). UI displays them; user picks one.
        repos: list[GitHubRepoOut] = []
        repos_resp = await client.get(
            f"{GITHUB_API}/user/repos",
            params={"affiliation": "owner,collaborator", "per_page": 100, "sort": "updated"},
        )
        repos_resp.raise_for_status()
        for r in repos_resp.json():
            repos.append(GitHubRepoOut(
                full_name=r["full_name"],
                name=r["name"],
                owner=r["owner"]["login"],
                default_branch=r.get("default_branch") or "main",
                private=r.get("private", False),
                html_url=r["html_url"],
            ))

    return ValidateResponse(
        login=user["login"],
        name=user.get("name"),
        avatar_url=user.get("avatar_url"),
        repos=repos,
        repo_count=len(repos),
    )


@router.get(
    "/projects/{project_id}/github/connection",
    response_model=Optional[ConnectionOut],
)
async def get_connection(project_id: str, db: AsyncSession = Depends(get_db)):
    """Return the project's saved connection metadata, or null if none."""
    await _ensure_project(db, project_id)
    q = await db.execute(
        select(ProjectGitHubConnection).where(ProjectGitHubConnection.project_id == project_id)
    )
    row = q.scalar_one_or_none()
    return _connection_out(row) if row else None


@router.post("/projects/{project_id}/github/connect", response_model=ConnectResponse)
async def connect_project(
    project_id: str,
    body: ConnectRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Step 2 of the connect flow. Persists the encrypted token + chosen repo,
    then installs the workflow file on the default branch. If the workflow
    already exists with different content and `force_workflow_overwrite`
    is false, returns the connection but with workflow_status='conflict' so
    the UI can prompt the user to confirm overwrite.
    """
    await _ensure_project(db, project_id)

    # Re-fetch user info — gives us avatar + canonical login to display, and
    # validates the token at connect-time (catches the "user pasted a stale
    # token between Validate and Connect" race).
    async with httpx.AsyncClient(headers=_headers(body.token), timeout=20.0) as client:
        user_resp = await client.get(f"{GITHUB_API}/user")
        if user_resp.status_code == 401:
            raise HTTPException(status_code=400, detail="Token rejected by GitHub (401).")
        user_resp.raise_for_status()
        user = user_resp.json()

    install: InstallResult
    try:
        install = await install_workflow(
            token=body.token,
            owner=body.owner,
            repo=body.repo,
            branch=body.default_branch,
            force=body.force_workflow_overwrite,
        )
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Workflow install failed: HTTP {e.response.status_code} — {e.response.text[:200]}",
        )

    encrypted = encrypt_token(body.token)
    preview = mask_token(body.token)
    now = datetime.now(timezone.utc)

    existing_q = await db.execute(
        select(ProjectGitHubConnection).where(ProjectGitHubConnection.project_id == project_id)
    )
    existing = existing_q.scalar_one_or_none()

    if existing:
        existing.encrypted_token = encrypted
        existing.token_preview = preview
        existing.owner = body.owner
        existing.repo = body.repo
        existing.default_branch = body.default_branch
        existing.github_user_login = user.get("login")
        existing.github_user_avatar_url = user.get("avatar_url")
        existing.last_validated_at = now
        if install.status in ("installed", "already_present"):
            existing.workflow_installed_at = now
        row = existing
    else:
        row = ProjectGitHubConnection(
            project_id=project_id,
            encrypted_token=encrypted,
            token_preview=preview,
            owner=body.owner,
            repo=body.repo,
            default_branch=body.default_branch,
            github_user_login=user.get("login"),
            github_user_avatar_url=user.get("avatar_url"),
            last_validated_at=now,
            workflow_installed_at=now if install.status in ("installed", "already_present") else None,
        )
        db.add(row)

    await db.commit()
    await db.refresh(row)

    return ConnectResponse(
        connection=_connection_out(row),
        workflow_status=install.status,
        workflow_message=install.message,
    )


@router.post(
    "/projects/{project_id}/github/reinstall-workflow",
    response_model=ConnectResponse,
)
async def reinstall_workflow(
    project_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Force-reinstall the workflow YAML (used after a 'conflict' result)."""
    await _ensure_project(db, project_id)
    q = await db.execute(
        select(ProjectGitHubConnection).where(ProjectGitHubConnection.project_id == project_id)
    )
    row = q.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="No GitHub connection for this project")

    token = decrypt_token(row.encrypted_token)
    try:
        install = await install_workflow(
            token=token,
            owner=row.owner,
            repo=row.repo,
            branch=row.default_branch,
            force=True,
        )
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Workflow install failed: HTTP {e.response.status_code} — {e.response.text[:200]}",
        )

    row.workflow_installed_at = datetime.now(timezone.utc)
    db.add(row)
    await db.commit()
    await db.refresh(row)

    return ConnectResponse(
        connection=_connection_out(row),
        workflow_status=install.status,
        workflow_message=install.message,
    )


@router.post("/projects/{project_id}/github/test-ping", response_model=PingResponse)
async def test_ping(project_id: str, db: AsyncSession = Depends(get_db)):
    """
    Smoke-test the stored connection without triggering an actual run.
    Calls GET /user (auth), checks the workflow file is still present, and
    reports the rate-limit headroom so the user can confirm everything is
    healthy before a viva.
    """
    await _ensure_project(db, project_id)
    q = await db.execute(
        select(ProjectGitHubConnection).where(ProjectGitHubConnection.project_id == project_id)
    )
    row = q.scalar_one_or_none()
    if not row:
        return PingResponse(ok=False, detail="No GitHub connection for this project")

    try:
        token = decrypt_token(row.encrypted_token)
    except RuntimeError as e:
        return PingResponse(ok=False, detail=str(e))

    async with httpx.AsyncClient(headers=_headers(token), timeout=15.0) as client:
        user_resp = await client.get(f"{GITHUB_API}/user")
        if user_resp.status_code == 401:
            return PingResponse(ok=False, detail="Token rejected (401). It may have expired — reconnect.")
        user_resp.raise_for_status()
        user = user_resp.json()
        rate = user_resp.headers.get("x-ratelimit-remaining")

        wf_resp = await client.get(
            f"{GITHUB_API}/repos/{row.owner}/{row.repo}/contents/{WORKFLOW_PATH}",
            params={"ref": row.default_branch},
        )
        workflow_present = wf_resp.status_code == 200

    row.last_validated_at = datetime.now(timezone.utc)
    db.add(row)
    await db.commit()

    return PingResponse(
        ok=True,
        login=user.get("login"),
        rate_limit_remaining=int(rate) if rate and rate.isdigit() else None,
        workflow_present=workflow_present,
        detail=None if workflow_present else "Connection OK but workflow file is missing — click Reinstall workflow.",
    )


@router.delete("/projects/{project_id}/github/connection", status_code=204)
async def disconnect_project(project_id: str, db: AsyncSession = Depends(get_db)):
    """Remove the project's GitHub connection. The workflow file on the repo
    is left in place — we don't touch the user's repo on disconnect."""
    await _ensure_project(db, project_id)
    await db.execute(
        delete(ProjectGitHubConnection).where(ProjectGitHubConnection.project_id == project_id)
    )
    await db.commit()
