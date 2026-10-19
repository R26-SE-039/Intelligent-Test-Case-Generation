"""
Validation orchestration: run static checks + LLM judge, combine them into an
explainable score, persist a ValidationReport, and answer summary/calibration
queries for the dashboard.

Scoring (documented in the stored `breakdown` so the UI can show it):

    static_score   = 100 - sum(penalty per deterministic finding)       [0..100]
    llm_score      = judge.pass_probability                              [0..100]
    scenario_rate  = predicted-pass scenarios / scenarios judged * 100   [0..100]

    base  = 0.5*llm_score + 0.3*scenario_rate + 0.2*static_score   (judge available)
    base  = static_score                                            (judge unavailable)

    caps: any static critical  -> min(base, 15)   (file will not even collect)
          any llm    critical  -> min(base, 40)
          any major            -> min(base, 85)

    verdict: likely_failing if critical or score < 50
             ready          if score >= 80 and no major
             needs_review   otherwise
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from typing import Optional

from sqlalchemy import select, func as sa_func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    DomElement,
    GherkinScenario,
    TestRunExecution,
    TestSuite,
    UserStory,
    ValidationReport,
)
from app.validation import static_checks
from app.validation.findings import Finding, count_by_severity, sort_findings, static_score
from app.validation.judge import judge_gherkin, judge_suite
from app.validation.llm_client import ValidatorUnavailable, is_independent_model

logger = logging.getLogger(__name__)

WEIGHTS = {"llm": 0.5, "scenario": 0.3, "static": 0.2}
CAP_STATIC_CRITICAL = 15
CAP_LLM_CRITICAL = 40
CAP_MAJOR = 85


def content_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _parse_criteria(raw) -> list[str]:
    if isinstance(raw, list):
        return [str(x) for x in raw if str(x).strip()]
    try:
        data = json.loads(raw or "[]")
        return [str(x) for x in data if str(x).strip()] if isinstance(data, list) else []
    except Exception:
        return [line.strip("-* ") for line in str(raw or "").splitlines() if line.strip()]


def compute_score(static_findings: list[Finding], judge: Optional[dict]) -> dict:
    s_score = static_score(static_findings)
    llm_findings: list[Finding] = judge["findings"] if judge else []
    all_findings = static_findings + llm_findings
    counts = count_by_severity(all_findings)

    scenario_total = len(judge["scenarios"]) if judge else 0
    scenario_pass = sum(1 for s in judge["scenarios"] if s["predicted"] == "pass") if judge else 0
    scenario_rate = round(100 * scenario_pass / scenario_total) if scenario_total else None
    llm_score = judge["pass_probability"] if judge else None

    if judge:
        rate = scenario_rate if scenario_rate is not None else llm_score
        base = WEIGHTS["llm"] * llm_score + WEIGHTS["scenario"] * rate + WEIGHTS["static"] * s_score
    else:
        base = float(s_score)

    caps_applied: list[str] = []
    score = base
    if any(f.severity == "critical" and f.source == "static" for f in all_findings):
        score = min(score, CAP_STATIC_CRITICAL)
        caps_applied.append(f"static critical -> cap {CAP_STATIC_CRITICAL}")
    if any(f.severity == "critical" and f.source == "llm" for f in all_findings):
        score = min(score, CAP_LLM_CRITICAL)
        caps_applied.append(f"judge critical -> cap {CAP_LLM_CRITICAL}")
    if counts["major"] > 0:
        score = min(score, CAP_MAJOR)
        caps_applied.append(f"major finding -> cap {CAP_MAJOR}")
    score = int(max(0, min(100, round(score))))

    if counts["critical"] > 0 or score < 50:
        verdict = "likely_failing"
    elif score >= 80 and counts["major"] == 0:
        verdict = "ready"
    else:
        verdict = "needs_review"

    return {
        "score": score,
        "verdict": verdict,
        "static_score": s_score,
        "llm_score": llm_score,
        "scenario_total": scenario_total,
        "scenario_pass_predicted": scenario_pass,
        "breakdown": {
            "weights": WEIGHTS if judge else {"static": 1.0},
            "static_score": s_score,
            "llm_score": llm_score,
            "scenario_rate": scenario_rate,
            "base": round(base, 1),
            "caps_applied": caps_applied,
            "counts": counts,
            "judge_available": bool(judge),
            "independent_model": is_independent_model(),
        },
    }


def report_out(r: ValidationReport) -> dict:
    return {
        "id": str(r.id),
        "project_id": str(r.project_id),
        "target_type": r.target_type,
        "target_id": str(r.target_id),
        "content_hash": r.content_hash,
        "framework": r.framework,
        "score": r.score,
        "verdict": r.verdict,
        "static_score": r.static_score,
        "llm_score": r.llm_score,
        "scenario_total": r.scenario_total,
        "scenario_pass_predicted": r.scenario_pass_predicted,
        "summary": r.summary,
        "findings": r.findings or [],
        "scenarios": r.scenarios or [],
        "breakdown": r.breakdown or {},
        "validator_provider": r.validator_provider,
        "validator_model": r.validator_model,
        "duration_ms": r.duration_ms,
        "parent_report_id": str(r.parent_report_id) if r.parent_report_id else None,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


def summary_out(r: ValidationReport, current_hash: Optional[str] = None) -> dict:
    counts = count_by_severity(r.findings or [])
    return {
        "report_id": str(r.id),
        "target_id": str(r.target_id),
        "score": r.score,
        "verdict": r.verdict,
        "is_current": (current_hash == r.content_hash) if current_hash else None,
        "critical": counts["critical"],
        "major": counts["major"],
        "minor": counts["minor"],
        "scenario_total": r.scenario_total,
        "scenario_pass_predicted": r.scenario_pass_predicted,
        "validator_model": r.validator_model,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


# ─── Context loaders ─────────────────────────────────────────────────────────

async def suite_context(db: AsyncSession, suite: TestSuite) -> tuple[list[str], list[dict]]:
    """Gherkin texts the suite was generated from, and the crawled DOM map."""
    ids = [str(i) for i in (suite.source_scenario_ids or [])]
    gherkins: list[GherkinScenario] = []
    if ids:
        try:
            q = await db.execute(select(GherkinScenario).where(GherkinScenario.id.in_([uuid.UUID(i) for i in ids])))
            gherkins = list(q.scalars().all())
        except Exception:
            gherkins = []
    if not gherkins:
        q = await db.execute(
            select(GherkinScenario).where(
                GherkinScenario.project_id == suite.project_id, GherkinScenario.approved.is_(True)
            )
        )
        gherkins = list(q.scalars().all())
    texts = [g.gherkin_text for g in gherkins if g.gherkin_text]

    dom: list[dict] = []
    if suite.mode == "dom":
        q = await db.execute(
            select(DomElement).where(DomElement.project_id == suite.project_id, DomElement.url == suite.url)
        )
        dom = [
            {"role": e.role, "selector": e.selector, "tag": e.tag, "text": e.text or "", "attributes": e.attributes or {}}
            for e in q.scalars().all()
        ]
    return texts, dom


async def gherkin_context(db: AsyncSession, g: GherkinScenario) -> tuple[dict, Optional[str]]:
    q = await db.execute(
        select(UserStory).where(UserStory.id == g.story_id, UserStory.project_id == g.project_id)
    )
    story = q.scalar_one_or_none()
    story_dict = {
        "id": g.story_id,
        "actor": story.actor if story else "",
        "action": story.action if story else "",
        "goal": story.goal if story else "",
        "acceptance_criteria": _parse_criteria(story.acceptance_criteria) if story else [],
    }
    url_q = await db.execute(
        select(TestSuite.url).where(TestSuite.project_id == g.project_id).order_by(desc(TestSuite.created_at)).limit(1)
    )
    url = url_q.scalar()
    if not url:
        dom_q = await db.execute(select(DomElement.url).where(DomElement.project_id == g.project_id).limit(1))
        url = dom_q.scalar()
    return story_dict, url


# ─── Validation runs ─────────────────────────────────────────────────────────

async def validate_suite(
    db: AsyncSession, suite: TestSuite, *, parent_report_id: Optional[str] = None, use_llm: bool = True
) -> ValidationReport:
    t0 = time.perf_counter()
    gherkin_texts, dom = await suite_context(db, suite)

    static_findings = static_checks.check_suite_code(
        suite.code, framework=suite.framework, mode=suite.mode, url=suite.url,
        gherkin_texts=gherkin_texts, dom_elements=dom or None,
    )

    judge: Optional[dict] = None
    judge_error: Optional[str] = None
    if use_llm:
        try:
            judge = await judge_suite(
                code=suite.code, framework=suite.framework, mode=suite.mode, url=suite.url,
                gherkin_texts=gherkin_texts, dom_elements=dom or None, static_findings=static_findings,
            )
        except ValidatorUnavailable as e:
            judge_error = str(e)
        except Exception as e:  # network / parse failures must not block the deterministic result
            logger.exception("LLM judge failed for suite %s", suite.id)
            judge_error = f"{type(e).__name__}: {e}"[:300]

    scoring = compute_score(static_findings, judge)
    findings = sort_findings(static_findings + (judge["findings"] if judge else []))
    if judge_error:
        findings.append(Finding("info", "validator", "LLM judge unavailable",
                                f"Score is based on deterministic checks only. {judge_error}", source="static", fixable=False))

    report = ValidationReport(
        id=uuid.uuid4(),
        project_id=suite.project_id,
        target_type="suite",
        target_id=suite.id,
        content_hash=content_hash(suite.code),
        framework=suite.framework,
        score=scoring["score"],
        verdict=scoring["verdict"],
        static_score=scoring["static_score"],
        llm_score=scoring["llm_score"],
        scenario_total=scoring["scenario_total"] or len(static_checks.scenario_titles(gherkin_texts)),
        scenario_pass_predicted=scoring["scenario_pass_predicted"],
        summary=(judge["summary"] if judge else _static_summary(static_findings)),
        findings=[f.to_dict() for f in findings],
        scenarios=(judge["scenarios"] if judge else []),
        breakdown={**scoring["breakdown"], "strengths": (judge or {}).get("strengths", []),
                   "dom_elements": len(dom), "gherkin_features": len(gherkin_texts)},
        validator_provider=(judge or {}).get("provider"),
        validator_model=(judge or {}).get("model"),
        duration_ms=int((time.perf_counter() - t0) * 1000),
        parent_report_id=uuid.UUID(parent_report_id) if parent_report_id else None,
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)
    return report


async def validate_gherkin(
    db: AsyncSession, g: GherkinScenario, *, parent_report_id: Optional[str] = None, use_llm: bool = True
) -> ValidationReport:
    t0 = time.perf_counter()
    story, url = await gherkin_context(db, g)
    static_findings = static_checks.check_gherkin(g.gherkin_text, story["acceptance_criteria"])

    judge: Optional[dict] = None
    judge_error: Optional[str] = None
    if use_llm:
        try:
            judge = await judge_gherkin(gherkin_text=g.gherkin_text, story=story, url=url, static_findings=static_findings)
        except ValidatorUnavailable as e:
            judge_error = str(e)
        except Exception as e:
            logger.exception("LLM judge failed for gherkin %s", g.id)
            judge_error = f"{type(e).__name__}: {e}"[:300]

    scoring = compute_score(static_findings, judge)
    findings = sort_findings(static_findings + (judge["findings"] if judge else []))
    if judge_error:
        findings.append(Finding("info", "validator", "LLM judge unavailable",
                                f"Score is based on deterministic checks only. {judge_error}", source="static", fixable=False))

    parsed = static_checks.parse_gherkin(g.gherkin_text)
    report = ValidationReport(
        id=uuid.uuid4(),
        project_id=g.project_id,
        target_type="gherkin",
        target_id=g.id,
        content_hash=content_hash(g.gherkin_text),
        framework=None,
        score=scoring["score"],
        verdict=scoring["verdict"],
        static_score=scoring["static_score"],
        llm_score=scoring["llm_score"],
        scenario_total=scoring["scenario_total"] or len(parsed.scenarios),
        scenario_pass_predicted=scoring["scenario_pass_predicted"],
        summary=(judge["summary"] if judge else _static_summary(static_findings)),
        findings=[f.to_dict() for f in findings],
        scenarios=(judge["scenarios"] if judge else []),
        breakdown={**scoring["breakdown"], "strengths": (judge or {}).get("strengths", []),
                   "coverage": (judge or {}).get("coverage", []), "story": story},
        validator_provider=(judge or {}).get("provider"),
        validator_model=(judge or {}).get("model"),
        duration_ms=int((time.perf_counter() - t0) * 1000),
        parent_report_id=uuid.UUID(parent_report_id) if parent_report_id else None,
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)
    return report


def _static_summary(findings: list[Finding]) -> str:
    counts = count_by_severity(findings)
    if not findings:
        return "Deterministic checks found no structural problems."
    return (f"Deterministic checks found {counts['critical']} critical, {counts['major']} major and "
            f"{counts['minor']} minor issue(s).")


# ─── Queries ─────────────────────────────────────────────────────────────────

async def latest_report(db: AsyncSession, target_type: str, target_id) -> Optional[ValidationReport]:
    q = await db.execute(
        select(ValidationReport)
        .where(ValidationReport.target_type == target_type, ValidationReport.target_id == target_id)
        .order_by(desc(ValidationReport.created_at))
        .limit(1)
    )
    return q.scalar_one_or_none()


async def project_latest(db: AsyncSession, project_id, target_type: str) -> list[ValidationReport]:
    """Latest report per target for the project."""
    q = await db.execute(
        select(ValidationReport)
        .where(ValidationReport.project_id == project_id, ValidationReport.target_type == target_type)
        .order_by(ValidationReport.target_id, desc(ValidationReport.created_at))
    )
    seen: set = set()
    out: list[ValidationReport] = []
    for r in q.scalars().all():
        if r.target_id in seen:
            continue
        seen.add(r.target_id)
        out.append(r)
    return out


async def project_summary(db: AsyncSession, project_id) -> dict:
    suites = await project_latest(db, project_id, "suite")
    gherkins = await project_latest(db, project_id, "gherkin")

    def agg(reports: list[ValidationReport]) -> dict:
        if not reports:
            return {"count": 0, "avg_score": None, "verdicts": {}}
        verdicts: dict[str, int] = {}
        for r in reports:
            verdicts[r.verdict] = verdicts.get(r.verdict, 0) + 1
        return {"count": len(reports), "avg_score": round(sum(r.score for r in reports) / len(reports)), "verdicts": verdicts}

    # Calibration: predicted (validator) vs actual (latest finished execution of that suite).
    calibration: list[dict] = []
    for r in suites:
        ex_q = await db.execute(
            select(TestRunExecution)
            .where(
                TestRunExecution.suite_id == r.target_id,
                TestRunExecution.total_count > 0,
                TestRunExecution.status.in_(["passed", "failed", "error"]),
            )
            .order_by(desc(TestRunExecution.started_at))
            .limit(1)
        )
        ex = ex_q.scalar_one_or_none()
        if not ex:
            continue
        actual = round(100 * ex.passed_count / ex.total_count) if ex.total_count else None
        predicted = (
            round(100 * r.scenario_pass_predicted / r.scenario_total) if r.scenario_total else r.score
        )
        calibration.append({
            "suite_id": str(r.target_id),
            "framework": r.framework,
            "predicted_pass_rate": predicted,
            "validator_score": r.score,
            "actual_pass_rate": actual,
            "executed_at": ex.finished_at.isoformat() if ex.finished_at else (ex.started_at.isoformat() if ex.started_at else None),
            "execution_id": str(ex.id),
        })
    errors = [abs(c["predicted_pass_rate"] - c["actual_pass_rate"]) for c in calibration if c["actual_pass_rate"] is not None]
    return {
        "suites": agg(suites),
        "gherkin": agg(gherkins),
        "calibration": calibration,
        "calibration_mae": (round(sum(errors) / len(errors), 1) if errors else None),
        "independent_model": is_independent_model(),
    }
