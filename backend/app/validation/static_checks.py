"""
Deterministic validation — no LLM involved.

Everything here is a pure function of the artefact text (plus the crawled DOM
map and the source Gherkin), so results are reproducible and can be unit-tested
without network access. These checks are intentionally conservative: they flag
what can be proven from the text and leave behavioural judgement to the judge.
"""
from __future__ import annotations

import ast
import difflib
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from app.code_gen.sanitizer import sanitize_generated_suite
from app.validation.findings import Finding, sort_findings

STOPWORDS = {
    "a", "an", "the", "and", "or", "of", "to", "in", "on", "at", "for", "with",
    "is", "are", "be", "as", "by", "from", "that", "this", "it", "its", "user",
    "should", "can", "when", "then", "given", "i", "my", "their", "them", "has",
    "have", "into", "than", "via", "using", "use", "after", "before", "will",
}

STEP_RE = re.compile(r"^\s*(Given|When|Then|And|But|\*)\s+(.*\S)\s*$")
SCENARIO_RE = re.compile(r"^\s*(Scenario Outline|Scenario Template|Scenario|Example):\s*(.*\S)?\s*$")
FEATURE_RE = re.compile(r"^\s*Feature:\s*(.*\S)?\s*$")
BACKGROUND_RE = re.compile(r"^\s*Background:")
EXAMPLES_RE = re.compile(r"^\s*(Examples|Scenarios):")
VAGUE_RE = re.compile(
    r"\b(works? (correctly|properly|as expected|fine)|should work|behaves? (correctly|properly)"
    r"|functions? (correctly|properly)|is (correct|fine|ok|okay)|everything is (correct|fine))\b",
    re.I,
)
QUOTE_CHARS = "'\"`"


def words(text: str) -> set[str]:
    return {
        w for w in re.findall(r"[a-z0-9]+", (text or "").lower())
        if len(w) > 2 and w not in STOPWORDS
    }


def overlap(a: set[str], b: set[str]) -> float:
    if not a:
        return 1.0
    return len(a & b) / len(a)


# ─── Gherkin ──────────────────────────────────────────────────────────────────

@dataclass
class GherkinScenario:
    title: str
    line: int
    kind: str                                    # Scenario | Scenario Outline
    steps: list[tuple[str, str, int]] = field(default_factory=list)   # (keyword, text, line)
    has_examples: bool = False
    example_columns: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return self.title + " " + " ".join(s[1] for s in self.steps)


@dataclass
class GherkinDoc:
    feature: Optional[str]
    scenarios: list[GherkinScenario]
    background_steps: list[tuple[str, str, int]]


def parse_gherkin(text: str) -> GherkinDoc:
    feature: Optional[str] = None
    scenarios: list[GherkinScenario] = []
    background: list[tuple[str, str, int]] = []
    current: Optional[GherkinScenario] = None
    in_background = False
    in_examples = False
    header_seen = False

    for i, raw in enumerate((text or "").splitlines(), start=1):
        line = raw.rstrip()
        if not line.strip() or line.strip().startswith("#") or line.strip().startswith("@"):
            continue
        m = FEATURE_RE.match(line)
        if m:
            feature = (m.group(1) or "").strip() or "(unnamed)"
            continue
        if BACKGROUND_RE.match(line):
            in_background, in_examples, current = True, False, None
            continue
        m = SCENARIO_RE.match(line)
        if m:
            kind = "Scenario Outline" if m.group(1) in ("Scenario Outline", "Scenario Template") else "Scenario"
            current = GherkinScenario(title=(m.group(2) or "").strip(), line=i, kind=kind)
            scenarios.append(current)
            in_background, in_examples, header_seen = False, False, False
            continue
        if EXAMPLES_RE.match(line):
            in_examples, header_seen = True, False
            if current:
                current.has_examples = True
            continue
        if in_examples and line.strip().startswith("|"):
            if current and not header_seen:
                current.example_columns = [c.strip() for c in line.strip().strip("|").split("|")]
                header_seen = True
            continue
        m = STEP_RE.match(line)
        if m:
            step = (m.group(1), m.group(2).strip(), i)
            if in_background:
                background.append(step)
            elif current is not None:
                current.steps.append(step)
            continue
        # Doc-strings / tables / description lines are ignored.
    return GherkinDoc(feature=feature, scenarios=scenarios, background_steps=background)


def _resolve_keywords(steps: list[tuple[str, str, int]]) -> list[str]:
    """Map And/But/* onto the preceding concrete keyword."""
    out: list[str] = []
    last = None
    for kw, _, _ in steps:
        if kw in ("And", "But", "*"):
            out.append(last or kw)
        else:
            last = kw
            out.append(kw)
    return out


def check_gherkin(text: str, acceptance_criteria: Optional[list[str]] = None) -> list[Finding]:
    findings: list[Finding] = []
    doc = parse_gherkin(text)

    if not (text or "").strip():
        return [Finding("critical", "structure", "Empty Gherkin", "The scenario text is empty.", fixable=False)]

    if doc.feature is None:
        findings.append(Finding(
            "major", "structure", "Missing Feature header",
            "A .feature file must start with a Feature: line so tooling can group its scenarios.",
            line=1, suggestion="Add 'Feature: <name>' at the top.",
        ))

    if not doc.scenarios:
        findings.append(Finding(
            "critical", "structure", "No scenarios found",
            "No Scenario: or Scenario Outline: blocks were parsed, so nothing can be generated or executed.",
            fixable=True,
        ))
        return sort_findings(findings)

    seen_titles: dict[str, int] = {}
    bg_keywords = set(_resolve_keywords(doc.background_steps))
    for sc in doc.scenarios:
        label = sc.title or f"(untitled, line {sc.line})"
        if not sc.title:
            findings.append(Finding("minor", "structure", "Untitled scenario",
                                    "Scenarios need a descriptive title for traceability.", line=sc.line, scenario=label))
        key = sc.title.strip().lower()
        if key:
            if key in seen_titles:
                findings.append(Finding(
                    "minor", "duplication", "Duplicate scenario title",
                    f"'{sc.title}' also appears at line {seen_titles[key]}. Duplicate titles collide when mapped to test names.",
                    line=sc.line, scenario=label,
                ))
            else:
                seen_titles[key] = sc.line

        if not sc.steps:
            findings.append(Finding("critical", "structure", "Empty scenario",
                                    "The scenario has no steps, so there is nothing to execute.", line=sc.line, scenario=label))
            continue

        kws = set(_resolve_keywords(sc.steps)) | bg_keywords
        if "When" not in kws:
            findings.append(Finding(
                "major", "structure", "No action step (When)",
                "Without a When step the scenario describes a state but no behaviour under test.",
                line=sc.line, scenario=label, suggestion="Add the user action that triggers the outcome.",
            ))
        if "Then" not in kws:
            findings.append(Finding(
                "major", "structure", "No verification step (Then)",
                "Without a Then step the generated test has nothing to assert and can never fail on a defect.",
                line=sc.line, scenario=label, suggestion="Add the observable outcome to verify.",
            ))
        if "Given" not in kws:
            findings.append(Finding(
                "minor", "structure", "No precondition step (Given)",
                "State the starting context (page, login state) so the test is self-contained.",
                line=sc.line, scenario=label,
            ))
        if sc.steps[0][0] in ("And", "But"):
            findings.append(Finding("minor", "structure", "Scenario starts with And/But",
                                    "The first step must be Given/When/Then.", line=sc.steps[0][2], scenario=label))

        for kw, step_text, ln in sc.steps:
            if VAGUE_RE.search(step_text):
                findings.append(Finding(
                    "minor", "testability", "Vague, untestable wording",
                    f"'{step_text}' cannot be turned into a concrete assertion.",
                    line=ln, scenario=label,
                    suggestion="Name the exact observable: URL, visible text, element state, count.",
                ))

        if sc.kind == "Scenario Outline":
            placeholders = set(re.findall(r"<([^<>]+)>", " ".join(s[1] for s in sc.steps)))
            if not sc.has_examples:
                findings.append(Finding("major", "structure", "Scenario Outline without Examples",
                                        "An outline needs an Examples: table or it never runs.", line=sc.line, scenario=label))
            else:
                missing = placeholders - set(sc.example_columns)
                if missing:
                    findings.append(Finding(
                        "major", "structure", "Placeholder not in Examples table",
                        f"Placeholders {sorted(missing)} have no matching column.", line=sc.line, scenario=label,
                    ))

    # Acceptance-criteria traceability (lexical; the judge does the semantic pass).
    for ac in acceptance_criteria or []:
        if not ac or not ac.strip():
            continue
        ac_words = words(ac)
        if not ac_words:
            continue
        best = max((overlap(ac_words, words(sc.text)) for sc in doc.scenarios), default=0.0)
        if best < 0.4:
            findings.append(Finding(
                "minor", "traceability", "Acceptance criterion not covered",
                f"No scenario clearly maps to: \"{ac.strip()}\" (best lexical overlap {int(best*100)}%).",
                suggestion="Add a scenario for this criterion or reword an existing one to reference it.",
            ))

    return sort_findings(findings)


def scenario_titles(gherkin_texts: list[str]) -> list[str]:
    titles: list[str] = []
    for t in gherkin_texts:
        titles.extend(sc.title for sc in parse_gherkin(t).scenarios if sc.title)
    return titles


# ─── Test code ────────────────────────────────────────────────────────────────

@dataclass
class TestFunction:
    name: str
    line: int
    end_line: int
    body: str
    doc: str = ""


def _python_tests(tree: ast.AST, code: str) -> list[TestFunction]:
    lines = code.splitlines()
    out: list[TestFunction] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test"):
            end = getattr(node, "end_lineno", node.lineno) or node.lineno
            body = "\n".join(lines[node.lineno - 1:end])
            out.append(TestFunction(node.name, node.lineno, end, body, ast.get_docstring(node) or ""))
    return out


def _js_block_end(code: str, open_idx: int) -> int:
    """Index just past the brace closing the one at open_idx (string-aware)."""
    depth = 0
    i = open_idx
    quote: Optional[str] = None
    while i < len(code):
        ch = code[i]
        if quote:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch in QUOTE_CHARS:
            quote = ch
        elif code.startswith("//", i):
            nl = code.find("\n", i)
            i = len(code) if nl == -1 else nl
            continue
        elif code.startswith("/*", i):
            close = code.find("*/", i + 2)
            i = len(code) if close == -1 else close + 2
            continue
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return len(code)


def _js_tests(code: str) -> list[TestFunction]:
    out: list[TestFunction] = []
    for m in re.finditer(r"\b(?:it|test)\s*\(\s*(['\"`])(.*?)\1\s*,", code):
        brace = code.find("{", m.end())
        if brace == -1:
            continue
        end = _js_block_end(code, brace)
        start_line = code.count("\n", 0, m.start()) + 1
        end_line = code.count("\n", 0, end) + 1
        out.append(TestFunction(m.group(2), start_line, end_line, code[m.start():end]))
    return out


def _js_bracket_check(code: str) -> Optional[tuple[int, str]]:
    pairs = {")": "(", "]": "[", "}": "{"}
    stack: list[tuple[str, int]] = []
    quote: Optional[str] = None
    line = 1
    i = 0
    while i < len(code):
        ch = code[i]
        if ch == "\n":
            line += 1
        if quote:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch in QUOTE_CHARS:
            quote = ch
        elif code.startswith("//", i):
            nl = code.find("\n", i)
            i = len(code) if nl == -1 else nl
            continue
        elif code.startswith("/*", i):
            close = code.find("*/", i + 2)
            if close == -1:
                return line, "Unterminated block comment"
            line += code.count("\n", i, close)
            i = close + 2
            continue
        elif ch in "([{":
            stack.append((ch, line))
        elif ch in ")]}":
            if not stack or stack[-1][0] != pairs[ch]:
                return line, f"Unexpected '{ch}'"
            stack.pop()
        i += 1
    if quote:
        return line, "Unterminated string literal"
    if stack:
        return stack[-1][1], f"Unclosed '{stack[-1][0]}'"
    return None


def _node_check(code: str) -> Optional[str]:
    node = shutil.which("node")
    if not node:
        return None
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "suite.cy.js"
        p.write_text(code, encoding="utf-8")
        try:
            r = subprocess.run([node, "--check", str(p)], capture_output=True, text=True, timeout=15)
        except Exception:
            return None
        if r.returncode != 0:
            msg = (r.stderr or r.stdout or "").strip()
            return msg.splitlines()[-1][:300] if msg else "node --check failed"
    return None


SELECTOR_LITERAL_RE = re.compile(r"""(?:"([#.\[][^"\n]{1,120})")|(?:'([#.\[][^'\n]{1,120})')""")
SELECTOR_SHAPE_RE = re.compile(r"""^[#.\[][A-Za-z0-9_\-\[\]=:'"\s>.#*~+()^$\\]+$""")
BY_RE = re.compile(r"""By\.(ID|CSS_SELECTOR|NAME|CLASS_NAME)\s*,\s*(['"])(.*?)\2""")
CY_GET_RE = re.compile(r"""cy\.get\(\s*(['"])(.*?)\1""")


def extract_selectors(code: str, framework: str) -> list[tuple[str, int]]:
    """Return (css_selector, line) pairs that the suite relies on."""
    found: list[tuple[str, int]] = []
    for ln, line in enumerate(code.splitlines(), start=1):
        if line.strip().startswith("#") or line.strip().startswith("//"):
            continue
        for m in BY_RE.finditer(line):
            kind, val = m.group(1), m.group(3)
            css = {"ID": f"#{val}", "CSS_SELECTOR": val, "NAME": f"[name='{val}']", "CLASS_NAME": f".{val}"}[kind]
            found.append((css, ln))
        for m in CY_GET_RE.finditer(line):
            found.append((m.group(2), ln))
        for m in SELECTOR_LITERAL_RE.finditer(line):
            cand = (m.group(1) or m.group(2) or "").strip()
            if not cand or not SELECTOR_SHAPE_RE.match(cand):
                continue
            if cand.startswith(".") and re.fullmatch(r"\.[a-z]{2,5}", cand):   # ".txt", ".js" etc.
                continue
            if re.fullmatch(r"\.\d+", cand):
                continue
            found.append((cand, ln))
    # de-duplicate keeping first line
    seen: set[str] = set()
    out: list[tuple[str, int]] = []
    for sel, ln in found:
        if sel not in seen:
            seen.add(sel)
            out.append((sel, ln))
    return out


def _grounded(selector: str, dom_elements: list[dict]) -> bool:
    sel = selector.strip()
    for e in dom_elements:
        if sel == (e.get("selector") or "").strip():
            return True
        attrs = e.get("attributes") or {}
        el_id = attrs.get("id")
        if el_id and sel in (f"#{el_id}", f"[id='{el_id}']", f'[id="{el_id}"]'):
            return True
        for key in ("data-test", "data-testid", "data-qa", "name"):
            v = attrs.get(key)
            if v and re.fullmatch(rf"\[{re.escape(key)}=['\"]?{re.escape(str(v))}['\"]?\]", sel):
                return True
        classes = str(attrs.get("class") or "").split()
        if sel.startswith(".") and " " not in sel and sel[1:] in classes:
            return True
    # Compound selector: grounded if every simple part is grounded.
    parts = [p for p in re.split(r"\s*[>\s+~]\s*", sel) if p]
    if len(parts) > 1:
        return all(_grounded(p, dom_elements) for p in parts)
    return False


ASSERT_PATTERNS = [
    r"\bassert\b", r"\bassert\w*\(", r"\bexpect\(", r"\.should\(", r"pytest\.raises", r"\.to_be",
    r"\.to_have", r"assert_that", r"\.until\(", r"wait_for_url\(", r"wait_for_selector\(",
]


def _has_assertion(body: str, framework: str, asserting_helpers: Optional[set[str]] = None) -> bool:
    if any(re.search(p, body) for p in ASSERT_PATTERNS):
        return True
    for name in asserting_helpers or ():
        if re.search(rf"\b{re.escape(name)}\s*\(", body):
            return True
    return False


def _asserting_helpers(code: str, is_python: bool) -> set[str]:
    """Names of non-test functions whose body (transitively) contains an assertion."""
    funcs: dict[str, str] = {}
    if is_python:
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return set()
        lines = code.splitlines()
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("test"):
                end = getattr(node, "end_lineno", node.lineno) or node.lineno
                funcs[node.name] = "\n".join(lines[node.lineno:end])
    else:
        pattern = r"(?:function\s+([A-Za-z_$][\w$]*)\s*\(|(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\(?[^)]*\)?\s*=>)"
        for m in re.finditer(pattern, code):
            name = m.group(1) or m.group(2)
            brace = code.find("{", m.end())
            if name and brace != -1:
                funcs[name] = code[brace:_js_block_end(code, brace)]
    asserting: set[str] = {n for n, b in funcs.items() if _has_assertion(b, "")}
    for _ in range(3):   # propagate through helper-calls-helper chains
        grew = False
        for n, b in funcs.items():
            if n not in asserting and _has_assertion(b, "", asserting):
                asserting.add(n)
                grew = True
        if not grew:
            break
    return asserting


def check_suite_code(
    code: str,
    *,
    framework: str,
    mode: str,
    url: str,
    gherkin_texts: list[str],
    dom_elements: Optional[list[dict]] = None,
) -> list[Finding]:
    findings: list[Finding] = []
    if not (code or "").strip():
        return [Finding("critical", "syntax", "Empty suite", "The generated file is empty.", fixable=False)]

    is_python = framework in ("playwright", "selenium")
    tests: list[TestFunction] = []
    syntax_ok = True

    if is_python:
        try:
            tree = ast.parse(code)
            tests = _python_tests(tree, code)
        except SyntaxError as e:
            syntax_ok = False
            findings.append(Finding(
                "critical", "syntax", "Python syntax error",
                f"{e.msg} - the file cannot be imported, so every test in it fails to collect.",
                line=e.lineno, snippet=(e.text or "").strip() or None,
                suggestion="Fix the syntax at the reported line.",
            ))
    else:
        br = _js_bracket_check(code)
        if br:
            syntax_ok = False
            findings.append(Finding("critical", "syntax", "JavaScript syntax error", br[1] + " - Cypress cannot load the spec.", line=br[0]))
        else:
            node_err = _node_check(code)
            if node_err:
                syntax_ok = False
                findings.append(Finding("critical", "syntax", "JavaScript syntax error", node_err, suggestion="Fix the syntax reported by node --check."))
        tests = _js_tests(code)

    if syntax_ok and not tests:
        findings.append(Finding(
            "critical", "structure", "No test functions found",
            "No def test_* / it(...) blocks were detected - the runner will collect zero tests.",
        ))

    # ── CI / runtime constraints ──
    for ln, line in enumerate(code.splitlines(), start=1):
        if re.search(r"headless\s*=\s*False", line) or re.search(r"headless\s*:\s*false", line):
            findings.append(Finding(
                "major", "ci", "Headed browser forced",
                "CI runners have no display server; a headed launch crashes immediately.",
                line=ln, snippet=line.strip(), suggestion="Use headless=True (or the default headless launch).",
            ))
        m = re.search(r"time\.sleep\(\s*(\d+(?:\.\d+)?)", line)
        if m and float(m.group(1)) >= 3:
            findings.append(Finding(
                "minor", "flakiness", "Long fixed sleep",
                f"time.sleep({m.group(1)}) slows the suite and still races on slow CI.",
                line=ln, snippet=line.strip(), suggestion="Wait on a condition (expect/wait_for_selector) instead.",
            ))
        m = re.search(r"cy\.wait\(\s*(\d{4,})\s*\)", line)
        if m:
            findings.append(Finding(
                "minor", "flakiness", "Long fixed cy.wait",
                f"cy.wait({m.group(1)}) is a hard sleep.", line=ln, snippet=line.strip(),
                suggestion="Assert on the element/network response instead of waiting a fixed time.",
            ))
        if "TODO" in line:
            findings.append(Finding(
                "minor", "incomplete", "Unresolved TODO",
                "The generator left a TODO, usually a missing selector or step mapping.",
                line=ln, snippet=line.strip(), fixable=False,
            ))

    # ── Placeholders ──
    placeholders = [(m.group(0), code.count("\n", 0, m.start()) + 1) for m in re.finditer(r"<<[A-Z0-9_]+>>", code)]
    if placeholders:
        if mode == "dom":
            findings.append(Finding(
                "critical", "selector_grounding", "Unresolved placeholder locator",
                f"{len(placeholders)} placeholder(s) such as {placeholders[0][0]} remain in a DOM-aware suite; they are not valid selectors.",
                line=placeholders[0][1], suggestion="Replace with selectors from the crawled element map.",
            ))
        else:
            findings.append(Finding(
                "info", "selector_grounding", "Abstract-mode placeholders present",
                f"{len(placeholders)} placeholder locator(s) must be resolved before execution (expected in Abstract mode).",
                line=placeholders[0][1], fixable=False,
            ))

    # ── Per-test checks ──
    asserting_helpers = _asserting_helpers(code, is_python) if syntax_ok else set()
    for t in tests:
        body_wo_header = "\n".join(t.body.splitlines()[1:])
        stripped = re.sub(r'""".*?"""|\'\'\'.*?\'\'\'', "", body_wo_header, flags=re.S)
        meaningful = [l for l in stripped.splitlines() if l.strip() and not l.strip().startswith(("#", "//"))]
        if is_python and all(l.strip() in ("pass", "...") for l in meaningful):
            findings.append(Finding("major", "structure", "Empty test body",
                                    f"{t.name} has no steps; it passes trivially.", line=t.line, scenario=t.name))
            continue
        if not _has_assertion(t.body, framework, asserting_helpers):
            findings.append(Finding(
                "major", "vacuous", "Test has no assertion",
                f"{t.name} performs actions but never asserts an outcome, so it cannot fail on a defect.",
                line=t.line, scenario=t.name, suggestion="Assert the Then-step outcome (URL, text, visibility, count).",
            ))
        if is_python:
            for m in re.finditer(r"\b(test_[A-Za-z0-9_]+)\s*\(", body_wo_header):
                if m.group(1) != t.name:
                    findings.append(Finding(
                        "major", "design", "Test calls another test",
                        f"{t.name} calls {m.group(1)} directly; fixtures are not injected, so this raises TypeError.",
                        line=t.line + body_wo_header[:m.start()].count("\n") + 1, scenario=t.name,
                        suggestion="Move the shared steps into a helper function and call that from both tests.",
                    ))

    # ── Scenario coverage ──
    titles = scenario_titles(gherkin_texts)
    code_lower = code.lower()
    for title in titles:
        tw = words(title)
        covered = title.lower() in code_lower
        if not covered:
            for t in tests:
                name_words = words(t.name.replace("_", " ")) | words(t.doc) | words(t.body[:400])
                if overlap(tw, name_words) >= 0.5:
                    covered = True
                    break
        if not covered:
            findings.append(Finding(
                "major", "coverage", "Scenario has no implementing test",
                f"No test matches the Gherkin scenario \"{title}\".", scenario=title,
                suggestion="Add a test function that implements this scenario's steps.",
            ))

    # ── Selector grounding (Mode B only, when a crawled map exists) ──
    if mode == "dom" and dom_elements:
        known = [str(e.get("selector") or "") for e in dom_elements if e.get("selector")]
        ungrounded: list[tuple[str, int, list[str]]] = []
        for sel, ln in extract_selectors(code, framework):
            if _grounded(sel, dom_elements):
                continue
            near = difflib.get_close_matches(sel, known, n=2, cutoff=0.45)
            sel_words = words(re.sub(r"[^a-z0-9]+", " ", sel.lower()))
            for e in dom_elements:
                if len(near) >= 3:
                    break
                if sel_words & words(str(e.get("role", "")).replace("_", " ")) and e["selector"] not in near:
                    near.append(e["selector"])
            ungrounded.append((sel, ln, near))
        if ungrounded:
            rows = "; ".join(
                f"{sel} (line {ln}" + (f", closest: {', '.join(near)}" if near else "") + ")"
                for sel, ln, near in ungrounded
            )
            findings.append(Finding(
                "minor", "selector_grounding", "Selectors not in crawled element map",
                f"{len(ungrounded)} selector(s) are unverified: they were not observed in the DOM crawl of {url}, "
                f"so they either belong to pages that were not crawled or were invented by the generator: {rows}",
                line=ungrounded[0][1], snippet=", ".join(u[0] for u in ungrounded[:6]),
                suggestion="Confirm each selector in the DOM inspector, or crawl the missing pages and regenerate.",
            ))

    # ── Known fatal anti-patterns (deterministic sanitizer dry-run) ──
    _, repairs = sanitize_generated_suite(code, framework=framework, url=url)
    for r in repairs:
        findings.append(Finding(
            "major", "anti_pattern", "Known fatal anti-pattern",
            r, suggestion="Auto-fix applies the deterministic repair.",
        ))

    return sort_findings(findings)
