from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional
import uuid

SEVERITY_ORDER = {"critical": 0, "major": 1, "minor": 2, "info": 3}
PENALTY = {"critical": 25, "major": 10, "minor": 3, "info": 0}


@dataclass
class Finding:
    severity: str                      # critical | major | minor | info
    category: str                      # short slug, e.g. "syntax", "coverage"
    title: str
    detail: str
    source: str = "static"             # static | llm
    line: Optional[int] = None
    snippet: Optional[str] = None
    suggestion: Optional[str] = None
    fixable: bool = True
    scenario: Optional[str] = None
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])

    def __post_init__(self) -> None:
        if self.severity not in SEVERITY_ORDER:
            self.severity = "minor"

    def to_dict(self) -> dict:
        return asdict(self)


def sort_findings(findings: list[Finding]) -> list[Finding]:
    return sorted(findings, key=lambda f: (SEVERITY_ORDER[f.severity], f.line or 10**9, f.title))


def static_score(findings: list[Finding]) -> int:
    """100 minus a fixed penalty per deterministic finding, floored at 0."""
    penalty = sum(PENALTY[f.severity] for f in findings if f.source == "static")
    return max(0, 100 - penalty)


def count_by_severity(findings: list[Finding] | list[dict]) -> dict[str, int]:
    out = {k: 0 for k in SEVERITY_ORDER}
    for f in findings:
        sev = f["severity"] if isinstance(f, dict) else f.severity
        out[sev] = out.get(sev, 0) + 1
    return out
