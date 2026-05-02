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

export interface CodeGenResult {
  framework: string;
  language: string;
  filename: string;
  code: string;
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

/** Generate test code for all Gherkin stories in a project. */
export async function generateTestCode(
  projectId: string,
  url: string,
  mode: string,
  frameworks: string[]
): Promise<CodeGenResult[]> {
  return request<CodeGenResult[]>("/api/v1/code/generate", {
    method: "POST",
    body: JSON.stringify({
      project_id: projectId,
      url,
      mode,
      frameworks,
    }),
  });
}
