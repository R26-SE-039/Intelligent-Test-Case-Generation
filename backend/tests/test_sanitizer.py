"""Unit tests for the deterministic post-generation sanitizer.

`sanitize_generated_suite` mechanically repairs a narrow, known set of fatal
anti-patterns in LLM-generated Playwright suites for SauceDemo. These tests pin
down its exact contract: when it no-ops, and exactly what it repairs.
"""
import pytest

from app.code_gen.sanitizer import sanitize_generated_suite

pytestmark = pytest.mark.unit

PW = "playwright"
URL = "https://www.saucedemo.com/inventory.html"
BACKPACK = "#add-to-cart-sauce-labs-backpack"


def _click(selector: str) -> str:
    return f"    page.click('{selector}')\n"


# ── No-op guards ──────────────────────────────────────────────────────────────

def test_noop_on_empty_code():
    assert sanitize_generated_suite("", framework=PW, url=URL) == ("", [])


def test_noop_when_framework_is_not_playwright():
    code = _click(BACKPACK) + _click(BACKPACK)
    assert sanitize_generated_suite(code, framework="selenium", url=URL) == (code, [])


def test_noop_when_url_is_not_saucedemo():
    code = _click(BACKPACK) + _click(BACKPACK)
    assert sanitize_generated_suite(code, framework=PW, url="https://example.com") == (code, [])


def test_noop_when_url_is_none():
    code = _click(BACKPACK) + _click(BACKPACK)
    assert sanitize_generated_suite(code, framework=PW, url=None) == (code, [])


# ── Core repair: collapse consecutive duplicate add-to-cart clicks ────────────

def test_collapses_consecutive_duplicate_add_click():
    code = _click(BACKPACK) + _click(BACKPACK)
    out, fixes = sanitize_generated_suite(code, framework=PW, url=URL)
    assert out.count(BACKPACK) == 1, "the redundant second add-click should be dropped"
    assert len(fixes) == 1
    assert BACKPACK in fixes[0]


def test_comment_between_duplicate_adds_still_collapses():
    # The model typically inserts a "# add again" comment between the two adds.
    code = _click(BACKPACK) + "    # add again\n" + _click(BACKPACK)
    out, fixes = sanitize_generated_suite(code, framework=PW, url=URL)
    assert out.count(f"page.click('{BACKPACK}')") == 1
    assert len(fixes) == 1


def test_keeps_different_add_selectors():
    bike = "#add-to-cart-sauce-labs-bike-light"
    code = _click(BACKPACK) + _click(bike)
    out, fixes = sanitize_generated_suite(code, framework=PW, url=URL)
    assert fixes == []
    assert out == code, "distinct products must both be added"


def test_real_statement_between_adds_prevents_collapse():
    # A genuine action between the two adds means they are NOT redundant.
    code = _click(BACKPACK) + "    page.goto('https://www.saucedemo.com/cart.html')\n" + _click(BACKPACK)
    out, fixes = sanitize_generated_suite(code, framework=PW, url=URL)
    assert fixes == []
    assert out == code


def test_new_function_resets_tracking():
    # An add at the end of one test and the start of the next are unrelated.
    code = (
        "def test_a(page):\n"
        + _click(BACKPACK)
        + "\n"
        + "def test_b(page):\n"
        + _click(BACKPACK)
    )
    out, fixes = sanitize_generated_suite(code, framework=PW, url=URL)
    assert fixes == []
    assert out == code


def test_three_consecutive_adds_collapse_to_one():
    code = _click(BACKPACK) + _click(BACKPACK) + _click(BACKPACK)
    out, fixes = sanitize_generated_suite(code, framework=PW, url=URL)
    assert out.count(BACKPACK) == 1
    assert len(fixes) == 2


def test_assert_line_is_not_treated_as_add_action():
    code = _click(BACKPACK) + f"    assert '{BACKPACK}' in page.content()\n"
    out, fixes = sanitize_generated_suite(code, framework=PW, url=URL)
    assert fixes == []
    assert out == code
