"""
Inference for the risk-prediction model.

Two responsibilities:
  1. Lazy-load the trained model from disk (single instance per process).
  2. Extract per-flow features from the live DB and score them.

If the model file is missing (no train run yet), `predict_for_project` falls
back to a deterministic heuristic so the UI never breaks — the response just
carries `source: "heuristic"` instead of `"model"` so the frontend can flag it.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from pathlib import Path
from typing import Optional

import joblib
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ml.features import (
    FEATURE_COLUMNS,
    FLOW_BUCKETS,
    FLOW_DISPLAY,
    FlowFeatures,
    RISK_CLASSES,
    bucket_for_label,
)
from app.models import (
    DomElement,
    GherkinScenario,
    TestRun,
    TestSuite,
    UserStory,
)

_MODEL_PATH = Path(__file__).parent / "data" / "model.pkl"
_cached_bundle: Optional[dict] = None


def _load_model() -> Optional[dict]:
    """Return the bundle dict {model, feature_columns, classes} or None."""
    global _cached_bundle
    if _cached_bundle is not None:
        return _cached_bundle
    if not _MODEL_PATH.exists():
        return None
    _cached_bundle = joblib.load(_MODEL_PATH)
    return _cached_bundle


def reset_cache() -> None:
    """Force the next call to re-read model.pkl. Useful after retraining."""
    global _cached_bundle
    _cached_bundle = None


# ─── Feature extraction from the live DB ──────────────────────────────────────

_AUTH_KEYWORDS = ("login", "log in", "sign in", "signin", "auth", "password")
_PAYMENT_KEYWORDS = ("payment", "pay", "checkout", "billing", "credit card")
_FORM_KEYWORDS = ("fill", "enter", "type", "input")


def _scenario_label(s: GherkinScenario) -> str:
    """Best-effort label used to decide which bucket a scenario belongs to."""
    return f"{s.feature_name or ''} {s.gherkin_text or ''}"


def _count_keywords(text: str, keywords: tuple[str, ...]) -> int:
    lower = text.lower()
    return sum(1 for kw in keywords if kw in lower)


def _scenario_metrics(text: str) -> dict[str, float]:
    """Cheap text-derived metrics: step count, has_auth, has_payment, etc."""
    lower = text.lower()
    n_steps = sum(
        1
        for line in text.splitlines()
        if line.strip().lower().startswith(("given", "when", "then", "and", "but"))
    )
    return {
        "n_steps": float(n_steps),
        "has_auth": 1.0 if any(kw in lower for kw in _AUTH_KEYWORDS) else 0.0,
        "has_payment": 1.0 if any(kw in lower for kw in _PAYMENT_KEYWORDS) else 0.0,
        "has_form_input": 1.0 if any(kw in lower for kw in _FORM_KEYWORDS) else 0.0,
    }


def _code_metrics(suites: list[TestSuite]) -> dict[str, float]:
    """Aggregate counts from the project's generated test code."""
    if not suites:
        return {"n_assertions": 0.0, "n_waits": 0.0, "code_lines": 0.0}
    total_lines = 0
    total_asserts = 0
    total_waits = 0
    for s in suites:
        code = (s.code or "").lower()
        total_lines += len((s.code or "").splitlines())
        total_asserts += code.count("assert") + code.count("expect(")
        total_waits += code.count("wait") + code.count("sleep(")
    n = len(suites)
    return {
        "n_assertions": total_asserts / n,
        "n_waits": total_waits / n,
        "code_lines": total_lines / n,
    }


def _dom_metrics(elements: list[DomElement]) -> dict[str, float]:
    if not elements:
        return {
            "n_inputs": 0.0,
            "n_buttons": 0.0,
            "avg_dom_confidence": 0.5,
            "qa_edit_ratio": 0.0,
        }
    n_inputs = sum(1 for e in elements if (e.tag or "").upper() == "INPUT")
    n_buttons = sum(1 for e in elements if (e.tag or "").upper() == "BUTTON")
    confs = [float(e.confidence) for e in elements if e.confidence is not None]
    edited = sum(1 for e in elements if e.edited_by_qa)
    return {
        "n_inputs": float(n_inputs),
        "n_buttons": float(n_buttons),
        "avg_dom_confidence": statistics.mean(confs) if confs else 0.5,
        "qa_edit_ratio": edited / len(elements),
    }


def _run_metrics(runs: list[TestRun]) -> dict[str, float]:
    """Past pass rate / duration stats for a flow. Defaults assume optimism
    when there's no execution history yet (so the model leans LOW)."""
    if not runs:
        return {
            "past_pass_rate": 0.95,
            "past_runs": 0.0,
            "mean_duration_s": 1.5,
            "duration_stddev_s": 0.3,
        }
    passed = sum(1 for r in runs if r.status == "passed")
    durations_s = [(r.duration_ms or 0) / 1000.0 for r in runs if r.duration_ms]
    return {
        "past_pass_rate": passed / len(runs),
        "past_runs": float(len(runs)),
        "mean_duration_s": statistics.mean(durations_s) if durations_s else 1.5,
        "duration_stddev_s": statistics.stdev(durations_s) if len(durations_s) >= 2 else 0.3,
    }


def _priority_one_hot(priority: str) -> tuple[float, float, float]:
    p = (priority or "medium").lower()
    return (
        1.0 if p == "high" else 0.0,
        1.0 if p == "medium" else 0.0,
        1.0 if p == "low" else 0.0,
    )


async def extract_features_per_flow(
    db: AsyncSession, project_id: str
) -> dict[str, FlowFeatures]:
    """
    Build one FlowFeatures vector per FLOW_BUCKETS bucket, aggregating from
    user_stories + gherkin_scenarios + dom_elements + test_runs in the project.
    Empty buckets get a low-risk default vector.
    """
    sc_q = await db.execute(
        select(GherkinScenario).where(GherkinScenario.project_id == project_id)
    )
    scenarios = list(sc_q.scalars().all())

    story_q = await db.execute(
        select(UserStory).where(UserStory.project_id == project_id)
    )
    stories = {s.id: s for s in story_q.scalars().all()}

    suite_q = await db.execute(
        select(TestSuite).where(TestSuite.project_id == project_id)
    )
    suites = list(suite_q.scalars().all())

    dom_q = await db.execute(
        select(DomElement).where(DomElement.project_id == project_id)
    )
    dom_elements = list(dom_q.scalars().all())

    run_q = await db.execute(
        select(TestRun).where(TestRun.project_id == project_id)
    )
    runs = list(run_q.scalars().all())

    # Group everything by bucket
    scenarios_by_bucket: dict[str, list[GherkinScenario]] = defaultdict(list)
    for s in scenarios:
        scenarios_by_bucket[bucket_for_label(_scenario_label(s))].append(s)

    runs_by_bucket: dict[str, list[TestRun]] = defaultdict(list)
    for r in runs:
        bucket = r.flow_name if r.flow_name in FLOW_BUCKETS else bucket_for_label(r.scenario_name)
        runs_by_bucket[bucket].append(r)

    # Code + DOM stats are project-wide (we don't currently tag suites/elements
    # by flow). Real next-step is to crawl per-flow URLs and split these too.
    code_stats = _code_metrics(suites)
    dom_stats = _dom_metrics(dom_elements)

    out: dict[str, FlowFeatures] = {}
    for bucket in FLOW_BUCKETS:
        bucket_scenarios = scenarios_by_bucket.get(bucket, [])

        if bucket_scenarios:
            text_blob = "\n".join(s.gherkin_text or "" for s in bucket_scenarios)
            text_metrics = _scenario_metrics(text_blob)
            text_metrics["n_steps"] /= len(bucket_scenarios)  # average per scenario

            # Aggregate priority across the stories the scenarios came from.
            priorities = [
                stories[s.story_id].priority.value
                for s in bucket_scenarios
                if s.story_id in stories
            ]
            if priorities:
                # Most common priority wins.
                top = max(set(priorities), key=priorities.count)
                pri_h, pri_m, pri_l = _priority_one_hot(top)
            else:
                pri_h, pri_m, pri_l = (0.0, 1.0, 0.0)
        else:
            text_metrics = {"n_steps": 0.0, "has_auth": 0.0, "has_payment": 0.0, "has_form_input": 0.0}
            pri_h, pri_m, pri_l = (0.0, 0.0, 1.0)  # treat empty buckets as low-priority

        run_stats = _run_metrics(runs_by_bucket.get(bucket, []))

        out[bucket] = FlowFeatures(
            priority_high=pri_h,
            priority_medium=pri_m,
            priority_low=pri_l,
            n_steps=text_metrics["n_steps"],
            has_auth=text_metrics["has_auth"],
            has_payment=text_metrics["has_payment"],
            has_form_input=text_metrics["has_form_input"],
            n_inputs=dom_stats["n_inputs"],
            n_buttons=dom_stats["n_buttons"],
            avg_dom_confidence=dom_stats["avg_dom_confidence"],
            qa_edit_ratio=dom_stats["qa_edit_ratio"],
            n_assertions=code_stats["n_assertions"],
            n_waits=code_stats["n_waits"],
            code_lines=code_stats["code_lines"],
            past_pass_rate=run_stats["past_pass_rate"],
            past_runs=run_stats["past_runs"],
            mean_duration_s=run_stats["mean_duration_s"],
            duration_stddev_s=run_stats["duration_stddev_s"],
        )
    return out


# ─── Scoring ──────────────────────────────────────────────────────────────────

def _heuristic_score(f: FlowFeatures) -> tuple[str, float]:
    """Fallback used when no model is available — same threshold rule the
    synthetic dataset uses, so behaviour is consistent."""
    pr = f.past_pass_rate
    if pr < 0.75:
        return "HIGH", 0.85 - pr           # rough confidence proxy
    if pr < 0.92:
        return "MEDIUM", 0.6
    return "LOW", min(0.99, 0.5 + pr / 2)


def _score_with_model(bundle: dict, features: FlowFeatures) -> tuple[str, float, dict[str, float]]:
    model = bundle["model"]
    classes = list(bundle["classes"])
    row = [features.to_row()]
    proba = model.predict_proba(row)[0]
    idx = int(max(range(len(proba)), key=lambda i: proba[i]))
    label = str(classes[idx])
    confidence = float(proba[idx])
    proba_map = {str(c): float(p) for c, p in zip(classes, proba)}
    return label, confidence, proba_map


async def predict_for_project(db: AsyncSession, project_id: str) -> dict:
    """
    Score each FLOW_BUCKETS bucket for the given project.

    Returns:
        {
          "source": "model" | "heuristic",
          "model_classes": [...],
          "predictions": [
            {"flow": "login_flow", "label": "Login Flow",
             "risk": "HIGH", "confidence": 0.83,
             "probabilities": {"LOW": .., "MEDIUM": .., "HIGH": ..},
             "features": {...}}
          ]
        }
    """
    feature_map = await extract_features_per_flow(db, project_id)
    bundle = _load_model()
    source = "model" if bundle else "heuristic"

    predictions = []
    for bucket in FLOW_BUCKETS:
        feats = feature_map[bucket]
        if bundle:
            risk, conf, proba = _score_with_model(bundle, feats)
        else:
            risk, conf = _heuristic_score(feats)
            proba = {c: 0.0 for c in RISK_CLASSES}
            proba[risk] = round(conf, 4)
        predictions.append(
            {
                "flow": bucket,
                "label": FLOW_DISPLAY[bucket],
                "risk": risk,
                "confidence": round(conf, 4),
                "probabilities": {k: round(v, 4) for k, v in proba.items()},
                "features": feats.to_dict(),
            }
        )

    return {
        "source": source,
        "model_classes": [str(c) for c in bundle["classes"]] if bundle else list(RISK_CLASSES),
        "feature_columns": list(FEATURE_COLUMNS),
        "predictions": predictions,
    }
