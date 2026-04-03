# NEXTGEN QA
### R26-SE-039 | SLIIT Faculty of Computing

---

## COMPONENT 2 — Intelligent Test Case Generation

> AI-powered Gherkin + Multi-Framework Code Generation with CI/CD Integration

| **Field**       | **Detail**                                        |
|-----------------|---------------------------------------------------|
| **Name**        | Abeygunasekara D T                                |
| **Index Number**| IT22303684                                        |
| **Project Code**| R26-SE-039                                        |
| **Component**   | Component 2 — Intelligent Test Case Generation    |
| **Supervisors** | Ms. Suriyaa Kumari & Mr. Eishan Weerasinghe       |
| **Institution** | SLIIT Faculty of Computing                        |
| **Methodology** | Design Science Research (DSR)                     |

---

## 1. Component Overview

### 1.1 What is Component 2?

Component 2 is the **Intelligent Test Case Generation** engine of the NextGen QA system. It sits directly after Component 1 (Voice/NLP) in the pipeline, receiving structured user story JSON from sprint meeting recordings and automatically producing two key deliverables:

- **Gherkin feature files** — human-readable Given/When/Then test scenarios
- **Executable test code** — Selenium, Cypress, or Playwright scripts ready to run

The core innovation is that a QA engineer does zero manual test script writing. They paste a staging URL, review the AI-generated Gherkin, and click Run. The system handles DOM inspection, locator extraction, code generation, CI/CD execution, and report delivery automatically.

### 1.2 Position in the NextGen QA Pipeline

| **C1 — Voice/NLP** | **C2 — Test Generation** | **C3 — Self-Healing** | **C4 — Quality & RTM** |
|---|---|---|---|
| Captures meeting audio, transcribes, detects conflicts, outputs user story JSON | **YOUR COMPONENT — generates Gherkin + test code, executes via CI/CD, reports results** | Classifies failures, auto-repairs broken test selectors using ML | Scores test quality, builds Requirements Traceability Matrix |
| Input to C2 | **Core engine** | Receives C2 failures | Receives C2 test data |

> *Data flow: C1 outputs `user_stories` table in PostgreSQL → C2 reads it, generates tests, writes to `test_cases` table → C3 and C4 consume `test_cases` for their own processing.*

---

## 2. The Two Generation Modes

### 2.1 Why Two Modes?

Not every company will give your system access to a live staging environment from day one. The two-mode design makes the product usable at any stage of a project and is a key research contribution — it proves the system is flexible, not brittle.

|  | **Mode A — Abstract Generation** | **Mode B — DOM-Aware Generation** |
|---|---|---|
| **Input needed** | User story JSON only (no app URL required) | User story JSON + live staging app URL |
| **How it works** | NLP parses intent, generates Gherkin, produces code with placeholder locators | NLP + headless browser crawls the real app DOM, extracts real CSS/XPath selectors, produces immediately runnable code |
| **Output example** | `driver.find_element(By.ID, "<<LOGIN_BTN>>").click()` | `driver.find_element(By.ID, "login-button").click()` |
| **Runnable immediately?** | No — QA fills in real selectors | Yes — executes against staging URL right away |
| **Best used when** | App is still in development, no staging yet, or showing portability | Staging environment is live and URL is accessible |
| **Demo value** | Shows NLP and code structure quality | **Highest impact — shows full end-to-end automation** |

> *For the viva: always demo Mode B live. Mode A is the fallback if the staging server is unavailable. Prepare both.*

### 2.2 Target Application Strategy

Your system works with any web application. The development strategy is phased to reduce complexity:

| **Phase** | **Target App** | **Purpose** |
|---|---|---|
| **Phase 1** | SauceDemo (saucedemo.com) | Build and validate your entire pipeline. SauceDemo is a public e-commerce demo built for test automation practice. Login, cart, and checkout flows map perfectly to user stories from sprint meetings. Commonly used in research papers. |
| **Phase 2** | Any URL the company provides | Replace hardcoded SauceDemo URL with an input field. The DOM crawler handles any app. This is the commercial product capability. |

> *Why SauceDemo? It has clean, stable element IDs (`id="login-button"`, `id="user-name"`) which make your generated tests look professional and your abstract → DOM-aware comparison very clear.*

---

## 3. Full Pipeline — Step by Step

### 3.1 Pipeline Overview

The pipeline has 6 stages. Each is a separate module in your FastAPI backend. The React dashboard shows progress in real time as each stage completes.

| **Step** | **Stage** | **What happens** | **Output** |
|---|---|---|---|
| **1** | User Story Intake | FastAPI reads latest `user_stories` from PostgreSQL (written by C1). Each story has actor, action, goal, priority fields. | Structured story objects in memory |
| **2** | NLP Parsing | spaCy (`en_core_web_trf`) extracts: action verbs (login, add, checkout), entities (username, cart item, password), flow intent (positive path, negative/error path). | Parsed intent JSON per story |
| **3** | Gherkin Generation | Jinja2 templates + LLM (CodeLlama) convert parsed intent to Given/When/Then scenarios. QA can edit in dashboard before proceeding. | `.feature` files saved to DB + shown in UI |
| **4** | DOM Inspection (Mode B only) | Playwright launches headless Chromium, navigates to staging URL, crawls all pages, extracts interactive elements with CSS selectors and XPath. Builds element map. | `page_element_map` JSON in PostgreSQL |
| **5** | Code Generation | Jinja2 templates map Gherkin steps to framework-specific code. Abstract mode uses `<<PLACEHOLDER>>` locators. DOM-aware mode substitutes real selectors from step 4. Generates Selenium, Cypress, and Playwright in parallel. | `.py` / `.js` test files saved to disk + shown in code editor |
| **6** | CI/CD Execution & Report | React app calls FastAPI which triggers GitHub Actions via REST API. Runner installs deps, executes tests against staging URL, captures screenshots and video per step, posts results back via webhook. | Live log, screenshots, video, Allure HTML report, PDF summary |

### 3.2 Stage 1 — User Story Intake

**Input format from C1**

Component 1 writes to the shared PostgreSQL database. Your FastAPI polls or receives a webhook when new stories are available.

```json
{
  "story_id": "US-042",
  "meeting_session_id": "MTG-2024-11-15",
  "actor": "registered customer",
  "action": "log in to the system",
  "goal": "access my order history",
  "priority": "high",
  "acceptance_criteria": [
    "Login succeeds with valid credentials",
    "Login fails with invalid credentials showing error",
    "Session persists across page refresh"
  ]
}
```

> *Your FastAPI endpoint: `GET /api/v1/stories/latest` — fetches all pending user stories not yet processed by C2.*

### 3.3 Stage 2 — NLP Parsing with spaCy

**What spaCy extracts**

Load the `en_core_web_trf` transformer model. For each user story, run NER and dependency parsing to extract:

- **Action verbs**: login, add, remove, checkout, search, submit, navigate
- **Entities**: username, password, cart item, order number, email address
- **Flow type**: happy path (success) vs negative path (error/failure)
- **Page context**: which page or section the action occurs on

**Key code structure**

```python
import spacy

nlp = spacy.load('en_core_web_trf')

def parse_story(story: dict) -> dict:
    doc = nlp(story['action'] + ' ' + story['goal'])
    actions = [t.lemma_ for t in doc if t.pos_ == 'VERB']
    entities = [(ent.text, ent.label_) for ent in doc.ents]
    return {
        'actions': actions,
        'entities': entities,
        'flow_type': detect_flow_type(story['acceptance_criteria']),
        'page_context': infer_page(actions, entities)
    }
```

### 3.4 Stage 3 — Gherkin Scenario Generation

**Template approach (Jinja2 + LLM hybrid)**

Use Jinja2 templates for common patterns (login, form submit, navigation) and CodeLlama for complex or novel flows. This gives you speed and reliability for standard flows with LLM power for edge cases.

**Example Gherkin output for login story**

```gherkin
Feature: User Authentication
  As a registered customer
  I want to log in to the system
  So that I can access my order history

  Scenario: Successful login with valid credentials
    Given I am on the login page
    When I enter valid username "standard_user"
    And I enter valid password "secret_sauce"
    And I click the login button
    Then I should be redirected to the products page
    And I should see my account dashboard

  Scenario: Failed login with invalid credentials
    Given I am on the login page
    When I enter invalid username "wrong_user"
    And I enter invalid password "wrong_pass"
    And I click the login button
    Then I should see an error message
    And I should remain on the login page
```

> *The QA engineer sees this in the dashboard and can edit it before generating code. This human-in-the-loop step is important for your research — it shows the system is collaborative.*

### 3.5 Stage 4 — DOM Inspection (Mode B Only)

**How the DOM crawler works**

When the QA pastes a staging URL, your system spins up a headless Playwright browser and systematically maps every interactive element.

1. Navigate to the URL and wait for full page load
2. Extract all interactive elements: inputs, buttons, links, dropdowns, forms
3. For each element, record: tag, id, class, name, placeholder, aria-label, XPath, CSS selector
4. Follow navigation links to discover additional pages
5. Build a `page_element_map` JSON and save to PostgreSQL
6. Match discovered elements to Gherkin step keywords using fuzzy string matching

**Crawler code structure**

```python
from playwright.async_api import async_playwright

async def crawl_app(url: str) -> dict:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(url)
        elements = await page.evaluate('''() => {
            return Array.from(document.querySelectorAll(
                'input, button, a, select, textarea'
            )).map(el => ({
                tag: el.tagName,
                id: el.id,
                css: el.id ? '#'+el.id : el.className,
                text: el.innerText?.trim(),
                placeholder: el.placeholder
            }))
        }''')
        return {'url': url, 'elements': elements}
```

**SauceDemo element map example**

| **Element** | **ID (CSS selector)** | **XPath** | **Gherkin step matched** |
|---|---|---|---|
| Username input | `#user-name` | `//input[@id='user-name']` | When I enter valid username |
| Password input | `#password` | `//input[@id='password']` | When I enter valid password |
| Login button | `#login-button` | `//input[@id='login-button']` | And I click the login button |
| Error message | `.error-message-container` | `//h3[@data-test='error']` | Then I should see an error message |
| Add to cart | `#add-to-cart-sauce-labs-backpack` | `//button[contains(@id,'add-to-cart')]` | When I add item to cart |

### 3.6 Stage 5 — Code Generation

**Three framework outputs simultaneously**

Using Jinja2 templates, your system generates the same test in all three frameworks from a single Gherkin source. This is one of the most impressive viva demonstration points — showing framework-agnostic abstraction.

**Selenium output (Mode B — DOM-aware)**

```python
from selenium import webdriver
from selenium.webdriver.common.by import By

def test_successful_login():
    driver = webdriver.Chrome()
    driver.get('https://www.saucedemo.com')
    driver.find_element(By.ID, 'user-name').send_keys('standard_user')
    driver.find_element(By.ID, 'password').send_keys('secret_sauce')
    driver.find_element(By.ID, 'login-button').click()
    assert 'inventory' in driver.current_url
    driver.quit()
```

**Playwright output (Mode B — DOM-aware)**

```python
from playwright.sync_api import sync_playwright

def test_successful_login():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto('https://www.saucedemo.com')
        page.fill('#user-name', 'standard_user')
        page.fill('#password', 'secret_sauce')
        page.click('#login-button')
        assert 'inventory' in page.url
        browser.close()
```

**Cypress output (Mode B — DOM-aware)**

```javascript
describe('User Authentication', () => {
    it('should login with valid credentials', () => {
        cy.visit('https://www.saucedemo.com')
        cy.get('#user-name').type('standard_user')
        cy.get('#password').type('secret_sauce')
        cy.get('#login-button').click()
        cy.url().should('include', 'inventory')
    })
})
```

> *Abstract mode (Mode A) replaces `#user-name` with `<<LOGIN_USERNAME_FIELD>>`, `#password` with `<<LOGIN_PASSWORD_FIELD>>`, etc. QA fills in real values.*

---

## 4. CI/CD Integration with GitHub Actions

### 4.1 Architecture Overview

Your React dashboard connects to GitHub via your FastAPI backend. No separate CI/CD server is needed — GitHub Actions is free and handles everything.

| **#** | **Component** | **Role** |
|---|---|---|
| **1** | React Dashboard | User clicks 'Run Tests'. Dashboard calls your FastAPI `/api/v1/execute` endpoint. |
| **2** | FastAPI Backend | Receives request, pushes generated test files to GitHub repo via GitHub API, then triggers workflow dispatch. |
| **3** | GitHub REST API | Creates a new branch, commits test files, triggers the `run-tests.yml` GitHub Actions workflow. |
| **4** | GitHub Actions Runner | Installs Playwright/Selenium/pytest, executes tests against staging URL, captures screenshots + video, generates Allure report. |
| **5** | Webhook → FastAPI | Actions posts results back to your FastAPI webhook endpoint when tests complete. |
| **6** | React Dashboard | Displays live log (via WebSocket), screenshots, video replay, pass/fail chart, and PDF download button. |

### 4.2 GitHub Actions Workflow File

**File: `.github/workflows/nextgenqa-run.yml`**

Your FastAPI generates this file and pushes it to the target repo on first connection. After that it lives in the repo.

```yaml
name: NextGen QA — Auto Test Run

on:
  workflow_dispatch: # Triggered by your FastAPI via GitHub REST API
    inputs:
      test_suite:
        description: 'Test suite name'
        required: true
      staging_url:
        description: 'Target staging URL'
        required: true
      framework:
        description: 'selenium | playwright | cypress'
        required: true
        default: 'playwright'

jobs:
  run-tests:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout generated tests
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.10'

      - name: Install Playwright + pytest
        run: |
          pip install playwright pytest pytest-playwright allure-pytest
          playwright install chromium

      - name: Run tests
        run: pytest tests/ --alluredir=allure-results --screenshot=on
        env:
          STAGING_URL: ${{ inputs.staging_url }}

      - name: Upload Allure results
        uses: actions/upload-artifact@v4
        with:
          name: allure-results
          path: allure-results/

      - name: Post results to NextGen QA
        if: always()
        run: |
          curl -X POST $NEXTGENQA_WEBHOOK \
            -H 'Content-Type: application/json' \
            -d '{"suite": "${{ inputs.test_suite }}", "status": "${{ job.status }}"}'
        env:
          NEXTGENQA_WEBHOOK: ${{ secrets.NEXTGENQA_WEBHOOK_URL }}
```

### 4.3 FastAPI Endpoint — Trigger CI/CD

**`POST /api/v1/execute`**

```python
import httpx

async def trigger_github_actions(repo: str, token: str, inputs: dict):
    url = f'https://api.github.com/repos/{repo}/actions/workflows/nextgenqa-run.yml/dispatches'
    headers = {
        'Authorization': f'Bearer {token}',
        'Accept': 'application/vnd.github+json'
    }
    payload = {
        'ref': 'main',
        'inputs': inputs  # test_suite, staging_url, framework
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json=payload, headers=headers)
        return resp.status_code == 204  # 204 = triggered successfully
```

> *The QA only needs to paste their GitHub Personal Access Token once in the dashboard settings. Your system stores it encrypted in the `.env`. They never touch the CI/CD configuration.*

### 4.4 Live Execution Dashboard (WebSocket)

Use FastAPI WebSocket to stream test execution logs to the React dashboard in real time. The QA sees each step as it runs — not just a spinner.

**FastAPI WebSocket endpoint**

```python
from fastapi import WebSocket

@app.websocket('/ws/execution/{run_id}')
async def execution_stream(websocket: WebSocket, run_id: str):
    await websocket.accept()
    async for log_line in poll_github_run_logs(run_id):
        await websocket.send_json({
            'step': log_line['name'],
            'status': log_line['status'],  # running | passed | failed
            'timestamp': log_line['time']
        })
```

**React dashboard — live log consumer**

```javascript
const ws = new WebSocket(`ws://localhost:8002/ws/execution/${runId}`);
ws.onmessage = (event) => {
    const log = JSON.parse(event.data);
    setLogs(prev => [...prev, log]);
};
```

---

## 5. React Dashboard — Screen by Screen

### 5.1 Screen Flow

The QA engineer moves through 5 screens in sequence. Each screen maps to one pipeline stage.

|  | **Screen** | **User action** | **C2 processing** |
|---|---|---|---|
| **S1** | User Story Review | Reviews stories auto-loaded from C1. Selects which ones to generate tests for. | Reads `user_stories` from PostgreSQL |
| **S2** | Gherkin Editor | Reviews AI-generated Gherkin. Can edit steps before generating code. Clicks 'Generate Code'. | spaCy NLP + Jinja2 + LLM generate `.feature` files |
| **S3** | Mode + URL Selection | Selects Mode A (abstract) or Mode B (DOM-aware). If Mode B, pastes staging URL. Selects framework (Selenium / Cypress / Playwright). | DOM crawler runs against staging URL |
| **S4** | Code Review | Reviews generated test code in 3-panel side-by-side editor (one per framework). Can edit before running. | Jinja2 templates produce `.py` and `.js` files |
| **S5** | Execution & Report | Clicks 'Run Tests'. Watches live log. Views screenshots, video replay, pass/fail chart. Downloads PDF report. | GitHub Actions runs tests, results stream back via WebSocket |

### 5.2 Key Dashboard Features for Viva Impact

These are the features that will make the panel remember your component. Build them in priority order.

| **Rank** | **Feature** | **Why it impresses the panel** | **Effort** |
|---|---|---|---|
| **1** | Live one-click demo button | Panel sees full pipeline run in 60 seconds. No slides. Real output. | Low — use Playwright record/video |
| **2** | 3-framework side-by-side switcher | Proves framework-agnostic abstraction layer. Very visual. | Medium — 3 Jinja2 templates |
| **3** | Plain English input (optional C1 bypass) | QA types 'test that login fails with wrong password' — your system does the rest. | Medium — LLM prompt + parser |
| **4** | Test coverage heatmap | Visual grid showing which pages/elements are covered vs not. QA managers love this. | Medium — build from element map |
| **5** | ML risk badge per test case | Shows 'High Risk' next to login test based on RandomForest prediction. | Medium — train RF model |
| **6** | Video replay embedded in dashboard | Panel watches browser navigate, click, and pass/fail. Most tangible proof tests actually ran. | Low — Playwright records natively |
| **7** | AI failure explanation | Failed test gets LLM explanation in plain English. Bridges C2 to C3 self-healing. | Medium — LLM prompt on error |

---

## 6. Technology Stack

### 6.1 Backend (FastAPI — Port 8002)

| **Library** | **Version** | **Purpose** |
|---|---|---|
| fastapi | 0.110+ | REST API + WebSocket for live execution log streaming |
| spacy | 3.7+ | NLP parsing — extract actions, entities, flow intent from user stories |
| en_core_web_trf | 3.7+ | Transformer-based spaCy model for high accuracy NER |
| playwright | 1.40+ | DOM crawler + test execution + screenshot + video capture |
| jinja2 | 3.1+ | Template engine for Gherkin and code generation |
| scikit-learn | 1.4+ | RandomForestClassifier for ML edge case prediction |
| httpx | 0.27+ | Async HTTP client for GitHub REST API calls |
| sqlalchemy | 2.0+ | ORM for PostgreSQL database access |
| reportlab | 4.1+ | PDF report generation for QA managers |
| joblib | 1.3+ | Saving and loading trained ML model |
| pytest | 8.0+ | Test runner for generated test suites |
| allure-pytest | 2.13+ | Allure report integration for rich HTML test reports |
| mutmut | 2.4+ | Mutation testing to validate generated test quality |

### 6.2 Frontend (React — Port 3000)

| **Library** | **Version** | **Purpose** |
|---|---|---|
| React | 18+ | Main UI framework |
| TailwindCSS | 3+ | Utility-first styling — clean professional UI |
| React Query | 5+ | API state management and polling for execution status |
| Monaco Editor | 0.46+ | VS Code-style code editor for reviewing/editing generated tests |
| Recharts | 2+ | Pass/fail donut chart, coverage heatmap, risk distribution |
| React Router | 6+ | Navigation between the 5 pipeline screens |
| Axios | 1.6+ | HTTP calls to FastAPI backend |

### 6.3 Infrastructure

| **Tool** | **Config** | **Purpose** |
|---|---|---|
| PostgreSQL 15 | Port 5432 | Shared database — user_stories, test_cases, element_maps, run_results |
| GitHub Actions | Free tier | CI/CD runner — executes generated tests in headless Ubuntu environment |
| Docker Compose | Root repo | Runs all 4 components + DB + Redis as one local system |
| GitHub REST API | v2022 | Trigger workflow dispatch, push test files, receive run status |

---

## 7. ML Model — Edge Case Predictor

### 7.1 What the ML Model Does

Your `RandomForestClassifier` predicts which user story areas are high-risk for bugs — before any test is written. This risk score appears as a badge next to each generated test case in the dashboard. It is the key element that makes Component 2 a research contribution rather than just a code generator.

> *Research claim: "Our system does not just generate tests — it prioritises them using ML-predicted risk based on historical bug patterns, ensuring the most critical scenarios are tested first."*

### 7.2 Training Data

Collect 500+ bug records from GitHub Issues on open-source projects that use similar web technology. Target projects: e-commerce apps, HR systems, form-heavy web applications.

- **Source**: GitHub Issues API (label: `bug`) from open-source projects
- **Fields to extract**: issue title, component affected, time to fix, reporter type, severity
- **Label**: `is_edge_case` (1 = yes, 0 = no) — label based on keywords: edge, boundary, special case, race condition
- **Target**: 500+ labelled records minimum. 1000+ preferred.

### 7.3 Feature Engineering

| **Feature** | **Type** | **Rationale** |
|---|---|---|
| Historical bug count for component | Numeric | Components with more past bugs are higher risk |
| Story complexity score (word count of criteria) | Numeric | More complex stories = more edge cases |
| Number of acceptance criteria | Numeric | More criteria = more paths to cover |
| Action verb category (auth / data / navigation) | Categorical | Auth flows historically highest bug rate |
| Story priority (high/medium/low) | Categorical | High priority often correlates with complex logic |
| Negative path present (yes/no) | Binary | Stories with error scenarios need more edge case testing |

### 7.4 Training Code

```python
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split, GridSearchCV
from sklearn.metrics import precision_score, recall_score, f1_score
import joblib, pandas as pd

df = pd.read_csv('training_data/bug_records.csv')
X = df[['bug_count', 'complexity', 'criteria_count',
        'action_category', 'priority', 'has_negative_path']]
y = df['is_edge_case']

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42)

param_grid = {
    'n_estimators': [100, 200, 300],
    'max_depth': [5, 10, None],
    'min_samples_split': [2, 5]
}

grid = GridSearchCV(RandomForestClassifier(random_state=42),
                    param_grid, cv=5, scoring='f1')
grid.fit(X_train, y_train)

best_model = grid.best_estimator_
y_pred = best_model.predict(X_test)

print(f'Precision: {precision_score(y_test, y_pred):.3f}')
print(f'Recall: {recall_score(y_test, y_pred):.3f}')
print(f'F1 Score: {f1_score(y_test, y_pred):.3f}')

joblib.dump(best_model, 'saved_models/edge_case_predictor.pkl')
```

| **Metric** | **Target** | **Meaning** |
|---|---|---|
| Precision | >= 0.80 | 80% of 'high risk' predictions are correct |
| Recall | >= 0.75 | 75% of actual edge cases are caught |
| F1 Score | >= 0.77 | Balanced accuracy metric for your dissertation |

---

## 8. Database Schema — Component 2 Tables

### 8.1 Tables Owned by C2

All tables live in the shared `nextgen_qa` PostgreSQL database. C2 reads from `user_stories` (written by C1) and writes to its own tables.

**`gherkin_scenarios` table**

```sql
CREATE TABLE gherkin_scenarios (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    story_id VARCHAR(50) REFERENCES user_stories(id),
    feature_name VARCHAR(255) NOT NULL,
    scenario_title VARCHAR(255) NOT NULL,
    gherkin_text TEXT NOT NULL,  -- full .feature file content
    edited_by_qa BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);
```

**`test_cases` table (shared with C3 and C4)**

```sql
CREATE TABLE test_cases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    gherkin_id UUID REFERENCES gherkin_scenarios(id),
    framework VARCHAR(20) NOT NULL,  -- selenium | playwright | cypress
    mode VARCHAR(10) NOT NULL,       -- abstract | dom_aware
    code_content TEXT NOT NULL,
    locators_json JSONB,             -- extracted DOM selectors
    risk_score FLOAT,                -- ML edge case prediction
    risk_label VARCHAR(10),          -- high | medium | low
    created_at TIMESTAMP DEFAULT NOW()
);
```

**`page_element_maps` table**

```sql
CREATE TABLE page_element_maps (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    app_url VARCHAR(500) NOT NULL,
    page_path VARCHAR(255) NOT NULL,
    elements_json JSONB NOT NULL,  -- all interactive elements
    crawled_at TIMESTAMP DEFAULT NOW()
);
```

**`run_results` table (written by CI/CD webhook)**

```sql
CREATE TABLE run_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    test_case_id UUID REFERENCES test_cases(id),
    run_number INTEGER NOT NULL,
    status VARCHAR(10) NOT NULL,      -- passed | failed | skipped
    duration_ms INTEGER,
    screenshot_urls JSONB,            -- array of screenshot paths
    video_url VARCHAR(500),
    error_message TEXT,
    allure_report VARCHAR(500),       -- link to Allure HTML report
    executed_at TIMESTAMP DEFAULT NOW()
);
```

---

## 9. Development Sprint Plan

| **Month** | **Focus** | **Deliverables** | **Status** |
|---|---|---|---|
| **1–2** | Foundation | FastAPI project structure, PostgreSQL connection, read user_stories from C1, basic Gherkin template for login flow, React skeleton with 5 screens | Setup |
| **3** | NLP + Gherkin | spaCy integration, intent parser, Jinja2 Gherkin templates for login/cart/checkout, editable Gherkin UI in React | Build |
| **4** | Code Generation | Abstract mode complete (Selenium/Cypress/Playwright), 3-panel code editor in React, Mode toggle in dashboard, SauceDemo as default target | Build |
| **5** | DOM Crawler | Playwright headless crawler, page element map extraction, fuzzy matching to Gherkin steps, Mode B DOM-aware code generation, URL input screen | Build |
| **6** | CI/CD Integration | GitHub Actions workflow file, FastAPI trigger endpoint, WebSocket live log, screenshot and video capture, Allure report integration, webhook receiver | Build |
| **7** | ML + Reporting | Collect training data, train RandomForest model, risk badges in UI, coverage heatmap, PDF report generation, connect to C3 and C4 APIs | ML |
| **8** | Validation + Viva | Benchmark executability (target >= 85%), run full demo against SauceDemo live, mutation testing with mutmut, dissertation write-up for C2, viva preparation | Test |

---

## 10. Performance Targets & Evaluation

| **Metric** | **Target** | **How to measure** | **Tool** |
|---|---|---|---|
| Test generation time | < 10 sec/scenario | Time from story input to `.feature` file | Python `time` module |
| Code executability rate | >= 85% | % of generated tests that run without syntax error | pytest + CI/CD |
| DOM crawl accuracy | >= 90% | % of elements correctly identified and matched to steps | Manual vs auto comparison |
| ML Precision | >= 0.80 | Precision score on held-out test set | scikit-learn |
| ML Recall | >= 0.75 | Recall score on held-out test set | scikit-learn |
| Gherkin quality (human eval) | >= 4/5 score | 5 QA practitioners rate generated Gherkin quality | Survey / questionnaire |
| End-to-end pipeline time | < 3 minutes | Story input to Allure report ready | Dashboard timer |

### 10.1 Viva Preparation — Key Questions and Answers

| **Panel will likely ask...** | **Your answer** |
|---|---|
| What is novel about your component vs Selenium IDE? | Selenium IDE requires manual recording. Our system automatically discovers the app UI from a URL, links discovered elements to AI-generated user stories from sprint meetings, predicts high-risk areas using ML, and produces multi-framework tests with zero manual scripting. |
| Why Playwright over Selenium as the crawler? | Playwright provides async DOM access, native screenshot/video capture, and handles modern JS-heavy SPAs better than Selenium. We still generate Selenium code — but Playwright is the crawler engine. |
| What if the ML model accuracy is low? | Even with moderate accuracy, the model demonstrates intelligent prioritisation. We compare with and without ML — showing that ML-predicted-first ordering catches bugs earlier. The contribution is the approach, not just the accuracy score. |
| Why frontend testing only, not backend APIs? | Frontend UI testing is where the most manual QA effort is spent. Backend API testing is well-served by existing tools like Postman and REST Assured. Our contribution is specifically the intelligent UI test generation layer. |
| How does C2 integrate with C3 and C4? | C2 writes `test_cases` and `run_results` to the shared PostgreSQL database. C3 reads failed `run_results` to apply self-healing. C4 reads `test_cases` to score quality and build the RTM. Integration is database-first with optional FastAPI webhooks. |

---

*NextGen QA — Component 2 | Abeygunasekara D T | IT22303684 | R26-SE-039*  
*SLIIT Faculty of Computing — Design Science Research*
