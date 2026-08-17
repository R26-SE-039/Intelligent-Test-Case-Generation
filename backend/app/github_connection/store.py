"""
DB-backed lookup for the active GitHub connection of a project.

`load_connection(project_id)` returns a ConnectionRecord with the decrypted
token, or None if no connection exists. The runner uses this at execute
time to pick GH vs local mode.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models import ProjectGitHubConnection

from .crypto import decrypt_token

logger = logging.getLogger(__name__)


@dataclass
class ConnectionRecord:
    project_id: str
    token: str               # decrypted PAT — keep in memory only
    owner: str
    repo: str
    default_branch: str
    workflow_installed: bool

    @property
    def repo_full(self) -> str:
        return f"{self.owner}/{self.repo}"


async def load_connection(project_id: str) -> Optional[ConnectionRecord]:
    """Read + decrypt the connection. Returns None if not configured."""
    async with AsyncSessionLocal() as db:
        q = await db.execute(
            select(ProjectGitHubConnection).where(
                ProjectGitHubConnection.project_id == project_id
            )
        )
        row = q.scalar_one_or_none()
        if not row:
            return None
        try:
            token = decrypt_token(row.encrypted_token)
        except RuntimeError as e:
            logger.warning("Failed to decrypt token for project %s: %s", project_id, e)
            return None
        return ConnectionRecord(
            project_id=str(row.project_id),
            token=token,
            owner=row.owner,
            repo=row.repo,
            default_branch=row.default_branch,
            workflow_installed=row.workflow_installed_at is not None,
        )
