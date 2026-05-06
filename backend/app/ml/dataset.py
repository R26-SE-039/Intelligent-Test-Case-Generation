"""
Synthesise a labelled training CSV for the risk model.

Why synthetic to start?
  - We have zero real test_runs in the DB on day 1, so a supervised classifier
    has nothing to learn from. Hand-crafted rules + Gaussian noise give the
    pipeline (feature extraction → fit → save → predict → API → UI) something
    end-to-end to validate against, and let us evaluate model code quality
    independently of data collection.
  - Once `test_runs` accumulates real rows, this script is replaced by a
    real-data extractor — same CSV schema, drop-in for train.py.

Generation strategy
  Per row, we sample one of the four flow buckets, draw plausible feature
  values from bucket-specific priors (e.g. checkout has more steps and lower
  pass rate than search), then *derive* the risk label from the resulting
  past_pass_rate with thresholded noise. This makes pass_rate the strongest
  signal — exactly what we'd expect from a real model — while still letting
  other features (qa_edit_ratio, has_payment, n_waits) provide secondary
  predictive power.

Run:  python -m app.ml.dataset --rows 2000 --out app/ml/data/training.csv
"""

from __future__ import annotations

import argparse
import csv
import random
from pathlib import Path
from typing import Callable

from app.ml.features import FEATURE_COLUMNS, FLOW_BUCKETS, RISK_CLASSES

# Per-bucket priors. Mean / std for each numeric feature, plus base pass rate.
# Tuned so that:
#   - login + checkout drift toward HIGH (high steps, payment, low pass rate)
#   - cart drifts toward MEDIUM
#   - search drifts toward LOW (few steps, high pass rate)
BUCKET_PRIORS: dict[str, dict] = {
    "login_flow": {
        "priority": ("high", 0.7),
        "n_steps": (8, 2),
        "has_auth": 1.0,
        "has_payment": 0.0,
        "has_form_input": 1.0,
        "n_inputs": (3, 1),
        "n_buttons": (1, 0.5),
        "avg_dom_confidence": (0.65, 0.10),
        "qa_edit_ratio": (0.35, 0.15),
        "n_assertions": (5, 2),
        "n_waits": (3, 1),
        "code_lines": (90, 25),
        "pass_rate": (0.78, 0.12),
        "past_runs": (40, 15),
        "mean_duration": (4.0, 1.2),
        "duration_stddev": (0.8, 0.4),
    },
    "cart_ops": {
        "priority": ("medium", 0.6),
        "n_steps": (6, 1.5),
        "has_auth": 0.4,
        "has_payment": 0.0,
        "has_form_input": 0.2,
        "n_inputs": (1, 0.8),
        "n_buttons": (3, 1),
        "avg_dom_confidence": (0.82, 0.08),
        "qa_edit_ratio": (0.15, 0.10),
        "n_assertions": (4, 1.5),
        "n_waits": (1, 0.8),
        "code_lines": (60, 15),
        "pass_rate": (0.88, 0.08),
        "past_runs": (30, 10),
        "mean_duration": (2.2, 0.8),
        "duration_stddev": (0.4, 0.2),
    },
    "checkout": {
        "priority": ("high", 0.85),
        "n_steps": (12, 3),
        "has_auth": 0.7,
        "has_payment": 1.0,
        "has_form_input": 1.0,
        "n_inputs": (5, 1.5),
        "n_buttons": (2, 1),
        "avg_dom_confidence": (0.58, 0.12),
        "qa_edit_ratio": (0.50, 0.18),
        "n_assertions": (8, 2.5),
        "n_waits": (4, 1.5),
        "code_lines": (130, 35),
        "pass_rate": (0.70, 0.13),
        "past_runs": (28, 12),
        "mean_duration": (6.5, 1.8),
        "duration_stddev": (1.3, 0.6),
    },
    "search": {
        "priority": ("low", 0.5),
        "n_steps": (3, 1),
        "has_auth": 0.05,
        "has_payment": 0.0,
        "has_form_input": 0.4,
        "n_inputs": (1, 0.5),
        "n_buttons": (1, 0.5),
        "avg_dom_confidence": (0.92, 0.05),
        "qa_edit_ratio": (0.05, 0.05),
        "n_assertions": (2, 1),
        "n_waits": (0, 0.5),
        "code_lines": (35, 12),
        "pass_rate": (0.96, 0.04),
        "past_runs": (55, 18),
        "mean_duration": (1.1, 0.5),
        "duration_stddev": (0.2, 0.15),
    },
}


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _sample_normal(mean: float, std: float, lo: float, hi: float) -> float:
    return _clamp(random.gauss(mean, std), lo, hi)


def _sample_int(mean: float, std: float, lo: int, hi: int) -> int:
    return int(round(_clamp(random.gauss(mean, std), lo, hi)))


def _sample_priority(prior: tuple[str, float]) -> tuple[float, float, float]:
    """One-hot priority with prob of `prior[0]` = `prior[1]`, rest split evenly."""
    label, p = prior
    if random.random() < p:
        chosen = label
    else:
        rest = [x for x in ("high", "medium", "low") if x != label]
        chosen = random.choice(rest)
    return (
        1.0 if chosen == "high" else 0.0,
        1.0 if chosen == "medium" else 0.0,
        1.0 if chosen == "low" else 0.0,
    )


def _label_from_pass_rate(pass_rate: float) -> str:
    """
    Threshold rule + light label noise so the classifier learns a soft, not
    razor-sharp, decision boundary. ~5% of rows get bumped one class up/down.
    """
    if pass_rate < 0.75:
        base = "HIGH"
    elif pass_rate < 0.92:
        base = "MEDIUM"
    else:
        base = "LOW"

    if random.random() < 0.05:
        idx = RISK_CLASSES.index(base)
        delta = random.choice([-1, 1])
        idx = _clamp(idx + delta, 0, len(RISK_CLASSES) - 1)
        return RISK_CLASSES[int(idx)]
    return base


def _sample_row(bucket: str) -> dict:
    p = BUCKET_PRIORS[bucket]
    pri_h, pri_m, pri_l = _sample_priority(p["priority"])

    pass_rate = _sample_normal(*p["pass_rate"], 0.30, 1.0)

    row = {
        "flow_bucket": bucket,
        "priority_high": pri_h,
        "priority_medium": pri_m,
        "priority_low": pri_l,
        "n_steps": _sample_int(*p["n_steps"], 1, 25),
        "has_auth": 1.0 if random.random() < p["has_auth"] else 0.0,
        "has_payment": 1.0 if random.random() < p["has_payment"] else 0.0,
        "has_form_input": 1.0 if random.random() < p["has_form_input"] else 0.0,
        "n_inputs": _sample_int(*p["n_inputs"], 0, 12),
        "n_buttons": _sample_int(*p["n_buttons"], 0, 8),
        "avg_dom_confidence": round(_sample_normal(*p["avg_dom_confidence"], 0.0, 1.0), 4),
        "qa_edit_ratio": round(_sample_normal(*p["qa_edit_ratio"], 0.0, 1.0), 4),
        "n_assertions": _sample_int(*p["n_assertions"], 0, 20),
        "n_waits": _sample_int(*p["n_waits"], 0, 12),
        "code_lines": _sample_int(*p["code_lines"], 5, 400),
        "past_pass_rate": round(pass_rate, 4),
        "past_runs": _sample_int(*p["past_runs"], 0, 200),
        "mean_duration_s": round(_sample_normal(*p["mean_duration"], 0.1, 30.0), 3),
        "duration_stddev_s": round(_sample_normal(*p["duration_stddev"], 0.0, 10.0), 3),
        "risk_label": _label_from_pass_rate(pass_rate),
    }
    return row


def synthesize(n_rows: int, seed: int | None = 42) -> list[dict]:
    """Generate `n_rows` synthetic training examples balanced across buckets."""
    if seed is not None:
        random.seed(seed)
    rows: list[dict] = []
    buckets = list(FLOW_BUCKETS)
    for i in range(n_rows):
        bucket = buckets[i % len(buckets)]   # round-robin → balanced classes
        rows.append(_sample_row(bucket))
    random.shuffle(rows)
    return rows


def write_csv(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["flow_bucket", *FEATURE_COLUMNS, "risk_label"]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Synthesise risk-prediction training data.")
    parser.add_argument("--rows", type=int, default=2000, help="Number of rows to generate.")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).parent / "data" / "training.csv",
        help="Output CSV path.",
    )
    parser.add_argument("--seed", type=int, default=42, help="RNG seed (use --seed -1 for random).")
    args = parser.parse_args(argv)

    seed = None if args.seed == -1 else args.seed
    rows = synthesize(args.rows, seed=seed)
    write_csv(rows, args.out)

    counts: dict[str, int] = {}
    for r in rows:
        counts[r["risk_label"]] = counts.get(r["risk_label"], 0) + 1
    print(f"Wrote {len(rows)} rows -> {args.out}")
    print(f"Class distribution: {counts}")


if __name__ == "__main__":
    main()
