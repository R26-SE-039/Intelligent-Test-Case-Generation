"""
DOM crawler — Phase 2 (no auth).

Launches headless Chromium, navigates to a public URL, and extracts
interactable elements with semantic role labels. Designed to be
site-agnostic: role inference is heuristic based on tag + attributes +
visible text, not hardcoded for any specific app.

Returns plain dataclasses; the route layer is responsible for persisting
them as DomElement rows.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

import httpx
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

from app.dom_crawler.auth import AuthPlan
from app.dom_crawler.log_broker import broker as _broker

logger = logging.getLogger(__name__)


@dataclass
class ExtractedElement:
    selector: str
    tag: str
    role: str
    text: Optional[str] = None
    attributes: dict = field(default_factory=dict)
    source_step: Optional[str] = None
    confidence: float = 0.5


@dataclass
class ProbeResult:
    ok: bool
    status: int
    title: Optional[str] = None
    error: Optional[str] = None


# JavaScript executed in-page. Returns one record per "interesting" element with
# enough context for Python-side role inference. Kept self-contained so it works
# on any site — no framework assumptions.
_EXTRACT_SCRIPT = r"""
() => {
  const escapeAttr = (v) => v.replace(/(["\\])/g, '\\$1');

  const cssEscape = (s) =>
    (window.CSS && CSS.escape) ? CSS.escape(s) : s.replace(/[^a-zA-Z0-9_-]/g, '\\$&');

  const buildSelector = (el) => {
    if (el.id) return '#' + cssEscape(el.id);
    const dt = el.getAttribute('data-testid');
    if (dt) return `[data-testid="${escapeAttr(dt)}"]`;
    const name = el.getAttribute('name');
    if (name) return `${el.tagName.toLowerCase()}[name="${escapeAttr(name)}"]`;
    const aria = el.getAttribute('aria-label');
    if (aria) return `${el.tagName.toLowerCase()}[aria-label="${escapeAttr(aria)}"]`;
    // fall back to a positional selector, scoped to nearest id'd ancestor
    let path = [];
    let node = el;
    while (node && node.nodeType === 1 && path.length < 6) {
      let part = node.tagName.toLowerCase();
      if (node.id) { part = '#' + cssEscape(node.id); path.unshift(part); break; }
      const parent = node.parentElement;
      if (parent) {
        const sibs = Array.from(parent.children).filter(c => c.tagName === node.tagName);
        if (sibs.length > 1) part += `:nth-of-type(${sibs.indexOf(node) + 1})`;
      }
      path.unshift(part);
      node = node.parentElement;
    }
    return path.join(' > ');
  };

  const isVisible = (el) => {
    if (!el.isConnected) return false;
    const rect = el.getBoundingClientRect();
    if (rect.width <= 1 || rect.height <= 1) return false;
    const cs = window.getComputedStyle(el);
    if (cs.visibility === 'hidden' || cs.display === 'none' || parseFloat(cs.opacity) === 0) return false;
    return true;
  };

  const out = [];
  const seen = new Set();

  // Inputs, textareas, selects, buttons, links, headings, anything with role=button
  const candidates = document.querySelectorAll(
    'input, textarea, select, button, a[href], h1, h2, h3, ' +
    '[role="button"], [role="link"], [role="textbox"], [role="searchbox"], [role="combobox"]'
  );

  candidates.forEach((el) => {
    if (!isVisible(el)) return;
    const sel = buildSelector(el);
    if (!sel || seen.has(sel)) return;
    seen.add(sel);

    const attrs = {};
    for (const a of el.attributes) {
      if (['id','name','type','placeholder','aria-label','role','data-testid','href','value'].includes(a.name)) {
        attrs[a.name] = a.value;
      }
    }

    out.push({
      selector: sel,
      tag: el.tagName,
      text: (el.innerText || el.value || '').trim().slice(0, 200),
      attributes: attrs,
    });
  });

  return out;
}
"""


# Heuristic role inference. Returns (role, confidence). Generic across sites —
# uses only universal attribute conventions (id/name patterns, input types,
# aria labels), not anything app-specific.
def _infer_role(el: dict) -> tuple[str, float]:
    tag = el["tag"].lower()
    attrs = el.get("attributes") or {}
    text = (el.get("text") or "").strip().lower()
    blob = " ".join([
        text,
        attrs.get("id", ""),
        attrs.get("name", ""),
        attrs.get("placeholder", ""),
        attrs.get("aria-label", ""),
        attrs.get("data-testid", ""),
    ]).lower()

    if tag == "input":
        itype = (attrs.get("type") or "text").lower()
        if itype == "password":
            return "password_input", 0.95
        if itype in ("email",):
            return "email_input", 0.9
        if itype in ("submit", "button"):
            if any(k in blob for k in ("login", "sign in", "signin", "log in")):
                return "login_button", 0.9
            if any(k in blob for k in ("search",)):
                return "search_button", 0.85
            return f"button_{_slug(text or attrs.get('value') or attrs.get('id') or 'submit')}", 0.6
        if itype in ("checkbox", "radio"):
            return f"{itype}_{_slug(blob or 'option')}", 0.7
        # text-like
        if any(k in blob for k in ("user", "username", "login", "email")):
            return "username_input", 0.8
        if any(k in blob for k in ("search", "query", "q")):
            return "search_input", 0.85
        if any(k in blob for k in ("first", "fname")):
            return "first_name_input", 0.8
        if any(k in blob for k in ("last", "lname")):
            return "last_name_input", 0.8
        return f"input_{_slug(blob or 'text')}", 0.5

    if tag == "textarea":
        return f"textarea_{_slug(blob or 'text')}", 0.6

    if tag == "select":
        return f"select_{_slug(blob or 'option')}", 0.6

    if tag == "button" or attrs.get("role") == "button":
        if any(k in blob for k in ("login", "sign in", "log in", "signin")):
            return "login_button", 0.9
        if any(k in blob for k in ("logout", "sign out")):
            return "logout_button", 0.9
        if any(k in blob for k in ("search",)):
            return "search_button", 0.85
        if any(k in blob for k in ("add to cart", "add-to-cart")):
            return f"add_to_cart_button_{_slug(blob)}", 0.85
        if any(k in blob for k in ("checkout",)):
            return "checkout_button", 0.9
        if any(k in blob for k in ("submit",)):
            return "submit_button", 0.8
        return f"button_{_slug(text or blob or 'action')}", 0.6

    if tag == "a":
        return f"link_{_slug(text or blob or 'unnamed')}", 0.6

    if tag in ("h1", "h2", "h3"):
        return f"heading_{_slug(text or 'page')}", 0.5

    return f"{tag}_{_slug(blob or 'element')}", 0.4


def _slug(s: str, maxlen: int = 40) -> str:
    out = []
    last_dash = False
    for c in (s or "").lower():
        if c.isalnum():
            out.append(c)
            last_dash = False
        elif not last_dash:
            out.append("_")
            last_dash = True
    text = "".join(out).strip("_")
    return (text[:maxlen] or "unnamed").rstrip("_") or "unnamed"


async def probe_url(url: str, timeout_seconds: float = 8.0) -> ProbeResult:
    """
    Lightweight reachability check used by the wizard's Validate button.
    Does NOT launch a browser — it's a plain HTTP request, fast and cheap.
    """
    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=timeout_seconds,
            headers={"User-Agent": "NextGenQA-Probe/1.0"},
        ) as client:
            r = await client.get(url)
            title = None
            ct = r.headers.get("content-type", "")
            if "html" in ct.lower():
                # cheap title scrape — avoids a parser dependency
                lower = r.text.lower()
                start = lower.find("<title")
                if start != -1:
                    gt = lower.find(">", start)
                    end = lower.find("</title", gt)
                    if gt != -1 and end != -1:
                        title = r.text[gt + 1:end].strip()[:200]
            return ProbeResult(ok=r.is_success, status=r.status_code, title=title)
    except httpx.HTTPError as e:
        return ProbeResult(ok=False, status=0, error=f"{type(e).__name__}: {e}")
    except Exception as e:  # network/DNS/etc
        return ProbeResult(ok=False, status=0, error=f"{type(e).__name__}: {e}")


def _replay_auth(page, plan: AuthPlan, log) -> None:
    """
    Execute each Action in the plan against the live page. Failures on
    individual steps are logged and skipped so the crawl can still extract
    whatever it can — a partial DOM is better than a total failure.
    """
    if plan.is_empty:
        return
    log(f"Replaying {len(plan.actions)} auth action(s)")
    for action in plan.actions:
        try:
            if action.kind == "goto":
                page.goto(action.target, wait_until="domcontentloaded", timeout=15000)
            elif action.kind == "fill":
                loc = page.locator(action.target).first
                loc.wait_for(state="visible", timeout=5000)
                loc.fill(action.value or "")
            elif action.kind == "click":
                loc = page.locator(action.target).first
                loc.wait_for(state="visible", timeout=5000)
                loc.click()
                # After a click that likely submits, wait for navigation/idle
                try:
                    page.wait_for_load_state("networkidle", timeout=5000)
                except PWTimeout:
                    pass
            elif action.kind == "wait":
                try:
                    page.wait_for_load_state(action.target or "domcontentloaded", timeout=5000)
                except PWTimeout:
                    pass
            log(f"  ok: {action.description}")
        except Exception as e:
            log(f"  skip ({type(e).__name__}): {action.description}")
    if plan.unmatched_steps:
        for s in plan.unmatched_steps:
            log(f"  warn: Background step not translated -> {s}")


def _crawl_sync(
    url: str,
    nav_timeout_ms: int,
    settle_ms: int,
    auth_plan: Optional[AuthPlan],
    storage_state: Optional[dict],
    run_id: Optional[str],
) -> tuple[list[ExtractedElement], list[str]]:
    """
    Synchronous crawl. Run from a worker thread via asyncio.to_thread() so it
    doesn't block the FastAPI event loop and doesn't depend on the asyncio
    subprocess transport (which is broken under uvicorn's default Selector loop
    on Windows).
    """
    logs: list[str] = []
    elements: list[ExtractedElement] = []

    def log(msg: str) -> None:
        logs.append(msg)
        logger.info("crawler: %s", msg)
        if run_id:
            _broker.publish_threadsafe(run_id, msg)

    auth_summary = (
        f" (with {len(auth_plan.actions)} auth actions)"
        if auth_plan and not auth_plan.is_empty
        else (" (with storageState)" if storage_state else "")
    )
    log(f"Launching Chromium headless -> {url}{auth_summary}")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            ctx_kwargs = {
                "user_agent": "NextGenQA-Crawler/1.0 (+research)",
                "viewport": {"width": 1280, "height": 800},
            }
            if storage_state:
                ctx_kwargs["storage_state"] = storage_state
            context = browser.new_context(**ctx_kwargs)
            page = context.new_page()
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=nav_timeout_ms)
            except PWTimeout:
                log(f"Navigation timed out after {nav_timeout_ms}ms - extracting whatever loaded")

            # Replay Gherkin-Background auth (Phase 4).
            if auth_plan and not auth_plan.is_empty:
                _replay_auth(page, auth_plan, log)

            try:
                page.wait_for_load_state("networkidle", timeout=5000)
            except PWTimeout:
                pass
            time.sleep(settle_ms / 1000)

            title = page.title() or "(no title)"
            current_url = page.url
            log(f"DOM ready - title='{title}' url='{current_url}'")

            raw = page.evaluate(_EXTRACT_SCRIPT)
            log(f"Found {len(raw)} candidate elements before role inference")

            seen_roles: set[str] = set()
            for el in raw:
                role, conf = _infer_role(el)
                base_role = role
                suffix = 2
                while role in seen_roles:
                    role = f"{base_role}_{suffix}"
                    suffix += 1
                seen_roles.add(role)

                elements.append(ExtractedElement(
                    selector=el["selector"],
                    tag=el["tag"],
                    role=role,
                    text=el.get("text") or None,
                    attributes=el.get("attributes") or {},
                    source_step="auto:dom-scan",
                    confidence=conf,
                ))

            log(f"Extracted {len(elements)} elements with semantic roles")
        finally:
            browser.close()

    return elements, logs


async def crawl_url(
    url: str,
    *,
    nav_timeout_ms: int = 20000,
    settle_ms: int = 800,
    auth_plan: Optional[AuthPlan] = None,
    storage_state: Optional[dict] = None,
    run_id: Optional[str] = None,
) -> tuple[list[ExtractedElement], list[str]]:
    """
    Visit `url` headlessly and extract interactable elements with inferred roles.

    auth_plan: Optional AuthPlan from app.dom_crawler.auth.build_auth_plan()
               replayed before extraction (Phase 4).
    storage_state: Optional Playwright storage state JSON for SSO/2FA sites
                   (Phase 6).
    run_id: Optional. When provided, log lines are also pushed to the
            log_broker so a WS subscriber receives them live (Phase 3).

    Runs the synchronous Playwright crawl in a worker thread.
    """
    return await asyncio.to_thread(
        _crawl_sync, url, nav_timeout_ms, settle_ms, auth_plan, storage_state, run_id
    )
