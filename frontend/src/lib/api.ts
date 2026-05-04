/**
 * API client for NextGen QA Component 2 backend.
 * Base URL reads from NEXT_PUBLIC_API_URL env var (defaults to localhost:8002).
 */

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8080";

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

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });

  if (!res.ok) {
    const error = await res.text();
    throw new Error(`API ${res.status}: ${error}`);
  }

  // 204 No Content
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
}

/** Reachability check (HTTP, no browser) for the wizard's Validate button. */
export async function probeUrl(url: string): Promise<ProbeResponse> {
  return request<ProbeResponse>("/api/v1/dom/probe", {
    method: "POST",
    body: JSON.stringify({ url }),
  });
}

/** Run the Playwright crawler against a URL and persist extracted elements. */
export async function crawlDom(projectId: string, url: string): Promise<DomCrawlResponse> {
  return request<DomCrawlResponse>("/api/v1/dom/crawl", {
    method: "POST",
    body: JSON.stringify({ project_id: projectId, url }),
  });
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
