
import os
import pytest
from pathlib import Path

SCREENSHOTS_DIR = Path(r"C:/Users/Dasun/Desktop/Research-project/Intelligent-Test-Case-Generation/reports/cc70c22d-67fd-4a17-9efd-85daa59b5633/screenshots")
STAGING_URL = os.environ.get("STAGING_URL", "https://www.saucedemo.com")

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None


@pytest.fixture(scope="session")
def staging_url():
    return STAGING_URL


@pytest.fixture
def page():
    """Headless Playwright page shared with the generated test."""
    if sync_playwright is None:
        pytest.skip("playwright not installed in runner environment")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(record_video_dir=None)
        pg = context.new_page()
        try:
            yield pg
        finally:
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
    # Best-effort: snapshot Playwright page if it exists in the test
    # signature, otherwise Selenium driver.
    try:
        for fixture_name, target in [("page", "screenshot"), ("driver", "save_screenshot")]:
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
