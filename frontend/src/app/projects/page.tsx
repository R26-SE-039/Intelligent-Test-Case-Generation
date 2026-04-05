"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { listProjects, createProject, deleteProject, listStories } from "@/lib/api";
import { useProject } from "@/lib/project-context";
import DashboardLayoutWrapper from "@/components/dashboard-layout-wrapper";
import type { Project } from "@/lib/api";
import {
  FolderOpen,
  Plus,
  Trash2,
  ChevronRight,
  AlertCircle,
  Loader2,
  BookOpen,
  CheckCircle,
  Calendar,
  Zap,
  X,
} from "lucide-react";

interface ProjectStats {
  storyCount: number;
}

export default function ProjectsPage() {
  const router = useRouter();
  const { setActiveProject } = useProject();

  const [projects, setProjects] = useState<Project[]>([]);
  const [projectStats, setProjectStats] = useState<Record<string, ProjectStats>>({});
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Create project modal
  const [showCreate, setShowCreate] = useState(false);
  const [newProjectName, setNewProjectName] = useState("");
  const [newProjectDesc, setNewProjectDesc] = useState("");
  const [isCreating, setIsCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  // Delete confirmation
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);

  const loadProjects = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const list = await listProjects();
      setProjects(list);

      // Load story counts per project
      const stats: Record<string, ProjectStats> = {};
      await Promise.all(
        list.map(async (p) => {
          try {
            const stories = await listStories(p.id);
            stats[p.id] = { storyCount: stories.length };
          } catch {
            stats[p.id] = { storyCount: 0 };
          }
        })
      );
      setProjectStats(stats);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Cannot reach the backend. Make sure the FastAPI server is running on port 8002."
      );
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadProjects();
  }, []);

  const handleCreate = async () => {
    if (!newProjectName.trim()) return;
    setIsCreating(true);
    setCreateError(null);
    try {
      const project = await createProject(newProjectName.trim(), newProjectDesc.trim() || undefined);
      setActiveProject({ id: project.id, name: project.name, description: project.description });
      router.push("/dashboard");
    } catch (err) {
      setCreateError(
        err instanceof Error ? err.message : "Failed to create project"
      );
      setIsCreating(false);
    }
  };

  const handleOpen = (project: Project) => {
    setActiveProject({ id: project.id, name: project.name, description: project.description });
    router.push("/dashboard");
  };

  const handleDelete = async (projectId: string) => {
    setIsDeleting(true);
    try {
      await deleteProject(projectId);
      setConfirmDeleteId(null);
      await loadProjects();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete project");
    } finally {
      setIsDeleting(false);
    }
  };

  const formatDate = (iso?: string) => {
    if (!iso) return "";
    return new Date(iso).toLocaleDateString("en-US", {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  };

  return (
    <DashboardLayoutWrapper>
      {/* Page Header */}
      <div className="sticky top-0 z-10 bg-slate-950/80 backdrop-blur-sm border-b border-slate-800 px-8 py-5">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-white">Projects</h1>
            <p className="text-slate-400 text-sm mt-0.5">
              Each project is an isolated workspace with its own stories, Gherkin scenarios and test results
            </p>
          </div>
          <button
            id="btn-new-project"
            onClick={() => setShowCreate(true)}
            className="flex items-center gap-2 px-5 py-2.5 bg-purple-600 hover:bg-purple-500 text-white rounded-xl font-semibold text-sm transition-all shadow-lg shadow-purple-600/30 hover:shadow-purple-500/40 hover:scale-[1.02]"
          >
            <Plus className="w-4 h-4" />
            New Project
          </button>
        </div>
      </div>

      <div className="p-8">
        {/* Error banner */}
        {error && (
          <div className="mb-6 flex items-start gap-3 p-4 bg-red-500/10 border border-red-500/20 rounded-xl">
            <AlertCircle className="w-4 h-4 text-red-400 mt-0.5 shrink-0" />
            <p className="text-sm text-red-300">{error}</p>
            <button onClick={() => setError(null)} className="ml-auto text-slate-500 hover:text-white">
              <X className="w-4 h-4" />
            </button>
          </div>
        )}

        {/* Section title */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h2 className="text-lg font-bold text-white">Your Projects</h2>
            <p className="text-sm text-slate-400 mt-0.5">
              Each project has its own stories, Gherkin scenarios, and test results.
            </p>
          </div>
          {!isLoading && projects.length > 0 && (
            <span className="text-sm text-slate-500">{projects.length} project{projects.length !== 1 ? "s" : ""}</span>
          )}
        </div>

        {/* Loading */}
        {isLoading && (
          <div className="flex items-center justify-center py-24">
            <div className="text-center">
              <Loader2 className="w-10 h-10 text-purple-400 animate-spin mx-auto mb-4" />
              <p className="text-slate-400">Loading projects…</p>
            </div>
          </div>
        )}

        {/* Empty state */}
        {!isLoading && projects.length === 0 && !error && (
          <div className="flex flex-col items-center justify-center py-24 border-2 border-dashed border-slate-700 rounded-2xl">
            <div className="w-16 h-16 bg-slate-800 rounded-2xl flex items-center justify-center mb-5">
              <FolderOpen className="w-8 h-8 text-slate-500" />
            </div>
            <h3 className="text-lg font-semibold text-white mb-2">No Projects Yet</h3>
            <p className="text-sm text-slate-400 mb-6 text-center max-w-xs">
              Create your first project to start generating Gherkin test cases from user stories.
            </p>
            <button
              onClick={() => setShowCreate(true)}
              className="flex items-center gap-2 px-5 py-2.5 bg-purple-600 hover:bg-purple-500 text-white rounded-xl font-semibold text-sm transition-all"
            >
              <Plus className="w-4 h-4" />
              Create First Project
            </button>
          </div>
        )}

        {/* Project cards */}
        {!isLoading && projects.length > 0 && (
          <div className="grid gap-4">
            {projects.map((project) => {
              const stats = projectStats[project.id];
              const isConfirmingDelete = confirmDeleteId === project.id;

              return (
                <div
                  key={project.id}
                  className="group relative rounded-2xl border border-slate-700/60 bg-slate-900/50 hover:border-slate-600 hover:bg-slate-900 transition-all duration-200"
                >
                  <div className="p-6 flex items-center gap-5">
                    {/* Icon */}
                    <div className="w-12 h-12 bg-linear-to-br from-purple-600/20 to-indigo-600/20 border border-purple-500/20 rounded-xl flex items-center justify-center shrink-0">
                      <FolderOpen className="w-6 h-6 text-purple-400" />
                    </div>

                    {/* Info */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-3 mb-1">
                        <h3 className="text-base font-semibold text-white truncate">
                          {project.name}
                        </h3>
                      </div>
                      {project.description && (
                        <p className="text-sm text-slate-400 truncate mb-2">{project.description}</p>
                      )}
                      <div className="flex items-center gap-4 text-xs text-slate-500">
                        <span className="flex items-center gap-1">
                          <BookOpen className="w-3.5 h-3.5" />
                          {stats?.storyCount ?? "—"} stor{stats?.storyCount !== 1 ? "ies" : "y"}
                        </span>
                        <span className="flex items-center gap-1">
                          <Calendar className="w-3.5 h-3.5" />
                          {formatDate(project.created_at)}
                        </span>
                      </div>
                    </div>

                    {/* Actions */}
                    <div className="flex items-center gap-2 shrink-0">
                      {isConfirmingDelete ? (
                        <div className="flex items-center gap-2 bg-red-500/10 border border-red-500/30 rounded-xl px-3 py-2">
                          <span className="text-xs text-red-300 font-medium">Delete project?</span>
                          <button
                            id={`btn-confirm-delete-${project.id}`}
                            onClick={() => handleDelete(project.id)}
                            disabled={isDeleting}
                            className="text-xs bg-red-500 hover:bg-red-400 text-white px-2.5 py-1 rounded-lg font-medium transition-all disabled:opacity-50"
                          >
                            {isDeleting ? <Loader2 className="w-3 h-3 animate-spin" /> : "Delete"}
                          </button>
                          <button
                            onClick={() => setConfirmDeleteId(null)}
                            className="text-slate-400 hover:text-white transition-colors"
                          >
                            <X className="w-4 h-4" />
                          </button>
                        </div>
                      ) : (
                        <button
                          id={`btn-delete-${project.id}`}
                          onClick={(e) => {
                            e.stopPropagation();
                            setConfirmDeleteId(project.id);
                          }}
                          className="p-2 text-slate-600 hover:text-red-400 rounded-lg hover:bg-red-500/10 transition-all opacity-0 group-hover:opacity-100"
                          title="Delete project"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      )}

                      <button
                        id={`btn-open-${project.id}`}
                        onClick={() => handleOpen(project)}
                        className="flex items-center gap-2 px-4 py-2 bg-purple-600 hover:bg-purple-500 text-white rounded-xl text-sm font-medium transition-all shadow-md shadow-purple-600/20"
                      >
                        <Zap className="w-3.5 h-3.5" />
                        Open
                        <ChevronRight className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Create Project Modal */}
      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl p-8 w-full max-w-md shadow-2xl shadow-black/50">
            <div className="flex items-center gap-3 mb-6">
              <div className="w-10 h-10 bg-purple-500/10 border border-purple-500/20 rounded-xl flex items-center justify-center">
                <Plus className="w-5 h-5 text-purple-400" />
              </div>
              <div>
                <h2 className="text-lg font-bold text-white">New Project</h2>
                <p className="text-xs text-slate-400">Each project is a fresh workspace</p>
              </div>
              <button
                onClick={() => { setShowCreate(false); setCreateError(null); setNewProjectName(""); setNewProjectDesc(""); }}
                className="ml-auto text-slate-500 hover:text-white transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {createError && (
              <div className="mb-4 flex items-center gap-2 p-3 bg-red-500/10 border border-red-500/20 rounded-xl text-sm text-red-300">
                <AlertCircle className="w-4 h-4 shrink-0" />
                {createError}
              </div>
            )}

            <div className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">
                  Project Name *
                </label>
                <input
                  id="input-project-name"
                  type="text"
                  value={newProjectName}
                  onChange={(e) => setNewProjectName(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleCreate()}
                  placeholder="e.g. E-Commerce Checkout Flow"
                  autoFocus
                  className="w-full bg-slate-800 border border-slate-600 rounded-xl px-4 py-3 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-purple-500 transition-colors"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">
                  Description <span className="text-slate-600 normal-case font-normal">(optional)</span>
                </label>
                <textarea
                  id="input-project-desc"
                  value={newProjectDesc}
                  onChange={(e) => setNewProjectDesc(e.target.value)}
                  placeholder="What are we testing in this project?"
                  rows={3}
                  className="w-full bg-slate-800 border border-slate-600 rounded-xl px-4 py-3 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-purple-500 transition-colors resize-none"
                />
              </div>

              <div className="flex gap-3 pt-2">
                <button
                  onClick={() => { setShowCreate(false); setCreateError(null); setNewProjectName(""); setNewProjectDesc(""); }}
                  className="flex-1 px-4 py-2.5 border border-slate-600 text-slate-400 hover:text-white rounded-xl text-sm font-medium transition-all"
                >
                  Cancel
                </button>
                <button
                  id="btn-create-project"
                  onClick={handleCreate}
                  disabled={isCreating || !newProjectName.trim()}
                  className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 bg-purple-600 hover:bg-purple-500 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-xl text-sm font-semibold transition-all"
                >
                  {isCreating ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <CheckCircle className="w-4 h-4" />
                  )}
                  {isCreating ? "Creating…" : "Create & Open"}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </DashboardLayoutWrapper>
  );
}
