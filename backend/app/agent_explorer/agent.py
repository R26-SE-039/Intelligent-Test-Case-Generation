"""
Agentic Goal-Driven Test Exploration — the heart of the novelty.

Pipeline per iteration:
  1. Take a screenshot of the live page.
  2. Inject the SoM overlay → numbered red boxes on every interactable + the
     element list (id → selector/role/text).
  3. Take a SECOND screenshot — that one goes to the vision model.
  4. Build the agent prompt: original intent, sub-goal queue, recent history,
     reflexion lessons, the SoM screenshot.
  5. A vision LLM (OpenAI gpt-4o-mini by default, via LLM_MODEL) returns a
     single JSON with four role-tagged thoughts
     (planner/actor/observer/critic) and an action.
  6. Execute the action via Playwright.
  7. Compute a state hash; if novel, record it. Drives coverage + termination.
  8. Stream every step to the broker so the UI sees it live.

Termination: novel-state-plateau (no new state for K cycles) OR max steps.
This is the "coverage-driven termination" novelty piece.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

from app.agent_explorer.log_broker import broker as _broker
from app.agent_explorer.som_overlay import SOM_INJECT_SCRIPT, SOM_REMOVE_SCRIPT

logger = logging.getLogger(__name__)


# ─── Public types ────────────────────────────────────────────────────────────

@dataclass
class AgentEvent:
    """One streamed event. Frontend renders by `type`."""
    type: str
    payload: dict


@dataclass
class DiscoveredScenario:
    title: str
    steps: list[str] = field(default_factory=list)


# ─── Configuration ───────────────────────────────────────────────────────────

LLM_API_KEY = os.getenv("LLM_API_KEY", "")
# The agent needs a VISION-capable model (it reasons over screenshots). The rest
# of the backend is driven by LLM_PROVIDER/LLM_MODEL; the default `gpt-4o-mini`
# is vision-capable, so the agent runs on the same OpenAI key as everything else.
# Override with AGENT_VISION_MODEL in .env if you want a different vision model.
VISION_MODEL = os.getenv("AGENT_VISION_MODEL", os.getenv("LLM_MODEL", "gpt-4o-mini"))
OPENAI_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
MAX_STEPS_DEFAULT = 12        # Hard cap so demo never runs forever.
PLATEAU_LIMIT = 3             # Stop when this many consecutive steps add no novel state.
HISTORY_WINDOW = 6            # How many past actions/observations to feed back into the prompt.


# ─── Anthropic call ──────────────────────────────────────────────────────────

def _strip_code_fences(s: str) -> str:
    """Claude sometimes wraps JSON in ```json ... ``` despite asking otherwise."""
    s = s.strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    return s.strip()


def _parse_agent_json(text: str) -> dict:
    """Parse the agent's JSON reply. Returns {} on failure (caller handles)."""
    cleaned = _strip_code_fences(text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # Last-ditch: find the outermost {...}
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(cleaned[start:end + 1])
            except json.JSONDecodeError:
                pass
        return {}


def _call_vision_llm_sync(
    *,
    intent: str,
    sub_goals_done: list[str],
    sub_goals_pending: list[str],
    history: list[dict],
    lessons: list[str],
    elements: list[dict],
    screenshot_b64: str,
    page_url: str,
    page_title: str,
) -> dict:
    """
    Single OpenAI (vision) call. The prompt frames the model as four roles
    (planner / actor / observer / critic) so the dissertation can describe
    it as a multi-role architecture without paying 4× tokens.
    """
    if not LLM_API_KEY:
        raise RuntimeError("LLM_API_KEY not set in backend/.env — agent cannot run.")

    # Compact the element list — full attribute dump blows the token budget fast.
    el_lines = []
    for e in elements:
        attrs = e.get("attrs") or {}
        ident = attrs.get("id") or attrs.get("name") or attrs.get("placeholder") or attrs.get("aria-label") or ""
        text = (e.get("text") or "")[:40]
        el_lines.append(
            f"  [{e['id']}] <{e['tag']}> role={e.get('role','-')} text='{text}' id/name='{ident}'"
        )
    elements_block = "\n".join(el_lines) if el_lines else "  (no interactable elements detected)"

    history_block = "\n".join(
        f"  step {h['step']}: {h['action_type']} on element {h.get('element_id','-')} → "
        f"{'novel state' if h.get('novel') else 'known state'}"
        for h in history
    ) or "  (no prior steps)"

    lessons_block = "\n".join(f"  • {l}" for l in lessons) or "  (no reflexion lessons yet)"

    pending_block = "\n".join(f"  • {g}" for g in sub_goals_pending) or "  (queue empty — planner must propose new sub-goals)"
    done_block = "\n".join(f"  ✓ {g}" for g in sub_goals_done) or "  (none yet)"

    system = """You are NextGenQA-Agent, an autonomous QA test exploration agent.

You play FOUR roles in a single response:
  - PLANNER: decomposes the QA's high-level intent into concrete sub-goals (positive, negative, boundary, edge cases)
  - ACTOR: picks the next concrete browser action against the screenshot
  - OBSERVER: notes what changed and whether it's a novel discovery
  - CRITIC: reflects on whether the prior step worked, and what to try next

Action types you may emit:
  - "click"            → click element with given id (from the SoM overlay)
  - "fill"             → type `value` into element with given id
  - "navigate"         → goto a URL (use sparingly; prefer in-page actions)
  - "complete_goal"    → mark the current sub-goal as done; queue next
  - "discover_scenario"→ output a fully-specified test scenario you've validated
                         (title + Given/When/Then steps in plain English)
  - "stop"             → exploration finished; coverage satisfied

YOUR PRIMARY DELIVERABLE IS DISCOVERED TEST SCENARIOS. Exploring the page is
only a means to that end. A run that ends with zero "discover_scenario" actions
is a FAILURE — aim to emit at least 3–5 scenarios per run.

Critical rules:
  - Pick element IDs ONLY from the numbered red boxes you see in the screenshot.
  - One action per response.
  - For a dropdown (a <select> element), use "fill" with the exact visible
    option label as `value` (e.g. value="Price (low to high)"). Do NOT try to
    click it open — the option is chosen directly.
  - Emit "discover_scenario" AS SOON AS you have seen enough to specify a journey
    — you do NOT need to fully execute it first. E.g. once you observe a product
    grid with add-to-cart buttons, you can already specify an "add item to cart"
    scenario. Emit scenarios AS YOU GO, not only at the very end.
  - After validating a journey, emit "discover_scenario" THEN "complete_goal".
  - Do NOT repeatedly click the same control that produces no visible change. If
    two attempts yield nothing new, write a lesson, emit whatever scenario you
    can from what you've already seen, and move to a different part of the page.
  - Before you "stop", make sure you have emitted every scenario you can justify.
  - Output VALID JSON ONLY. No markdown fences, no commentary outside the JSON.
"""

    user_text = f"""# Original QA Intent
{intent}

# Page Context
URL: {page_url}
Title: {page_title}

# Sub-goals completed
{done_block}

# Sub-goals pending
{pending_block}

# Reflexion lessons (memory of prior failures)
{lessons_block}

# Recent history
{history_block}

# Visible interactable elements (from SoM overlay)
{elements_block}

Respond with EXACTLY this JSON shape:
{{
  "thought_planner": "string — what sub-goal am I working on, and what's still missing from coverage?",
  "thought_actor":   "string — what concrete action will I take next, and why this element?",
  "thought_observer":"string — what should I be looking for in the screenshot AFTER this action?",
  "thought_critic":  "string — reflection on the previous step(s) and any course correction",
  "action": {{
    "type": "click" | "fill" | "navigate" | "complete_goal" | "discover_scenario" | "stop",
    "element_id": <int, optional>,
    "value": "<string, optional, for fill>",
    "url": "<string, optional, for navigate>",
    "scenario": {{ "title": "...", "steps": ["Given ...", "When ...", "Then ..."] }},
    "lesson": "<string, optional — append to reflexion memory>",
    "reason": "<string — short justification>"
  }}
}}
"""

    # OpenAI chat-completions with vision. httpx (sync) is already a dependency
    # and matches the OpenAI path in app/gherkin/generator.py — no SDK needed.
    import httpx

    with httpx.Client(timeout=60) as client:
        resp = client.post(
            f"{OPENAI_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {LLM_API_KEY}"},
            json={
                "model": VISION_MODEL,
                "max_tokens": 1500,
                "temperature": 0.2,
                # Force a JSON object back so parsing never depends on the model
                # obeying the "no fences" instruction.
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": system},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": user_text},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/png;base64,{screenshot_b64}"},
                            },
                        ],
                    },
                ],
            },
        )

    if resp.status_code != 200:
        # Surface the provider's error verbatim so the UI shows a real reason
        # (401 invalid key, 404 unknown model, 429 rate limit, …).
        raise RuntimeError(f"OpenAI API error {resp.status_code}: {resp.text[:300]}")

    data = resp.json()
    raw = (data.get("choices") or [{}])[0].get("message", {}).get("content", "") or ""
    parsed = _parse_agent_json(raw)
    if not parsed:
        raise RuntimeError(f"Agent returned non-JSON response: {raw[:300]}")
    return parsed


# ─── Scenario synthesis fallback ─────────────────────────────────────────────

def _synthesize_scenarios_sync(
    *,
    intent: str,
    history: list[dict],
    elements: list[dict],
    page_url: str,
    page_title: str,
    visited_states: int,
) -> list[dict]:
    """
    Turn an exploration trace into concrete test scenarios.

    Called when a run ends WITHOUT the agent having emitted any scenario itself,
    so the results panel is never empty: the agent still visited real UI states,
    and those are enough for a senior-QA model to write the scenarios worth
    automating. Returns a list of {title, steps} dicts (possibly empty).
    """
    if not LLM_API_KEY:
        return []

    import httpx

    hist_lines = "\n".join(
        f"  step {h['step']}: {h['action_type']} on element {h.get('element_id', '-')} "
        f"({'novel state' if h.get('novel') else 'known state'})"
        for h in history
    ) or "  (no steps recorded)"

    el_lines = "\n".join(
        f"  [{e['id']}] <{e.get('tag')}> {(e.get('text') or '')[:40]}"
        for e in elements[:30]
    ) or "  (none)"

    system = (
        "You are a senior QA engineer. Turn an autonomous agent's exploration "
        "trace into concrete, automatable test scenarios in Given/When/Then form."
    )
    user = f"""An autonomous agent explored a web app for the QA intent below and visited {visited_states} distinct UI states, but did not formalize any scenarios. Using the intent, the action trace, and the elements on the final screen, write the test scenarios worth automating.

# QA Intent
{intent}

# Final page
URL: {page_url}
Title: {page_title}

# Action trace
{hist_lines}

# Elements on final screen
{el_lines}

Return ONLY JSON of this exact shape:
{{ "scenarios": [ {{ "title": "...", "steps": ["Given ...", "When ...", "Then ..."] }} ] }}
Write 3–6 scenarios covering happy path, negative, and edge cases relevant to the intent."""

    payload = {
        "model": VISION_MODEL,
        "max_tokens": 1200,
        "temperature": 0.3,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }

    with httpx.Client(timeout=60) as client:
        resp = client.post(
            f"{OPENAI_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {LLM_API_KEY}"},
            json=payload,
        )
    if resp.status_code != 200:
        raise RuntimeError(f"OpenAI API error {resp.status_code}: {resp.text[:200]}")

    data = resp.json()
    raw = (data.get("choices") or [{}])[0].get("message", {}).get("content", "") or ""
    parsed = _parse_agent_json(raw)
    scenarios = parsed.get("scenarios") if isinstance(parsed, dict) else None
    return scenarios if isinstance(scenarios, list) else []


# ─── State hashing for novelty detection ────────────────────────────────────

def _state_hash(url: str, elements: list[dict]) -> str:
    """
    Hash of (URL + sorted element fingerprints). Two pages with the same
    interactables in the same positions hash to the same value — so revisiting
    the login page after a failed login is correctly flagged as 'known state'.
    """
    h = hashlib.sha1()
    h.update(url.encode())
    fp = sorted(
        f"{e.get('tag')}|{e.get('selector')}|{(e.get('text') or '')[:40]}"
        for e in elements
    )
    for line in fp:
        h.update(b"\x00")
        h.update(line.encode())
    return h.hexdigest()[:16]


# ─── Action execution ────────────────────────────────────────────────────────

def _choose_select_option(locator, eid: int, sel: str, value: str) -> tuple[bool, str]:
    """
    Pick an option in a native <select>. The model typically supplies the
    visible option label (e.g. "Price (low to high)"), but sometimes the value
    attribute — try label, then value, then a case-insensitive partial match.
    """
    value = (value or "").strip()
    if not value:
        return False, f"element {eid} is a <select>; a target option value is required"

    for kwargs in ({"label": value}, {"value": value}):
        try:
            locator.select_option(timeout=5000, **kwargs)
            return True, f"selected '{value}' in element {eid} ({sel})"
        except Exception:
            continue

    # Fallback: match against the actual option labels (handles partial/fuzzy text).
    try:
        options = locator.locator("option").all_inner_texts()
        wanted = value.casefold()
        for opt in options:
            if wanted in opt.casefold():
                locator.select_option(label=opt, timeout=5000)
                return True, f"selected '{opt}' in element {eid} ({sel})"
        return False, f"no option matching '{value}' in element {eid}; options: {options}"
    except Exception as e:
        return False, f"could not select '{value}' in element {eid}: {type(e).__name__}: {e}"


def _exec_action(page, action: dict, elements: list[dict], log_event) -> tuple[bool, str]:
    """
    Run a Playwright action. Returns (success, message).
    Element resolution is by SoM id, so `elements` must be the list returned
    from the most-recent SOM_INJECT_SCRIPT call.
    """
    by_id = {e["id"]: e for e in elements}
    atype = action.get("type")

    try:
        if atype == "click":
            eid = int(action.get("element_id") or 0)
            if eid not in by_id:
                return False, f"No element with id {eid} in current SoM"
            el = by_id[eid]
            sel = el["selector"]
            # A <select> can't be "clicked" to pick an option the way the model
            # imagines — route to select_option when a target value is given.
            if (el.get("tag") or "").lower() == "select" and action.get("value"):
                return _choose_select_option(page.locator(sel).first, eid, sel, action["value"])
            page.locator(sel).first.click(timeout=5000)
            return True, f"clicked element {eid} ({sel})"

        if atype == "fill":
            eid = int(action.get("element_id") or 0)
            value = action.get("value") or ""
            if eid not in by_id:
                return False, f"No element with id {eid} in current SoM"
            el = by_id[eid]
            sel = el["selector"]
            # Dropdowns are <select>, not text inputs — fill() raises on them.
            # Translate a fill-on-select into the correct select_option call.
            if (el.get("tag") or "").lower() == "select":
                return _choose_select_option(page.locator(sel).first, eid, sel, value)
            page.locator(sel).first.fill(value, timeout=5000)
            return True, f"filled element {eid} ({sel}) with '{value}'"

        if atype == "navigate":
            url = action.get("url")
            if not url:
                return False, "navigate requires url"
            page.goto(url, wait_until="domcontentloaded", timeout=15000)
            return True, f"navigated to {url}"

        if atype in ("complete_goal", "discover_scenario", "stop"):
            return True, f"meta:{atype}"

        return False, f"unknown action type '{atype}'"
    except PWTimeout as e:
        return False, f"timeout: {e}"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


# ─── Main exploration loop ───────────────────────────────────────────────────

def _run_exploration_sync(
    *,
    intent: str,
    start_url: str,
    max_steps: int,
    headless: bool,
    run_id: str,
) -> None:
    """
    Synchronous implementation. Run from a worker thread via asyncio.to_thread()
    so it doesn't block the FastAPI event loop and avoids the asyncio subprocess
    transport issue under uvicorn's selector loop on Windows.
    """

    def emit(event_type: str, **payload) -> None:
        evt = {"type": event_type, "ts": time.time(), **payload}
        _broker.publish_threadsafe(run_id, evt)
        logger.info("agent[%s] %s %s", run_id[:8], event_type, payload.get("brief", ""))

    emit("status", message=f"Launching browser (headless={headless})", brief="launching")

    sub_goals_pending: list[str] = []
    sub_goals_done: list[str] = []
    history: list[dict] = []
    lessons: list[str] = []
    discovered: list[DiscoveredScenario] = []
    state_set: set[str] = set()
    plateau = 0
    step = 0
    # Kept fresh each iteration; also read by finish() for the synthesis fallback.
    elements: list[dict] = []
    page_url = start_url
    page_title = ""

    def finish(reason: str, brief: str) -> None:
        """
        Emit the terminal 'done' event. If the agent never formalized a scenario
        itself, synthesize scenarios from the exploration trace first so the
        results panel is never empty.
        """
        if not discovered:
            emit("status",
                 message="Run ended with no explicit scenarios — synthesizing from the exploration trace…",
                 brief="synthesize")
            try:
                for sc in _synthesize_scenarios_sync(
                    intent=intent,
                    history=history,
                    elements=elements,
                    page_url=page_url,
                    page_title=page_title,
                    visited_states=len(state_set),
                ):
                    title = (sc.get("title") or "").strip() or f"Scenario {len(discovered) + 1}"
                    steps = [str(s) for s in (sc.get("steps") or []) if str(s).strip()]
                    if not steps:
                        continue
                    ds = DiscoveredScenario(title=title, steps=steps)
                    discovered.append(ds)
                    emit("scenario_discovered", title=title, steps=steps, step=step, synthesized=True)
            except Exception as e:
                emit("status", message=f"Scenario synthesis failed: {type(e).__name__}: {e}", brief="synth-fail")

        emit("done", reason=reason,
             total_steps=step, total_novel_states=len(state_set),
             scenarios=[d.__dict__ for d in discovered], brief=brief)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
            try:
                context = browser.new_context(
                    user_agent="NextGenQA-AgentExplorer/1.0 (+research)",
                    viewport={"width": 1280, "height": 800},
                )
                page = context.new_page()
                page.goto(start_url, wait_until="domcontentloaded", timeout=20000)
                emit("status", message=f"Page loaded: {start_url}", brief=f"goto {start_url}")

                while step < max_steps:
                    step += 1

                    # 1. Inject SoM overlay → element map.
                    try:
                        page.wait_for_load_state("networkidle", timeout=3000)
                    except PWTimeout:
                        pass
                    elements = page.evaluate(SOM_INJECT_SCRIPT)
                    page_url = page.url
                    page_title = page.title() or "(no title)"

                    # 2. Screenshot WITH boxes — that's what the model sees.
                    shot_bytes = page.screenshot(type="png", full_page=False)
                    shot_b64 = base64.b64encode(shot_bytes).decode("ascii")

                    # 3. State hash (using clean elements, not the overlay).
                    h = _state_hash(page_url, elements)
                    novel = h not in state_set
                    if novel:
                        state_set.add(h)
                        plateau = 0
                    else:
                        plateau += 1

                    emit("screenshot",
                         step=step,
                         b64=shot_b64,
                         elements=elements,
                         url=page_url,
                         title=page_title,
                         state_hash=h,
                         novel_state=novel,
                         total_novel_states=len(state_set))

                    if plateau >= PLATEAU_LIMIT:
                        finish(f"coverage plateau ({PLATEAU_LIMIT} steps without novel state)", "plateau")
                        return

                    # 4. Ask the agent for next action.
                    try:
                        agent_reply = _call_vision_llm_sync(
                            intent=intent,
                            sub_goals_done=sub_goals_done,
                            sub_goals_pending=sub_goals_pending,
                            history=history[-HISTORY_WINDOW:],
                            lessons=lessons,
                            elements=elements,
                            screenshot_b64=shot_b64,
                            page_url=page_url,
                            page_title=page_title,
                        )
                    except Exception as e:
                        emit("error", message=f"LLM call failed: {type(e).__name__}: {e}")
                        return

                    # 5. Stream each role's thought as if it came from a separate agent.
                    for role in ("planner", "actor", "observer", "critic"):
                        thought = (agent_reply.get(f"thought_{role}") or "").strip()
                        if thought:
                            emit("thought", role=role, text=thought, step=step)

                    # 6. Update planner queue from PLANNER's output. We do this by
                    # treating the planner's commentary as authoritative when it
                    # mentions sub-goals — but to keep things simple we let the
                    # ACTOR drive forward via complete_goal and discover_scenario.
                    action = agent_reply.get("action") or {}
                    if action.get("lesson"):
                        lessons.append(action["lesson"])
                        emit("lesson", text=action["lesson"], step=step)

                    atype = action.get("type")

                    # Meta actions: don't hit the page; just bookkeep.
                    if atype == "stop":
                        finish("agent emitted stop", "stop")
                        return

                    if atype == "discover_scenario":
                        sc = action.get("scenario") or {}
                        title = (sc.get("title") or "").strip() or f"Scenario {len(discovered)+1}"
                        steps = [str(s) for s in (sc.get("steps") or []) if str(s).strip()]
                        ds = DiscoveredScenario(title=title, steps=steps)
                        discovered.append(ds)
                        emit("scenario_discovered", title=title, steps=steps, step=step)
                        history.append({"step": step, "action_type": "discover_scenario",
                                        "element_id": None, "novel": novel})
                        continue

                    if atype == "complete_goal":
                        # If queue empty, store the goal that was implicit in actor's reasoning.
                        goal_label = (action.get("reason") or "").strip()[:80] or f"goal #{len(sub_goals_done)+1}"
                        if sub_goals_pending:
                            done_goal = sub_goals_pending.pop(0)
                            sub_goals_done.append(done_goal)
                        else:
                            sub_goals_done.append(goal_label)
                        emit("coverage", goals_done=sub_goals_done, goals_pending=sub_goals_pending, step=step)
                        history.append({"step": step, "action_type": "complete_goal",
                                        "element_id": None, "novel": novel})
                        continue

                    # Real browser action.
                    ok, msg = _exec_action(page, action, elements, emit)
                    emit("action",
                         action_type=atype,
                         element_id=action.get("element_id"),
                         value=action.get("value"),
                         url=action.get("url"),
                         reason=action.get("reason"),
                         success=ok,
                         message=msg,
                         step=step)
                    history.append({
                        "step": step,
                        "action_type": atype,
                        "element_id": action.get("element_id"),
                        "novel": novel,
                        "ok": ok,
                    })

                    # Settle so the next iteration's screenshot reflects the change.
                    try:
                        page.wait_for_load_state("networkidle", timeout=3000)
                    except PWTimeout:
                        pass

                # Hit max_steps.
                finish(f"reached max_steps={max_steps}", "maxsteps")
            finally:
                browser.close()
    except Exception as e:
        emit("error", message=f"{type(e).__name__}: {e}")
        raise
    finally:
        _broker.close(run_id)


async def run_exploration(
    *,
    intent: str,
    start_url: str,
    run_id: str,
    max_steps: int = MAX_STEPS_DEFAULT,
    headless: bool = False,
) -> None:
    """Public async entry point. Streams events via the broker; returns when done."""
    await asyncio.to_thread(
        _run_exploration_sync,
        intent=intent,
        start_url=start_url,
        max_steps=max_steps,
        headless=headless,
        run_id=run_id,
    )
