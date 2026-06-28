# NextGen QA — Component 2 Database Schema

> Source of truth: [`backend/app/models.py`](backend/app/models.py)
> Startup migration: [`backend/app/database.py`](backend/app/database.py)
> Database: PostgreSQL 15 (`nextgen_qa`)
> Connection: `postgresql://admin:password123@localhost:5432/nextgen_qa`

---

## Table Index

| Table | Purpose | Owned by |
|---|---|---|
| [`projects`](#projects) | Top-level workspace container | C2 |
| [`user_stories`](#user_stories) | Stories from C1 or manual entry | C1 → C2 reads |
| [`gherkin_scenarios`](#gherkin_scenarios) | AI-generated Gherkin per story | C2 |
| [`test_suites`](#test_suites) | Versioned LLM-generated test code | C2 |
| [`dom_elements`](#dom_elements) | Real selectors crawled from staging DOM | C2 |
| [`test_runs`](#test_runs) | Per-scenario execution rows (ML labels) | C2 → C3/C4 read |
| [`test_run_executions`](#test_run_executions) | One row per "Run Tests" click | C2 |
| [`test_run_screenshots`](#test_run_screenshots) | Per-scenario screenshot index | C2 |

---

## Enumerations

```sql
-- Used by user_stories.priority
priority_enum: 'high' | 'medium' | 'low'

-- Used by user_stories.status
status_enum:   'pending' | 'processing' | 'done'
```

String columns hold the rest (no DB-level enum) so values are easy to add without migrations:

| Column | Allowed values |
|---|---|
| `gherkin_scenarios.generator` | `jinja2`, `llm` |
| `test_suites.framework` | `selenium`, `playwright`, `cypress` |
| `test_suites.language` | `python`, `javascript` |
| `test_suites.mode` | `abstract`, `dom` |
| `test_runs.status` | `passed`, `failed`, `error` |
| `test_run_executions.mode` | `github`, `local` |
| `test_run_executions.status` | `queued`, `running`, `passed`, `failed`, `error` |
| `test_run_screenshots.status` | `passed`, `failed` |

---

## Relationship overview

```
projects (1) ──┬──< user_stories         (CASCADE on delete)
               ├──< gherkin_scenarios    (CASCADE)
               ├──< test_suites          (CASCADE)
               ├──< dom_elements         (CASCADE)
               ├──< test_runs            (CASCADE)
               └──< test_run_executions  (CASCADE)
                       │
                       └──< test_run_screenshots  (CASCADE on delete of run)

test_suites (1) ──< test_runs              (SET NULL on delete)
test_suites (1) ──< test_run_executions    (SET NULL on delete)

user_stories ──── gherkin_scenarios         (composite FK (story_id, project_id))
```

---

## `projects`

Top-level container. Every other domain row hangs off a project.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `UUID` | PK, default `gen_random_uuid()` | |
| `name` | `VARCHAR(200)` | NOT NULL, UNIQUE | One workspace per name |
| `description` | `TEXT` | NULL | |
| `created_at` | `TIMESTAMPTZ` | default `NOW()` | |
| `updated_at` | `TIMESTAMPTZ` | onupdate `NOW()` | |

---

## `user_stories`

Stories arriving from Component 1 (voice/NLP) or entered manually. Same story id can exist across projects → composite primary key.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `VARCHAR(50)` | PK (composite with `project_id`) | e.g. `US-042` |
| `project_id` | `UUID` | PK (composite), FK→`projects.id` ON DELETE CASCADE, NOT NULL | |
| `actor` | `VARCHAR(200)` | NOT NULL | |
| `action` | `VARCHAR(500)` | NOT NULL | |
| `goal` | `VARCHAR(500)` | NOT NULL | |
| `priority` | `priority_enum` | default `medium` | |
| `status` | `status_enum` | default `pending` | |
| `source` | `VARCHAR(20)` | default `manual` | `C1` or `manual` |
| `acceptance_criteria` | `TEXT` | default `'[]'` | JSON array as text |
| `created_at` | `TIMESTAMPTZ` | default `NOW()` | |
| `updated_at` | `TIMESTAMPTZ` | onupdate `NOW()` | |

**Indexes / constraints**
- Primary key: `(id, project_id)`
- Foreign key: `project_id → projects.id` (cascade)

---

## `gherkin_scenarios`

AI-generated Given/When/Then text per user story. QA can edit and toggle approval.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `UUID` | PK | |
| `story_id` | `VARCHAR(50)` | NOT NULL | Composite FK with `project_id` (see below) |
| `project_id` | `UUID` | FK→`projects.id` ON DELETE CASCADE, NOT NULL | |
| `feature_name` | `VARCHAR(255)` | NOT NULL | |
| `gherkin_text` | `TEXT` | NOT NULL | Full `.feature` file body |
| `generator` | `VARCHAR(20)` | default `jinja2` | `jinja2` \| `llm` |
| `llm_model` | `VARCHAR(100)` | NULL | e.g. `gpt-4o`, `codellama` |
| `edited_by_qa` | `BOOLEAN` | default `false` | |
| `approved` | `BOOLEAN` | default `false` | |
| `created_at` | `TIMESTAMPTZ` | default `NOW()` | |
| `updated_at` | `TIMESTAMPTZ` | onupdate `NOW()` | |

**Indexes / constraints**
- Foreign key: composite `(story_id, project_id) → user_stories (id, project_id)` (cascade) — added by the startup migration in `database.py`.

---

## `test_suites`

Versioned LLM-generated test code. Each `(project, framework)` is an append-only chain of versions.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `UUID` | PK | |
| `project_id` | `UUID` | FK→`projects.id` ON DELETE CASCADE, NOT NULL | |
| `framework` | `VARCHAR(40)` | NOT NULL | `selenium` \| `playwright` \| `cypress` |
| `language` | `VARCHAR(40)` | NOT NULL | `python` \| `javascript` |
| `filename` | `VARCHAR(255)` | NOT NULL | e.g. `test_suite_playwright.py` |
| `code` | `TEXT` | NOT NULL | Generated source |
| `mode` | `VARCHAR(40)` | NOT NULL | `abstract` \| `dom` |
| `url` | `TEXT` | NOT NULL | Target staging URL |
| `llm_model` | `VARCHAR(100)` | NULL | |
| `source_scenarios_hash` | `VARCHAR(64)` | NOT NULL | SHA-256 of input scenarios + DOM |
| `source_scenario_ids` | `JSONB` | NOT NULL, default `[]` | |
| `source_scenario_count` | `INTEGER` | NOT NULL, default 0 | |
| `version` | `INTEGER` | NOT NULL, default 1 | 1-based per `(project, framework)` |
| `is_active` | `BOOLEAN` | NOT NULL, default `true` | Head of the chain |
| `selected_for_run` | `BOOLEAN` | NOT NULL, default `false` | One per project max |
| `created_at` | `TIMESTAMPTZ` | default `NOW()` | |
| `updated_at` | `TIMESTAMPTZ` | onupdate `NOW()` | |

**Indexes / constraints**
- Unique: `uq_test_suites_project_framework_version (project_id, framework, version)`
- Foreign key: `project_id → projects.id` (cascade)

**Lifecycle invariants** (enforced in application code, not DB constraints)
- Exactly one `is_active=true` row per `(project_id, framework)`.
- At most one `selected_for_run=true` row per `project_id`.
- Selecting a non-active version for run is rejected with HTTP 409.
- `version` is monotonically increasing — `restore` and `save-as-new-version` both insert at `max(version)+1`.

---

## `dom_elements`

Real CSS selectors extracted by the Playwright crawler. QA can edit or add manually.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `UUID` | PK | |
| `project_id` | `UUID` | FK→`projects.id` ON DELETE CASCADE, NOT NULL | |
| `url` | `TEXT` | NOT NULL | Page the element lives on |
| `selector` | `TEXT` | NOT NULL | e.g. `#user-name` |
| `tag` | `VARCHAR(40)` | NOT NULL | `INPUT`, `BUTTON`, `A`, ... |
| `text` | `TEXT` | NULL | Visible text / value |
| `attributes` | `JSONB` | NOT NULL, default `{}` | id, name, type, placeholder, aria-label, ... |
| `role` | `VARCHAR(120)` | NOT NULL | Semantic label: `username_input`, `login_button`, ... |
| `source_step` | `TEXT` | NULL | Gherkin step / heuristic that produced it |
| `confidence` | `FLOAT` | NULL | 0..1, crawler's confidence in the role mapping |
| `edited_by_qa` | `BOOLEAN` | default `false` | |
| `approved` | `BOOLEAN` | default `false` | |
| `created_at` | `TIMESTAMPTZ` | default `NOW()` | |
| `updated_at` | `TIMESTAMPTZ` | onupdate `NOW()` | |

**Indexes / constraints**
- Unique: `uq_dom_elements_project_url_role (project_id, url, role)`
- Foreign key: `project_id → projects.id` (cascade)

---

## `test_runs`

One row per executed scenario. Drives the ML risk model (failure rate per flow becomes the supervised label).

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `UUID` | PK | |
| `project_id` | `UUID` | FK→`projects.id` ON DELETE CASCADE, NOT NULL, **indexed** | |
| `suite_id` | `UUID` | FK→`test_suites.id` ON DELETE SET NULL, NULL | |
| `scenario_name` | `VARCHAR(255)` | NOT NULL | |
| `flow_name` | `VARCHAR(64)` | NOT NULL, **indexed** | `login_flow`, `cart_ops`, `checkout`, `search`, `other` |
| `framework` | `VARCHAR(40)` | NOT NULL | |
| `status` | `VARCHAR(20)` | NOT NULL | `passed` \| `failed` \| `error` |
| `duration_ms` | `INTEGER` | NULL | |
| `error_message` | `TEXT` | NULL | |
| `executed_at` | `TIMESTAMPTZ` | default `NOW()`, **indexed** | |

**Indexes / constraints**
- Indexes: `project_id`, `flow_name`, `executed_at`
- Foreign keys: `project_id` (cascade), `suite_id` (set null)

---

## `test_run_executions`

One row per click of "Run Tests" — the run-level record. The `raw_log_text` column is the "log file saved in DB" deliverable.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `UUID` | PK | Surfaced as `run_id` in URLs and WS |
| `project_id` | `UUID` | FK→`projects.id` ON DELETE CASCADE, NOT NULL, **indexed** | |
| `suite_id` | `UUID` | FK→`test_suites.id` ON DELETE SET NULL, NULL | |
| `framework` | `VARCHAR(40)` | NOT NULL | |
| `mode` | `VARCHAR(20)` | NOT NULL | `github` \| `local` |
| `status` | `VARCHAR(20)` | NOT NULL, default `queued` | `queued` \| `running` \| `passed` \| `failed` \| `error` |
| `github_run_id` | `VARCHAR(64)` | NULL | Numeric GH run id |
| `github_run_url` | `TEXT` | NULL | Clickable URL to the Actions run |
| `github_branch` | `VARCHAR(120)` | NULL | `runs/{uuid}` |
| `started_at` | `TIMESTAMPTZ` | default `NOW()` | |
| `finished_at` | `TIMESTAMPTZ` | NULL | |
| `duration_ms` | `INTEGER` | NULL | |
| `total_count` | `INTEGER` | NOT NULL, default 0 | |
| `passed_count` | `INTEGER` | NOT NULL, default 0 | |
| `failed_count` | `INTEGER` | NOT NULL, default 0 | |
| `raw_log_text` | `TEXT` | NULL | Full pytest stdout / GH Actions log archive |
| `artifacts_json` | `JSONB` | NOT NULL, default `{}` | `{screenshots: [...], video, allure_url}` |
| `pdf_path` | `TEXT` | NULL | Local FS path to generated PDF report |
| `error_message` | `TEXT` | NULL | |

**Indexes / constraints**
- Index: `project_id`
- Foreign keys: `project_id` (cascade), `suite_id` (set null)

---

## `test_run_screenshots`

Per-scenario screenshot index. The image bytes live on disk under `./reports/{run_id}/screenshots/`; this table just stores the metadata + relative path so the dashboard grid renders with one query.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `UUID` | PK | |
| `run_id` | `UUID` | FK→`test_run_executions.id` ON DELETE CASCADE, NOT NULL, **indexed** | |
| `scenario` | `VARCHAR(255)` | NOT NULL | |
| `label` | `VARCHAR(255)` | NOT NULL | Human-readable caption for the PDF |
| `status` | `VARCHAR(20)` | NOT NULL | `passed` \| `failed` |
| `image_path` | `TEXT` | NOT NULL | Relative path under `reports/` |
| `captured_at` | `TIMESTAMPTZ` | default `NOW()` | |

**Indexes / constraints**
- Index: `run_id`
- Foreign key: `run_id → test_run_executions.id` (cascade)

---

## Cascade behaviour summary

| Action | Effect |
|---|---|
| Delete project | Cascades to user_stories, gherkin_scenarios, test_suites, dom_elements, test_runs, test_run_executions → screenshots |
| Delete user story | Cascades to its gherkin_scenarios via composite FK |
| Delete test_suite | `test_runs.suite_id` → NULL; `test_run_executions.suite_id` → NULL (history of past runs is preserved) |
| Delete test_run_execution | Cascades to `test_run_screenshots` |

---

## Startup migration notes

[`backend/app/database.py`](backend/app/database.py) runs idempotent SQL on every server boot:

1. Creates `projects` if missing.
2. Adds `project_id` to `user_stories` and `gherkin_scenarios` if missing.
3. Backfills orphaned rows into an auto-created "Default Project".
4. Upgrades `user_stories.PK` from `(id)` → `(id, project_id)` if needed.
5. Runs `Base.metadata.create_all` for any new tables in `models.py`.
6. Adds `version` / `is_active` / `selected_for_run` to `test_suites` if missing; swaps the old `UNIQUE (project_id, framework)` constraint for `UNIQUE (project_id, framework, version)`.
7. Marks stuck `processing` stories as `done` if a Gherkin already exists for them.

Net result: pulling the latest code and restarting `uvicorn` is enough to bring an old DB up to the current schema without manual `alembic` runs.

---

## How each table is used per pipeline stage

| Stage | Reads | Writes |
|---|---|---|
| S1 — User Story Intake | `user_stories` | — |
| S2 — Gherkin Generation | `user_stories` | `gherkin_scenarios` |
| S3 — Mode + URL Setup | — | — (UI state only) |
| S4 — DOM Inspector | `projects` | `dom_elements` |
| S5 — Code Review | `gherkin_scenarios`, `dom_elements`, `test_suites` (history) | `test_suites` (insert new version, flip `is_active`, set `selected_for_run`) |
| S6 — Execution & Report | `test_suites` (the selected version) | `test_run_executions`, `test_run_screenshots`, `test_runs` |
