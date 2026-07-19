/**
 * API client for NextGen QA Component 2 backend.
 * Base URL reads from NEXT_PUBLIC_API_URL env var (defaults to localhost:8000,
 * matching the Makefile's `BACKEND_PORT ?= 8000`).
 */

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8002";

// Per-request fetch timeout. Without this, a hung backend (restarting, wrong
// port, blocked by firewall) freezes the UI on its loading spinner forever.
// LLM-heavy endpoints (code generation) override via the `timeoutMs` arg.
const REQUEST_TIMEOUT_MS = 30_000;
const LLM_REQUEST_TIMEOUT_MS = 180_000;
const CRAWL_REQUEST_TIMEOUT_MS = 90_000;

// ─── Types ────────────────────────────────────────────────────────────────────

export interface Project {
  id: string;
  name: string;
  description?: string;
  created_at?: string;
}

export interface UserStoryPayload {
  id: string;
  actor: string;
  action: string;
  goal: string;
  priority: string;
  status: string;
  source: string;
  acceptance_criteria: string[];
}

export interface UserStoryResponse extends UserStoryPayload {
  project_id: string;
}

export interface GherkinResult {
  id: string;
  story_id: string;
  project_id: string;
  feature_name: string;
  gherkin_text: string;
  generator: string;
  edited_by_qa: boolean;
  approved: boolean;
}

export interface TestSuite {
  id: string;
  project_id: string;
  framework: string;
  language: string;
  filename: string;
  code: string;
  mode: string;
  url: string;
  llm_model?: string | null;
  source_scenarios_hash: string;
  source_scenario_count: number;
  is_stale: boolean;
  version: number;
  is_active: boolean;
  selected_for_run: boolean;
  updated_at?: string | null;
}

// ─── Core fetch helper ────────────────────────────────────────────────────────

async function request<T>(
  path: string,
  options?: RequestInit & { timeoutMs?: number },
): Promise<T> {
  const timeoutMs = options?.timeoutMs ?? REQUEST_TIMEOUT_MS;
  const controller = new AbortController();
  if (options?.signal) {
    options.signal.addEventListener("abort", () => controller.abort(), { once: true });
  }
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  let res: Response;
  try {
    res = await fetch(`${BASE_URL}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...options,
      signal: controller.signal,
    });
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") {
      throw new Error(
        `API timeout after ${timeoutMs}ms: ${path}. Backend at ${BASE_URL} unreachable, slow, or stuck on an LLM call?`,
      );
    }
    throw e;
  } finally {
    clearTimeout(timer);
  }

  if (!res.ok) {
    const error = await res.text();
    throw new Error(`API ${res.status}: ${error}`);
  }

  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

// ─── Project API ──────────────────────────────────────────────────────────────

/** Create a new project. */
export async function createProject(name: string, description?: string): Promise<Project> {
  return request<Project>("/api/v1/projects", {
    method: "POST",
    body: JSON.stringify({ name, description }),
  });
}

/** List all projects. */
export async function listProjects(): Promise<Project[]> {
  return request<Project[]>("/api/v1/projects");
}

/** Delete a project and all its data. */
export async function deleteProject(projectId: string): Promise<void> {
  return request<void>(`/api/v1/projects/${projectId}`, { method: "DELETE" });
}

// ─── Story API (project-scoped) ───────────────────────────────────────────────

/** List all stories for a project. */
export async function listStories(projectId: string): Promise<UserStoryResponse[]> {
  return request<UserStoryResponse[]>(`/api/v1/projects/${projectId}/stories`);
}

/** Save (upsert) multiple stories into a project. */
export async function saveStories(
  projectId: string,
  stories: UserStoryPayload[]
): Promise<UserStoryResponse[]> {
  return request<UserStoryResponse[]>(`/api/v1/projects/${projectId}/stories/bulk`, {
    method: "POST",
    body: JSON.stringify(stories),
  });
}

/** Add or update a single story in a project. */
export async function addStory(
  projectId: string,
  story: UserStoryPayload
): Promise<UserStoryResponse> {
  return request<UserStoryResponse>(`/api/v1/projects/${projectId}/stories`, {
    method: "POST",
    body: JSON.stringify(story),
  });
}

/** Delete a story from a project (also deletes its Gherkin). */
export async function deleteStory(projectId: string, storyId: string): Promise<void> {
  return request<void>(`/api/v1/projects/${projectId}/stories/${storyId}`, {
    method: "DELETE",
  });
}

// ─── Gherkin API ──────────────────────────────────────────────────────────────

/** Trigger Gherkin generation for a list of story IDs within a project. */
export async function generateGherkin(
  projectId: string,
  storyIds: string[]
): Promise<GherkinResult[]> {
  return request<GherkinResult[]>("/api/v1/gherkin/generate", {
    method: "POST",
    body: JSON.stringify({ project_id: projectId, story_ids: storyIds }),
  });
}

/** Fetch generated Gherkin for a single story in a project. */
export async function getGherkinForStory(
  projectId: string,
  storyId: string
): Promise<GherkinResult | null> {
  return request<GherkinResult | null>(`/api/v1/gherkin/${projectId}/${storyId}`);
}

/** Save QA edits to a Gherkin scenario. */
export async function updateGherkin(
  gherkinId: string,
  gherkinText: string
): Promise<GherkinResult> {
  return request<GherkinResult>(`/api/v1/gherkin/${gherkinId}`, {
    method: "PUT",
    body: JSON.stringify({ gherkin_text: gherkinText }),
  });
}

/** Toggle approval status for a Gherkin scenario (persisted to DB). */
export async function approveGherkin(gherkinId: string): Promise<GherkinResult> {
  return request<GherkinResult>(`/api/v1/gherkin/${gherkinId}/approve`, {
    method: "PUT",
  });
}

/** Force-regenerate Gherkin for a story (ignores edited_by_qa flag). */
export async function regenerateGherkin(
  projectId: string,
  storyId: string
): Promise<GherkinResult> {
  return request<GherkinResult>(`/api/v1/gherkin/${projectId}/${storyId}/regenerate`, {
    method: "POST",
  });
}

// ─── Code Generation API ──────────────────────────────────────────────────────

/**
 * Generate (or regenerate) test code for the given frameworks.
 * Persisted server-side: subsequent loads should use `getTestSuites` instead
 * of calling this, so we don't burn LLM tokens on every navigation.
 */
export async function generateTestCode(
  projectId: string,
  url: string,
  mode: string,
  frameworks: string[]
): Promise<TestSuite[]> {
  return request<TestSuite[]>("/api/v1/code/generate", {
    method: "POST",
    body: JSON.stringify({
      project_id: projectId,
      url,
      mode,
      frameworks,
    }),
    timeoutMs: LLM_REQUEST_TIMEOUT_MS,
  });
}

/**
 * Load the active head of each (project, framework) chain — no LLM calls.
 * Older versions live in the history endpoint.
 */
export async function getTestSuites(projectId: string): Promise<TestSuite[]> {
  return request<TestSuite[]>(`/api/v1/code/suites?project_id=${encodeURIComponent(projectId)}`);
}

/** Fetch a single suite by id (any version — used by the dedicated editor). */
export async function getTestSuite(suiteId: string): Promise<TestSuite> {
  return request<TestSuite>(`/api/v1/code/suites/${suiteId}`);
}

/**
 * Every version of the (project, framework) chain that `suiteId` belongs to,
 * newest first. Powers the version dropdown.
 */
export async function getTestSuiteHistory(suiteId: string): Promise<TestSuite[]> {
  return request<TestSuite[]>(`/api/v1/code/suites/${suiteId}/history`);
}

/**
 * Autosave QA edits into the active head. Editing a historical (is_active=false)
 * suite returns 409 — the UI must restore it first.
 */
export async function updateTestSuiteCode(
  suiteId: string,
  code: string,
): Promise<TestSuite> {
  return request<TestSuite>(`/api/v1/code/suites/${suiteId}`, {
    method: "PUT",
    body: JSON.stringify({ code }),
  });
}

/**
 * Snapshot the current code as a fresh version (version + 1). The prior head
 * is deactivated but preserved in history.
 */
export async function saveTestSuiteAsNewVersion(
  suiteId: string,
  code: string,
): Promise<TestSuite> {
  return request<TestSuite>(`/api/v1/code/suites/${suiteId}/save-as-new-version`, {
    method: "POST",
    body: JSON.stringify({ code }),
  });
}

/**
 * Copy a historical version's code forward as a new head row.
 * History stays append-only — the old row remains in place.
 */
export async function restoreTestSuiteVersion(suiteId: string): Promise<TestSuite> {
  return request<TestSuite>(`/api/v1/code/suites/${suiteId}/restore`, {
    method: "POST",
  });
}

/**
 * Mark this suite as the framework + version CI/CD should execute next.
 * Only one suite per project carries the flag at a time.
 */
export async function selectTestSuiteForRun(suiteId: string): Promise<TestSuite> {
  return request<TestSuite>(`/api/v1/code/suites/${suiteId}/select-for-run`, {
    method: "POST",
  });
}

// ─── DOM Crawler API ──────────────────────────────────────────────────────────

export interface DomElement {
  id: string;
  project_id: string;
  url: string;
  selector: string;
  tag: string;
  text?: string | null;
  attributes: Record<string, string>;
  role: string;
  source_step?: string | null;
  confidence?: number | null;
  edited_by_qa: boolean;
  approved: boolean;
  updated_at?: string | null;
}

export interface ProbeResponse {
  ok: boolean;
  status: number;
  title?: string | null;
  error?: string | null;
}

export interface DomCrawlResponse {
  project_id: string;
  url: string;
  elements: DomElement[];
  logs: string[];
  extracted_count: number;
  auth_strategy_used: string;
  auth_steps_replayed: number;
  unmatched_background_steps: string[];
}

export type AuthStrategy = "background" | "none" | "manual" | "storage_state";

export interface ManualAuthConfig {
  login_url?: string;
  username_selector?: string;
  username_value?: string;
  password_selector?: string;
  password_value?: string;
  submit_selector?: string;
}

export interface CrawlOptions {
  authStrategy?: AuthStrategy;
  manualAuth?: ManualAuthConfig;
  storageState?: unknown;  // Playwright storageState JSON
}

/** Reachability check (HTTP, no browser) for the wizard's Validate button. */
export async function probeUrl(url: string): Promise<ProbeResponse> {
  return request<ProbeResponse>("/api/v1/dom/probe", {
    method: "POST",
    body: JSON.stringify({ url }),
  });
}

/**
 * Run the Playwright crawler against a URL and persist extracted elements.
 * Default auth strategy is "background" — replays the project's Gherkin
 * Background steps to log in. Pass `authStrategy: "none"` for public pages,
 * "manual" with `manualAuth` for fixed-credential forms, or "storage_state"
 * with a Playwright storageState JSON for SSO/2FA-protected sites.
 *
 * `runId` lets you open `openCrawlLogStream(runId)` in parallel for live logs.
 */
export async function crawlDom(
  projectId: string,
  url: string,
  options: CrawlOptions & { runId?: string } = {},
): Promise<DomCrawlResponse> {
  return request<DomCrawlResponse>("/api/v1/dom/crawl", {
    method: "POST",
    body: JSON.stringify({
      project_id: projectId,
      url,
      auth_strategy: options.authStrategy ?? "background",
      manual_auth: options.manualAuth,
      storage_state: options.storageState,
      run_id: options.runId,
    }),
    timeoutMs: CRAWL_REQUEST_TIMEOUT_MS,
  });
}

/** Open a WebSocket that streams crawler log lines for a given run_id. */
export function openCrawlLogStream(
  runId: string,
  onLog: (line: string) => void,
  onEnd?: () => void,
): WebSocket {
  // Convert HTTP base URL to WS protocol (http -> ws, https -> wss).
  const wsBase = BASE_URL.replace(/^http/, "ws");
  const ws = new WebSocket(`${wsBase}/ws/dom/crawl/${encodeURIComponent(runId)}`);
  ws.onmessage = (evt) => {
    try {
      const data = JSON.parse(evt.data);
      if (data.type === "log" && typeof data.line === "string") onLog(data.line);
      else if (data.type === "end") {
        onEnd?.();
        ws.close();
      }
    } catch {
      // ignore malformed frames
    }
  };
  ws.onerror = () => {
    // Browser will also fire close after this; nothing actionable here.
  };
  return ws;
}

/** List persisted DOM elements for a project (optionally a single URL). */
export async function listDomElements(
  projectId: string,
  url?: string,
): Promise<DomElement[]> {
  const qs = new URLSearchParams({ project_id: projectId });
  if (url) qs.set("url", url);
  return request<DomElement[]>(`/api/v1/dom/elements?${qs.toString()}`);
}

/** Update one DOM element (sets edited_by_qa=true). */
export async function updateDomElement(
  elementId: string,
  patch: Partial<Pick<DomElement, "selector" | "tag" | "text" | "attributes" | "role" | "approved">>,
): Promise<DomElement> {
  return request<DomElement>(`/api/v1/dom/elements/${elementId}`, {
    method: "PUT",
    body: JSON.stringify(patch),
  });
}

/** Manually add (or upsert by role) a DOM element. */
export async function addDomElement(
  payload: Omit<DomElement, "id" | "edited_by_qa" | "approved" | "updated_at">,
): Promise<DomElement> {
  return request<DomElement>("/api/v1/dom/elements", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

/** Delete one DOM element. */
export async function deleteDomElement(elementId: string): Promise<void> {
  return request<void>(`/api/v1/dom/elements/${elementId}`, { method: "DELETE" });
}

/** Approve (or unapprove) every element in a project, optionally scoped to a URL. */
export async function bulkApproveDomElements(
  projectId: string,
  approved: boolean,
  url?: string,
): Promise<DomElement[]> {
  return request<DomElement[]>("/api/v1/dom/elements/bulk-approve", {
    method: "POST",
    body: JSON.stringify({ project_id: projectId, url, approved }),
  });
}

// ─── ML Risk Prediction API ──────────────────────────────────────────────────

export type RiskLevel = "LOW" | "MEDIUM" | "HIGH";

export interface RiskPrediction {
  flow: string;
  label: string;
  risk: RiskLevel;
  confidence: number;
  probabilities: Record<RiskLevel, number>;
  features: Record<string, number>;
}

export interface RiskResponse {
  project_id: string;
  source: "model" | "heuristic";
  model_classes: string[];
  feature_columns: string[];
  predictions: RiskPrediction[];
}

/** Score the four flow buckets for a project. Returns model-driven predictions
 * when the trained classifier is available, otherwise a heuristic fallback. */
export async function getRiskPredictions(projectId: string): Promise<RiskResponse> {
  return request<RiskResponse>(`/api/v1/projects/${projectId}/risk`);
}

// ─── GitHub Connection API ───────────────────────────────────────────────────

export interface GitHubRepo {
  full_name: string;
  name: string;
  owner: string;
  default_branch: string;
  private: boolean;
  html_url: string;
}

export interface GitHubValidateResponse {
  login: string;
  name?: string | null;
  avatar_url?: string | null;
  repos: GitHubRepo[];
  repo_count: number;
}

export interface GitHubConnection {
  project_id: string;
  owner: string;
  repo: string;
  repo_full: string;
  default_branch: string;
  token_preview: string;
  github_user_login?: string | null;
  github_user_avatar_url?: string | null;
  workflow_installed: boolean;
  workflow_installed_at?: string | null;
  last_validated_at?: string | null;
  updated_at?: string | null;
}

export interface GitHubConnectResponse {
  connection: GitHubConnection;
  workflow_status: "installed" | "already_present" | "conflict";
  workflow_message: string;
}

export interface GitHubPingResponse {
  ok: boolean;
  login?: string | null;
  rate_limit_remaining?: number | null;
  workflow_present: boolean;
  detail?: string | null;
}

/** Validate a PAT — returns user identity + a list of repos they can push to. */
export async function validateGitHubToken(token: string): Promise<GitHubValidateResponse> {
  return request<GitHubValidateResponse>("/api/v1/github/validate", {
    method: "POST",
    body: JSON.stringify({ token }),
  });
}

/** Get the current connection for a project, or null if not configured. */
export async function getGitHubConnection(projectId: string): Promise<GitHubConnection | null> {
  return request<GitHubConnection | null>(
    `/api/v1/projects/${encodeURIComponent(projectId)}/github/connection`,
  );
}

/** Persist token + repo and install the workflow. */
export async function connectGitHub(
  projectId: string,
  body: {
    token: string;
    owner: string;
    repo: string;
    default_branch?: string;
    force_workflow_overwrite?: boolean;
  },
): Promise<GitHubConnectResponse> {
  return request<GitHubConnectResponse>(
    `/api/v1/projects/${encodeURIComponent(projectId)}/github/connect`,
    {
      method: "POST",
      body: JSON.stringify(body),
    },
  );
}

/** Force-reinstall the workflow file (use after a 'conflict' response). */
export async function reinstallGitHubWorkflow(projectId: string): Promise<GitHubConnectResponse> {
  return request<GitHubConnectResponse>(
    `/api/v1/projects/${encodeURIComponent(projectId)}/github/reinstall-workflow`,
    { method: "POST" },
  );
}

/** Smoke-test the stored connection: token still valid? workflow still present? */
export async function pingGitHubConnection(projectId: string): Promise<GitHubPingResponse> {
  return request<GitHubPingResponse>(
    `/api/v1/projects/${encodeURIComponent(projectId)}/github/test-ping`,
    { method: "POST" },
  );
}

/** Remove the connection (leaves the workflow file on the repo intact). */
export async function disconnectGitHub(projectId: string): Promise<void> {
  return request<void>(
    `/api/v1/projects/${encodeURIComponent(projectId)}/github/connection`,
    { method: "DELETE" },
  );
}

// ─── Execution & Report API ──────────────────────────────────────────────────

export interface ExecuteResponse {
  run_id: string;
  mode: string;
}

export interface RunSummary {
  id: string;
  project_id: string;
  suite_id?: string | null;
  framework: string;
  mode: string;
  status: string;
  github_run_id?: string | null;
  github_run_url?: string | null;
  github_branch?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  duration_ms?: number | null;
  total_count: number;
  passed_count: number;
  failed_count: number;
  pdf_url?: string | null;
  log_url: string;
  error_message?: string | null;
}

export interface RunScenario {
  scenario_name: string;
  flow_name: string;
  status: string;
  duration_ms?: number | null;
  error_message?: string | null;
}

export interface RunScreenshot {
  scenario: string;
  label: string;
  status: string;
  image_url: string;
}

export interface RunDetail extends RunSummary {
  scenarios: RunScenario[];
  screenshots: RunScreenshot[];
  raw_log_preview: string;
}

export type ExecutionEvent =
  | { type: "step"; step: string; status: string }
  | { type: "log"; line: string }
  | { type: "github"; run_url: string; branch: string }
  | { type: "pdf_ready"; url: string }
  | { type: "done"; status: string; passed: number; failed: number; total: number; duration_ms: number }
  | { type: "error"; message: string }
  | { type: "end" };

/** Trigger an execution run. Returns the run_id (subscribe to WS immediately). */
export async function executeSuite(params: {
  suiteId: string;
  projectId: string;
  mode?: "github" | "local";
}): Promise<ExecuteResponse> {
  return request<ExecuteResponse>("/api/v1/execute", {
    method: "POST",
    body: JSON.stringify({
      suite_id: params.suiteId,
      project_id: params.projectId,
      mode: params.mode,
    }),
    timeoutMs: 60_000,
  });
}

/**
 * Re-run a previous GitHub Actions run via the official rerun API. The
 * returned `run_id` is a NEW TestRunExecution row tracking the new attempt
 * — subscribe to its WS stream just like a normal run.
 */
export async function rerunRun(prevRunId: string): Promise<ExecuteResponse> {
  return request<ExecuteResponse>(
    `/api/v1/runs/${encodeURIComponent(prevRunId)}/rerun`,
    { method: "POST", timeoutMs: 60_000 },
  );
}

/** List recent runs for a project (newest first). */
export async function listRuns(projectId: string, limit = 20): Promise<RunSummary[]> {
  return request<RunSummary[]>(
    `/api/v1/runs?project_id=${encodeURIComponent(projectId)}&limit=${limit}`,
  );
}

/** Fetch one run + scenarios + screenshots + log preview. */
export async function getRun(runId: string): Promise<RunDetail> {
  return request<RunDetail>(`/api/v1/runs/${runId}`);
}

/** Subscribe to the live execution WebSocket. */
export function openExecutionStream(
  runId: string,
  onEvent: (event: ExecutionEvent) => void,
): WebSocket {
  const wsBase = BASE_URL.replace(/^http/, "ws");
  const ws = new WebSocket(`${wsBase}/ws/execution/${encodeURIComponent(runId)}`);
  ws.onmessage = (evt) => {
    try {
      const data = JSON.parse(evt.data) as ExecutionEvent;
      onEvent(data);
      if (data.type === "end") ws.close();
    } catch {
      // malformed frame — ignore
    }
  };
  return ws;
}

/** Absolute URL for the raw log download. */
export function runLogUrl(runId: string): string {
  return `${BASE_URL}/api/v1/runs/${runId}/log`;
}

/** Absolute URL for the generated PDF report. */
export function runPdfUrl(runId: string): string {
  return `${BASE_URL}/api/v1/runs/${runId}/report.pdf`;
}

/** Absolute URL for a captured screenshot (image served from disk). */
export function runScreenshotUrl(runId: string, filename: string): string {
  return `${BASE_URL}/api/v1/runs/${runId}/screenshots/${encodeURIComponent(filename)}`;
}

/**
 * Absolute URL for the live "newest frame" preview. The frontend appends a
 * cache-buster on each poll so the browser actually re-fetches.
 */
export function runLatestFrameUrl(runId: string): string {
  return `${BASE_URL}/api/v1/runs/${runId}/screenshots/latest`;
}

// ─── Agent Explorer API ──────────────────────────────────────────────────────

export interface AgentSomElement {
  id: number;
  tag: string;
  selector: string;
  text: string;
  role: string;
  bbox: { x: number; y: number; w: number; h: number };
  attrs: Record<string, string>;
}

export type AgentRole = "planner" | "actor" | "observer" | "critic";

export type AgentEvent =
  | { type: "status"; ts: number; message: string }
  | {
      type: "screenshot";
      ts: number;
      step: number;
      b64: string;
      elements: AgentSomElement[];
      url: string;
      title: string;
      state_hash: string;
      novel_state: boolean;
      total_novel_states: number;
    }
  | { type: "thought"; ts: number; role: AgentRole; text: string; step: number }
  | {
      type: "action";
      ts: number;
      step: number;
      action_type: string;
      element_id?: number;
      value?: string;
      url?: string;
      reason?: string;
      success: boolean;
      message: string;
    }
  | { type: "lesson"; ts: number; step: number; text: string }
  | {
      type: "coverage";
      ts: number;
      step: number;
      goals_done: string[];
      goals_pending: string[];
    }
  | {
      type: "scenario_discovered";
      ts: number;
      step: number;
      title: string;
      steps: string[];
    }
  | {
      type: "done";
      ts: number;
      reason: string;
      total_steps: number;
      total_novel_states: number;
      scenarios: { title: string; steps: string[] }[];
    }
  | { type: "error"; ts: number; message: string }
  | { type: "end" };

export interface StartExplorationResponse {
  run_id: string;
  message: string;
}

/** Kick off an agent exploration run. Open `openAgentEventStream(run_id)`
 *  immediately after this resolves to receive live events. */
export async function startExploration(params: {
  intent: string;
  url: string;
  projectId?: string;
  maxSteps?: number;
  headless?: boolean;
}): Promise<StartExplorationResponse> {
  return request<StartExplorationResponse>("/api/v1/agent/explore", {
    method: "POST",
    body: JSON.stringify({
      intent: params.intent,
      url: params.url,
      project_id: params.projectId,
      max_steps: params.maxSteps ?? 12,
      headless: params.headless ?? false,
    }),
  });
}

/** Open a WebSocket that streams typed AgentEvent messages for a run. */
export function openAgentEventStream(
  runId: string,
  onEvent: (event: AgentEvent) => void,
): WebSocket {
  const wsBase = BASE_URL.replace(/^http/, "ws");
  const ws = new WebSocket(`${wsBase}/ws/agent/${encodeURIComponent(runId)}`);
  ws.onmessage = (evt) => {
    try {
      const data = JSON.parse(evt.data) as AgentEvent;
      onEvent(data);
      if (data.type === "end") ws.close();
    } catch {
      // ignore malformed frames
    }
  };
  return ws;
}
