# Independent Validation of Generated Test Cases

**Component 2 — Intelligent Test Case Generation · NextGen QA (R26-SE-039)**

This document describes the validation gate added in response to the research panel
comment *"make sure to have a mechanism to independently validate the generated test
cases"*. It validates both artefacts the component produces — Gherkin scenarios
(Stage 2) and executable test suites (Stage 5) — before they are approved or executed.

## 1. Why "independent"

Before this gate, the only checks on a generated artefact were the LLM that produced it
and the QA engineer who clicked *Approve*. A generator cannot be trusted to grade its
own output, and a human reviewer cannot be the only safeguard at scale. The gate adds
checks whose correctness does **not** depend on the generator:

| Layer | Independence comes from | Runs without LLM |
|---|---|---|
| Deterministic static checks | Pure functions of the artefact text, the crawled DOM map and the source Gherkin — no model involved | Yes |
| LLM judge | A **different model/vendor** from the generator (`VALIDATOR_MODEL`), in a reviewer role with a different prompt, told explicitly not to trust the code | No |
| Execution calibration | The real CI/CD result of the same suite, compared against the prediction | Yes |
| Human review | QA sees the findings, the per-scenario prediction and the diff before approving | — |

## 2. What is checked

### 2.1 Static checks (`backend/app/validation/static_checks.py`)

Test suites (Playwright / Selenium / Cypress):

- **Syntax** — `ast.parse` for Python, bracket/string scanner plus `node --check` for JavaScript. A syntax error is *critical*: the file cannot be collected, so every test fails.
- **Structure** — at least one `test_*` / `it(...)`; no empty test bodies; tests never call other tests (fixtures are not injected → `TypeError`).
- **Vacuous tests** — every test must assert its *Then* outcome (`assert`, `expect`, `.should`, explicit waits, or a helper that asserts). A test without an assertion can never fail on a defect.
- **Scenario coverage** — every Gherkin scenario title must map to an implementing test (lexical match on name/docstring/body).
- **Selector grounding (Mode B)** — selectors used in the code are compared against the crawled element map. Unverified selectors are reported as one grouped *minor* finding with the closest crawled candidates, so hallucinated locators are visible but a partial crawl does not fail the suite.
- **CI constraints** — headed browser launches, long fixed sleeps, leftover `TODO`s, unresolved `<<PLACEHOLDER>>` locators in DOM-aware code.
- **Known fatal anti-patterns** — dry-run of the deterministic sanitizer (e.g. clicking the same `#add-to-cart-*` twice).

Gherkin:

- `Feature:` header, at least one scenario, every scenario has *When* and *Then* (a scenario without *Then* produces a test with nothing to assert).
- Duplicate titles, scenarios starting with *And/But*, outlines without `Examples`, placeholders without a matching column.
- Vague, untestable wording ("works correctly", "should work").
- **Acceptance-criteria traceability** — each criterion of the user story must lexically map to at least one scenario.

### 2.2 LLM judge (`backend/app/validation/judge.py`)

The judge receives the Gherkin, the line-numbered code, the (explicitly *partial*) DOM map,
known facts about the target application, and the static findings already discovered (so
it does not repeat them). It returns strict JSON:

- `pass_probability` — holistic probability the suite passes as-is;
- per-scenario `predicted: pass | fail | uncertain` with confidence and a one-line reason;
- findings with severity, line number, offending snippet, concrete suggestion and `fixable`;
- for Gherkin: a semantic acceptance-criteria coverage table.

Severity is defined in the prompt (critical = file will not run / one root cause fails most
tests; major = one test fails or is vacuous; minor = fragile/unverified).

### 2.3 Score and verdict (`backend/app/validation/service.py`)

```
static_score  = 100 − Σ penalty          (critical −25, major −10, minor −3)
scenario_rate = predicted-pass / judged scenarios × 100
base          = 0.5·judge + 0.3·scenario_rate + 0.2·static_score   (static only when no judge)
caps          : static critical → ≤15 · judge critical → ≤40 · any major → ≤85
verdict       : likely_failing (critical or <50) · ready (≥80, no major) · needs_review
```

The breakdown (weights, caps applied, counts, model used, whether it is an independent
model) is stored with every report and shown in the UI under *How the score is computed*.

### 2.4 Auto-fix (`backend/app/validation/fixer.py`)

The fixer receives the artefact and the selected findings (ids, lines, suggestions) and
returns the minimally changed artefact plus a change log mapping each edit to a finding.
Deterministic repairs run afterwards. The proposal is **never saved automatically**: the UI
shows a side-by-side diff, the change log and the deterministic before/after score; applying
creates a *new suite version* (the original is kept) and triggers a re-validation linked to
the previous report, so the before → after score is visible.

### 2.5 Calibration (predicted vs actual)

`GET /api/v1/validation/projects/{id}/summary` joins each suite's latest report with its
latest finished CI execution and reports predicted pass-rate vs actual pass-rate plus the
mean absolute error. This is the evidence that the validator is informative, and it is the
metric to report in the evaluation (alongside M1 executability and M5 fault detection).

## 3. Persistence

`validation_reports` (created automatically on startup via `create_all`):
`target_type` (suite | gherkin), `target_id`, `content_hash` (so the UI can mark a report
*outdated* when the text changed), score fields, `findings` / `scenarios` / `breakdown`
JSONB, `validator_provider` / `validator_model`, `duration_ms`, `parent_report_id`.

## 4. API

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/v1/validation/suites/{suite_id}` | Validate a suite (body: `parent_report_id?`, `use_llm?`) |
| GET | `/api/v1/validation/suites/{suite_id}` | Latest report (+ `is_current`) |
| POST | `/api/v1/validation/suites/{suite_id}/fix` | Fix proposal (body: `finding_ids?`, `code?`) — not saved |
| POST / GET | `/api/v1/validation/gherkin/{gherkin_id}` | Same for Gherkin |
| POST | `/api/v1/validation/gherkin/{gherkin_id}/fix` | Fix proposal (body: `finding_ids?`, `text?`) |
| GET | `/api/v1/validation/projects/{id}/latest?target_type=` | Latest report per artefact |
| GET | `/api/v1/validation/projects/{id}/summary` | Counts, averages, calibration |
| GET | `/api/v1/validation/reports/{report_id}` | One report |

## 5. Configuration

```
# backend/.env
VALIDATOR_PROVIDER=openai      # optional; defaults to LLM_PROVIDER
VALIDATOR_MODEL=gpt-4o         # pin a DIFFERENT model than LLM_MODEL for independence
VALIDATOR_API_KEY=             # optional; defaults to LLM_API_KEY
```

If no LLM is configured, validation still runs (static checks only) and the report says so.
On the EC2 deployment the same variables go into the server's `backend/.env`.

## 6. UI (merged frontend, `feature/test-case-validation`)

- **Code Review** — each suite card shows its predicted pass %, verdict, predicted-pass
  scenarios and critical/major counts; *Validate All Suites*; a summary strip with validated
  count, average score and predicted-vs-actual calibration.
- **Suite editor** — *Validate* button; right-hand validation panel with score ring,
  per-scenario prediction, findings grouped by severity (each tagged *Static check* or
  *AI judge*, line numbers jump to the code), score breakdown; *Auto-fix with AI* opens a
  diff dialog; *Apply as new version & re-validate* shows the before → after score.
- **Gherkin editor** — the same panel and fix flow for scenarios, plus acceptance-criteria
  coverage.

## 7. Evaluation hooks for the paper

- Report **validator precision/recall** on a labelled sample: findings confirmed by execution ÷ findings raised.
- Report **calibration**: MAE between predicted and actual pass rate across executed suites (available from the summary endpoint).
- Report **fix effectiveness**: score and actual pass-rate before vs after auto-fix, using `parent_report_id` chains.
- Repeat with `VALIDATOR_MODEL` equal to vs different from `LLM_MODEL` to quantify the value of model independence.

## 8. Tests

`backend/tests/test_validation_static.py` — 21 unit tests covering the Gherkin parser,
every static rule, selector extraction, scoring and caps. No LLM or database is needed.

//
