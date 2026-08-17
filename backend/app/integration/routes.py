"""
Integration routes — the API Component 2 exposes to Component 3 (Failure
Analysis & Self-Healing).

This is the mirror of how Component 1 hands us user stories: C3 pulls C2's
failed test executions (shaped to match C3's `POST /analyze` request) and C2's
known-good DOM selectors (ground truth for locator self-healing), through the
API Gateway. C3 never touches C2's database.

Endpoints (reached by C3 via the gateway as `/api/test-case` + these paths):
  GET /api/v1/projects/{project_id}/failed-tests          — failed scenarios ready to analyze
  GET /api/v1/projects/{project_id}/selectors             — approved selectors for locator repair
  GET /api/v1/projects/{project_id}/test-suites           — generated test code + metadata
  GET /api/v1/projects/{project_id}/test-suites/{suite_id} — one suite (full code)
  GET /api/v1/projects/{project_id}/test-runs             — run executions (run-level, log preview)
  GET /api/v1/projects/{project_id}/test-runs/{run_id}    — one execution + scenarios + full log
"""

from __future__ import annotations

import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Project, TestRun, TestRunExecution, TestSuite, DomElement

router = APIRouter(prefix="/api/v1", tags=["integration (C3)"])


# ─── Response schemas ────────────────────────────────────────────────────────
# `FailureForAnalysis` intentionally matches Component 3's POST /analyze request
# body, so C3 can forward each item straight into its pipeline with no mapping.


class FailureForAnalysis(BaseModel):
    # Fields consumed by C3's /analyze pipeline
    test_name: str
    pipeline: str
    error_message: str
    stack_trace: str
    failure_stage: str = "test"
    failure_type: str = "Test Failure"
    severity: str = "MEDIUM"
    retry_count: int = 0
    test_duration_sec: float = 0.0
    cpu_usage_pct: float = 0.0
    memory_usage_mb: float = 0.0
    is_flaky_test: int = 0
    old_locator: Optional[str] = None
    # Traceability extras — C3 may ignore these, but they let a failure be
    # traced back to the exact C2 project / suite / scenario that produced it.
    source: str = "C2"
    project_id: str
    suite_id: Optional[str] = None
    framework: Optional[str] = None
    run_status: str = "failed"
    executed_at: Optional[str] = None


class FailedTestsResponse(BaseModel):
    project_id: str
    total: int
    failures: list[FailureForAnalysis]


class SelectorOut(BaseModel):
    role: str            # semantic label, e.g. "login_button"
    selector: str        # CSS selector, e.g. "#login"
    url: str
    tag: str
    text: Optional[str] = None
    attributes: dict
    confidence: Optional[float] = None
    approved: bool


class SelectorsResponse(BaseModel):
    project_id: str
    total: int
    selectors: list[SelectorOut]


class TestSuiteOut(BaseModel):
    """The generated executable test code C3 needs to apply a self-healing fix."""
    id: str
    project_id: str
    framework: str          # selenium | playwright | cypress
    language: str           # python | javascript
    filename: str
    code: str               # the actual source C3 edits when healing
    mode: str               # abstract | dom
    url: str
    version: int
    is_active: bool
    selected_for_run: bool
    source_scenario_count: int
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class TestSuitesResponse(BaseModel):
    project_id: str
    total: int
    test_suites: list[TestSuiteOut]


class RunScenarioOut(BaseModel):
    scenario_name: str
    flow_name: str
    status: str
    duration_ms: Optional[int] = None
    error_message: Optional[str] = None


class TestRunExecutionOut(BaseModel):
    """Run-level record of one 'Run Tests' execution (CI/CD or local)."""
    id: str
    project_id: str
    suite_id: Optional[str] = None
    framework: str
    mode: str               # github | local
    status: str             # queued | running | passed | failed | error
    github_run_id: Optional[str] = None
    github_run_url: Optional[str] = None
    github_branch: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    duration_ms: Optional[int] = None
    total_count: int = 0
    passed_count: int = 0
    failed_count: int = 0
    error_message: Optional[str] = None
    log_preview: Optional[str] = None   # last lines of raw_log_text


class TestRunExecutionDetailOut(TestRunExecutionOut):
    raw_log: Optional[str] = None       # full execution log
    scenarios: list[RunScenarioOut] = []


class TestRunsResponse(BaseModel):
    project_id: str
    total: int
    test_runs: list[TestRunExecutionOut]


# ─── Heuristics ──────────────────────────────────────────────────────────────

# Try to pull a CSS/XPath-ish selector out of a failure message so C3's locator
# healing has an `old_locator` to repair. Best-effort — returns None if nothing
# looks like a selector.
_LOCATOR_PATTERNS = [
    re.compile(r"""locator\(\s*['"]([^'"]+)['"]""", re.IGNORECASE),
    re.compile(r"""(?:selector|locator)['"]?\s*[:=]\s*['"]([^'"]+)['"]""", re.IGNORECASE),
    re.compile(r"""(?:not found|locate element|waiting for selector|no such element)[:\s]+['"]?([#.\[/][^\s'"]+)""", re.IGNORECASE),
    re.compile(r"""(#[A-Za-z0-9_-]+|\[[^\]]+\]|//[^\s'"]+)"""),
]


def _extract_locator(message: Optional[str]) -> Optional[str]:
    if not message:
        return None
    for pattern in _LOCATOR_PATTERNS:
        match = pattern.search(message)
        if match:
            return match.group(1).strip()
    return None


def _classify_failure_type(status: str, message: Optional[str]) -> str:
    msg = (message or "").lower()
    if any(k in msg for k in ("timeout", "timed out", "waiting for")):
        return "Timeout"
    if any(k in msg for k in ("econnrefused", "connection refused", "network", "http 5", "502", "503", "504")):
        return "Network Error"
    if status == "error":
        return "Error"
    return "Test Failure"


def _to_failure(row: TestRun) -> FailureForAnalysis:
    message = row.error_message or ""
    duration_sec = round((row.duration_ms or 0) / 1000.0, 3)
    return FailureForAnalysis(
        test_name=row.scenario_name,
        pipeline=f"NextGenQA C2 / {row.framework}",
        error_message=message,
        # C2 stores one combined message per scenario; feed it as the stack
        # trace too so C3's TF-IDF has the maximum available signal.
        stack_trace=message,
        failure_type=_classify_failure_type(row.status, message),
        test_duration_sec=duration_sec,
        old_locator=_extract_locator(message),
        project_id=str(row.project_id),
        suite_id=str(row.suite_id) if row.suite_id else None,
        framework=row.framework,
        run_status=row.status,
        executed_at=row.executed_at.isoformat() if row.executed_at else None,
    )


def _suite_out(row: TestSuite) -> TestSuiteOut:
    return TestSuiteOut(
        id=str(row.id),
        project_id=str(row.project_id),
        framework=row.framework,
        language=row.language,
        filename=row.filename,
        code=row.code,
        mode=row.mode,
        url=row.url,
        version=row.version,
        is_active=bool(row.is_active),
        selected_for_run=bool(row.selected_for_run),
        source_scenario_count=row.source_scenario_count or 0,
        created_at=row.created_at.isoformat() if row.created_at else None,
        updated_at=row.updated_at.isoformat() if row.updated_at else None,
    )


def _log_tail(text: Optional[str], lines: int = 200) -> Optional[str]:
    if not text:
        return None
    return "\n".join(text.splitlines()[-lines:])


def _execution_out(row: TestRunExecution) -> TestRunExecutionOut:
    return TestRunExecutionOut(
        id=str(row.id),
        project_id=str(row.project_id),
        suite_id=str(row.suite_id) if row.suite_id else None,
        framework=row.framework,
        mode=row.mode,
        status=row.status,
        github_run_id=row.github_run_id,
        github_run_url=row.github_run_url,
        github_branch=row.github_branch,
        started_at=row.started_at.isoformat() if row.started_at else None,
        finished_at=row.finished_at.isoformat() if row.finished_at else None,
        duration_ms=row.duration_ms,
        total_count=row.total_count or 0,
        passed_count=row.passed_count or 0,
        failed_count=row.failed_count or 0,
        error_message=row.error_message,
        log_preview=_log_tail(row.raw_log_text),
    )


async def _require_project(project_id: str, db: AsyncSession) -> None:
    proj = await db.execute(select(Project).where(Project.id == project_id))
    if not proj.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Project not found")


# ─── Endpoints ───────────────────────────────────────────────────────────────


@router.get("/projects/{project_id}/failed-tests", response_model=FailedTestsResponse)
async def get_failed_tests(
    project_id: str,
    limit: int = 50,
    suite_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Failed / errored test scenarios for a project, newest first, shaped for
    Component 3's `POST /analyze` pipeline.

    C3 polls this to discover fresh failures to classify + heal. Each item is a
    ready-to-analyze failure; optionally scope to one suite with `suite_id`.
    """
    await _require_project(project_id, db)

    query = (
        select(TestRun)
        .where(TestRun.project_id == project_id)
        .where(TestRun.status.in_(["failed", "error"]))
        .order_by(TestRun.executed_at.desc())
        .limit(max(1, min(limit, 500)))
    )
    if suite_id:
        query = query.where(TestRun.suite_id == suite_id)

    rows = (await db.execute(query)).scalars().all()
    failures = [_to_failure(r) for r in rows]
    return FailedTestsResponse(project_id=project_id, total=len(failures), failures=failures)


@router.get("/projects/{project_id}/selectors", response_model=SelectorsResponse)
async def get_selectors(
    project_id: str,
    url: Optional[str] = None,
    approved_only: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """
    Known-good DOM selectors crawled/curated by C2, so C3's locator self-healing
    can propose a real stable selector (by role) instead of a placeholder.

    Filter by page `url`, or set `approved_only=true` for QA-approved selectors.
    """
    await _require_project(project_id, db)

    query = select(DomElement).where(DomElement.project_id == project_id)
    if url:
        query = query.where(DomElement.url == url)
    if approved_only:
        query = query.where(DomElement.approved.is_(True))
    query = query.order_by(DomElement.url.asc(), DomElement.role.asc())

    rows = (await db.execute(query)).scalars().all()
    selectors = [
        SelectorOut(
            role=r.role,
            selector=r.selector,
            url=r.url,
            tag=r.tag,
            text=r.text,
            attributes=r.attributes or {},
            confidence=r.confidence,
            approved=bool(r.approved),
        )
        for r in rows
    ]
    return SelectorsResponse(project_id=project_id, total=len(selectors), selectors=selectors)


@router.get("/projects/{project_id}/test-suites", response_model=TestSuitesResponse)
async def get_test_suites(
    project_id: str,
    active_only: bool = False,
    selected_only: bool = False,
    framework: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Generated test suites (with their source code) for a project. C3 needs the
    actual code to apply a self-healing fix in context.

    `active_only=true` returns only the head of each version chain;
    `selected_only=true` returns the one suite marked for the next CI/CD run;
    `framework` filters to selenium | playwright | cypress.
    """
    await _require_project(project_id, db)

    query = select(TestSuite).where(TestSuite.project_id == project_id)
    if active_only:
        query = query.where(TestSuite.is_active.is_(True))
    if selected_only:
        query = query.where(TestSuite.selected_for_run.is_(True))
    if framework:
        query = query.where(TestSuite.framework == framework)
    query = query.order_by(TestSuite.framework.asc(), TestSuite.version.desc())

    rows = (await db.execute(query)).scalars().all()
    suites = [_suite_out(r) for r in rows]
    return TestSuitesResponse(project_id=project_id, total=len(suites), test_suites=suites)


@router.get("/projects/{project_id}/test-suites/{suite_id}", response_model=TestSuiteOut)
async def get_test_suite(
    project_id: str,
    suite_id: str,
    db: AsyncSession = Depends(get_db),
):
    """One test suite's full detail (including code), scoped to the project."""
    await _require_project(project_id, db)
    row = (
        await db.execute(
            select(TestSuite)
            .where(TestSuite.id == suite_id)
            .where(TestSuite.project_id == project_id)
        )
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Test suite not found in this project")
    return _suite_out(row)


@router.get("/projects/{project_id}/test-runs", response_model=TestRunsResponse)
async def get_test_runs(
    project_id: str,
    limit: int = 20,
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Run-level execution records (one per 'Run Tests'), newest first, with a log
    preview. Filter with `status` (e.g. `failed`); use the detail endpoint for
    the full log + per-scenario breakdown.
    """
    await _require_project(project_id, db)

    query = (
        select(TestRunExecution)
        .where(TestRunExecution.project_id == project_id)
        .order_by(TestRunExecution.started_at.desc())
        .limit(max(1, min(limit, 200)))
    )
    if status:
        query = query.where(TestRunExecution.status == status)

    rows = (await db.execute(query)).scalars().all()
    runs = [_execution_out(r) for r in rows]
    return TestRunsResponse(project_id=project_id, total=len(runs), test_runs=runs)


@router.get("/projects/{project_id}/test-runs/{run_id}", response_model=TestRunExecutionDetailOut)
async def get_test_run(
    project_id: str,
    run_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    One execution's full detail: run metadata, the complete raw log, and every
    scenario result — the deepest context C3 can use to analyze a failure.
    """
    await _require_project(project_id, db)
    row = (
        await db.execute(
            select(TestRunExecution)
            .where(TestRunExecution.id == run_id)
            .where(TestRunExecution.project_id == project_id)
        )
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Run not found in this project")

    # Scenarios are tracked per suite; scope by the execution's suite when present.
    sc_query = select(TestRun).where(TestRun.project_id == project_id)
    if row.suite_id:
        sc_query = sc_query.where(TestRun.suite_id == row.suite_id)
    sc_query = sc_query.order_by(TestRun.executed_at.asc())
    scenarios = (await db.execute(sc_query)).scalars().all()

    base = _execution_out(row)
    return TestRunExecutionDetailOut(
        **base.model_dump(),
        raw_log=row.raw_log_text,
        scenarios=[
            RunScenarioOut(
                scenario_name=s.scenario_name,
                flow_name=s.flow_name,
                status=s.status,
                duration_ms=s.duration_ms,
                error_message=s.error_message,
            )
            for s in scenarios
        ],
    )
