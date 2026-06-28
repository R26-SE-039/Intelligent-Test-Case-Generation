"""
Local subprocess runner — the demo-safe fallback when GITHUB_TOKEN is not
configured (or when the GH path errors out). Runs the selected suite's code
through pytest/playwright on the FastAPI host, captures stdout/stderr line
by line, and broadcasts events to the dashboard via log_broker.

Why this exists: viva day. WiFi dies, the GitHub PAT expires, the workflow
file got renamed — none of those should break the live demo. This module
guarantees a real test execution happens even if every other piece is down.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .log_broker import broker as log_broker

logger = logging.getLogger(__name__)

_DEFAULT_REPORTS_DIR = Path(__file__).resolve().parents[3] / "reports"
REPORTS_ROOT = Path(os.getenv("NEXTGENQA_REPORTS_DIR", str(_DEFAULT_REPORTS_DIR))).resolve()


@dataclass
class ScenarioResult:
    name: str
    status: str          # passed | failed | error
    duration_ms: int
    error_message: Optional[str] = None
    screenshot_path: Optional[str] = None


@dataclass
class LocalRunResult:
    status: str          # passed | failed | error
    total: int
    passed: int
    failed: int
    duration_ms: int
    raw_log_text: str
    scenarios: list[ScenarioResult]
    screenshots: list[ScenarioResult]   # subset with screenshot_path populated
    error_message: Optional[str] = None


# pytest output patterns we sniff out of stdout to drive the live UI. Failure
# detection is lenient — we accept either pytest's `FAILED` or `PASSED` lines.
_SCENARIO_LINE = re.compile(r"^(?P<file>\S+\.py)::(?P<name>\S+)\s+(?P<status>PASSED|FAILED|ERROR)", re.M)
_SUMMARY_LINE = re.compile(r"=+\s*(?P<failed>\d+)\s+failed.*?(?P<passed>\d+)\s+passed", re.I)
_PASSED_ONLY = re.compile(r"=+\s*(?P<passed>\d+)\s+passed", re.I)


def _run_pytest_blocking(
    run_id: str,
    cmd: list[str],
    workdir: Path,
    staging_url: str,
) -> tuple[str, int]:
    """
    Blocking subprocess.Popen runner. Lives in a worker thread (called via
    asyncio.to_thread) so the asyncio event loop is irrelevant — it doesn't
    matter whether uvicorn is on Selector or Proactor here.

    Pushes each line to log_broker via the threadsafe API so the WebSocket
    subscriber sees live output.
    """
    raw_lines: list[str] = []
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd=str(workdir),
        env={**os.environ, "STAGING_URL": staging_url, "PYTHONUNBUFFERED": "1"},
        text=True,
        bufsize=1,                       # line-buffered
        encoding="utf-8",
        errors="replace",
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        line = line.rstrip("\r\n")
        raw_lines.append(line)
        log_broker.publish_threadsafe(run_id, {"type": "log", "line": line})

        m = _SCENARIO_LINE.search(line)
        if m:
            log_broker.publish_threadsafe(run_id, {
                "type": "step",
                "step": m.group("name"),
                "status": m.group("status").lower(),
            })

    exit_code = proc.wait()
    return "\n".join(raw_lines), exit_code


async def run_suite_locally(
    *,
    run_id: str,
    suite_code: str,
    framework: str,
    language: str,
    staging_url: str,
) -> LocalRunResult:
    """
    Execute the given suite code as a subprocess. Returns once the run is
    complete; events are pushed to log_broker as output arrives.

    `framework` controls the harness — only Python frameworks are runnable
    locally for now (Selenium/Playwright Python via pytest). Cypress would
    need Node; we surface a clear error instead of pretending.
    """
    started = time.time()
    workdir = REPORTS_ROOT / run_id
    workdir.mkdir(parents=True, exist_ok=True)
    screenshots_dir = workdir / "screenshots"
    screenshots_dir.mkdir(exist_ok=True)

    # Python-only for the local path. Cypress falls through to a clear error.
    if language != "python":
        msg = (
            f"Local execution only supports Python frameworks (got '{framework}' / "
            f"'{language}'). Configure GITHUB_TOKEN and re-run for Cypress."
        )
        log_broker.publish(run_id, {"type": "error", "message": msg})
        return LocalRunResult(
            status="error", total=0, passed=0, failed=0,
            duration_ms=int((time.time() - started) * 1000),
            raw_log_text=msg, scenarios=[], screenshots=[], error_message=msg,
        )

    suite_file = workdir / "test_suite.py"
    suite_file.write_text(suite_code, encoding="utf-8")

    # The runner uses pytest with a screenshot-on-failure hook so the
    # generated code doesn't need to know about our reports/ layout. We
    # write a tiny conftest.py next to the suite file.
    conftest = workdir / "conftest.py"
    conftest_body = (
        _CONFTEST_TEMPLATE
        .replace("__SCREENSHOTS_DIR__", str(screenshots_dir).replace("\\", "/"))
        .replace("__STAGING_URL__", staging_url)
    )
    conftest.write_text(conftest_body, encoding="utf-8")

    log_broker.publish(run_id, {
        "type": "step",
        "step": f"Local runner spawning pytest for {framework}",
        "status": "running",
    })

    cmd = [
        sys.executable, "-u", "-m", "pytest",
        str(suite_file),
        "-v", "--tb=short", "--no-header",
        f"--rootdir={workdir}",
    ]

    # Run pytest in a worker thread using blocking subprocess.Popen. We
    # cannot use asyncio.create_subprocess_exec here because uvicorn on
    # Windows may have created a Selector event loop, which raises
    # NotImplementedError on subprocess transport. The same pattern is what
    # dom_crawler/crawler.py uses (sync Playwright in a thread).
    raw_log, exit_code = await asyncio.to_thread(
        _run_pytest_blocking, run_id, cmd, workdir, staging_url
    )
    raw_lines = raw_log.splitlines()
    duration_ms = int((time.time() - started) * 1000)

    # Parse final counts. Pytest prints e.g.
    #   "==== 3 failed, 2 passed, 1 skipped in 12.34s ===="
    #   "==== 5 passed in 8.21s ===="
    passed = failed = 0
    sm = _SUMMARY_LINE.search(raw_log)
    if sm:
        passed = int(sm.group("passed"))
        failed = int(sm.group("failed"))
    else:
        pm = _PASSED_ONLY.search(raw_log)
        if pm:
            passed = int(pm.group("passed"))
        failed = 0 if pm and "failed" not in raw_log.lower() else 0

    # Walk scenario lines for the per-row breakdown.
    scenarios: list[ScenarioResult] = []
    for m in _SCENARIO_LINE.finditer(raw_log):
        name = m.group("name")
        status = m.group("status").lower()
        if status not in ("passed", "failed", "error"):
            status = "error"
        sc = screenshots_dir / f"{name}.png"
        scenarios.append(ScenarioResult(
            name=name,
            status=status,
            duration_ms=0,   # pytest -v doesn't print per-test durations without plugins
            screenshot_path=str(sc.relative_to(REPORTS_ROOT)) if sc.exists() else None,
        ))

    total = len(scenarios) or (passed + failed)
    status = "passed" if exit_code == 0 and failed == 0 else "failed"
    if exit_code not in (0, 1):   # pytest: 0=ok, 1=test failures, 2+=collection/runtime error
        status = "error"

    screenshots = [s for s in scenarios if s.screenshot_path]

    log_broker.publish(run_id, {
        "type": "step",
        "step": f"Local run finished — exit {exit_code}",
        "status": status,
    })

    return LocalRunResult(
        status=status,
        total=total,
        passed=passed,
        failed=failed,
        duration_ms=duration_ms,
        raw_log_text=raw_log,
        scenarios=scenarios,
        screenshots=screenshots,
        error_message=None if exit_code in (0, 1) else f"pytest exit {exit_code}",
    )


# A conftest that:
#   - injects a Playwright `page` fixture pre-configured for headless mode
#   - captures LIVE FRAMES on every navigation/load so the dashboard can
#     show a real-time browser preview (the "viva impact" feature)
#   - takes a final screenshot after every test (passed or failed) into
#     reports/{run}/screenshots
#   - exposes STAGING_URL via env (already set by the parent process too)
#
# Live frames are timestamped (frame_<ms>.png) so the backend can serve "the
# newest one" by lexical sort — no extra state file needed. They land in the
# same screenshots/ directory; the per-test final shot uses the test name as
# its filename so it doesn't collide.
#
# The placeholders __SCREENSHOTS_DIR__ / __STAGING_URL__ are substituted with
# .replace() at write time so Python format-string syntax inside the body
# (e.g. f-strings) survives unmolested.
_CONFTEST_TEMPLATE = r'''
import os
import time
import pytest
from pathlib import Path

SCREENSHOTS_DIR = Path(r"__SCREENSHOTS_DIR__")
STAGING_URL = os.environ.get("STAGING_URL", "__STAGING_URL__")

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None


def _live_frame_path() -> Path:
    """Monotonically-named PNG so backend can pick the newest by name sort."""
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    return SCREENSHOTS_DIR / f"frame_{int(time.time() * 1000)}.png"


def _safe_snap(pg) -> None:
    """Best-effort screenshot — never raises (page may be navigating)."""
    try:
        pg.screenshot(path=str(_live_frame_path()), full_page=False)
    except Exception:
        pass


@pytest.fixture(scope="session")
def staging_url():
    return STAGING_URL


@pytest.fixture
def page():
    """Headless Playwright page that streams live frames to the dashboard.

    A snapshot is taken on:
      - every page `load` event
      - every `framenavigated` event (top frame only)
      - test entry and exit (via the makereport hook below)
    """
    if sync_playwright is None:
        pytest.skip("playwright not installed in runner environment")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        pg = context.new_page()

        # Live frame ticker — these listeners take a screenshot whenever
        # the page settles or navigates. Each fires on the Playwright sync
        # event loop so there's no cross-thread contention.
        pg.on("load", lambda: _safe_snap(pg))
        pg.on("framenavigated", lambda frame: _safe_snap(pg) if frame == pg.main_frame else None)

        _safe_snap(pg)  # initial blank-tab frame so the dashboard has something
        try:
            yield pg
        finally:
            try:
                _safe_snap(pg)  # final state
            except Exception:
                pass
            try:
                context.close()
            finally:
                browser.close()


@pytest.fixture
def driver():
    """Selenium driver fallback. Kept minimal — the generated code does the rest."""
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
    except ImportError:
        pytest.skip("selenium not installed in runner environment")
    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    drv = webdriver.Chrome(options=opts)
    try:
        yield drv
    finally:
        drv.quit()


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    if rep.when != "call":
        return
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    # Final per-test screenshot, named after the test so the dashboard
    # screenshot grid can label it cleanly. Live frames live alongside
    # under the frame_<ms>.png naming convention.
    try:
        for fixture_name in ("page", "driver"):
            obj = item.funcargs.get(fixture_name)
            if obj is None:
                continue
            path = SCREENSHOTS_DIR / f"{item.name}.png"
            if fixture_name == "page":
                obj.screenshot(path=str(path))
            else:
                obj.save_screenshot(str(path))
            break
    except Exception:
        pass
'''
