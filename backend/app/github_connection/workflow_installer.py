"""
Idempotent installer for the NextGen QA workflow YAML.

On Connect, the dashboard PUTs the workflow file to
.github/workflows/nextgenqa-run.yml on the repo's default branch. If the
file already exists with identical content, we no-op. If it exists with
different content, we report a conflict so the UI can ask the user to
overwrite (UI passes force=True on the second attempt).

Reuses the canonical workflow body from app/execution/github_runner.py so
there's exactly one source of truth.
"""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass
from typing import Optional

import httpx

from app.execution.github_runner import _workflow_yaml_body

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"
WORKFLOW_PATH = ".github/workflows/nextgenqa-run.yml"


@dataclass
class InstallResult:
    status: str           # "installed" | "already_present" | "conflict"
    sha: Optional[str] = None
    message: str = ""


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


async def install_workflow(
    *,
    token: str,
    owner: str,
    repo: str,
    branch: str,
    force: bool = False,
) -> InstallResult:
    """
    PUT the workflow file. Returns:
      - status='already_present' if our exact YAML already lives there.
      - status='conflict' if the path exists with different content and
        force=False (UI offers to overwrite).
      - status='installed' on a successful create/update.
    """
    body_text = _workflow_yaml_body()
    body_b64 = base64.b64encode(body_text.encode("utf-8")).decode("ascii")

    async with httpx.AsyncClient(headers=_headers(token), timeout=30.0) as client:
        # 1. Check whether the file already exists on the branch.
        get_resp = await client.get(
            f"{GITHUB_API}/repos/{owner}/{repo}/contents/{WORKFLOW_PATH}",
            params={"ref": branch},
        )
        existing_sha: Optional[str] = None
        if get_resp.status_code == 200:
            existing = get_resp.json()
            existing_sha = existing.get("sha")
            existing_b64 = (existing.get("content") or "").replace("\n", "")
            if existing_b64 == body_b64:
                return InstallResult(
                    status="already_present",
                    sha=existing_sha,
                    message="Workflow file is already up to date.",
                )
            if not force:
                return InstallResult(
                    status="conflict",
                    sha=existing_sha,
                    message=(
                        "A workflow file with different content already lives at "
                        f"{WORKFLOW_PATH}. Confirm overwrite to replace it."
                    ),
                )
        elif get_resp.status_code not in (404, 200):
            get_resp.raise_for_status()

        # 2. PUT (create or update).
        put_body: dict = {
            "message": "Install NextGen QA test runner workflow",
            "content": body_b64,
            "branch": branch,
        }
        if existing_sha:
            put_body["sha"] = existing_sha

        put_resp = await client.put(
            f"{GITHUB_API}/repos/{owner}/{repo}/contents/{WORKFLOW_PATH}",
            json=put_body,
        )
        put_resp.raise_for_status()
        data = put_resp.json()
        new_sha = (data.get("content") or {}).get("sha")
        return InstallResult(
            status="installed",
            sha=new_sha,
            message="Workflow file installed on default branch.",
        )
