# Component 2 Dashboard API Response

## Purpose

This document describes the API responses used when a user selects a project in the NextGenQA dashboard and opens **Test Case Gen**.

The selected project is stored in the frontend as `currentProject`. Component 2 uses the same project UUID so stories, Gherkin scenarios, generated suites, selectors, and execution records remain isolated per workspace.

## Request Flow

```text
1. Dashboard loads projects
   GET http://localhost:8080/api/auth-service/projects

2. User selects a project
   Frontend stores the selected project as currentProject

3. Test Case Gen ensures the project exists in Component 2
   POST http://localhost:8080/api/test-case/api/v1/projects

4. Test Case Gen loads project data
   GET http://localhost:8080/api/test-case/api/v1/projects/{project_id}/stories
```

The browser communicates with the API Gateway on port `8080`. The gateway strips `/api/test-case` and forwards the request to Component 2 on port `8002`.

## 1. Dashboard Project Response

### Request

```http
GET /api/auth-service/projects
Host: localhost:8080
Authorization: Bearer <access_token>
```

### Response

```json
[
  {
    "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    "name": "SauceDemo Test Workspace",
    "description": "Automated test generation project",
    "createdAt": "2026-08-19T08:30:00.000Z",
    "lastAccessed": "2026-08-19T09:15:00.000Z",
    "memberCount": 1,
    "userRole": "Admin",
    "isPrivate": true
  }
]
```

The frontend stores the selected object as `currentProject`. The important field for Component 2 is `currentProject.id`.

## 2. Component 2 Project Response

The Test Case Gen frontend calls this endpoint before loading project data. It is a get-or-create operation when an existing project UUID is supplied.

### Request

```http
POST /api/test-case/api/v1/projects
Host: localhost:8080
Content-Type: application/json

{
  "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
  "name": "SauceDemo Test Workspace",
  "description": "Automated test generation project",
  "organization_id": "11111111-1111-1111-1111-111111111111"
}
```

### Response

```json
{
  "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
  "name": "SauceDemo Test Workspace",
  "description": "Automated test generation project",
  "organization_id": "11111111-1111-1111-1111-111111111111",
  "created_at": "2026-08-19T08:30:00+00:00",
  "updated_at": null
}
```

The returned `id` is the project ID used by all later Component 2 requests.

## 3. User Stories Response

### Request

```http
GET /api/test-case/api/v1/projects/{project_id}/stories
Host: localhost:8080
```

Example:

```http
GET /api/test-case/api/v1/projects/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/stories
```

### Response

```json
[
  {
    "id": "US-001",
    "project_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    "actor": "a user",
    "action": "log in with valid credentials",
    "goal": "access the product inventory",
    "priority": "high",
    "status": "done",
    "source": "C1",
    "acceptance_criteria": [
      "The user can enter a valid username and password",
      "The user is redirected to the inventory page"
    ],
    "created_at": "2026-08-19T08:40:00+00:00",
    "updated_at": null
  }
]
```

This response is what populates the **Backlog Stories** table shown in the dashboard.

## 4. Additional Component 2 Responses

All of these requests use the same `project_id`.

| Dashboard data                           | Gateway endpoint                                                         |
| ---------------------------------------- | ------------------------------------------------------------------------ |
| Gherkin for a story                      | `GET /api/test-case/api/v1/gherkin/{project_id}/{story_id}`              |
| DOM selectors                            | `GET /api/test-case/api/v1/projects/{project_id}/selectors`              |
| Generated suites                         | `GET /api/test-case/api/v1/projects/{project_id}/test-suites`            |
| One suite with source code               | `GET /api/test-case/api/v1/projects/{project_id}/test-suites/{suite_id}` |
| Execution records                        | `GET /api/test-case/api/v1/projects/{project_id}/test-runs`              |
| Full execution detail                    | `GET /api/test-case/api/v1/projects/{project_id}/test-runs/{run_id}`     |
| Complete story-to-execution traceability | `GET /api/test-case/api/v1/projects/{project_id}/traceability`           |

## Generated Test Suites Response

```json
{
  "project_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
  "total": 3,
  "test_suites": [
    {
      "id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
      "project_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
      "framework": "playwright",
      "language": "python",
      "filename": "test_suite.py",
      "code": "import pytest\n...",
      "mode": "dom",
      "url": "https://www.saucedemo.com",
      "version": 1,
      "is_active": true,
      "selected_for_run": true,
      "source_scenario_count": 4,
      "created_at": "2026-08-19T08:50:00+00:00",
      "updated_at": null
    }
  ]
}
```

This response populates the **Code Review** cards for Cypress, Playwright, and Selenium. The `selected_for_run` value identifies the suite selected for execution.

## 5. Component 2 to C3/C4 Traceability Contract

### Complete traceability endpoint

Use this endpoint when C3 or RTM needs the complete Component 2 view in one request. It returns project metadata, stories with `iteration_id`, all Gherkin scenarios, generated suites with `source_scenario_ids`, and execution records with full logs and scenario PASS/FAIL results.

```http
GET /api/test-case/api/v1/projects/{project_id}/traceability
Host: localhost:8080
```

Optional iteration filter:

```http
GET /api/test-case/api/v1/projects/{project_id}/traceability?iteration_id={iteration_id}
```

Response shape:

```json
{
  "project": {
    "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    "name": "SauceDemo Test Workspace",
    "organization_id": "11111111-1111-1111-1111-111111111111"
  },
  "stories": [
    {
      "id": "US-001",
      "project_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
      "iteration_id": "dddddddd-dddd-dddd-dddd-dddddddddddd",
      "actor": "a user",
      "action": "log in with valid credentials",
      "goal": "access the product inventory",
      "priority": "high",
      "status": "done",
      "source": "C1",
      "acceptance_criteria": ["The user can access inventory"],
      "gherkin_scenarios": [
        {
          "id": "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee",
          "story_id": "US-001",
          "project_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
          "feature_name": "User Login",
          "gherkin_text": "Feature: User Login\\n  Scenario: Valid login\\n    Given ...",
          "generator": "llm",
          "llm_model": null,
          "edited_by_qa": false,
          "approved": true,
          "created_at": "2026-08-19T08:50:00+00:00",
          "updated_at": null
        }
      ]
    }
  ],
  "suites": [
    {
      "id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
      "project_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
      "framework": "playwright",
      "language": "python",
      "filename": "test_suite.py",
      "code": "...generated test source...",
      "mode": "dom",
      "url": "https://www.saucedemo.com",
      "version": 1,
      "is_active": true,
      "selected_for_run": true,
      "source_scenario_ids": ["eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"],
      "source_scenario_count": 1,
      "created_at": "2026-08-19T08:55:00+00:00",
      "updated_at": null
    }
  ],
  "executions": [
    {
      "id": "cccccccc-cccc-cccc-cccc-cccccccccccc",
      "project_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
      "suite_id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
      "framework": "playwright",
      "mode": "local",
      "status": "failed",
      "total_count": 1,
      "passed_count": 0,
      "failed_count": 1,
      "raw_log": "...full execution log...",
      "artifacts": {},
      "scenario_results": [
        {
          "test_run_id": "ffffffff-ffff-ffff-ffff-ffffffffffff",
          "scenario_name": "User logs in with valid credentials",
          "flow_name": "login_flow",
          "result": "FAIL",
          "duration_ms": 3500,
          "error_message": "Timeout waiting for selector '#login-button'",
          "executed_at": "2026-08-19T09:01:12+00:00"
        }
      ]
    }
  ]
}
```

The response provides the identifiers needed by C3/C4:

```text
project.id
stories[].iteration_id
stories[].id
stories[].gherkin_scenarios[].id
suites[].id
executions[].id
executions[].scenario_results[].test_run_id
executions[].scenario_results[].result
```

Important schema note: the current `test_runs` table stores `suite_id` but does not store `execution_id`. Therefore, the endpoint returns the available scenario results grouped under the matching suite and preserves each `test_run_id`; an exact scenario-to-execution audit requires adding `execution_id` to `test_runs`.

For failure analysis and the Requirements Traceability Matrix (RTM), one test result must be traceable through this chain:

```text
project_id
  -> iteration_id
  -> user_story_id
  -> gherkin_scenario_id / gherkin_text
  -> test_suite_id / test_name
  -> execution_id / test_run_id
  -> PASS or FAIL result
```

Component 2 owns the generated story, Gherkin, suite, and execution data. C3 must not query the Component 2 database directly. C4/RTM should consume the same API data through the gateway.

### Current read API sequence

```text
1. Read the story and its iteration
   GET /api/test-case/api/v1/projects/{project_id}/stories?iteration_id={iteration_id}

2. Read the Gherkin scenario for each story
   GET /api/test-case/api/v1/gherkin/{project_id}/{user_story_id}

3. Read the generated suite and source code
   GET /api/test-case/api/v1/projects/{project_id}/test-suites/{suite_id}

4. Read the execution summary
   GET /api/test-case/api/v1/projects/{project_id}/test-runs/{execution_id}

5. For failed scenarios, read the failure feed
   GET /api/test-case/api/v1/projects/{project_id}/failed-tests
```

The execution detail response is the source for the final result:

```json
{
  "id": "cccccccc-cccc-cccc-cccc-cccccccccccc",
  "project_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
  "suite_id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
  "framework": "playwright",
  "mode": "local",
  "status": "failed",
  "total_count": 4,
  "passed_count": 3,
  "failed_count": 1,
  "started_at": "2026-08-19T09:00:00+00:00",
  "finished_at": "2026-08-19T09:01:12+00:00",
  "duration_ms": 72000,
  "raw_log": "...full execution log...",
  "scenarios": [
    {
      "scenario_name": "User logs in with valid credentials",
      "flow_name": "login_flow",
      "status": "passed",
      "duration_ms": 1200,
      "error_message": null
    },
    {
      "scenario_name": "User sees an error for invalid credentials",
      "flow_name": "login_flow",
      "status": "failed",
      "duration_ms": 3500,
      "error_message": "Timeout waiting for selector '#login-button'"
    }
  ]
}
```

`status` is the final execution result (`passed`, `failed`, or `error`). For the RTM, map `passed` to `PASS`, and map `failed` or `error` to `FAIL`.

### Complete C3 analysis payload

C3 currently accepts the ML fields below, but its current `/analyze/` schema ignores additional JSON fields and its `failures` table does not persist the traceability IDs. The following is the required payload contract for the complete integration:

```http
POST /api/failure/analyze/
Host: localhost:8080
Content-Type: application/json
```

```json
{
  "organization_id": "11111111-1111-1111-1111-111111111111",
  "project_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
  "iteration_id": "dddddddd-dddd-dddd-dddd-dddddddddddd",
  "user_story_id": "US-001",
  "gherkin_scenario_id": "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee",
  "gherkin_text": "Feature: User Login\n  Scenario: User logs in with valid credentials\n    Given ...",
  "suite_id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
  "execution_id": "cccccccc-cccc-cccc-cccc-cccccccccccc",
  "test_run_id": "ffffffff-ffff-ffff-ffff-ffffffffffff",
  "test_name": "User logs in with valid credentials",
  "pipeline": "NextGenQA C2 / playwright",
  "framework": "playwright",
  "language": "python",
  "test_code_file": "test_suite.py",
  "test_code": "...generated test source...",
  "execution_status": "failed",
  "scenario_status": "failed",
  "error_message": "Timeout waiting for selector '#login-button'",
  "stack_trace": "...stack trace...",
  "logs": "...full or relevant execution log...",
  "failure_stage": "test",
  "failure_type": "Timeout",
  "severity": "HIGH",
  "retry_count": 0,
  "test_duration_sec": 3.5,
  "cpu_usage_pct": 0,
  "memory_usage_mb": 0,
  "is_flaky_test": 0,
  "old_locator": "#login-button",
  "github_actions_run_url": null,
  "executed_at": "2026-08-19T09:01:12+00:00"
}
```

For a passing scenario, send the same traceability fields with:

```json
{
  "execution_status": "passed",
  "scenario_status": "passed",
  "error_message": "",
  "stack_trace": "",
  "failure_type": "None",
  "severity": "LOW"
}
```

Do not send passing scenarios to the current C3 `/analyze/` endpoint because that endpoint is designed only for failures. Send all pass/fail rows to the future C4/RTM result endpoint, and send only failed/error rows to C3 for healing analysis.

### Required C4/RTM endpoint

C4/RTM is not implemented in this workspace yet. The gateway route `/api/rtm` currently points to the placeholder service `http://localhost:8003`.

The required C4 endpoint should accept the complete traceability result as one batch:

```http
POST /api/rtm/api/v1/traceability/results
Host: localhost:8080
Content-Type: application/json
```

```json
{
  "project_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
  "iteration_id": "dddddddd-dddd-dddd-dddd-dddddddddddd",
  "execution_id": "cccccccc-cccc-cccc-cccc-cccccccccccc",
  "framework": "playwright",
  "suite_id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
  "execution_status": "failed",
  "results": [
    {
      "user_story_id": "US-001",
      "gherkin_scenario_id": "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee",
      "test_name": "User logs in with valid credentials",
      "result": "PASS",
      "duration_ms": 1200,
      "failure_id": null
    },
    {
      "user_story_id": "US-001",
      "gherkin_scenario_id": "gggggggg-gggg-gggg-gggg-gggggggggggg",
      "test_name": "User sees an error for invalid credentials",
      "result": "FAIL",
      "duration_ms": 3500,
      "failure_id": "TEST-AB12CD34"
    }
  ]
}
```

The RTM can then display one row per story/scenario/test:

| Project      | Iteration      | User story      | Gherkin scenario      | Test suite | Execution      | Result          |
| ------------ | -------------- | --------------- | --------------------- | ---------- | -------------- | --------------- |
| `project_id` | `iteration_id` | `user_story_id` | `gherkin_scenario_id` | `suite_id` | `execution_id` | `PASS` / `FAIL` |

### Important implementation gaps

The current code needs these changes before the complete payload can work end to end:

1. Add `iteration_id` to the frontend `UserStoryPayload` and `UserStoryResponse` types.
2. Add `user_story_id`, `gherkin_scenario_id`, and `gherkin_text` to C2's failed-test integration response. The current response contains the scenario name, project, suite, framework, and failure message, but not the story or Gherkin link.
3. Add the traceability fields to C3's `AnalyzeRequest` schema and `Failure` database model, then add a migration for existing databases.
4. Add a C4/RTM service on port `8003` with the batch endpoint above. It does not exist yet; `/api/rtm` is only a gateway placeholder.

Until those changes are implemented, C2 can provide the data through its separate read endpoints, but one C3 request cannot reliably store the full RTM relationship.

## Error Responses

### Project not found

Use a valid UUID format when testing project routes.

```json
{
  "detail": "Project not found"
}
```

Expected status: `404`.

### Missing project selection

If the user has not selected a project, the frontend should stop before calling Component 2 and show:

```text
Select a project before opening Test Case Gen.
```

### Service unavailable

If Component 2 is not running on port `8002`, the frontend reports:

```text
Test case service unreachable. Is the backend running on port 8002?
```

## Local Service Checks

```text
Component 2 health:
GET http://localhost:8002/health

Gateway health:
GET http://localhost:8080/health

Component 2 OpenAPI:
GET http://localhost:8002/openapi.json
```

Expected health response from Component 2:

```json
{
  "status": "healthy"
}
```
