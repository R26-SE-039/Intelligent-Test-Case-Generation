"use client";

import { useState, useEffect, useCallback } from "react";
import DashboardLayoutWrapper from "@/components/dashboard-layout-wrapper";
import { listStories, getGherkinForStory, updateGherkin, approveGherkin, regenerateGherkin } from "@/lib/api";
import { useProject } from "@/lib/project-context";
import { useRouter } from "next/navigation";
import dynamic from "next/dynamic";
import {
  FileText,
  ChevronRight,
  ChevronLeft,
  Edit3,
  CheckCircle,
  Info,
  Copy,
  Check,
  Loader2,
  AlertCircle,
  Cpu,
  RefreshCw,
  FolderOpen,
} from "lucide-react";
import Link from "next/link";

const MonacoEditor = dynamic(() => import("@monaco-editor/react"), { ssr: false });

interface GherkinStory {
  id: string;           // story id e.g. "US-001"
  gherkinId: string;    // UUID from gherkin_scenarios table
  title: string;
  content: string;
  edited: boolean;
  generator: string;
  approved: boolean;    // from DB — persists on refresh ✅
}

export default function GherkinEditorPage() {
  const router = useRouter();
  const { activeProject } = useProject();

  const [stories, setStories] = useState<GherkinStory[]>([]);
  const [activeId, setActiveId] = useState<string>("");
  const [copied, setCopied] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [isRegenerating, setIsRegenerating] = useState(false);
  const [isApproving, setIsApproving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Redirect if no project
  useEffect(() => {
    if (!activeProject) {
      router.replace("/projects");
    }
  }, [activeProject, router]);

  const loadGherkin = useCallback(async () => {
    if (!activeProject) return;
    setIsLoading(true);
    setError(null);

    try {
      // Load all stories for the project, then fetch each story's Gherkin in
      // parallel — one slow scenario shouldn't gate the rest.
      const storyList = await listStories(activeProject.id);
      const gherkins = await Promise.all(
        storyList.map((s) => getGherkinForStory(activeProject.id, s.id).catch(() => null)),
      );

      const loaded: GherkinStory[] = [];
      storyList.forEach((s, i) => {
        const gherkin = gherkins[i];
        if (gherkin) {
          loaded.push({
            id: s.id,
            gherkinId: gherkin.id,
            title: gherkin.feature_name,
            content: gherkin.gherkin_text,
            edited: gherkin.edited_by_qa,
            generator: gherkin.generator,
            approved: gherkin.approved,
          });
        }
      });

      if (loaded.length > 0) {
        setStories(loaded);
        setActiveId(loaded[0].id);
      } else {
        setError("No Gherkin scenarios found. Go back and generate some first.");
      }
    } catch (err) {
      console.error("Failed to load Gherkin:", err);
      const message =
        err instanceof Error ? err.message : "Could not load Gherkin from backend.";
      setError(`${message} Is the backend running on the configured port?`);
    } finally {
      setIsLoading(false);
    }
  }, [activeProject]);

  useEffect(() => {
    loadGherkin();
  }, [loadGherkin]);

  if (!activeProject) return null;

  const activeStory = stories.find((s) => s.id === activeId);

  const handleChange = (value: string | undefined) => {
    setStories((prev) =>
      prev.map((s) =>
        s.id === activeId ? { ...s, content: value ?? s.content, edited: true } : s
      )
    );
  };

  /** Save QA edits back to PostgreSQL */
  const handleSave = async () => {
    if (!activeStory || !activeStory.gherkinId) return;
    setIsSaving(true);
    try {
      await updateGherkin(activeStory.gherkinId, activeStory.content);
      setStories((prev) =>
        prev.map((s) => (s.id === activeId ? { ...s, edited: false } : s))
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setIsSaving(false);
    }
  };

  /** Toggle approval — persists to DB */
  const handleApprove = async () => {
    if (!activeStory?.gherkinId) return;
    setIsApproving(true);
    try {
      const result = await approveGherkin(activeStory.gherkinId);
      setStories((prev) =>
        prev.map((s) => (s.id === activeId ? { ...s, approved: result.approved } : s))
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Approve failed");
    } finally {
      setIsApproving(false);
    }
  };

  /** Force-regenerate Gherkin (ignores edited_by_qa flag) */
  const handleRegenerate = async () => {
    if (!activeStory) return;
    setIsRegenerating(true);
    try {
      const result = await regenerateGherkin(activeProject.id, activeStory.id);
      setStories((prev) =>
        prev.map((s) =>
          s.id === activeId
            ? { ...s, content: result.gherkin_text, generator: result.generator, edited: false, approved: false }
            : s
        )
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Regenerate failed");
    } finally {
      setIsRegenerating(false);
    }
  };

  const handleCopy = async () => {
    if (!activeStory) return;
    await navigator.clipboard.writeText(activeStory.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const approvedCount = stories.filter((s) => s.approved).length;

  if (isLoading) {
    return (
      <DashboardLayoutWrapper>
        <div className="flex items-center justify-center h-screen">
          <div className="text-center">
            <Loader2 className="w-10 h-10 text-purple-600 animate-spin mx-auto mb-4" />
            <p className="text-slate-700 font-medium">Loading Gherkin scenarios…</p>
            <p className="text-slate-500 text-sm mt-1">Fetching from database</p>
          </div>
        </div>
      </DashboardLayoutWrapper>
    );
  }

  return (
    <DashboardLayoutWrapper>
      {/* Header */}
      <div className="sticky top-0 z-10 bg-white/80 backdrop-blur-sm border-b border-slate-200 px-8 py-5">
        <div className="flex justify-between items-center">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="text-xs font-bold text-purple-700 bg-purple-50 border border-purple-200 px-2 py-0.5 rounded-full tracking-wider">
                S2
              </span>
              <span className="text-xs text-slate-500">Pipeline Stage 2 of 5</span>
              <span className="text-slate-300 mx-1">·</span>
              <Link
                href="/projects"
                className="flex items-center gap-1 text-xs text-slate-500 hover:text-purple-600 transition-colors"
              >
                <FolderOpen className="w-3.5 h-3.5" />
                {activeProject.name}
              </Link>
            </div>
            <h1 className="text-2xl font-bold text-slate-900">Gherkin Editor</h1>
            <p className="text-slate-600 text-sm mt-0.5">
              Review and edit AI-generated Given/When/Then scenarios
            </p>
          </div>
          <div className="flex items-center gap-3">
            <Link
              href="/dashboard"
              className="flex items-center gap-2 px-4 py-2 border border-slate-300 text-slate-600 hover:text-slate-900 hover:border-slate-400 hover:bg-slate-50 rounded-lg text-sm transition-all"
            >
              <ChevronLeft className="w-4 h-4" />
              Back
            </Link>
            <Link
              href="/dashboard/mode-setup"
              className="flex items-center gap-2 px-5 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg font-medium text-sm transition-all shadow-lg shadow-purple-600/30"
            >
              Mode & URL Setup
              <ChevronRight className="w-4 h-4" />
            </Link>
          </div>
        </div>
      </div>

      {/* Error banner */}
      {error && (
        <div className="mx-8 mt-4 flex items-start gap-3 px-4 py-3 bg-red-50 border border-red-200 rounded-xl">
          <AlertCircle className="w-4 h-4 text-red-600 mt-0.5 shrink-0" />
          <p className="text-sm text-red-700">{error}</p>
          <button onClick={() => setError(null)} className="ml-auto text-slate-400 hover:text-slate-900">✕</button>
        </div>
      )}

      {/* Human-in-the-loop info banner */}
      <div className="mx-8 mt-6 flex items-start gap-3 px-4 py-3 bg-blue-50 border border-blue-200 rounded-xl">
        <Info className="w-4 h-4 text-blue-600 mt-0.5 shrink-0" />
        <p className="text-sm text-blue-700">
          <span className="font-semibold">Human-in-the-loop:</span> Edit Gherkin scenarios before
          generating code. Save changes to PostgreSQL. Approve each scenario when satisfied — approvals
          persist across sessions.
        </p>
      </div>

      {/* Empty state */}
      {stories.length === 0 && !isLoading && (
        <div className="flex flex-col items-center justify-center py-20">
          <FileText className="w-12 h-12 text-slate-400 mb-4" />
          <h3 className="text-base font-semibold text-slate-900 mb-2">No Gherkin Scenarios</h3>
          <p className="text-sm text-slate-600 mb-5">
            Go back to User Stories and generate Gherkin first.
          </p>
          <Link
            href="/dashboard"
            className="flex items-center gap-2 px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg text-sm font-medium transition-all"
          >
            <ChevronLeft className="w-4 h-4" /> Back to Stories
          </Link>
        </div>
      )}

      {/* Main editor layout */}
      {stories.length > 0 && (
        <div className="flex gap-0 h-[calc(100vh-280px)] mx-8 mt-6 mb-8 rounded-xl border border-slate-200 overflow-hidden bg-white shadow-sm">
          {/* Left panel — story list */}
          <div className="w-64 shrink-0 bg-slate-50 border-r border-slate-200 flex flex-col">
            <div className="px-4 py-3 border-b border-slate-200 flex items-center justify-between bg-white">
              <p className="text-xs font-semibold text-slate-500 uppercase tracking-widest">
                Stories ({stories.length})
              </p>
              <span className="text-[10px] text-emerald-700 font-semibold">
                {approvedCount}/{stories.length} approved
              </span>
            </div>
            <div className="flex-1 overflow-y-auto py-2" style={{ scrollbarWidth: "none" }}>
              {stories.map((story) => {
                const isActive = story.id === activeId;
                return (
                  <button
                    key={story.id}
                    onClick={() => setActiveId(story.id)}
                    className={`w-full text-left px-4 py-3 transition-all border-l-2 ${
                      isActive
                        ? "border-purple-500 bg-purple-50 text-slate-900"
                        : "border-transparent text-slate-600 hover:bg-white hover:text-slate-900"
                    }`}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-xs font-mono text-purple-700">{story.id}</span>
                      <div className="flex items-center gap-1">
                        {story.generator === "llm" && <Cpu className="w-3 h-3 text-indigo-600" />}
                        {story.edited && <Edit3 className="w-3 h-3 text-amber-600" />}
                        {story.approved && <CheckCircle className="w-3 h-3 text-emerald-600" />}
                      </div>
                    </div>
                    <p className="text-xs font-medium leading-tight">{story.title}</p>
                    <p className="text-[10px] text-slate-500 mt-0.5 capitalize">
                      {story.generator === "llm" ? "🤖 LLM" : "⚙️ Jinja2"}
                    </p>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Right panel — Monaco editor */}
          {activeStory && (
            <div className="flex-1 flex flex-col bg-white">
              {/* Editor toolbar */}
              <div className="flex items-center justify-between px-4 py-2.5 border-b border-slate-200 bg-slate-50">
                <div className="flex items-center gap-2">
                  <FileText className="w-4 h-4 text-purple-600" />
                  <span className="text-sm font-medium text-slate-800">
                    {activeStory.title}.feature
                  </span>
                  {activeStory.edited && (
                    <span className="text-[10px] bg-amber-100 text-amber-700 border border-amber-200 px-1.5 py-0.5 rounded">
                      UNSAVED
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  {/* Regenerate */}
                  <button
                    onClick={handleRegenerate}
                    disabled={isRegenerating}
                    title="Force regenerate (overwrites edits)"
                    className="flex items-center gap-1.5 text-xs text-slate-600 hover:text-indigo-700 px-2.5 py-1.5 rounded-md hover:bg-white transition-all disabled:opacity-50"
                  >
                    {isRegenerating ? (
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    ) : (
                      <RefreshCw className="w-3.5 h-3.5" />
                    )}
                    Regenerate
                  </button>

                  {/* Save to DB */}
                  {activeStory.edited && activeStory.gherkinId && (
                    <button
                      onClick={handleSave}
                      disabled={isSaving}
                      className="flex items-center gap-1.5 text-xs text-emerald-700 hover:text-emerald-800 px-2.5 py-1.5 rounded-md hover:bg-emerald-50 transition-all"
                    >
                      {isSaving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : null}
                      Save to DB
                    </button>
                  )}

                  {/* Copy */}
                  <button
                    onClick={handleCopy}
                    className="flex items-center gap-1.5 text-xs text-slate-600 hover:text-slate-900 transition-colors px-2.5 py-1.5 rounded-md hover:bg-white"
                  >
                    {copied ? <><Check className="w-3.5 h-3.5 text-emerald-600" /> Copied</> : <><Copy className="w-3.5 h-3.5" /> Copy</>}
                  </button>

                  {/* Approve — persists to DB */}
                  <button
                    onClick={handleApprove}
                    disabled={isApproving}
                    className={`flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-md font-medium transition-all disabled:opacity-50 ${
                      activeStory.approved
                        ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                        : "bg-purple-600 hover:bg-purple-700 text-white"
                    }`}
                  >
                    {isApproving ? (
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    ) : (
                      <CheckCircle className="w-3.5 h-3.5" />
                    )}
                    {activeStory.approved ? "Approved ✓" : "Approve"}
                  </button>
                </div>
              </div>

              {/* Monaco */}
              <div className="flex-1">
                <MonacoEditor
                  height="100%"
                  language="plaintext"
                  theme="vs"
                  value={activeStory.content}
                  onChange={handleChange}
                  options={{
                    fontSize: 13,
                    lineHeight: 22,
                    minimap: { enabled: false },
                    wordWrap: "on",
                    scrollBeyondLastLine: false,
                    padding: { top: 16, bottom: 16 },
                    fontFamily: "'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace",
                    fontLigatures: true,
                  }}
                />
              </div>

              {/* Bottom status bar */}
              <div className="flex items-center justify-between px-4 py-2 border-t border-slate-200 bg-slate-50">
                <div className="flex items-center gap-4 text-[11px] text-slate-500">
                  <span>{activeStory.content.split("\n").length} lines</span>
                  <span>Gherkin · Given/When/Then</span>
                  <span className="capitalize">
                    Generator: <span className="text-purple-700">{activeStory.generator}</span>
                  </span>
                </div>
                <div className="text-[11px] text-slate-500">
                  {approvedCount}/{stories.length} approved
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </DashboardLayoutWrapper>
  );
}
