"""
GitHub Actions execution path — the "real CI/CD" runner.

Flow per click of [Run Tests]:
  1. Create a fresh branch  runs/{run_id}  in the target repo.
  2. PUT the selected suite code + the workflow YAML onto that branch.
  3. POST workflow_dispatch with `run_id`, `framework`, `staging_url` inputs.
  4. Poll the runs list for the new run id (workflow_dispatch returns 204
     with no body, so we have to discover the id by matching head_branch).
  5. Stream step-level status from /jobs into log_broker every 3 seconds.
  6. When the run finishes, fetch the full log archive and return it.

We *also* run the local fallback if any of the above fails — the orchestrator
in runner.py decides between modes; this file just exposes both halves
(trigger + poll) for it to call.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import re
import time
import zipfile
from dataclasses import dataclass
from io import BytesIO
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


GITHUB_API_BASE = "https://api.github.com"
WORKFLOW_FILENAME = "nextgenqa-run.yml"


@dataclass
class GitHubConfig:
    token: str
    owner: str
    repo: str
    base_branch: str = "main"

    @classmethod
    def from_env(cls) -> Optional["GitHubConfig"]:
        token = os.getenv("GITHUB_TOKEN", "").strip()
        repo_full = os.getenv("GITHUB_REPO", "").strip()
        if not token or "/" not in repo_full:
            return None
        owner, repo = repo_full.split("/", 1)
        return cls(
            token=token,
            owner=owner,
            repo=repo,
            base_branch=os.getenv("GITHUB_BASE_BRANCH", "main"),
        )

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }


@dataclass
class GitHubTriggerResult:
    run_id_github: str           # numeric GH run id
    run_url: str                 # https://github.com/{owner}/{repo}/actions/runs/{id}
    branch: str


@dataclass
class GitHubFinalResult:
    status: str                  # passed | failed | error
    raw_log_text: str
    duration_ms: int
    error_message: Optional[str] = None


async def trigger_run(
    cfg: GitHubConfig,
    *,
    run_id: str,
    suite_code: str,
    filename: str,
    framework: str,
    staging_url: str,
) -> GitHubTriggerResult:
    """
    Create branch, push suite + workflow, fire workflow_dispatch, discover
    the resulting numeric run id. Raises httpx.HTTPStatusError on failure.
    """
    branch = f"runs/{run_id}"

    async with httpx.AsyncClient(headers=cfg.headers, timeout=30.0) as client:
        # 1. Get the SHA of base_branch so we know where to fork from.
        base_ref = await client.get(
            f"{GITHUB_API_BASE}/repos/{cfg.owner}/{cfg.repo}/git/ref/heads/{cfg.base_branch}"
        )
        base_ref.raise_for_status()
        base_sha = base_ref.json()["object"]["sha"]

        # 2. Create the branch.
        create_ref = await client.post(
            f"{GITHUB_API_BASE}/repos/{cfg.owner}/{cfg.repo}/git/refs",
            json={"ref": f"refs/heads/{branch}", "sha": base_sha},
        )
        # 422 = branch exists; tolerate so retries work.
        if create_ref.status_code not in (201, 422):
            create_ref.raise_for_status()

        # 3. Commit the suite file to the branch.
        await _put_file(
            client, cfg, branch,
            path=f"tests/{filename}",
            content=suite_code,
            message=f"NextGen QA run {run_id}: {framework} suite",
        )

        # 4. Ensure the workflow YAML lives on the branch.
        workflow_yaml = _workflow_yaml_body()
        await _put_file(
            client, cfg, branch,
            path=f".github/workflows/{WORKFLOW_FILENAME}",
            content=workflow_yaml,
            message=f"NextGen QA workflow for run {run_id}",
        )

        # 5. workflow_dispatch.
        dispatch = await client.post(
            f"{GITHUB_API_BASE}/repos/{cfg.owner}/{cfg.repo}/actions/workflows/{WORKFLOW_FILENAME}/dispatches",
            json={
                "ref": branch,
                "inputs": {
                    "run_id": run_id,
                    "framework": framework,
                    "staging_url": staging_url,
                },
            },
        )
        dispatch.raise_for_status()  # 204 expected

        # 6. Discover the numeric run id. GH usually exposes the run within
        # 5–10 seconds — poll for up to 60s.
        deadline = time.time() + 60
        gh_run_id: Optional[str] = None
        gh_run_url: Optional[str] = None
        while time.time() < deadline:
            await asyncio.sleep(3)
            runs = await client.get(
                f"{GITHUB_API_BASE}/repos/{cfg.owner}/{cfg.repo}/actions/runs",
                params={"branch": branch, "per_page": 5},
            )
            runs.raise_for_status()
            payload = runs.json()
            for r in payload.get("workflow_runs", []):
                if r.get("head_branch") == branch:
                    gh_run_id = str(r["id"])
                    gh_run_url = r["html_url"]
                    break
            if gh_run_id:
                break

        if not gh_run_id:
            raise RuntimeError(
                "workflow_dispatch accepted but no matching run appeared in 60s — "
                "check that the workflow file is present on the default branch."
            )

        return GitHubTriggerResult(
            run_id_github=gh_run_id,
            run_url=gh_run_url or "",
            branch=branch,
        )


async def stream_run_progress(
    cfg: GitHubConfig,
    gh_run_id: str,
    *,
    on_step: callable,
    poll_seconds: float = 3.0,
) -> str:
    """
    Poll /jobs every `poll_seconds` while the run is active. Each new step
    transition fires `on_step({"step": ..., "status": ...})`. Returns the
    final run conclusion ("success", "failure", "cancelled", "timed_out",
    "skipped", "neutral", ...).
    """
    seen: set[tuple[str, str]] = set()
    final_conclusion = "neutral"

    async with httpx.AsyncClient(headers=cfg.headers, timeout=20.0) as client:
        while True:
            run_meta = await client.get(
                f"{GITHUB_API_BASE}/repos/{cfg.owner}/{cfg.repo}/actions/runs/{gh_run_id}"
            )
            run_meta.raise_for_status()
            meta = run_meta.json()
            status = meta.get("status")            # queued | in_progress | completed
            conclusion = meta.get("conclusion")    # success | failure | None until done

            jobs = await client.get(
                f"{GITHUB_API_BASE}/repos/{cfg.owner}/{cfg.repo}/actions/runs/{gh_run_id}/jobs"
            )
            jobs.raise_for_status()
            for job in jobs.json().get("jobs", []):
                for step in job.get("steps", []):
                    key = (job["name"], step["name"])
                    state = step.get("status")     # queued | in_progress | completed
                    res = step.get("conclusion")   # success | failure | None
                    if state == "completed" and key not in seen:
                        seen.add(key)
                        on_step({
                            "step": step["name"],
                            "status": "passed" if res == "success" else "failed" if res else "info",
                        })
                    elif state == "in_progress" and (key, "running") not in seen:
                        seen.add((key, "running"))
                        on_step({"step": step["name"], "status": "running"})

            if status == "completed":
                final_conclusion = conclusion or "neutral"
                break
            await asyncio.sleep(poll_seconds)

    return final_conclusion


async def fetch_run_log(
    cfg: GitHubConfig,
    gh_run_id: str,
) -> str:
    """
    Download the logs zip via REST and concatenate all per-step .txt files
    into one big string. This is the "raw log saved to DB" payload.
    """
    async with httpx.AsyncClient(headers=cfg.headers, timeout=120.0) as client:
        # GH returns a 302 to a short-lived signed URL — let httpx follow.
        resp = await client.get(
            f"{GITHUB_API_BASE}/repos/{cfg.owner}/{cfg.repo}/actions/runs/{gh_run_id}/logs",
            follow_redirects=True,
        )
        if resp.status_code != 200:
            return f"[NextGenQA] Failed to fetch GitHub Actions logs: HTTP {resp.status_code}"

        archive = zipfile.ZipFile(BytesIO(resp.content))
        chunks: list[str] = []
        for name in sorted(archive.namelist()):
            if not name.endswith(".txt"):
                continue
            try:
                chunks.append(f"=== {name} ===\n" + archive.read(name).decode("utf-8", errors="replace"))
            except Exception as e:
                chunks.append(f"=== {name} === (decode error: {e})")
        return "\n\n".join(chunks)


# ─── Internal helpers ────────────────────────────────────────────────────────


async def _put_file(
    client: httpx.AsyncClient,
    cfg: GitHubConfig,
    branch: str,
    *,
    path: str,
    content: str,
    message: str,
) -> None:
    """PUT contents to a file path on the branch. Idempotent — looks up the
    existing blob SHA if the file already exists so the API doesn't 409."""
    existing = await client.get(
        f"{GITHUB_API_BASE}/repos/{cfg.owner}/{cfg.repo}/contents/{path}",
        params={"ref": branch},
    )
    sha = existing.json().get("sha") if existing.status_code == 200 else None
    body = {
        "message": message,
        "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
        "branch": branch,
    }
    if sha:
        body["sha"] = sha
    resp = await client.put(
        f"{GITHUB_API_BASE}/repos/{cfg.owner}/{cfg.repo}/contents/{path}",
        json=body,
    )
    resp.raise_for_status()


def _workflow_yaml_body() -> str:
    """The pinned workflow contents we push to every per-run branch."""
    return """\
name: NextGen QA Auto Test Run

on:
  workflow_dispatch:
    inputs:
      run_id:
        description: 'NextGen QA run id (UUID)'
        required: true
      framework:
        description: 'selenium | playwright | cypress'
        required: true
        default: 'playwright'
      staging_url:
        description: 'Target staging URL'
        required: true

jobs:
  run-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        if: ${{ inputs.framework != 'cypress' }}
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Set up Node
        if: ${{ inputs.framework == 'cypress' }}
        uses: actions/setup-node@v4
        with:
          node-version: '20'

      - name: Install Playwright runner
        if: ${{ inputs.framework == 'playwright' }}
        run: |
          pip install pytest pytest-playwright allure-pytest
          playwright install --with-deps chromium

      - name: Install Selenium runner
        if: ${{ inputs.framework == 'selenium' }}
        run: |
          pip install pytest selenium allure-pytest

      - name: Install Cypress
        if: ${{ inputs.framework == 'cypress' }}
        run: |
          npm install --save-dev cypress

      - name: Run Python tests
        if: ${{ inputs.framework != 'cypress' }}
        run: |
          pytest tests/ -v --tb=short --alluredir=allure-results
        env:
          STAGING_URL: ${{ inputs.staging_url }}

      - name: Run Cypress
        if: ${{ inputs.framework == 'cypress' }}
        run: |
          npx cypress run --spec tests/
        env:
          CYPRESS_baseUrl: ${{ inputs.staging_url }}

      - name: Upload screenshots
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: screenshots-${{ inputs.run_id }}
          path: |
            **/screenshots/
            allure-results/

      - name: Notify NextGen QA backend
        if: always() && env.NEXTGENQA_WEBHOOK_URL != ''
        run: |
          curl -X POST "$NEXTGENQA_WEBHOOK_URL" \\
            -H 'Content-Type: application/json' \\
            -d '{"run_id":"${{ inputs.run_id }}","github_run_id":"${{ github.run_id }}","status":"${{ job.status }}","framework":"${{ inputs.framework }}"}' \\
            || echo "Webhook delivery failed (non-fatal)"
        env:
          NEXTGENQA_WEBHOOK_URL: ${{ secrets.NEXTGENQA_WEBHOOK_URL }}
"""
