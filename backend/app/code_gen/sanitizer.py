"""
Deterministic post-generation guardrail for generated test suites.

LLM output for SauceDemo/Playwright reliably re-introduces a small set of fatal
anti-patterns no matter how the prompt is worded (see generator.py's SauceDemo
rules). Prompt guidance is probabilistic; this pass is not. It runs AFTER the
model returns and mechanically repairs the patterns that are safe to repair,
returning the cleaned code plus a list of applied fixes for logging.

Scope is intentionally narrow: only Playwright suites targeting saucedemo.com,
and only repairs that cannot change the meaning of otherwise-correct code.
"""

from __future__ import annotations

import re

# Matches an add-to-cart id anywhere on a line, e.g. "#add-to-cart-sauce-labs-backpack".
_ADD_SELECTOR = re.compile(r"#add-to-cart-[A-Za-z0-9_-]+")


def _is_add_to_cart_action(line: str) -> tuple[bool, str | None]:
    """True if `line` performs an add-to-cart click (either page.click(...) or a
    helper call like add_to_cart(page, ...)). Returns the selector string too."""
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or stripped.startswith("assert"):
        return False, None
    if "(" not in line:
        return False, None
    m = _ADD_SELECTOR.search(line)
    if not m:
        return False, None
    return True, m.group(0)


def _collapse_duplicate_add_clicks(code: str) -> tuple[str, list[str]]:
    """Remove a second consecutive click on the same #add-to-cart-* selector.

    SauceDemo's add button toggles to a remove button after the first click, so
    a repeated add-click on the same selector hangs until timeout. Comment and
    blank lines between the two clicks are ignored (the model usually inserts a
    "# add again" comment). Any other statement resets the tracking, so we never
    collapse two adds that are genuinely separated by real actions.
    """
    fixes: list[str] = []
    out: list[str] = []
    prev_add_selector: str | None = None

    for line in code.splitlines(keepends=True):
        stripped = line.strip()

        # Blank/comment lines don't break an add→add run.
        if stripped == "" or stripped.startswith("#"):
            out.append(line)
            continue

        # New function body starts a fresh tracking scope.
        if stripped.startswith("def ") or stripped.startswith("async def "):
            prev_add_selector = None
            out.append(line)
            continue

        is_add, selector = _is_add_to_cart_action(line)
        if is_add:
            if selector == prev_add_selector:
                fixes.append(
                    f"removed duplicate add-to-cart click on {selector} "
                    f"(button has already toggled to remove state)"
                )
                continue  # drop the redundant line
            prev_add_selector = selector
            out.append(line)
        else:
            # A real statement between two adds breaks the consecutive run.
            prev_add_selector = None
            out.append(line)

    return "".join(out), fixes


def sanitize_generated_suite(
    code: str,
    *,
    framework: str,
    url: str,
) -> tuple[str, list[str]]:
    """Apply deterministic repairs. No-op unless this is a Playwright suite
    targeting SauceDemo. Returns (possibly_modified_code, applied_fixes)."""
    if not code:
        return code, []
    if framework != "playwright":
        return code, []
    if "saucedemo.com" not in (url or "").lower():
        return code, []

    code, fixes = _collapse_duplicate_add_clicks(code)
    return code, fixes
