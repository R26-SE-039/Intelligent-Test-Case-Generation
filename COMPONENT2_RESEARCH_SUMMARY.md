# Component 2 — Intelligent Test Case Generation
## Research Paper Summary & Evaluation Plan

**Author:** Abeygunasekara D T (IT22303684) · **Project:** NextGen QA (R26-SE-039) · SLIIT Faculty of Computing
**Methodology:** Design Science Research (DSR) · **Supervisors:** Ms. Suriyaa Kumari & Mr. Eishan Weerasinghe

---

## 1. What This Component Is (one paragraph for the paper)

Component 2 is the **test generation engine** of NextGen QA. It receives structured user
stories (from Component 1's meeting-transcription pipeline), and autonomously produces
**human-readable Gherkin scenarios** and **executable multi-framework test code**
(Selenium / Playwright / Cypress), grounds that code in the real application UI via a
**vision-guided exploration agent**, executes the tests through **GitHub Actions CI/CD**,
and **prioritises test execution using an ML risk model** — closing the loop from
"requirement spoken in a sprint meeting" to "test report on a dashboard" with zero
manual scripting.

**Position in pipeline:** C1 (Voice/NLP) → **C2 (this)** → C3 (Self-Healing) reads C2's failed runs → C4 (Quality/RTM) reads C2's test cases.

---

## 2. What Is Actually Implemented (system inventory)

| Module | Status | What it does |
|---|---|---|
| `gherkin/` | ✅ Built | Jinja2-first Gherkin generation (login/cart/checkout/search templates + generic fallback) with pluggable LLM slot |
| `dom_crawler/` | ✅ Built | Playwright headless crawler + auth handling, element map extraction, live log streaming |
| `agent_explorer/` | ✅ Built | **Vision-LLM agentic exploration**: Set-of-Marks (SoM) overlay → numbered screenshot → Claude vision model reasons in 4 roles (planner / actor / observer / critic) → acts via Playwright → reflexion lessons → novel-state hashing → **coverage-plateau termination** |
| `code_gen/` | ✅ Built | LLM multi-framework code generation (Anthropic/Gemini/OpenAI); Mode A abstract placeholders vs Mode B exact DOM selectors |
| `execution/` | ✅ Built | Local runner + GitHub Actions runner, WebSocket live logs, PDF report generation |
| `github_connection/` | ✅ Built | Encrypted PAT store, automatic workflow-file installation, dispatch trigger |
| `ml/` | ✅ Built (⚠ synthetic data) | RandomForest risk classifier, SMOTE balancing, feature extraction, training notebook, prediction API |
| Frontend (Next.js) | ✅ Built | Dashboard, test cards, stats, code review, execution screens (merged frontend, port per project structure) |
| Shared DB | ✅ Built | `gherkin_scenarios`, `test_cases`, `page_element_maps`, `run_results` in shared PostgreSQL |

---

## 3. Contribution Ranking — Where the Research Value Is

### 🥇 C-1. Vision-guided agentic test exploration (THE paper's core novelty — lead with this)
A goal-driven agent that *sees* the application: SoM-annotated screenshots + a
multi-role reasoning loop (planner/actor/observer/critic), reflexion memory of failed
attempts, and a **novel-state-plateau termination criterion** that stops exploring when
UI-state coverage saturates. This connects the 2024–25 web-agent literature
(Set-of-Mark prompting, WebVoyager, AppAgent, Reflexion) to **test generation** —
a combination that is genuinely publishable. No other undergraduate component in this
project space typically has this.

**Claim to write:** *"We propose coverage-driven agentic exploration: a vision-LLM agent
that autonomously discovers application behaviour and grounds generated test cases in
observed UI states, terminating when the rate of novel-state discovery plateaus."*

### 🥈 C-2. Dual-mode generation (Abstract vs DOM-aware) with executability grounding
Mode A works with no app access (placeholder locators); Mode B grounds the same Gherkin
in real crawled selectors. This gives you a **built-in ablation study**: same stories,
with/without DOM grounding → measure executability delta. Reviewers love ablations.

### 🥉 C-3. End-to-end closed loop (story → Gherkin → code → CI/CD → report)
Individually each stage exists in industry; the contribution is the **integrated,
human-in-the-loop pipeline** (QA edits Gherkin/code before execution) with live
streaming. Frame as the DSR *artifact*; measure end-to-end time and human-effort saved.

### 4th. ML risk prioritisation
Currently the weakest scientifically (see §6.1 — synthetic data). Keep it, but reframe
the claim from "94% accurate model" to "**risk-ordered execution finds faults earlier**"
and evaluate with APFD (§5.3). The approach is the contribution, not the accuracy.

---

## 4. How to Write C2 Into the Single Combined Paper

Typical structure for one combined paper (IEEE conference format, ~6–10 pages, 4 components):

| Paper section | Your C2 content |
|---|---|
| **Abstract** | One clause: "…automatically generates and executes multi-framework UI tests grounded by a vision-LLM exploration agent…" |
| **Introduction** | One contribution bullet (use C-1 claim above). State the research gap: existing generators either need manual recording (Selenium IDE/Katalon) or hallucinate selectors (pure-LLM generation) |
| **Related Work** | ~1 paragraph: (a) LLM test generation (TestPilot, ChatUniTest, CodaMosa); (b) GUI/web agents (Set-of-Mark — Yang et al. 2023, WebVoyager, AppAgent, Reflexion — Shinn et al. 2023); (c) BDD/Gherkin generation from requirements; (d) test prioritisation (APFD — Rothermel et al.). Position C2 at the intersection of (a)+(b) |
| **System Design / Methodology** | One architecture figure (6-stage pipeline), one **agent-loop figure** (SoM screenshot → 4-role reasoning → action → state hash), pseudocode box for the exploration loop with plateau termination. Dual-mode table |
| **Evaluation** | Metrics tables from §5. Lead with the ablation results (Mode A vs B, agent vs plain crawler), then APFD, then human eval |
| **Discussion / Limitations** | Synthetic ML training data, single benchmark app (SauceDemo) mitigated by phase-2 any-URL support, LLM non-determinism (report mean±std over N runs) |
| **Threats to Validity** | Internal: label derivation in synthetic data. External: SauceDemo generalisability. Construct: executability ≠ fault-finding — that's why you also measure fault detection (§5.2) |

**DSR framing:** artifact = the C2 pipeline; design cycles = Phase 1 (SauceDemo) → Phase 2
(any URL); evaluation = the metrics below; knowledge contribution = coverage-driven
agentic exploration method.

---

## 5. Evaluation Plan — Metrics That Get You Approved

### 5.1 Core generation metrics (must have)

| # | Metric | Target | How to measure |
|---|---|---|---|
| M1 | **Executability rate** | ≥ 85% | % of generated tests that run without syntax/locator error, per framework, per mode. **Report Mode A vs Mode B separately — this delta is your key ablation** |
| M2 | **Selector accuracy** | ≥ 90% | % of crawled/agent-discovered selectors that match a manually-built ground-truth element map of SauceDemo |
| M3 | Generation latency | < 10 s/scenario | story → `.feature`; and < 3 min end-to-end story → report |
| M4 | **Scenario coverage** | ≥ 80% | % of acceptance criteria that map to ≥1 generated scenario (traceability — also feeds C4's RTM) |

### 5.2 Fault-detection metrics (the panel's "so what?" answer)

| # | Metric | How to measure |
|---|---|---|
| M5 | **Fault detection rate** | 💡 **SauceDemo ships seeded defects for free**: run the same generated suite as `standard_user` (all pass) vs **`problem_user` / `error_user` / `visual_user`** (broken images, misrouted clicks, checkout failures). % of seeded behavioural defects your generated tests flag = your fault-detection score, with zero benchmark-building effort |
| M6 | Mutation score (optional, stronger) | `mutmut` on a small clone/local app — % of injected mutants killed by generated tests |

### 5.3 Agent & ML metrics

| # | Metric | How to measure |
|---|---|---|
| M7 | **UI-state coverage of agent vs baseline** | # unique states / % interactive elements reached: agentic explorer vs plain BFS crawler vs random walker, at equal step budget. **This is the headline chart for contribution C-1** |
| M8 | Agent efficiency | Steps-to-goal, LLM tokens & cost per scenario, mean±std over ≥5 runs (LLM non-determinism) |
| M9 | Reflexion ablation | Goal-completion rate with vs without reflexion memory |
| M10 | **APFD (Average Percentage of Faults Detected)** | Execute suite in ML-risk order vs random order vs alphabetical; compute APFD across the problem_user faults. **This converts the ML model from "synthetic-data classifier" into a defensible prioritisation result** |
| M11 | ML classification report | Per-class precision/recall/F1 + confusion matrix (currently acc 94.3% / macro-F1 0.943 — but see §6.1 caveat) |

### 5.4 Human evaluation (needed for the "quality" claim)

| # | Metric | How |
|---|---|---|
| M12 | Gherkin quality | ≥5 QA practitioners rate 10–15 generated scenarios on 1–5 Likert: readability, correctness, completeness. Target mean ≥ 4/5. **Report inter-rater agreement (Fleiss' κ)** — this single number makes the survey look rigorous |
| M13 | Effort savings | Time for a QA to write the login/cart/checkout suite manually vs review-and-approve generated suite. Even n=3 participants gives a compelling "X× faster" figure |

---

## 6. Gaps — What Needs More Work Before Submission

### 6.1 ⚠ CRITICAL: the ML model's synthetic-data problem
Current state: 94.25% accuracy, **but** the training CSV is synthesised and the risk
label is *derived from* `past_pass_rate` — which is also the model's dominant feature
(58% importance). The model is partly re-learning its own labelling rule. Worse, the
RandomForest scores **identical** accuracy (0.9425) to the single decision-tree baseline,
so the paper cannot claim RF adds value on this data. A reviewer or viva panel member
who asks one question about data provenance will find this.

**Fix (pick at least one):**
1. **Best:** accumulate real `run_results` rows during your own evaluation runs (you'll
   generate hundreds of executions doing §5 anyway) and retrain on real features.
2. **Good:** mine real bug data — GitHub Issues (`label:bug`) from open-source web apps
   as originally planned (500+ records).
3. **Minimum:** keep synthetic training but *say so openly* in Limitations, present the
   pipeline as the contribution, and let **APFD (M10)** carry the prioritisation claim —
   "risk-ordered execution detected faults earlier than random order" is defensible even
   with an imperfect model.

Never present 94.25% as a headline result without the data-provenance caveat.

### 6.2 Other gaps
- **No ground-truth element map yet** → build one manual SauceDemo element inventory (an afternoon's work) to unlock M2 and M7.
- **Single target app** → run the pipeline once on 1–2 extra public demo apps (e.g. OrangeHRM demo, the-internet.herokuapp.com) purely to claim generalisability; results don't need to be as strong.
- **No repeated-run statistics** → every LLM-dependent number should be mean ± std over ≥5 runs.
- **Human eval not yet done** → schedule the 5-practitioner survey early; ethics/consent may need lead time.
- **Baseline comparison** → add one "naïve LLM" baseline: zero-shot ChatGPT/Claude prompt "write a Selenium test for this story" with no DOM grounding → measure its executability vs your Mode B. Expect a big gap in your favour; that's your best table.

---

## 7. Viva / Review Defence Cheat-Sheet

| They ask | You answer |
|---|---|
| "Isn't this just an LLM wrapper?" | No — the LLM is one stage in a closed loop: vision-grounded exploration constrains generation to *real* selectors (measured: Mode B executability ≥85% vs naïve LLM baseline), coverage-plateau termination makes exploration bounded and measurable, and CI/CD execution feeds results back for prioritisation |
| "Your ML accuracy is on synthetic data" | Correct, and we state it — the classifier bootstraps the pipeline; the scientific claim is prioritisation utility, shown by APFD on real seeded faults, not classifier accuracy |
| "Why SauceDemo?" | Standard benchmark in test-automation literature with **built-in seeded-defect accounts** enabling controlled fault-detection measurement; generalisability shown by any-URL Mode B runs on secondary apps |
| "Novelty vs Selenium IDE / Katalon?" | Those record what a human does. Ours *discovers* the app autonomously via a vision agent, links behaviour to sprint-meeting requirements, and needs zero recording |
| "What if the demo fails live?" | Mode A works offline; recorded video of a full Mode B run as fallback; local runner exists alongside GitHub Actions |

---

## 8. Priority Order (my recommendation)

1. **Build the SauceDemo ground-truth element map** → unlocks M2, M7 immediately.
2. **Run the ablation grid** (Mode A vs B vs naïve-LLM baseline; agent vs BFS crawler) — this is 80% of your evaluation section.
3. **Run the problem_user fault-detection experiment + APFD ordering** — turns the ML story from liability into result.
4. **Retrain ML on the real run data** you just produced in steps 2–3.
5. **Human eval survey** (5 QA practitioners, Fleiss' κ).
6. Write Limitations honestly (synthetic bootstrap, single primary benchmark, LLM cost/variance).

---

*NextGen QA — Component 2 | Abeygunasekara D T | IT22303684 | R26-SE-039*
