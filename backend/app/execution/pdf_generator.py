"""
PDF report generator — Jinja2 template rendered through Playwright's
`page.pdf()`. Produces a single A4 PDF per run, saved to
./reports/{run_id}/report.pdf. The path is stored on the TestRunExecution
row so the dashboard can offer a one-click download.

Why Playwright over ReportLab: Playwright is already a dependency for the
DOM crawler and the local runner. CSS does the layout; we get a beautiful
report with no per-element coordinate math.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent / "templates"
_DEFAULT_REPORTS_DIR = Path(__file__).resolve().parents[3] / "reports"
REPORTS_ROOT = Path(os.getenv("NEXTGENQA_REPORTS_DIR", str(_DEFAULT_REPORTS_DIR))).resolve()

_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
    trim_blocks=True,
    lstrip_blocks=True,
)


def _format_dt(value: Optional[datetime]) -> str:
    if not value:
        return "—"
    return value.strftime("%Y-%m-%d %H:%M:%S UTC")


def _format_duration(ms: Optional[int]) -> str:
    if not ms:
        return "—"
    s = ms / 1000.0
    if s < 60:
        return f"{s:.1f}s"
    return f"{s / 60:.1f}m"


_env.filters["fdt"] = _format_dt
_env.filters["fdur"] = _format_duration


async def render_run_pdf(
    *,
    run_id: str,
    row: Any,                                # TestRunExecution (kept loose to avoid circular import)
    suite: Optional[Any],
    screenshots: list[dict[str, Any]],
) -> str:
    """Render the HTML template, push it through headless Chromium, return
    the absolute PDF path."""
    workdir = REPORTS_ROOT / run_id
    workdir.mkdir(parents=True, exist_ok=True)
    pdf_path = workdir / "report.pdf"

    # Embed screenshots inline so the PDF is portable (one file). Skip any
    # screenshot we can't read — better a missing image than a broken PDF.
    embedded: list[dict[str, Any]] = []
    for s in screenshots:
        rel = s.get("image_path") or ""
        src = ""
        full = REPORTS_ROOT / rel if rel else None
        if full and full.exists():
            try:
                data = full.read_bytes()
                src = "data:image/png;base64," + base64.b64encode(data).decode("ascii")
            except Exception:
                src = ""
        embedded.append({
            "scenario": s.get("scenario"),
            "label": s.get("label"),
            "status": s.get("status"),
            "src": src,
        })

    total = max(row.total_count or 0, 1)
    pass_pct = round((row.passed_count or 0) * 100 / total)

    template = _env.get_template("report.html.j2")
    html = template.render(
        run=row,
        suite=suite,
        screenshots=embedded,
        pass_pct=pass_pct,
        generated_at=datetime.utcnow(),
    )

    # Render in a worker thread using sync Playwright so we don't depend on
    # the asyncio event loop supporting subprocesses (uvicorn on Windows
    # often hands us a Selector loop, which doesn't). Same pattern as the
    # dom_crawler.
    await asyncio.to_thread(_render_pdf_sync, html, pdf_path)

    logger.info("PDF written to %s", pdf_path)
    return str(pdf_path)


def _render_pdf_sync(html: str, pdf_path: Path) -> None:
    """Blocking PDF render in a worker thread."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.set_content(html, wait_until="networkidle")
            page.pdf(
                path=str(pdf_path),
                format="A4",
                print_background=True,
                margin={"top": "12mm", "right": "12mm", "bottom": "12mm", "left": "12mm"},
            )
        finally:
            browser.close()
