"""
LLM-assisted repair of validated artefacts.

The fixer is given the artefact plus the findings (static + judge) and must
return the minimally changed artefact that resolves them, together with a
change log mapping each edit back to a finding id. The reply format uses
explicit markers instead of JSON so large code bodies survive intact.
Deterministic repairs (sanitizer) are applied afterwards as a safety net.
"""
from __future__ import annotations

import re
from typing import Optional

from app.code_gen.sanitizer import sanitize_generated_suite
from app.validation.findings import Finding
from app.validation.judge import SAUCEDEMO_FACTS
from app.validation.llm_client import call_llm, extract_json, numbered, strip_fences

FIX_SYSTEM = (
    "You are a senior QA automation engineer repairing a generated test suite after an independent "
    "review. Make the smallest set of edits that resolves the listed findings. Preserve everything "
    "that is already correct, keep the same framework, file layout and test names unless a finding "
    "requires otherwise, and do not add scenarios that are not in the Gherkin. Follow the reply "
    "format exactly."
)

GHERKIN_FIX_SYSTEM = (
    "You are a senior BDD analyst repairing Gherkin scenarios after an independent review. Make the "
    "smallest edits that resolve the findings while keeping the scenarios faithful to the user story. "
    "Follow the reply format exactly."
)

CODE_MARK = "=====CODE====="
CHANGES_MARK = "=====CHANGES====="
END_MARK = "=====END====="


def _findings_block(findings: list[Finding | dict]) -> str:
    rows = []
    for f in findings:
        d = f if isinstance(f, dict) else f.to_dict()
        rows.append(
            f"- id={d['id']} [{d['severity']}] {d['title']}"
            + (f" (line {d['line']})" if d.get("line") else "")
            + f"\n    problem: {d['detail']}"
            + (f"\n    suggestion: {d['suggestion']}" if d.get("suggestion") else "")
        )
    return "\n".join(rows) or "(none)"


def _parse_marked(text: str) -> tuple[str, list[dict]]:
    body = text
    if CODE_MARK not in body or CHANGES_MARK not in body:
        # Fallback: treat the whole reply as code with no change log.
        return strip_fences(body), []
    code_part = body.split(CODE_MARK, 1)[1].split(CHANGES_MARK, 1)[0]
    changes_part = body.split(CHANGES_MARK, 1)[1]
    if END_MARK in changes_part:
        changes_part = changes_part.split(END_MARK, 1)[0]
    code = strip_fences(code_part.strip("\n"))
    changes: list[dict] = []
    try:
        data = extract_json("{\"changes\": " + changes_part.strip() + "}") if changes_part.strip().startswith("[") else extract_json(changes_part)
        raw = data.get("changes") if isinstance(data, dict) else data
        for c in raw or []:
            if isinstance(c, dict):
                changes.append({
                    "finding_id": str(c.get("finding_id", ""))[:16] or None,
                    "description": str(c.get("description", ""))[:400],
                    "line": c.get("line"),
                })
    except Exception:
        for line in changes_part.splitlines():
            line = line.strip(" -*")
            if line:
                changes.append({"finding_id": None, "description": line[:400], "line": None})
    return code, changes


def _framework_rules(framework: str, url: str) -> str:
    rules = [
        "- Tests must run headless in Linux CI (never headless=False).",
        "- Never call one test function from another; share steps through helper functions.",
        "- Every test must end with at least one assertion of the Then-step outcome.",
    ]
    if framework == "playwright":
        rules.append("- Python + pytest + playwright.sync_api; use a fresh page per test.")
    elif framework == "selenium":
        rules.append("- Python + pytest + Selenium WebDriver; headless Chrome options.")
    else:
        rules.append("- JavaScript Cypress spec (describe/it, cy.visit, cy.get, .should).")
    return "\n".join(rules) + ("\n\n" + SAUCEDEMO_FACTS if "saucedemo.com" in (url or "").lower() else "")


async def fix_suite(
    *,
    code: str,
    framework: str,
    mode: str,
    url: str,
    gherkin_texts: list[str],
    dom_elements: Optional[list[dict]],
    findings: list[Finding | dict],
) -> dict:
    dom_rows = "\n".join(
        f"- role={e.get('role','')} selector={e.get('selector','')} tag={e.get('tag','')}"
        for e in (dom_elements or [])[:120]
    ) or "(no crawled DOM map available)"
    dom_rows = (
        "NOTE: this map is PARTIAL (only crawled pages). Listed selectors are confirmed to exist; selectors "
        "NOT listed are unverified, not wrong. Keep an existing selector unless a finding gives a confirmed "
        "replacement from the facts above or from this map for the SAME element. Never swap a selector for an "
        "unrelated element (e.g. a login field for a checkout field).\n" + dom_rows
    )
    features = "\n\n".join(gherkin_texts)
    prompt = f"""Framework: {framework} | Mode: {mode} | Target URL: {url}

Rules the repaired suite must satisfy:
{_framework_rules(framework, url)}

Gherkin scenarios (source of truth for scope and expected behaviour):
{features}

Crawled DOM element map:
{dom_rows}

Findings to resolve (each has an id):
{_findings_block(findings)}

Current suite (line-numbered for reference; return the code WITHOUT line numbers):
{numbered(code)}

Reply in exactly this format and nothing else:
{CODE_MARK}
<the complete repaired source file, raw text, no markdown fences>
{CHANGES_MARK}
[{{"finding_id": "<id or null>", "line": <int or null>, "description": "<what you changed and why>"}}]
{END_MARK}"""

    text, provider, model = await call_llm(prompt, system=FIX_SYSTEM, max_tokens=8192)
    fixed, changes = _parse_marked(text)
    if not fixed.strip():
        raise ValueError("Fixer returned empty code")

    fixed, repairs = sanitize_generated_suite(fixed, framework=framework, url=url)
    for r in repairs:
        changes.append({"finding_id": None, "line": None, "description": f"Deterministic repair: {r}"})

    return {"code": fixed, "changes": changes, "provider": provider, "model": model}


async def fix_gherkin(
    *,
    gherkin_text: str,
    story: dict,
    url: Optional[str],
    findings: list[Finding | dict],
) -> dict:
    criteria = "\n".join(f"- {c}" for c in (story.get("acceptance_criteria") or [])) or "(none)"
    prompt = f"""User story:
  As a {story.get('actor','')}, I want to {story.get('action','')}, so that {story.get('goal','')}.
Acceptance criteria:
{criteria}
Target application: {url or "(unknown)"}
{SAUCEDEMO_FACTS if "saucedemo.com" in (url or "").lower() else ""}
Findings to resolve (each has an id):
{_findings_block(findings)}

Current Gherkin (line-numbered for reference; return it WITHOUT line numbers):
{numbered(gherkin_text)}

Rules: keep the Feature header, keep existing scenario titles when they are still accurate, make every
Then step name a concrete observable (exact text, URL, visibility, count), add scenarios only for
uncovered acceptance criteria, and never invent application behaviour that contradicts the facts above.

Reply in exactly this format and nothing else:
{CODE_MARK}
<the complete repaired .feature text, raw, no markdown fences>
{CHANGES_MARK}
[{{"finding_id": "<id or null>", "line": <int or null>, "description": "<what you changed and why>"}}]
{END_MARK}"""

    text, provider, model = await call_llm(prompt, system=GHERKIN_FIX_SYSTEM, max_tokens=4096)
    fixed, changes = _parse_marked(text)
    if not fixed.strip():
        raise ValueError("Fixer returned empty Gherkin")
    # Normalise stray leading pipes/numbering the model might echo.
    fixed = re.sub(r"^\s*\d+\s*\|\s?", "", fixed, flags=re.M) if re.search(r"^\s*\d+\s*\|", fixed, re.M) else fixed
    return {"text": fixed, "changes": changes, "provider": provider, "model": model}
