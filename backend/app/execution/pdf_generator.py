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

    header_html, footer_html = _running_header_footer(str(run_id))

    # Render in a worker thread using sync Playwright so we don't depend on
    # the asyncio event loop supporting subprocesses (uvicorn on Windows
    # often hands us a Selector loop, which doesn't). Same pattern as the
    # dom_crawler.
    await asyncio.to_thread(_render_pdf_sync, html, pdf_path, header_html, footer_html)

    logger.info("PDF written to %s", pdf_path)
    return str(pdf_path)


def _running_header_footer(run_id: str) -> tuple[str, str]:
    """Chromium header/footer templates rendered in the page margins on EVERY
    page. Chromium substitutes the special classes (pageNumber/totalPages) and
    requires an explicit font-size (its default is 0). Kept as tiny inline-styled
    HTML — external CSS does not apply to these fragments."""
    short_id = run_id[:8]
    generated = _format_dt(datetime.utcnow())
    base = (
        "width:100%;font-size:8px;font-family:'Segoe UI',Helvetica,Arial,sans-serif;"
        "color:#94a3b8;"
    )
    header = (
        f'<div style="{base}padding:4px 14mm 0;">'
        '<div style="display:flex;justify-content:space-between;align-items:center;'
        'border-bottom:0.5px solid #e2e8f0;padding-bottom:4px;">'
        '<span style="font-weight:700;color:#4f46e5;">NextGen QA</span>'
        f'<span>Test Execution Report &middot; Run {short_id}</span>'
        '</div></div>'
    )
    footer = (
        f'<div style="{base}padding:0 14mm 4px;">'
        '<div style="display:flex;justify-content:space-between;align-items:center;'
        'border-top:0.5px solid #e2e8f0;padding-top:4px;">'
        '<span>SLIIT &middot; R26-SE-039 &middot; Component 2</span>'
        f'<span>Generated {generated}</span>'
        '<span>Page <span class="pageNumber"></span> of <span class="totalPages"></span></span>'
        '</div></div>'
    )
    return header, footer


def _render_pdf_sync(html: str, pdf_path: Path, header_html: str, footer_html: str) -> None:
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
                display_header_footer=True,
                header_template=header_html,
                footer_template=footer_html,
                # Reserve space for the running header/footer in the margins.
                margin={"top": "20mm", "right": "14mm", "bottom": "16mm", "left": "14mm"},
            )
        finally:
            browser.close()
