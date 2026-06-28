"use client";

import { useState, useEffect, Suspense, useCallback } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import DashboardLayoutWrapper from "@/components/dashboard-layout-wrapper";
import {
  Code2,
  ChevronRight,
  ChevronLeft,
  PlayCircle,
  Loader2,
  Sparkles,
  AlertTriangle,
  FileCode2,
  CheckCircle2,
  GitBranch,
  Pencil,
} from "lucide-react";
import Link from "next/link";
import {
  generateTestCode,
  getTestSuites,
  selectTestSuiteForRun,
  type TestSuite,
} from "@/lib/api";
import { useProject } from "@/lib/project-context";

type Framework = "selenium" | "playwright" | "cypress";

const FRAMEWORKS: { id: Framework; label: string; badge: string; accent: string }[] = [
  { id: "selenium",   label: "Selenium",   badge: "Python",     accent: "text-blue-600" },
  { id: "playwright", label: "Playwright", badge: "Python",     accent: "text-emerald-600" },
  { id: "cypress",    label: "Cypress",    badge: "JavaScript", accent: "text-amber-600" },
];

function formatRelative(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  const diff = Date.now() - d.getTime();
  const min = Math.round(diff / 60_000);
  if (min < 1) return "just now";
  if (min < 60) return `${min}m ago`;
  const hr = Math.round(min / 60);
  if (hr < 24) return `${hr}h ago`;
  const day = Math.round(hr / 24);
  if (day < 7) return `${day}d ago`;
  return d.toLocaleDateString();
}

function CodeReviewContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const modeParam = searchParams.get("mode") || "dom";
  const urlParam = searchParams.get("url") || "https://www.saucedemo.com";
  const { activeProject } = useProject();

  const [suites, setSuites] = useState<Record<Framework, TestSuite | null>>({
    selenium: null,
    playwright: null,
    cypress: null,
  });
  const [isLoading, setIsLoading] = useState(false);
  const [generating, setGenerating] = useState<Framework | "all" | null>(null);
  const [selectingId, setSelectingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    if (!activeProject) return;
    setIsLoading(true);
    setError(null);
    try {
      const list = await getTestSuites(activeProject.id);
      const next: Record<Framework, TestSuite | null> = {
        selenium: null,
        playwright: null,
        cypress: null,
      };
      for (const s of list) {
        if (s.framework in next) next[s.framework as Framework] = s;
      }
      setSuites(next);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load test suites");
    } finally {
      setIsLoading(false);
    }
  }, [activeProject]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const generate = useCallback(
    async (frameworks: Framework[]) => {
      if (!activeProject) return;
      setError(null);
      setGenerating(frameworks.length > 1 ? "all" : frameworks[0]);
      try {
        await generateTestCode(activeProject.id, urlParam, modeParam, frameworks);
        await reload();
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to generate code");
      } finally {
        setGenerating(null);
      }
    },
    [activeProject, urlParam, modeParam, reload],
  );

  const handleSelectForRun = useCallback(
    async (suite: TestSuite) => {
      setSelectingId(suite.id);
      setError(null);
      try {
        const updated = await selectTestSuiteForRun(suite.id);
        setSuites((prev) => {
          // Selection clears the flag on every other framework. Reset all
          // selected_for_run flags client-side, then apply the server response.
          const next: Record<Framework, TestSuite | null> = {
            selenium: prev.selenium ? { ...prev.selenium, selected_for_run: false } : null,
            playwright: prev.playwright ? { ...prev.playwright, selected_for_run: false } : null,
            cypress: prev.cypress ? { ...prev.cypress, selected_for_run: false } : null,
          };
          if (updated.framework in next) next[updated.framework as Framework] = updated;
          return next;
        });
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to select suite for run");
      } finally {
        setSelectingId(null);
      }
    },
    [],
  );

  const selectedSuite =
    suites.selenium?.selected_for_run ? suites.selenium :
    suites.playwright?.selected_for_run ? suites.playwright :
    suites.cypress?.selected_for_run ? suites.cypress :
    null;

  const goToExecution = () => {
    if (!selectedSuite) return;
    const qs = new URLSearchParams({
      suite: selectedSuite.id,
      framework: selectedSuite.framework,
    });
    router.push(`/dashboard/execution?${qs.toString()}`);
  };

  return (
    <DashboardLayoutWrapper>
      {/* Header */}
      <div className="sticky top-0 z-10 bg-white/80 backdrop-blur-sm border-b border-slate-200 px-8 py-5">
        <div className="flex justify-between items-center">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="text-xs font-bold text-purple-700 bg-purple-50 border border-purple-200 px-2 py-0.5 rounded-full tracking-wider">
                S5
              </span>
              <span className="text-xs text-slate-500">Pipeline Stage 5 of 6</span>
            </div>
            <h1 className="text-2xl font-bold text-slate-900">Code Review</h1>
            <p className="text-slate-600 text-sm mt-0.5">
              Pick one framework to execute · Open any suite in the dedicated editor · Versions saved in DB
            </p>
          </div>
          <div className="flex items-center gap-3">
            <Link
              href="/dashboard/mode-setup"
              className="flex items-center gap-2 px-4 py-2 border border-slate-300 text-slate-600 hover:text-slate-900 hover:border-slate-400 hover:bg-slate-50 rounded-lg text-sm transition-all"
            >
              <ChevronLeft className="w-4 h-4" />
              Back
            </Link>
            <button
              onClick={goToExecution}
              disabled={!selectedSuite}
              className={`flex items-center gap-2 px-5 py-2 rounded-lg font-medium text-sm transition-all ${
                selectedSuite
                  ? "bg-purple-600 hover:bg-purple-700 text-white shadow-lg shadow-purple-600/30"
                  : "bg-slate-200 text-slate-400 cursor-not-allowed"
              }`}
              title={
                selectedSuite
                  ? `Run ${selectedSuite.framework} v${selectedSuite.version} via GitHub Actions`
                  : "Select a framework first"
              }
            >
              <PlayCircle className="w-4 h-4" />
              Run Tests
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>

      {error && (
        <div className="mx-6 mt-4 p-3 bg-red-50 text-red-600 text-sm rounded border border-red-200">
          {error}
        </div>
      )}

      {/* Mode + URL summary */}
      <div className="mx-6 mt-4 flex items-center gap-3 text-xs text-slate-500">
        <span className="px-2 py-0.5 rounded bg-emerald-50 text-emerald-700 border border-emerald-200">
          Mode {modeParam === "dom" ? "B · DOM-Aware" : "A · Abstract"}
        </span>
        <span className="font-mono">{urlParam}</span>
        {!activeProject && (
          <span className="ml-auto text-amber-700">
            Select a project from the sidebar to load suites.
          </span>
        )}
      </div>

      {/* Selection helper banner */}
      {!selectedSuite && Object.values(suites).some(Boolean) && (
        <div className="mx-6 mt-4 p-3 bg-purple-50 border border-purple-200 rounded-lg text-sm text-purple-800 flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 shrink-0" />
          Tick the radio on one framework card to choose which suite gets executed via GitHub Actions.
        </div>
      )}

      {/* Suite cards grid */}
      <div className="px-6 py-6 grid grid-cols-3 gap-5">
        {isLoading
          ? Array.from({ length: 3 }).map((_, i) => (
              <div
                key={i}
                className="rounded-xl border border-slate-200 bg-white p-5 h-56 animate-pulse"
              />
            ))
          : FRAMEWORKS.map((fw) => {
              const suite = suites[fw.id];
              const isGen = generating === fw.id || generating === "all";

              if (!suite) {
                return (
                  <div
                    key={fw.id}
                    className="rounded-xl border border-dashed border-slate-300 bg-white p-5 flex flex-col"
                  >
                    <div className="flex items-center gap-2 mb-3">
                      <Code2 className="w-4 h-4 text-slate-400" />
                      <p className="text-sm font-semibold text-slate-700">{fw.label}</p>
                      <span className={`text-[10px] font-semibold ${fw.accent}`}>
                        {fw.badge}
                      </span>
                    </div>
                    <p className="text-xs text-slate-500 flex-1">
                      No {fw.label} suite generated yet. Generation calls the LLM and saves the
                      result as version 1.
                    </p>
                    <button
                      onClick={() => generate([fw.id])}
                      disabled={generating !== null || !activeProject}
                      className="mt-3 flex items-center justify-center gap-2 px-3 py-2 bg-purple-600 hover:bg-purple-700 disabled:opacity-50 text-white text-xs font-medium rounded-md transition-all"
                    >
                      {isGen ? (
                        <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      ) : (
                        <Sparkles className="w-3.5 h-3.5" />
                      )}
                      Generate {fw.label}
                    </button>
                  </div>
                );
              }

              const isSelected = suite.selected_for_run;
              return (
                <div
                  key={fw.id}
                  className={`rounded-xl border bg-white p-5 flex flex-col transition-all ${
                    isSelected
                      ? "border-purple-500 ring-2 ring-purple-200 shadow-md"
                      : "border-slate-200 hover:border-slate-300 hover:shadow-sm"
                  }`}
                >
                  {/* Top row: framework + radio */}
                  <div className="flex items-start justify-between mb-3">
                    <div className="flex items-center gap-2">
                      <Code2 className="w-4 h-4 text-slate-700" />
                      <p className="text-sm font-semibold text-slate-900">{fw.label}</p>
                      <span className={`text-[10px] font-semibold ${fw.accent}`}>
                        {fw.badge}
                      </span>
                    </div>
                    <label className="flex items-center gap-1.5 cursor-pointer">
                      <input
                        type="radio"
                        name="suite-to-run"
                        checked={isSelected}
                        onChange={() => handleSelectForRun(suite)}
                        disabled={selectingId !== null}
                        className="accent-purple-600 w-4 h-4"
                      />
                      <span
                        className={`text-[11px] font-medium ${
                          isSelected ? "text-purple-700" : "text-slate-500"
                        }`}
                      >
                        Run this
                      </span>
                    </label>
                  </div>

                  {/* Filename */}
                  <p className="text-[11px] font-mono text-slate-600 truncate mb-2">
                    {suite.filename}
                  </p>

                  {/* Meta row */}
                  <div className="flex items-center gap-2 flex-wrap mb-3">
                    <span className="inline-flex items-center gap-1 text-[10px] text-slate-600 bg-slate-100 px-1.5 py-0.5 rounded font-mono">
                      <GitBranch className="w-3 h-3" /> v{suite.version}
                    </span>
                    <span className="text-[10px] text-slate-500">
                      {suite.source_scenario_count} scenario
                      {suite.source_scenario_count === 1 ? "" : "s"}
                    </span>
                    <span className="text-[10px] text-slate-400">
                      saved {formatRelative(suite.updated_at)}
                    </span>
                  </div>

                  {/* Stale banner */}
                  {suite.is_stale && (
                    <div className="mb-3 flex items-center gap-1.5 text-[11px] text-amber-700 bg-amber-50 border border-amber-200 px-2 py-1 rounded">
                      <AlertTriangle className="w-3 h-3 shrink-0" />
                      Scenarios changed since this version was generated.
                    </div>
                  )}

                  {/* Selected pill */}
                  {isSelected && (
                    <div className="mb-3 inline-flex items-center gap-1.5 text-[11px] text-purple-700 bg-purple-50 border border-purple-200 px-2 py-1 rounded self-start">
                      <CheckCircle2 className="w-3 h-3" />
                      Selected for next run
                    </div>
                  )}

                  {/* Actions */}
                  <div className="mt-auto pt-3 flex items-center gap-2 border-t border-slate-100">
                    <button
                      onClick={() => router.push(`/dashboard/code-review/${suite.id}`)}
                      className="flex-1 flex items-center justify-center gap-1.5 px-3 py-1.5 border border-slate-300 hover:border-slate-400 hover:bg-slate-50 text-slate-700 text-xs font-medium rounded-md transition-all"
                    >
                      <Pencil className="w-3.5 h-3.5" />
                      Open Editor
                    </button>
                    <button
                      onClick={() => generate([fw.id])}
                      disabled={generating !== null}
                      className="flex items-center justify-center gap-1.5 px-3 py-1.5 text-xs font-medium text-purple-700 hover:text-purple-800 hover:bg-purple-50 rounded-md transition-all disabled:opacity-50"
                      title={`Regenerate ${fw.label} — creates v${suite.version + 1}`}
                    >
                      {isGen ? (
                        <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      ) : (
                        <Sparkles className="w-3.5 h-3.5" />
                      )}
                      Regenerate
                    </button>
                  </div>
                </div>
              );
            })}
      </div>

      {/* Bulk generate */}
      {!isLoading &&
        Object.values(suites).every((s) => s === null) &&
        activeProject && (
          <div className="mx-6 mb-8 p-6 rounded-xl border border-slate-200 bg-white text-center">
            <FileCode2 className="w-8 h-8 text-purple-500 mx-auto mb-3" />
            <p className="text-sm font-medium text-slate-800 mb-1">
              No test suites yet for this project
            </p>
            <p className="text-xs text-slate-500 max-w-md mx-auto mb-4">
              Generate code for all three frameworks at once. Each one is a separate LLM call and
              is saved as version 1.
            </p>
            <button
              onClick={() => generate(["selenium", "playwright", "cypress"])}
              disabled={generating !== null}
              className="inline-flex items-center gap-2 px-4 py-2 bg-purple-600 hover:bg-purple-700 disabled:opacity-50 text-white text-sm font-medium rounded-md transition-all"
            >
              {generating === "all" ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Sparkles className="w-4 h-4" />
              )}
              Generate All Frameworks
            </button>
          </div>
        )}
    </DashboardLayoutWrapper>
  );
}

export default function CodeReviewPage() {
  return (
    <Suspense fallback={<div className="p-8">Loading Code Review...</div>}>
      <CodeReviewContent />
    </Suspense>
  );
}
