"""
Feature engineering for risk prediction.

Single source of truth for:
  - the four flow buckets surfaced in the UI
  - keyword rules that map a scenario name → bucket
  - the ordered list of feature columns the model is trained on

Both the synthetic dataset generator and the live inference path import from
here, so the model's input shape can never drift between train and serve.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Iterable

# Flow buckets shown in the Code Review "ML Risk Prediction" panel.
FLOW_BUCKETS: tuple[str, ...] = ("login_flow", "cart_ops", "checkout", "search")

# Human-readable label for each bucket — what the UI renders.
FLOW_DISPLAY: dict[str, str] = {
    "login_flow": "Login Flow",
    "cart_ops": "Cart Operations",
    "checkout": "Checkout",
    "search": "Search",
}

# Keyword → bucket mapping. First match wins; everything else falls into "search"
# as a low-risk default. Order matters: more specific terms first.
_BUCKET_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("checkout", ("checkout", "payment", "pay", "order", "billing", "shipping")),
    ("cart_ops", ("cart", "add to cart", "remove from cart", "basket", "wishlist")),
    ("login_flow", ("login", "log in", "sign in", "signin", "auth", "logout", "password")),
    ("search", ("search", "filter", "browse", "view", "list", "find")),
)

# Ordered feature columns. The model is trained and served on this exact order.
FEATURE_COLUMNS: tuple[str, ...] = (
    "priority_high",
    "priority_medium",
    "priority_low",
    "n_steps",
    "has_auth",
    "has_payment",
    "has_form_input",
    "n_inputs",
    "n_buttons",
    "avg_dom_confidence",
    "qa_edit_ratio",
    "n_assertions",
    "n_waits",
    "code_lines",
    "past_pass_rate",
    "past_runs",
    "mean_duration_s",
    "duration_stddev_s",
)

# Class labels — kept as strings so they round-trip through JSON cleanly.
RISK_CLASSES: tuple[str, ...] = ("LOW", "MEDIUM", "HIGH")


@dataclass
class FlowFeatures:
    """
    Per-flow feature vector. Field order MUST match FEATURE_COLUMNS so
    `to_row()` produces a stable input for the model.
    """
    priority_high: float
    priority_medium: float
    priority_low: float
    n_steps: float
    has_auth: float
    has_payment: float
    has_form_input: float
    n_inputs: float
    n_buttons: float
    avg_dom_confidence: float
    qa_edit_ratio: float
    n_assertions: float
    n_waits: float
    code_lines: float
    past_pass_rate: float
    past_runs: float
    mean_duration_s: float
    duration_stddev_s: float

    def to_row(self) -> list[float]:
        """Return values in FEATURE_COLUMNS order."""
        d = asdict(self)
        return [float(d[c]) for c in FEATURE_COLUMNS]

    def to_dict(self) -> dict[str, float]:
        return {c: float(v) for c, v in asdict(self).items()}


def bucket_for_label(label: str) -> str:
    """
    Map a free-form scenario / story / feature label to one of FLOW_BUCKETS.
    Defaults to 'search' when no keyword matches — keeps "long tail" features
    from polluting the high-risk buckets.
    """
    text = (label or "").lower()
    for bucket, keywords in _BUCKET_KEYWORDS:
        if any(kw in text for kw in keywords):
            return bucket
    return "search"


def bucket_many(labels: Iterable[str]) -> dict[str, list[str]]:
    """Group labels by bucket. Useful for aggregating scenarios per flow."""
    out: dict[str, list[str]] = {b: [] for b in FLOW_BUCKETS}
    for lbl in labels:
        out[bucket_for_label(lbl)].append(lbl)
    return out
