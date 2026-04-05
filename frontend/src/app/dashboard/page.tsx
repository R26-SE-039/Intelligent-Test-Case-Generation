"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import DashboardLayoutWrapper from "@/components/dashboard-layout-wrapper";
import { listStories, addStory, deleteStory, saveStories, generateGherkin } from "@/lib/api";
import { useProject } from "@/lib/project-context";
import type { UserStoryResponse } from "@/lib/api";
import {
  CheckCircle,
  Clock,
  Zap,
  ChevronRight,
  Plus,
  RefreshCw,
  Filter,
  User,
  Loader2,
  AlertCircle,
  Trash2,
  FolderOpen,
  ArrowLeft,
} from "lucide-react";
import Link from "next/link";

type Priority = "high" | "medium" | "low";
type Status = "pending" | "processing" | "done";

interface UserStory {
  id: string;
  actor: string;
  action: string;
  goal: string;
  priority: Priority;
  status: Status;
  acceptanceCriteria: string[];
  source: "C1" | "manual";
}

const priorityConfig: Record<Priority, { label: string; color: string; bg: string }> = {
  high: { label: "HIGH", color: "text-red-400", bg: "bg-red-500/10 border border-red-500/20" },
  medium: { label: "MED", color: "text-amber-400", bg: "bg-amber-500/10 border border-amber-500/20" },
  low: { label: "LOW", color: "text-emerald-400", bg: "bg-emerald-500/10 border border-emerald-500/20" },
};

const statusConfig: Record<Status, { label: string; icon: React.ReactNode; color: string }> = {
  pending: { label: "Pending", icon: <Clock className="w-3.5 h-3.5" />, color: "text-slate-400" },
  processing: { label: "Processing", icon: <RefreshCw className="w-3.5 h-3.5 animate-spin" />, color: "text-blue-400" },
  done: { label: "Done", icon: <CheckCircle className="w-3.5 h-3.5" />, color: "text-emerald-400" },
};

function toStory(r: UserStoryResponse): UserStory {
  return {
    id: r.id,
    actor: r.actor,
    action: r.action,
    goal: r.goal,
    priority: r.priority as Priority,
    status: r.status as Status,
    acceptanceCriteria: r.acceptance_criteria,
    source: r.source as "C1" | "manual",
  };
}

export default function UserStoryIntakePage() {
  const router = useRouter();
  const { activeProject } = useProject();

  const [stories, setStories] = useState<UserStory[]>([]);
  const [isLoadingStories, setIsLoadingStories] = useState(true);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [showManual, setShowManual] = useState(false);
  const [manualActor, setManualActor] = useState("");
  const [manualAction, setManualAction] = useState("");
  const [manualGoal, setManualGoal] = useState("");
  const [filterPriority, setFilterPriority] = useState<Priority | "all">("all");
  const [isGenerating, setIsGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  // Redirect to project picker if no project is active
  useEffect(() => {
    if (!activeProject) {
      router.replace("/projects");
      return;
    }
  }, [activeProject, router]);

  // Load stories from DB for the active project
  useEffect(() => {
    if (!activeProject) return;
    const load = async () => {
      setIsLoadingStories(true);
      try {
        const data = await listStories(activeProject.id);
        setStories(data.map(toStory));
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load stories");
      } finally {
        setIsLoadingStories(false);
      }
    };
    load();
  }, [activeProject]);

  if (!activeProject) return null;

  const toggle = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const toggleAll = () => {
    if (selected.size === stories.length) setSelected(new Set());
    else setSelected(new Set(stories.map((s) => s.id)));
  };

  const nextStoryId = () => {
    const nums = stories.map((s) => parseInt(s.id.replace(/\D/g, ""), 10)).filter((n) => !isNaN(n));
    const max = nums.length > 0 ? Math.max(...nums) : 0;
    return `US-${String(max + 1).padStart(3, "0")}`;
  };

  const addManualStory = async () => {
    if (!manualAction.trim()) return;
    const newStory: UserStory = {
      id: nextStoryId(),
      actor: manualActor.trim() || "QA engineer",
      action: manualAction.trim(),
      goal: manualGoal.trim() || "validate expected behaviour",
      priority: "medium",
      status: "pending",
      source: "manual",
      acceptanceCriteria: ["Scenario behaves as described"],
    };

    try {
      const saved = await addStory(activeProject.id, {
        id: newStory.id,
        actor: newStory.actor,
        action: newStory.action,
        goal: newStory.goal,
        priority: newStory.priority,
        status: newStory.status,
        source: newStory.source,
        acceptance_criteria: newStory.acceptanceCriteria,
      });
      setStories((prev) => [toStory(saved), ...prev]);
      setManualActor("");
      setManualAction("");
      setManualGoal("");
      setShowManual(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add story");
    }
  };

  const handleDeleteStory = async (storyId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setDeletingId(storyId);
    try {
      await deleteStory(activeProject.id, storyId);
      setStories((prev) => prev.filter((s) => s.id !== storyId));
      setSelected((prev) => { const n = new Set(prev); n.delete(storyId); return n; });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete story");
    } finally {
      setDeletingId(null);
    }
  };

  const handleGenerateGherkin = async () => {
    if (selected.size === 0) return;
    setIsGenerating(true);
    setError(null);

    try {
      const selectedStories = stories.filter((s) => selected.has(s.id));

      // Save / sync to DB
      await saveStories(
        activeProject.id,
        selectedStories.map((s) => ({
          id: s.id,
          actor: s.actor,
          action: s.action,
          goal: s.goal,
          priority: s.priority,
          status: s.status,
          source: s.source,
          acceptance_criteria: s.acceptanceCriteria,
        }))
      );

      // Generate Gherkin
      await generateGherkin(activeProject.id, [...selected]);

      // Navigate to Gherkin editor
      router.push(`/dashboard/gherkin-editor`);
    } catch (err) {
      console.error("Generation failed:", err);
      setError(
        err instanceof Error
          ? err.message
          : "Failed to connect to backend. Is the FastAPI server running on port 8002?"
      );
      setIsGenerating(false);
    }
  };

  const filtered =
    filterPriority === "all"
      ? stories
      : stories.filter((s) => s.priority === filterPriority);

  const stats = {
    total: stories.length,
    pending: stories.filter((s) => s.status === "pending").length,
    processing: stories.filter((s) => s.status === "processing").length,
    done: stories.filter((s) => s.status === "done").length,
  };

  return (
    <DashboardLayoutWrapper>
      {/* Page Header */}
      <div className="sticky top-0 z-10 bg-slate-950/80 backdrop-blur-sm border-b border-slate-800 px-8 py-5">
        <div className="flex justify-between items-center">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="text-xs font-bold text-purple-400 bg-purple-500/10 border border-purple-500/20 px-2 py-0.5 rounded-full tracking-wider">
                S1
              </span>
              <span className="text-xs text-slate-500">Pipeline Stage 1 of 5</span>
              <span className="text-slate-700 mx-1">·</span>
              <Link
                href="/projects"
                className="flex items-center gap-1 text-xs text-slate-500 hover:text-purple-400 transition-colors"
              >
                <FolderOpen className="w-3.5 h-3.5" />
                {activeProject.name}
              </Link>
            </div>
            <h1 className="text-2xl font-bold text-white">User Story Intake</h1>
            <p className="text-slate-400 text-sm mt-0.5">
              Review and manage stories · Select to generate Gherkin test scenarios
            </p>
          </div>
          <div className="flex items-center gap-3">
            <Link
              href="/projects"
              className="flex items-center gap-2 px-4 py-2 rounded-lg border border-slate-700 text-slate-400 hover:border-slate-600 hover:text-white transition-all text-sm font-medium"
            >
              <ArrowLeft className="w-4 h-4" />
              Projects
            </Link>
            <button
              onClick={() => setShowManual((v) => !v)}
              className="flex items-center gap-2 px-4 py-2 rounded-lg border border-slate-700 text-slate-300 hover:border-purple-500 hover:text-purple-300 transition-all text-sm font-medium"
            >
              <Plus className="w-4 h-4" />
              Add Story
            </button>
            {selected.size > 0 && (
              <button
                onClick={handleGenerateGherkin}
                disabled={isGenerating}
                className="flex items-center gap-2 px-5 py-2 bg-purple-600 hover:bg-purple-500 disabled:opacity-60 disabled:cursor-not-allowed text-white rounded-lg font-medium text-sm transition-all shadow-lg shadow-purple-600/30"
              >
                {isGenerating ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Zap className="w-4 h-4" />
                )}
                {isGenerating ? "Generating…" : `Generate Gherkin (${selected.size})`}
                {!isGenerating && <ChevronRight className="w-4 h-4" />}
              </button>
            )}
          </div>
        </div>
      </div>

      <div className="p-8">
        {/* Error Banner */}
        {error && (
          <div className="mb-6 flex items-start gap-3 p-4 bg-red-500/10 border border-red-500/20 rounded-xl">
            <AlertCircle className="w-4 h-4 text-red-400 mt-0.5 shrink-0" />
            <div>
              <p className="text-sm font-semibold text-red-300">Error</p>
              <p className="text-xs text-red-400/80 mt-0.5">{error}</p>
            </div>
            <button
              onClick={() => setError(null)}
              className="ml-auto text-slate-500 hover:text-white text-xs"
            >
              ✕
            </button>
          </div>
        )}

        {/* Stats Row */}
        <div className="grid grid-cols-4 gap-4 mb-8">
          {[
            { label: "Total Stories", value: stats.total, color: "text-violet-400", bg: "bg-violet-500/10 border-violet-500/30", dot: "bg-violet-400" },
            { label: "Pending", value: stats.pending, color: "text-slate-200", bg: "bg-slate-800/60 border-slate-700", dot: "bg-slate-400" },
            { label: "Processing", value: stats.processing, color: "text-sky-400", bg: "bg-sky-500/10 border-sky-500/30", dot: "bg-sky-400" },
            { label: "Completed", value: stats.done, color: "text-emerald-400", bg: "bg-emerald-500/10 border-emerald-500/30", dot: "bg-emerald-400" },
          ].map((s) => (
            <div key={s.label} className={`rounded-xl border ${s.bg} p-4 transition-all hover:scale-[1.02]`}>
              <div className="flex items-center gap-2 mb-2">
                <span className={`w-2 h-2 rounded-full ${s.dot}`} />
                <p className="text-xs text-slate-400 font-medium">{s.label}</p>
              </div>
              <p className={`text-3xl font-bold ${s.color}`}>{s.value}</p>
            </div>
          ))}
        </div>

        {/* Manual Input Panel */}
        {showManual && (
          <div className="mb-6 p-5 bg-slate-800/50 border border-slate-700 rounded-xl">
            <div className="flex items-center gap-2 mb-4">
              <User className="w-4 h-4 text-purple-400" />
              <p className="text-sm font-semibold text-white">Add Story Manually</p>
            </div>
            <div className="grid grid-cols-3 gap-3 mb-3">
              <div>
                <label className="block text-xs text-slate-400 mb-1.5">Actor (who)</label>
                <input
                  value={manualActor}
                  onChange={(e) => setManualActor(e.target.value)}
                  placeholder='e.g. "registered customer"'
                  className="w-full bg-slate-900 border border-slate-600 rounded-lg px-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-purple-500 transition-colors"
                />
              </div>
              <div>
                <label className="block text-xs text-slate-400 mb-1.5">Action (what) *</label>
                <input
                  value={manualAction}
                  onChange={(e) => setManualAction(e.target.value)}
                  placeholder='e.g. "log in to the system"'
                  className="w-full bg-slate-900 border border-slate-600 rounded-lg px-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-purple-500 transition-colors"
                />
              </div>
              <div>
                <label className="block text-xs text-slate-400 mb-1.5">Goal (why)</label>
                <input
                  value={manualGoal}
                  onChange={(e) => setManualGoal(e.target.value)}
                  placeholder='e.g. "access my order history"'
                  className="w-full bg-slate-900 border border-slate-600 rounded-lg px-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-purple-500 transition-colors"
                />
              </div>
            </div>
            <div className="flex gap-3">
              <button
                onClick={addManualStory}
                disabled={!manualAction.trim()}
                className="px-4 py-2 bg-purple-600 hover:bg-purple-500 disabled:opacity-50 text-white rounded-lg text-sm font-medium transition-all"
              >
                Add Story
              </button>
              <button
                onClick={() => setShowManual(false)}
                className="px-4 py-2 border border-slate-600 text-slate-400 hover:text-white rounded-lg text-sm transition-all"
              >
                Cancel
              </button>
            </div>
          </div>
        )}

        {/* Loading stories */}
        {isLoadingStories && (
          <div className="flex items-center justify-center py-16">
            <div className="text-center">
              <Loader2 className="w-8 h-8 text-purple-400 animate-spin mx-auto mb-3" />
              <p className="text-slate-400 text-sm">Loading stories from database…</p>
            </div>
          </div>
        )}

        {/* Empty state */}
        {!isLoadingStories && stories.length === 0 && (
          <div className="flex flex-col items-center justify-center py-16 border-2 border-dashed border-slate-700 rounded-xl">
            <FolderOpen className="w-10 h-10 text-slate-600 mb-4" />
            <h3 className="text-base font-semibold text-white mb-1">No Stories Yet</h3>
            <p className="text-sm text-slate-400 mb-5 text-center max-w-xs">
              This project has no user stories. Add them manually or import from Component 1.
            </p>
            <button
              onClick={() => setShowManual(true)}
              className="flex items-center gap-2 px-4 py-2 bg-purple-600 hover:bg-purple-500 text-white rounded-lg text-sm font-medium transition-all"
            >
              <Plus className="w-4 h-4" /> Add First Story
            </button>
          </div>
        )}

        {/* Toolbar */}
        {!isLoadingStories && stories.length > 0 && (
          <>
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-3">
                <button
                  onClick={toggleAll}
                  className="text-xs text-slate-400 hover:text-white transition-colors flex items-center gap-1.5"
                >
                  <div
                    className={`w-4 h-4 rounded border transition-all ${
                      selected.size === stories.length ? "bg-purple-600 border-purple-600" : "border-slate-600"
                    }`}
                  >
                    {selected.size === stories.length && <CheckCircle className="w-4 h-4 text-white" />}
                  </div>
                  Select All
                </button>
                <span className="text-slate-700">|</span>
                <div className="flex items-center gap-1.5 text-xs text-slate-400">
                  <Filter className="w-3.5 h-3.5" />
                  {(["all", "high", "medium", "low"] as const).map((p) => (
                    <button
                      key={p}
                      onClick={() => setFilterPriority(p)}
                      className={`px-2.5 py-1 rounded-md transition-all capitalize ${
                        filterPriority === p ? "bg-slate-700 text-white" : "text-slate-500 hover:text-slate-300"
                      }`}
                    >
                      {p}
                    </button>
                  ))}
                </div>
              </div>
              <p className="text-xs text-slate-500">
                {selected.size > 0 ? `${selected.size} selected` : `${filtered.length} stories`}
              </p>
            </div>

            {/* Story Cards */}
            <div className="space-y-3">
              {filtered.map((story) => {
                const pCfg = priorityConfig[story.priority];
                const sCfg = statusConfig[story.status];
                const isSelected = selected.has(story.id);
                const isBeingDeleted = deletingId === story.id;

                return (
                  <div
                    key={story.id}
                    onClick={() => toggle(story.id)}
                    className={`group relative rounded-xl border cursor-pointer transition-all duration-200 ${
                      isSelected
                        ? "border-purple-500/60 bg-purple-500/5 shadow-md shadow-purple-500/10"
                        : "border-slate-700/60 bg-slate-800/30 hover:border-slate-600 hover:bg-slate-800/50"
                    }`}
                  >
                    <div className="p-5">
                      <div className="flex items-start gap-4">
                        {/* Checkbox */}
                        <div
                          className={`mt-0.5 w-5 h-5 rounded-md border-2 flex items-center justify-center shrink-0 transition-all ${
                            isSelected ? "bg-purple-600 border-purple-600" : "border-slate-600 group-hover:border-slate-500"
                          }`}
                        >
                          {isSelected && <CheckCircle className="w-4 h-4 text-white" />}
                        </div>

                        {/* Content */}
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 flex-wrap mb-2">
                            <span className="text-xs font-mono font-bold text-purple-400">{story.id}</span>
                            <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${pCfg.bg} ${pCfg.color}`}>
                              {pCfg.label}
                            </span>
                            <span className={`flex items-center gap-1 text-[11px] ${sCfg.color}`}>
                              {sCfg.icon} {sCfg.label}
                            </span>
                            {story.source === "manual" && (
                              <span className="text-[10px] text-amber-400 bg-amber-500/10 border border-amber-500/20 px-2 py-0.5 rounded-full">
                                MANUAL
                              </span>
                            )}
                          </div>

                          <p className="text-sm text-white font-medium mb-1">
                            As a <span className="text-purple-300">{story.actor}</span>, I want to{" "}
                            <span className="text-white">{story.action}</span>, so that I can{" "}
                            <span className="text-slate-300">{story.goal}</span>.
                          </p>

                          <div className="mt-3 flex flex-wrap gap-2">
                            {story.acceptanceCriteria.map((ac, i) => (
                              <span key={i} className="text-[11px] bg-slate-700/50 text-slate-400 px-2.5 py-1 rounded-lg border border-slate-700">
                                ✓ {ac}
                              </span>
                            ))}
                          </div>
                        </div>

                        {/* Right — delete + status */}
                        <div className="shrink-0 flex items-center gap-2">
                          {story.status === "done" && (
                            <span className="text-[11px] text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-2.5 py-1 rounded-lg">
                              Tests Generated
                            </span>
                          )}
                          <button
                            onClick={(e) => handleDeleteStory(story.id, e)}
                            disabled={isBeingDeleted}
                            title="Delete story"
                            className="p-1.5 text-slate-600 hover:text-red-400 hover:bg-red-500/10 rounded-lg transition-all opacity-0 group-hover:opacity-100 disabled:opacity-50"
                          >
                            {isBeingDeleted ? (
                              <Loader2 className="w-4 h-4 animate-spin" />
                            ) : (
                              <Trash2 className="w-4 h-4" />
                            )}
                          </button>
                          <ChevronRight
                            className={`w-4 h-4 transition-all ${
                              isSelected ? "text-purple-400" : "text-slate-600 group-hover:text-slate-400"
                            }`}
                          />
                        </div>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </>
        )}

        {/* Bottom CTA */}
        {selected.size > 0 && (
          <div className="mt-8 flex justify-center">
            <button
              onClick={handleGenerateGherkin}
              disabled={isGenerating}
              className="flex items-center gap-3 px-8 py-4 bg-linear-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 disabled:opacity-60 disabled:cursor-not-allowed text-white rounded-xl font-semibold text-base transition-all shadow-xl shadow-purple-600/30 hover:shadow-purple-500/40 hover:scale-[1.02]"
            >
              {isGenerating ? (
                <Loader2 className="w-5 h-5 animate-spin" />
              ) : (
                <Zap className="w-5 h-5" />
              )}
              {isGenerating
                ? "Saving to DB & generating…"
                : `Generate Gherkin for ${selected.size} stor${selected.size > 1 ? "ies" : "y"}`}
              {!isGenerating && <ChevronRight className="w-5 h-5" />}
            </button>
          </div>
        )}
      </div>
    </DashboardLayoutWrapper>
  );
}
