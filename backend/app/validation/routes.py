"""
Validation endpoints (independent validation of generated artefacts).

  POST /api/v1/validation/suites/{suite_id}           — run static checks + LLM judge, store report
  GET  /api/v1/validation/suites/{suite_id}           — latest report for the suite (null if none)
  POST /api/v1/validation/suites/{suite_id}/fix       — LLM repair proposal (not saved)
  POST /api/v1/validation/gherkin/{gherkin_id}        — validate a Gherkin scenario set
  GET  /api/v1/validation/gherkin/{gherkin_id}        — latest report
  POST /api/v1/validation/gherkin/{gherkin_id}/fix    — LLM repair proposal (not saved)
  GET  /api/v1/validation/projects/{project_id}/latest?target_type=suite|gherkin
  GET  /api/v1/validation/projects/{project_id}/summary — counts, averages, predicted-vs-actual calibration
  GET  /api/v1/validation/reports/{report_id}
"""
from __future__ import annotations

import uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import GherkinScenario, TestSuite, ValidationReport
from app.validation import service, static_checks
from app.validation.findings import Finding, count_by_severity, static_score
from app.validation.fixer import fix_gherkin, fix_suite
from app.validation.llm_client import ValidatorUnavailable

router = APIRouter(prefix="/api/v1", tags=["validation"])


class ValidateIn(BaseModel):
    parent_report_id: Optional[str] = None
    use_llm: bool = True


class FixIn(BaseModel):
    finding_ids: Optional[list[str]] = None     # subset to fix; default = all fixable
    code: Optional[str] = None                  # validate/fix unsaved editor text instead of the stored one
    text: Optional[str] = None                  # gherkin counterpart of `code`


def _uuid(value: str, what: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except Exception:
        raise HTTPException(status_code=400, detail=f"Invalid {what} id")


async def _get_suite(db: AsyncSession, suite_id: str) -> TestSuite:
    q = await db.execute(select(TestSuite).where(TestSuite.id == _uuid(suite_id, "suite")))
    suite = q.scalar_one_or_none()
    if not suite:
        raise HTTPException(status_code=404, detail="Test suite not found")
    return suite


async def _get_gherkin(db: AsyncSession, gherkin_id: str) -> GherkinScenario:
    q = await db.execute(select(GherkinScenario).where(GherkinScenario.id == _uuid(gherkin_id, "gherkin")))
    g = q.scalar_one_or_none()
    if not g:
        raise HTTPException(status_code=404, detail="Gherkin scenario not found")
    return g


def _select_findings(report: Optional[ValidationReport], fresh: list[Finding], ids: Optional[list[str]]) -> list[dict]:
    """Findings to hand the fixer: the stored report's (if it matches) merged with fresh static ones."""
    pool: dict[str, dict] = {}
    if report:
        for f in report.findings or []:
            pool[f["id"]] = f
    for f in fresh:
        # Avoid duplicating a stored static finding with the same title+line.
        if not any(p["title"] == f.title and p.get("line") == f.line and p["source"] == "static" for p in pool.values()):
            pool[f.id] = f.to_dict()
    selected = [f for f in pool.values() if f.get("fixable", True) and f["severity"] != "info"]
    if ids:
        wanted = set(ids)
        selected = [f for f in selected if f["id"] in wanted]
    return selected


# ─── Suites ──────────────────────────────────────────────────────────────────

@router.post("/validation/suites/{suite_id}")
async def validate_suite(suite_id: str, body: Optional[ValidateIn] = None, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    body = body or ValidateIn()
    suite = await _get_suite(db, suite_id)
    report = await service.validate_suite(db, suite, parent_report_id=body.parent_report_id, use_llm=body.use_llm)
    return service.report_out(report)


@router.get("/validation/suites/{suite_id}")
async def latest_suite_report(suite_id: str, db: AsyncSession = Depends(get_db)) -> Optional[dict[str, Any]]:
    suite = await _get_suite(db, suite_id)
    report = await service.latest_report(db, "suite", suite.id)
    if not report:
        return None
    out = service.report_out(report)
    out["is_current"] = report.content_hash == service.content_hash(suite.code)
    return out


@router.post("/validation/suites/{suite_id}/fix")
async def propose_suite_fix(suite_id: str, body: Optional[FixIn] = None, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    body = body or FixIn()
    suite = await _get_suite(db, suite_id)
    code = body.code if isinstance(body.code, str) and body.code.strip() else suite.code
    gherkin_texts, dom = await service.suite_context(db, suite)

    fresh_static = static_checks.check_suite_code(
        code, framework=suite.framework, mode=suite.mode, url=suite.url, gherkin_texts=gherkin_texts, dom_elements=dom or None
    )
    report = await service.latest_report(db, "suite", suite.id)
    if report and report.content_hash != service.content_hash(code):
        report = None   # stored findings describe different code; rely on fresh static ones
    findings = _select_findings(report, fresh_static, body.finding_ids)
    if not findings:
        raise HTTPException(status_code=400, detail="No fixable findings - validate the suite first or edit the code.")

    try:
        result = await fix_suite(
            code=code, framework=suite.framework, mode=suite.mode, url=suite.url,
            gherkin_texts=gherkin_texts, dom_elements=dom or None, findings=findings,
        )
    except ValidatorUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Auto-fix failed: {e}")

    after = static_checks.check_suite_code(
        result["code"], framework=suite.framework, mode=suite.mode, url=suite.url,
        gherkin_texts=gherkin_texts, dom_elements=dom or None,
    )
    return {
        "suite_id": str(suite.id),
        "original_code": code,
        "fixed_code": result["code"],
        "changes": result["changes"],
        "addressed_findings": findings,
        "static_before": {"score": static_score(fresh_static), "counts": count_by_severity(fresh_static)},
        "static_after": {"score": static_score(after), "counts": count_by_severity(after), "findings": [f.to_dict() for f in after]},
        "fixer_provider": result["provider"],
        "fixer_model": result["model"],
    }


# ─── Gherkin ─────────────────────────────────────────────────────────────────

@router.post("/validation/gherkin/{gherkin_id}")
async def validate_gherkin(gherkin_id: str, body: Optional[ValidateIn] = None, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    body = body or ValidateIn()
    g = await _get_gherkin(db, gherkin_id)
    report = await service.validate_gherkin(db, g, parent_report_id=body.parent_report_id, use_llm=body.use_llm)
    return service.report_out(report)


@router.get("/validation/gherkin/{gherkin_id}")
async def latest_gherkin_report(gherkin_id: str, db: AsyncSession = Depends(get_db)) -> Optional[dict[str, Any]]:
    g = await _get_gherkin(db, gherkin_id)
    report = await service.latest_report(db, "gherkin", g.id)
    if not report:
        return None
    out = service.report_out(report)
    out["is_current"] = report.content_hash == service.content_hash(g.gherkin_text)
    return out


@router.post("/validation/gherkin/{gherkin_id}/fix")
async def propose_gherkin_fix(gherkin_id: str, body: Optional[FixIn] = None, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    body = body or FixIn()
    g = await _get_gherkin(db, gherkin_id)
    text = body.text if isinstance(body.text, str) and body.text.strip() else g.gherkin_text
    story, url = await service.gherkin_context(db, g)

    fresh_static = static_checks.check_gherkin(text, story["acceptance_criteria"])
    report = await service.latest_report(db, "gherkin", g.id)
    if report and report.content_hash != service.content_hash(text):
        report = None
    findings = _select_findings(report, fresh_static, body.finding_ids)
    if not findings:
        raise HTTPException(status_code=400, detail="No fixable findings - validate the scenario first or edit the text.")

    try:
        result = await fix_gherkin(gherkin_text=text, story=story, url=url, findings=findings)
    except ValidatorUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Auto-fix failed: {e}")

    after = static_checks.check_gherkin(result["text"], story["acceptance_criteria"])
    return {
        "gherkin_id": str(g.id),
        "original_text": text,
        "fixed_text": result["text"],
        "changes": result["changes"],
        "addressed_findings": findings,
        "static_before": {"score": static_score(fresh_static), "counts": count_by_severity(fresh_static)},
        "static_after": {"score": static_score(after), "counts": count_by_severity(after), "findings": [f.to_dict() for f in after]},
        "fixer_provider": result["provider"],
        "fixer_model": result["model"],
    }


# ─── Project-level ───────────────────────────────────────────────────────────

@router.get("/validation/projects/{project_id}/latest")
async def project_latest(
    project_id: str,
    target_type: str = Query("suite", pattern="^(suite|gherkin)$"),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    pid = _uuid(project_id, "project")
    reports = await service.project_latest(db, pid, target_type)
    # Attach whether each report still matches the current artefact text.
    current: dict = {}
    if target_type == "suite":
        q = await db.execute(select(TestSuite.id, TestSuite.code).where(TestSuite.project_id == pid))
        current = {row[0]: service.content_hash(row[1]) for row in q.all()}
    else:
        q = await db.execute(select(GherkinScenario.id, GherkinScenario.gherkin_text).where(GherkinScenario.project_id == pid))
        current = {row[0]: service.content_hash(row[1]) for row in q.all()}
    return [service.summary_out(r, current.get(r.target_id)) for r in reports]


@router.get("/validation/projects/{project_id}/summary")
async def project_summary(project_id: str, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    return await service.project_summary(db, _uuid(project_id, "project"))


@router.get("/validation/reports/{report_id}")
async def get_report(report_id: str, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    q = await db.execute(select(ValidationReport).where(ValidationReport.id == _uuid(report_id, "report")))
    r = q.scalar_one_or_none()
    if not r:
        raise HTTPException(status_code=404, detail="Report not found")
    return service.report_out(r)
