"""
LLM judge — an independent reviewer that did NOT write the artefact.

The judge receives the Gherkin, the generated code (line-numbered), the
crawled DOM map and the deterministic findings already discovered, and returns
a structured prediction: per-scenario pass/fail, a holistic pass probability,
and concrete findings with line numbers and suggested fixes.

Static findings are passed in so the judge concentrates on behavioural and
semantic problems (wrong flow, wrong expected text, missing login, wrong
assertion target) instead of re-reporting syntax.
"""
from __future__ import annotations

import json
from typing import Optional

from app.validation.findings import Finding
from app.validation.llm_client import call_llm, extract_json, numbered

JUDGE_SYSTEM = (
    "You are an independent senior QA automation reviewer. You did NOT write the code you are "
    "reviewing and you must not trust it. Your job is to predict, as accurately as possible, "
    "whether each generated test will PASS when executed headlessly in CI against the real "
    "application, and to list the concrete defects that would make it fail or make it vacuous. "
    "Be specific: cite line numbers and the exact wrong value. Never invent problems; when the "
    "code is correct say so. Reply with a single JSON object and nothing else."
)

SAUCEDEMO_FACTS = (
    "Known facts about saucedemo.com (use them as ground truth; they override any gap in the crawled map):\n"
    "- Login page selectors that definitely exist: #user-name, #password, #login-button, [data-test='error'] "
    "(also .error-message-container). Inventory page: .inventory_list, .inventory_item, .inventory_item_name, "
    ".shopping_cart_link, .shopping_cart_badge, .product_sort_container. Cart/checkout: .cart_item, #checkout, "
    "#first-name, #last-name, #postal-code, #continue, #finish, .summary_info, .complete-header.\n"
    "- Valid login standard_user/secret_sauce lands on /inventory.html. Direct navigation to any "
    "post-login page without logging in redirects to the login page.\n"
    "- Invalid login error text: 'Epic sadface: Username and password do not match any user in this service'.\n"
    "- Locked out user error text starts with 'Epic sadface: Sorry, this user has been locked out.'\n"
    "- Add-to-cart buttons are #add-to-cart-<item-slug> and toggle to #remove-<item-slug> after one click.\n"
    "- .shopping_cart_badge is absent (not '0') when the cart is empty. Cart link: .shopping_cart_link.\n"
    "- Checkout: #checkout -> step one (#first-name, #last-name, #postal-code, #continue) -> step two "
    "(#finish) -> .complete-header 'Thank you for your order!'. Missing postal code error: "
    "'Error: Postal Code is required'. Missing first name: 'Error: First Name is required'.\n"
    "- Sorting select: .product_sort_container with values az, za, lohi, hilo.\n"
)


def _facts_for(url: str) -> str:
    return SAUCEDEMO_FACTS if "saucedemo.com" in (url or "").lower() else ""


DOM_CAVEAT = (
    "IMPORTANT: the crawled map is PARTIAL — it only lists elements on the pages the crawler visited. "
    "A selector that is absent from the map is UNVERIFIED, not wrong. Treat it as a real defect only when "
    "the known application facts above contradict it or the selector is clearly malformed/invented. "
    "Never claim a selector 'does not exist' solely because it is missing from this map.\n"
)


def _dom_block(dom_elements: Optional[list[dict]]) -> str:
    if not dom_elements:
        return "(no crawled DOM map available)"
    rows = [DOM_CAVEAT]
    for e in dom_elements[:120]:
        rows.append(f"- role={e.get('role','')} selector={e.get('selector','')} tag={e.get('tag','')}"
                    + (f" text={e.get('text')!r}" if e.get("text") else ""))
    return "\n".join(rows)


def _static_block(static_findings: list[Finding]) -> str:
    if not static_findings:
        return "(none)"
    return "\n".join(
        f"- [{f.severity}] {f.title}" + (f" (line {f.line})" if f.line else "") + f": {f.detail}"
        for f in static_findings
    )


def _clamp(v, lo=0, hi=100, default=0) -> int:
    try:
        return int(max(lo, min(hi, round(float(v)))))
    except Exception:
        return default


def _norm_findings(raw: list, code_lines: int) -> list[Finding]:
    out: list[Finding] = []
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        line = item.get("line")
        try:
            line = int(line) if line is not None else None
            if line is not None and not (1 <= line <= max(code_lines, 1)):
                line = None
        except Exception:
            line = None
        out.append(Finding(
            severity=str(item.get("severity", "minor")).lower(),
            category=str(item.get("category", "behaviour"))[:40],
            title=str(item.get("title", "Issue"))[:140],
            detail=str(item.get("detail", ""))[:1200],
            source="llm",
            line=line,
            snippet=(str(item.get("snippet"))[:300] if item.get("snippet") else None),
            suggestion=(str(item.get("suggestion"))[:600] if item.get("suggestion") else None),
            fixable=bool(item.get("fixable", True)),
            scenario=(str(item.get("scenario"))[:200] if item.get("scenario") else None),
        ))
    return out


async def judge_suite(
    *,
    code: str,
    framework: str,
    mode: str,
    url: str,
    gherkin_texts: list[str],
    dom_elements: Optional[list[dict]],
    static_findings: list[Finding],
) -> dict:
    features = "\n\n".join(f"--- Feature {i+1} ---\n{t}" for i, t in enumerate(gherkin_texts))
    prompt = f"""Framework: {framework}
Generation mode: {"DOM-aware (selectors should come from the crawled map below)" if mode == "dom" else "Abstract (placeholder locators are expected and should not be penalised)"}
Target URL: {url}

{_facts_for(url)}
Gherkin scenarios the suite must implement:
{features}

Crawled DOM element map:
{_dom_block(dom_elements)}

Deterministic checks already flagged these (do NOT repeat them, build on them):
{_static_block(static_findings)}

Generated test suite (line-numbered):
{numbered(code)}

Evaluate every Gherkin scenario. For each one decide whether a test implements it and whether that
test will PASS against the real application in headless CI. Look especially for: wrong expected
strings/URLs, missing login before protected pages, invented or malformed selectors, assertions that
cannot fail, wrong flow order (e.g. finishing checkout without #finish), fixture misuse, non-isolated
tests, and steps from the Gherkin that are silently skipped. Read each Gherkin scenario carefully and
judge the test against what THAT scenario says (e.g. a 'successful checkout' scenario fills every field;
only a 'missing postal code' scenario leaves it empty). Do not penalise a test for a selector merely
because the crawled map omits it; a selector named in the known application facts IS verified.

Severity scale (apply strictly): critical = the file will not import/collect or most tests fail for one
root cause; major = one specific test will fail or is vacuous; minor = fragile, unverified or stylistic
but likely to pass; info = observation. A scenario with no implementing test is one `major` finding.

Return ONLY this JSON:
{{
  "pass_probability": <0-100 integer: probability the whole suite passes as-is>,
  "summary": "<2-3 sentence verdict a QA lead can read>",
  "scenarios": [
    {{"title": "<Gherkin scenario title>", "test_name": "<implementing test or null>",
      "implemented": true|false, "predicted": "pass"|"fail"|"uncertain",
      "confidence": <0-100>, "reason": "<one sentence>"}}
  ],
  "findings": [
    {{"severity": "critical"|"major"|"minor"|"info", "category": "<slug>", "title": "<short>",
      "detail": "<what is wrong and why it fails>", "line": <int or null>, "snippet": "<offending code or null>",
      "suggestion": "<concrete fix>", "fixable": true|false, "scenario": "<scenario title or null>"}}
  ],
  "strengths": ["<things done right>"]
}}"""

    text, provider, model = await call_llm(prompt, system=JUDGE_SYSTEM, max_tokens=4096)
    data = extract_json(text)

    code_lines = len(code.splitlines())
    scenarios = []
    for s in data.get("scenarios") or []:
        if not isinstance(s, dict):
            continue
        predicted = str(s.get("predicted", "uncertain")).lower()
        if predicted not in ("pass", "fail", "uncertain"):
            predicted = "uncertain"
        scenarios.append({
            "title": str(s.get("title", ""))[:200],
            "test_name": (str(s.get("test_name"))[:120] if s.get("test_name") else None),
            "implemented": bool(s.get("implemented", True)),
            "predicted": predicted,
            "confidence": _clamp(s.get("confidence", 50), default=50),
            "reason": str(s.get("reason", ""))[:400],
        })

    return {
        "pass_probability": _clamp(data.get("pass_probability", 0)),
        "summary": str(data.get("summary", ""))[:1500],
        "scenarios": scenarios,
        "findings": _norm_findings(data.get("findings") or [], code_lines),
        "strengths": [str(x)[:200] for x in (data.get("strengths") or [])][:8],
        "provider": provider,
        "model": model,
    }


GHERKIN_JUDGE_SYSTEM = (
    "You are an independent BDD reviewer and senior QA analyst. You did NOT write these scenarios. "
    "Judge whether they are correct, complete and automatable for the given user story, and whether "
    "a test generated from them could pass against the real application. Reply with a single JSON "
    "object and nothing else."
)


async def judge_gherkin(
    *,
    gherkin_text: str,
    story: dict,
    url: Optional[str],
    static_findings: list[Finding],
) -> dict:
    criteria = story.get("acceptance_criteria") or []
    criteria_block = "\n".join(f"- {c}" for c in criteria) or "(none provided)"
    prompt = f"""User story:
  As a {story.get('actor','')}, I want to {story.get('action','')}, so that {story.get('goal','')}.
Acceptance criteria:
{criteria_block}
Target application: {url or "(unknown)"}

{_facts_for(url or "")}
Deterministic checks already flagged these (do NOT repeat them):
{_static_block(static_findings)}

Gherkin under review (line-numbered):
{numbered(gherkin_text)}

Assess each scenario for: correctness against the story and the application facts, testability
(every Then step names an observable), completeness (happy path + key negative paths from the
acceptance criteria), independence (no hidden dependency on another scenario), and automatability.

Return ONLY this JSON:
{{
  "quality_score": <0-100 integer: how likely a test generated from this Gherkin passes and genuinely verifies the story>,
  "summary": "<2-3 sentences>",
  "scenarios": [
    {{"title": "<scenario title>", "predicted": "pass"|"fail"|"uncertain", "confidence": <0-100>,
      "testable": true|false, "reason": "<one sentence>"}}
  ],
  "coverage": [ {{"criterion": "<acceptance criterion>", "covered": true|false, "scenario": "<title or null>"}} ],
  "findings": [
    {{"severity": "critical"|"major"|"minor"|"info", "category": "<slug>", "title": "<short>",
      "detail": "<what is wrong>", "line": <int or null>, "suggestion": "<concrete rewrite>", "fixable": true|false,
      "scenario": "<scenario title or null>"}}
  ],
  "strengths": ["<things done right>"]
}}"""

    text, provider, model = await call_llm(prompt, system=GHERKIN_JUDGE_SYSTEM, max_tokens=3000)
    data = extract_json(text)
    lines = len(gherkin_text.splitlines())

    scenarios = []
    for s in data.get("scenarios") or []:
        if not isinstance(s, dict):
            continue
        predicted = str(s.get("predicted", "uncertain")).lower()
        if predicted not in ("pass", "fail", "uncertain"):
            predicted = "uncertain"
        scenarios.append({
            "title": str(s.get("title", ""))[:200],
            "test_name": None,
            "implemented": True,
            "predicted": predicted,
            "confidence": _clamp(s.get("confidence", 50), default=50),
            "reason": str(s.get("reason", ""))[:400],
            "testable": bool(s.get("testable", True)),
        })
    coverage = []
    for c in data.get("coverage") or []:
        if isinstance(c, dict):
            coverage.append({
                "criterion": str(c.get("criterion", ""))[:300],
                "covered": bool(c.get("covered", False)),
                "scenario": (str(c.get("scenario"))[:200] if c.get("scenario") else None),
            })

    return {
        "pass_probability": _clamp(data.get("quality_score", 0)),
        "summary": str(data.get("summary", ""))[:1500],
        "scenarios": scenarios,
        "coverage": coverage,
        "findings": _norm_findings(data.get("findings") or [], lines),
        "strengths": [str(x)[:200] for x in (data.get("strengths") or [])][:8],
        "provider": provider,
        "model": model,
    }


def findings_to_json(findings: list[Finding]) -> str:
    return json.dumps([f.to_dict() for f in findings], indent=2)
