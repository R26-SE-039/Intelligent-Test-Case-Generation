"""
Phase 4 — Gherkin Background replay.

Parse Background steps from a project's Gherkin scenarios and convert each step
into a sequence of Playwright actions that drive the crawler past the login
wall and onto the page that subsequent scenarios actually test.

Site-agnostic: the matcher uses universal patterns ("log in with username X
and password Y", "I am on the products page") that map to standard form
locators (input[type=password], button containing "log in", first text-like
input). No assumptions about a specific app.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


# Each Action describes one Playwright operation in plain data so the sync
# crawler can replay it without importing this module's matcher logic.
@dataclass
class Action:
    kind: str                            # "goto" | "fill" | "click" | "wait"
    target: Optional[str] = None         # selector / URL / wait-for argument
    value: Optional[str] = None          # for fill
    description: str = ""                # human-readable, surfaced in crawler logs


@dataclass
class AuthPlan:
    """Result of parsing a Gherkin Background block."""
    actions: list[Action] = field(default_factory=list)
    final_url: Optional[str] = None      # if Background ends with "I am on …"
    raw_steps: list[str] = field(default_factory=list)
    # Steps the matcher couldn't translate — surfaced as warnings so QA knows.
    unmatched_steps: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.actions


# ─── Background extraction ────────────────────────────────────────────────────

_BACKGROUND_RE = re.compile(
    r"^\s*Background:\s*\n((?:\s*(?:Given|When|Then|And|But)\b.*\n?)+)",
    re.MULTILINE | re.IGNORECASE,
)
_STEP_RE = re.compile(r"^\s*(?:Given|When|Then|And|But)\b\s*(.+?)\s*$", re.IGNORECASE)


def extract_background_steps(gherkin_texts: list[str]) -> list[str]:
    """
    Pull Background steps from one or more .feature file contents. If multiple
    features declare a Background, the first non-empty one wins (Background is
    expected to be identical across features in a single project).
    """
    for text in gherkin_texts:
        if not text:
            continue
        m = _BACKGROUND_RE.search(text)
        if not m:
            continue
        steps: list[str] = []
        for line in m.group(1).splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            sm = _STEP_RE.match(stripped)
            if sm:
                steps.append(sm.group(1).strip())
        if steps:
            return steps
    return []


# ─── Step → action matchers ───────────────────────────────────────────────────
# Each matcher returns a list of Actions if it can handle the step, else None.
# Order matters — first match wins.

_QUOTED = r'["“”‘’\']([^"“”‘’\']+)["“”‘’\']'

# "I am on … URL" / "I navigate to …"
_GOTO_RE = re.compile(
    rf'\b(?:am\s+on|navigate\s+to|go\s+to|visit)\b[^"]*{_QUOTED}',
    re.IGNORECASE,
)

# "log in with username X and password Y"
_LOGIN_RE = re.compile(
    rf'log\s*in.*username\s*{_QUOTED}.*password\s*{_QUOTED}',
    re.IGNORECASE | re.DOTALL,
)

# "I enter username X" / "I enter password Y" — single-field variants
_ENTER_USERNAME_RE = re.compile(
    rf'(?:enter|fill|type|input).*(?:username|user|email|login)\s*{_QUOTED}',
    re.IGNORECASE,
)
_ENTER_PASSWORD_RE = re.compile(
    rf'(?:enter|fill|type|input).*password\s*{_QUOTED}',
    re.IGNORECASE,
)

# "I click X" / "I click on X" / "I press X"
_CLICK_RE = re.compile(
    rf'(?:click|press|tap|submit)(?:\s+the)?(?:\s+on)?\s*{_QUOTED}?(?:\s*button)?',
    re.IGNORECASE,
)

# "I am on the products page" / "I should be on …"  — final-state assertions
# we treat as a navigation hint. No quotes required.
_FINAL_PAGE_RE = re.compile(
    r'\bam\s+on\s+the\s+([a-z\s\-]+?)\s+(?:page|view|screen)\b',
    re.IGNORECASE,
)


# Generic locator strings — Playwright accepts these directly. Picking the
# first visible match works on virtually all login forms. Exported so the
# manual-auth route can fall back to them when a user leaves a selector blank.
USERNAME_LOCATOR = (
    'input[type="email"], input[name*="user" i], input[name*="email" i], '
    'input[id*="user" i], input[id*="email" i], input[id*="login" i], '
    'input:not([type="password"]):not([type="submit"]):not([type="button"]):not([type="hidden"]):not([type="checkbox"]):not([type="radio"])'
)
PASSWORD_LOCATOR = 'input[type="password"]'
LOGIN_BUTTON_LOCATOR = (
    'button:has-text("Login"), button:has-text("Log in"), button:has-text("Sign in"), '
    'input[type="submit"], button[type="submit"]'
)

# Aliases preserved for the matcher rules below
_USERNAME_LOCATOR = USERNAME_LOCATOR
_PASSWORD_LOCATOR = PASSWORD_LOCATOR
_LOGIN_BUTTON_LOCATOR = LOGIN_BUTTON_LOCATOR


def _match_step(step: str) -> tuple[Optional[list[Action]], Optional[str]]:
    """Return (actions, unmatched_reason). actions is None if no rule fired."""
    s = step.strip()

    # Login with both creds in one step
    m = _LOGIN_RE.search(s)
    if m:
        username, password = m.group(1), m.group(2)
        return [
            Action("fill", _USERNAME_LOCATOR, username, f"fill username '{username}'"),
            Action("fill", _PASSWORD_LOCATOR, password, "fill password"),
            Action("click", _LOGIN_BUTTON_LOCATOR, None, "click login button"),
        ], None

    # Goto explicit URL
    m = _GOTO_RE.search(s)
    if m:
        url = m.group(1)
        return [Action("goto", url, None, f"goto {url}")], None

    # Single-field enter
    m = _ENTER_USERNAME_RE.search(s)
    if m:
        username = m.group(1)
        return [Action("fill", _USERNAME_LOCATOR, username, f"fill username '{username}'")], None

    m = _ENTER_PASSWORD_RE.search(s)
    if m:
        return [Action("fill", _PASSWORD_LOCATOR, m.group(1), "fill password")], None

    # Click — must come after the more specific patterns
    m = _CLICK_RE.search(s)
    if m and m.group(1):
        label = m.group(1)
        return [
            Action(
                "click",
                f'button:has-text("{label}"), a:has-text("{label}"), input[value="{label}" i]',
                None,
                f"click '{label}'",
            )
        ], None

    # Final-page assertion — used as the URL to crawl after auth, not a click
    m = _FINAL_PAGE_RE.search(s)
    if m:
        return [Action("wait", "domcontentloaded", None, f"reached '{m.group(1).strip()} page'")], None

    return None, f"no rule matched: {s}"


def build_auth_plan(gherkin_texts: list[str]) -> AuthPlan:
    """
    Top-level entry: parse Background from project Gherkin and produce an
    AuthPlan the crawler can replay before extraction.
    """
    plan = AuthPlan()
    steps = extract_background_steps(gherkin_texts)
    plan.raw_steps = steps

    for step in steps:
        actions, unmatched = _match_step(step)
        if actions:
            plan.actions.extend(actions)
        elif unmatched:
            plan.unmatched_steps.append(step)

    return plan
