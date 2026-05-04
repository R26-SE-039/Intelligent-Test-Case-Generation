/**
 * API client for NextGen QA Component 2 backend.
 * Base URL reads from NEXT_PUBLIC_API_URL env var (defaults to localhost:8000,
 * matching the Makefile's `BACKEND_PORT ?= 8000`).
 */

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

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

/** Load persisted test suites for a project (no LLM calls). */
export async function getTestSuites(projectId: string): Promise<TestSuite[]> {
  return request<TestSuite[]>(`/api/v1/code/suites?project_id=${encodeURIComponent(projectId)}`);
}

/** Save QA edits to a suite's code without regenerating. */
export async function updateTestSuiteCode(
  suiteId: string,
  code: string,
): Promise<TestSuite> {
  return request<TestSuite>(`/api/v1/code/suites/${suiteId}`, {
    method: "PUT",
    body: JSON.stringify({ code }),
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
