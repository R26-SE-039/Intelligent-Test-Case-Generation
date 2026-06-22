# Page 8 – Agent Explorer (Novelty)

**URL:** `/dashboard/agent-explorer`
**This is the research novelty of Component 2.**

---

## Simple Speech for Viva

> "This is the Agent Explorer page. This is the part of the system that makes our research a real contribution and not just another test generator.
>
> The problem we are solving: in the normal pipeline, the QA engineer must write a user story for every single test case. Login with valid password, login with wrong password, login with empty fields, login when locked out — that is four user stories the QA must think of. If they forget one, that bug never gets tested.
>
> The Agent Explorer fixes this. The QA writes only one short sentence — for example *'check the login flow'* — and an autonomous AI agent does everything else: it opens a real browser, looks at the page, decides what to test, clicks the buttons, types the values, watches what happens, and reports back every scenario it discovered.
>
> When the page opens, the user sees three panels.
>
> On the **left side** is the **Live View**. This is a real screenshot of a real Chromium browser, updated after every action. We draw red numbered boxes on top of every clickable element on the page — input fields, buttons, links. This technique is called **Set-of-Mark grounding**, from a 2023 research paper by Yang and team. It is important because it stops the AI from guessing wrong CSS selectors, which is the number one failure of normal LLM browser agents.
>
> In the **middle** is the **Agent Reasoning** panel. The AI plays four roles in every step:
> - **Planner** (blue): decides which sub-goal to work on next
> - **Actor** (purple): picks the next concrete action and the element to click
> - **Observer** (green): notes what should change after the action
> - **Critic** (amber): reflects on whether the previous step worked
>
> Each role's thought is shown as a separate card so the panel can read what the AI is thinking in real time. This is much more transparent than a single black-box LLM.
>
> On the **right side** is the **Coverage and Discoveries** panel. We show:
> - How many novel page states the agent has discovered (this is our coverage metric)
> - Every test scenario the agent has validated, written in plain Given/When/Then steps
> - The Reflexion Memory — short lessons the agent learned when something failed, so it does not repeat the same mistake
>
> The agent stops by itself when it cannot find any new page state for three steps in a row. We call this **coverage-driven termination**, and this is one of our novel research contributions because most other agents stop after a fixed number of steps even if they are still finding new things, or they keep running forever in a loop.
>
> So in one sentence — the QA types one intent, watches a real browser get explored autonomously, and gets back a list of test scenarios the agent itself discovered, including ones the QA never thought of."

---

## What the panel sees in the live demo

1. QA types `Check the login flow on this site` and the URL `https://www.saucedemo.com`
2. Click **Run Agent**
3. A real Chromium window opens (we run headed for the demo)
4. After 1–2 seconds the screenshot appears with red numbered boxes around the username field, password field, and login button
5. The agent's Planner card appears: *"I will cover four sub-goals: valid login, invalid password, empty fields, locked-out user"*
6. The Actor card appears: *"I will fill element 1 with 'standard_user'"* — and the screenshot updates showing the value typed
7. After several steps the agent emits its first scenario: *"Login fails with invalid password — error message shown"*
8. The novel-state counter ticks up; the scenario card animates into the right panel
9. After it discovers the locked-out user behaviour (something the QA did not ask about) the panel sees the agent has gone *beyond* the original intent

---

## Five Novelty Layers — what to defend in viva

The dissertation does not claim "we used an LLM." It claims a five-layer architecture, each layer from a published 2023–2025 research technique.

| # | Layer | What it is | Source |
|---|-------|------------|--------|
| 1 | **Multi-role agent loop** | One Claude vision call produces four role-tagged thoughts: Planner, Actor, Observer, Critic | ReAct pattern — Yao et al. 2022 |
| 2 | **Set-of-Mark visual grounding** | Numbered red boxes drawn on screenshots; agent picks "element 7" instead of guessing CSS | Yang et al. 2023 |
| 3 | **DOM-diff state hashing** | Each page state hashed by URL + sorted element fingerprints; novel state = new hash | Custom, inspired by WebArena 2024 |
| 4 | **Reflexion memory** | When a step fails, agent writes a short lesson; lesson is fed into next prompt | Yao et al. 2023 (Reflexion) |
| 5 | **Coverage-driven termination** | Stop when no new state for N consecutive steps, instead of fixed step budget | Our novel contribution |

---

## Technology Stack — what runs the demo

### Backend (Python, FastAPI)

| Library | Purpose |
|---------|---------|
| **Anthropic Claude Sonnet 4.6 (vision)** | The brain — sees screenshots, returns structured JSON action |
| **Playwright (sync_playwright)** | Drives the real Chromium browser, captures screenshots, executes clicks/fills |
| **FastAPI WebSocket** | Streams typed events (`screenshot`, `thought`, `action`, `scenario_discovered`, `done`) to the React dashboard |
| **asyncio.to_thread** | Runs the synchronous Playwright + LLM loop without blocking the FastAPI event loop |
| **In-memory pub/sub broker** | Per-run event queue (`AgentBroker`) — fans out events from the worker thread to the WebSocket subscriber |
| **hashlib (SHA-1)** | Computes the per-state hash for novelty detection |
| **Pydantic** | Type-safe request/response models for the new endpoints |

### Browser-Side Injection

| Component | Purpose |
|-----------|---------|
| **`page.evaluate()` JS injector** | Runs our `SOM_INJECT_SCRIPT` inside the live page — finds every visible interactable, draws the red numbered overlay, returns the element list |
| **Absolute-positioned `<div>` overlay** | The numbered boxes live in a single overlay container so the original page DOM is not mutated |
| **CSS escape + selector builder** | Generates a unique CSS selector for each element using `id` → `data-testid` → `name` → `aria-label` → positional path fallback |

### Frontend (Next.js 16, React 19)

| Library | Purpose |
|---------|---------|
| **TypeScript discriminated union (`AgentEvent`)** | Strict typing for every event variant the WS can deliver — no `any` in the streaming layer |
| **Native WebSocket API** | Live event stream, no extra socket library needed |
| **TailwindCSS 4** | Three-panel layout, role-coloured thought cards, animated scenario badges |
| **lucide-react icons** | Sparkles, Brain, Compass, Eye, MousePointerClick — one icon per agent role |
| **React 19 hooks** | `useState` + `useRef` + `useEffect` for the live event log; auto-scroll on new entries |

### Why these choices (defend in viva)

- **Why Claude Sonnet 4.6 with vision over GPT-4o or Gemini?** Sonnet 4.6 has the most reliable JSON output mode for structured agent tools, and its vision is strong enough to correctly identify numbered SoM elements at 1280×800. We can swap the model by changing `AGENT_VISION_MODEL` in `.env`.
- **Why headed Chromium over headless for the demo?** The panel sees the browser physically open and click. Headless is faster but offers nothing visual to demo. We support both via the **Headless** checkbox.
- **Why a single LLM call playing four roles instead of four separate agents?** Four separate calls would be 4× the latency and cost. Shared context across roles in one call also gives more coherent reasoning. The architecture is still legitimately multi-role — the prompt explicitly asks for four role-tagged outputs.
- **Why in-memory broker instead of Redis?** PP1 demo is single-process. The broker is a clean abstraction so we can swap to Redis Pub/Sub if we scale to multiple workers later. The pattern is identical to the existing `dom_crawler/log_broker.py` so the codebase stays consistent.
- **Why SHA-1 over MD5 or full hashing?** SHA-1 truncated to 16 hex chars gives 64 bits of entropy — more than enough for a single demo session. The point is comparison, not cryptographic security.

---

## Key points to mention

- The QA gives **one** intent sentence — the agent decomposes it into many sub-goals
- The agent uses **vision** to read the screenshot, not raw HTML
- **Set-of-Mark** numbered boxes prevent CSS selector hallucination
- **Four role-tagged thoughts** per step give transparency, not a black box
- **Coverage-driven termination** — agent stops when it stops finding new things
- **Reflexion memory** — the agent learns from its own mistakes within a single run
- **Headed Chromium** — the panel watches the browser do real clicks and typing
- This is the bridge to **future work**: the same trace can be replayed through our existing Jinja2 → Selenium/Playwright/Cypress generators, closing the loop with the rest of Component 2

---

## What to say if the panel asks "this is just GPT, no?"

> "No. The novelty is not the LLM — that is a commodity. The contribution is the five-layer architecture: multi-role reasoning, Set-of-Mark visual grounding, DOM-diff state hashing for coverage, Reflexion-style failure memory, and coverage-driven termination. Each of these comes from a published 2023–2025 research technique that we have integrated into a single agent specifically for QA test exploration. Without this stack, the LLM would hallucinate selectors, run forever, and never know what it has already covered."
