"""Unit tests for the deterministic half of the validator (no LLM, no DB)."""
import pytest

from app.validation import static_checks as sc
from app.validation.findings import Finding, count_by_severity, static_score
from app.validation.service import compute_score

pytestmark = pytest.mark.unit

GOOD_GHERKIN = """Feature: Login

  Scenario: Successful login with valid credentials
    Given the user is on the login page
    When the user enters "standard_user" and "secret_sauce"
    And clicks the login button
    Then the user is redirected to the inventory page

  Scenario: Login fails with invalid password
    Given the user is on the login page
    When the user enters "standard_user" and "wrong"
    Then the error "Epic sadface: Username and password do not match any user in this service" is shown
"""

GOOD_SUITE = '''import pytest
from playwright.sync_api import sync_playwright, expect

BASE = "https://www.saucedemo.com/"

@pytest.fixture
def page():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        pg = browser.new_page()
        yield pg
        browser.close()

def login(page, user, pwd):
    page.goto(BASE)
    page.fill("#user-name", user)
    page.fill("#password", pwd)
    page.click("#login-button")

def test_successful_login_with_valid_credentials(page):
    login(page, "standard_user", "secret_sauce")
    expect(page).to_have_url("https://www.saucedemo.com/inventory.html")

def test_login_fails_with_invalid_password(page):
    login(page, "standard_user", "wrong")
    assert "Epic sadface" in page.locator("[data-test='error']").inner_text()
'''

DOM = [
    {"role": "username_input", "selector": "#user-name", "tag": "INPUT", "attributes": {"id": "user-name"}},
    {"role": "password_input", "selector": "#password", "tag": "INPUT", "attributes": {"id": "password"}},
    {"role": "login_button", "selector": "#login-button", "tag": "INPUT", "attributes": {"id": "login-button"}},
    {"role": "error_message", "selector": "[data-test='error']", "tag": "H3", "attributes": {"data-test": "error"}},
]


# ─── Gherkin ──────────────────────────────────────────────────────────────────

def test_parse_gherkin_structure():
    doc = sc.parse_gherkin(GOOD_GHERKIN)
    assert doc.feature == "Login"
    assert [s.title for s in doc.scenarios] == [
        "Successful login with valid credentials",
        "Login fails with invalid password",
    ]
    assert len(doc.scenarios[0].steps) == 4


def test_good_gherkin_has_no_findings():
    assert sc.check_gherkin(GOOD_GHERKIN) == []


def test_gherkin_missing_then_and_feature():
    text = "Scenario: Add to cart\n  Given the user is logged in\n  When the user adds an item\n"
    titles = {f.title for f in sc.check_gherkin(text)}
    assert "Missing Feature header" in titles
    assert "No verification step (Then)" in titles


def test_gherkin_vague_wording_and_duplicates():
    text = (
        "Feature: X\n"
        "Scenario: A\n  Given a\n  When b\n  Then it works correctly\n"
        "Scenario: A\n  Given a\n  When b\n  Then c is shown\n"
    )
    titles = [f.title for f in sc.check_gherkin(text)]
    assert "Vague, untestable wording" in titles
    assert "Duplicate scenario title" in titles


def test_gherkin_acceptance_criteria_coverage():
    criteria = ["User can log in with valid credentials", "Cart badge shows the number of items"]
    findings = sc.check_gherkin(GOOD_GHERKIN, criteria)
    uncovered = [f for f in findings if f.category == "traceability"]
    assert len(uncovered) == 1
    assert "Cart badge" in uncovered[0].detail


def test_scenario_outline_needs_examples():
    text = "Feature: X\nScenario Outline: O\n  Given <a>\n  When b\n  Then c\n"
    assert any(f.title == "Scenario Outline without Examples" for f in sc.check_gherkin(text))


# ─── Suite code ───────────────────────────────────────────────────────────────

def test_good_suite_is_clean():
    findings = sc.check_suite_code(
        GOOD_SUITE, framework="playwright", mode="dom", url="https://www.saucedemo.com/",
        gherkin_texts=[GOOD_GHERKIN], dom_elements=DOM,
    )
    assert [f.to_dict() for f in findings] == []


def test_python_syntax_error_is_critical():
    code = GOOD_SUITE + "\ndef broken(:\n    pass\n"
    findings = sc.check_suite_code(code, framework="playwright", mode="dom", url="x", gherkin_texts=[GOOD_GHERKIN])
    assert findings[0].severity == "critical"
    assert findings[0].category == "syntax"
    assert findings[0].line is not None


def test_detects_headed_browser_vacuous_test_and_test_calling_test():
    code = GOOD_SUITE.replace("headless=True", "headless=False") + '''
def test_no_assert(page):
    login(page, "a", "b")

def test_calls_other(page):
    test_successful_login_with_valid_credentials(page)
    assert True
'''
    findings = sc.check_suite_code(code, framework="playwright", mode="dom", url="x", gherkin_texts=[GOOD_GHERKIN])
    titles = {f.title for f in findings}
    assert "Headed browser forced" in titles
    assert "Test has no assertion" in titles
    assert "Test calls another test" in titles


def test_missing_scenario_is_reported():
    gherkin = GOOD_GHERKIN + "\n  Scenario: Locked out user sees lockout error\n    Given a\n    When b\n    Then c\n"
    findings = sc.check_suite_code(GOOD_SUITE, framework="playwright", mode="dom", url="x", gherkin_texts=[gherkin])
    missing = [f for f in findings if f.category == "coverage"]
    assert len(missing) == 1
    assert "Locked out" in missing[0].detail


def test_ungrounded_selector_in_dom_mode():
    code = GOOD_SUITE.replace('"#login-button"', '"#signin-btn"')
    findings = sc.check_suite_code(
        code, framework="playwright", mode="dom", url="x", gherkin_texts=[GOOD_GHERKIN], dom_elements=DOM,
    )
    sel = [f for f in findings if f.category == "selector_grounding"]
    assert len(sel) == 1 and "#signin-btn" in sel[0].detail
    assert "#login-button" in sel[0].detail          # nearest crawled selector is suggested
    assert "#user-name" not in sel[0].detail          # grounded selectors are not reported


def test_placeholder_in_dom_mode_is_critical_but_info_in_abstract():
    code = GOOD_SUITE.replace('"#user-name"', '"<<USERNAME_INPUT_PLACEHOLDER>>"')
    dom_f = sc.check_suite_code(code, framework="playwright", mode="dom", url="x", gherkin_texts=[GOOD_GHERKIN])
    abs_f = sc.check_suite_code(code, framework="playwright", mode="abstract", url="x", gherkin_texts=[GOOD_GHERKIN])
    assert any(f.severity == "critical" and f.category == "selector_grounding" for f in dom_f)
    assert all(f.severity != "critical" for f in abs_f if f.category == "selector_grounding")


def test_sanitizer_antipattern_surfaces_as_major():
    code = GOOD_SUITE + '''
def test_add_twice(page):
    login(page, "standard_user", "secret_sauce")
    page.click("#add-to-cart-sauce-labs-backpack")
    page.click("#add-to-cart-sauce-labs-backpack")
    assert page.locator(".shopping_cart_badge").inner_text() == "1"
'''
    findings = sc.check_suite_code(code, framework="playwright", mode="dom", url="https://www.saucedemo.com/", gherkin_texts=[GOOD_GHERKIN])
    assert any(f.category == "anti_pattern" and f.severity == "major" for f in findings)


def test_cypress_bracket_error_and_tests_extracted():
    good = 'describe("s", () => { it("Successful login with valid credentials", () => { cy.visit("/"); cy.get("#user-name").should("exist"); }); });'
    bad = good[:-3]
    f_good = sc.check_suite_code(good, framework="cypress", mode="abstract", url="x", gherkin_texts=["Feature: L\nScenario: Successful login with valid credentials\n Given a\n When b\n Then c\n"])
    f_bad = sc.check_suite_code(bad, framework="cypress", mode="abstract", url="x", gherkin_texts=[])
    assert not any(f.severity == "critical" for f in f_good)
    assert any(f.category == "syntax" and f.severity == "critical" for f in f_bad)


def test_extract_selectors_handles_by_and_literals():
    code = 'driver.find_element(By.ID, "user-name")\npage.click(".btn_primary")\nx = "hello"\n'
    sels = [s for s, _ in sc.extract_selectors(code, "selenium")]
    assert "#user-name" in sels and ".btn_primary" in sels and "hello" not in sels


def test_extract_selectors_does_not_span_quotes():
    code = 'assert page.locator(".shopping_cart_badge").inner_text() == "1"\ncy.get(".x").should("contain", "a")\n'
    sels = [s for s, _ in sc.extract_selectors(code, "playwright")]
    assert sels == [".shopping_cart_badge", ".x"]


def test_assertion_via_helper_counts():
    code = GOOD_SUITE + '''
def assert_badge_hidden(page):
    assert not page.locator(".shopping_cart_badge").is_visible()

def test_badge_hidden_after_login(page):
    login(page, "standard_user", "secret_sauce")
    assert_badge_hidden(page)
'''
    findings = sc.check_suite_code(code, framework="playwright", mode="abstract", url="x", gherkin_texts=[GOOD_GHERKIN])
    assert not any(f.category == "vacuous" for f in findings)


# ─── Scoring ──────────────────────────────────────────────────────────────────

def test_static_score_penalties():
    fs = [Finding("critical", "x", "a", "b"), Finding("major", "x", "a", "b"), Finding("minor", "x", "a", "b")]
    assert static_score(fs) == 100 - 25 - 10 - 3
    assert count_by_severity(fs)["major"] == 1


def test_compute_score_without_judge_uses_static_only():
    out = compute_score([], None)
    assert out["score"] == 100 and out["verdict"] == "ready"
    assert out["breakdown"]["judge_available"] is False


def test_compute_score_caps_on_static_critical():
    judge = {"pass_probability": 95, "scenarios": [{"predicted": "pass"}] * 4, "findings": []}
    out = compute_score([Finding("critical", "syntax", "boom", "x")], judge)
    assert out["score"] <= 15 and out["verdict"] == "likely_failing"


def test_compute_score_blends_signals():
    judge = {
        "pass_probability": 80,
        "scenarios": [{"predicted": "pass"}, {"predicted": "pass"}, {"predicted": "fail"}, {"predicted": "pass"}],
        "findings": [Finding("minor", "x", "a", "b", source="llm")],
    }
    out = compute_score([], judge)
    # 0.5*80 + 0.3*75 + 0.2*100 = 82.5 -> 82 or 83 depending on rounding
    assert 82 <= out["score"] <= 83
    assert out["scenario_total"] == 4 and out["scenario_pass_predicted"] == 3
    assert out["verdict"] == "ready"
