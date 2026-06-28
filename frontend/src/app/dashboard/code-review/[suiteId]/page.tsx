"use client";

import { useState, useEffect, useRef, useCallback, use } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ChevronLeft,
  Copy,
  Check,
  Download,
  Save,
  GitBranch,
  History,
  Sparkles,
  Loader2,
  CheckCircle2,
  RotateCcw,
  AlertTriangle,
  PlayCircle,
} from "lucide-react";
import {
  getTestSuite,
  getTestSuiteHistory,
  updateTestSuiteCode,
  saveTestSuiteAsNewVersion,
  restoreTestSuiteVersion,
  selectTestSuiteForRun,
  type TestSuite,
} from "@/lib/api";

const MonacoEditor = dynamic(() => import("@monaco-editor/react"), { ssr: false });

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
  return d.toLocaleString();
}

interface PageProps {
  params: Promise<{ suiteId: string }>;
}

export default function SuiteEditorPage({ params }: PageProps) {
  const { suiteId } = use(params);
  const router = useRouter();

  const [suite, setSuite] = useState<TestSuite | null>(null);
  const [history, setHistory] = useState<TestSuite[]>([]);
  const [activeHead, setActiveHead] = useState<TestSuite | null>(null);

  const [code, setCode] = useState<string>("");
  const [dirty, setDirty] = useState(false);
  const [savingStatus, setSavingStatus] = useState<"idle" | "saving" | "saved">("idle");

  const [isLoading, setIsLoading] = useState(true);
  const [isWorking, setIsWorking] = useState(false);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const isHistorical = suite ? !suite.is_active : false;

  const loadSuite = useCallback(
    async (id: string) => {
      setIsLoading(true);
      setError(null);
      try {
        const [s, h] = await Promise.all([
          getTestSuite(id),
          getTestSuiteHistory(id),
        ]);
        setSuite(s);
        setHistory(h);
        setActiveHead(h.find((row) => row.is_active) ?? null);
        setCode(s.code);
        setDirty(false);
        setSavingStatus("idle");
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load suite");
      } finally {
        setIsLoading(false);
      }
    },
    [],
  );

  useEffect(() => {
    void loadSuite(suiteId);
  }, [suiteId, loadSuite]);

  // Autosave to active head only. Historical versions never autosave —
  // changes there are discarded unless the user "Restore"s first.
  useEffect(() => {
    if (!suite || !dirty || isHistorical) return;
    if (saveTimer.current) clearTimeout(saveTimer.current);
    const id = suite.id;
    const value = code;
    saveTimer.current = setTimeout(async () => {
      setSavingStatus("saving");
      try {
        const updated = await updateTestSuiteCode(id, value);
        setSuite(updated);
        setHistory((prev) => prev.map((r) => (r.id === updated.id ? updated : r)));
        setActiveHead(updated);
        setDirty(false);
        setSavingStatus("saved");
        setTimeout(() => setSavingStatus("idle"), 1500);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Autosave failed");
        setSavingStatus("idle");
      }
    }, 1200);
    return () => {
      if (saveTimer.current) clearTimeout(saveTimer.current);
    };
  }, [code, dirty, suite, isHistorical]);

  const handleVersionChange = (versionId: string) => {
    if (dirty && !confirm("Discard unsaved changes and switch version?")) return;
    router.push(`/dashboard/code-review/${versionId}`);
  };

  const handleSaveAsNewVersion = async () => {
    if (!suite) return;
    setIsWorking(true);
    setError(null);
    try {
      const created = await saveTestSuiteAsNewVersion(suite.id, code);
      router.push(`/dashboard/code-review/${created.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save new version");
    } finally {
      setIsWorking(false);
    }
  };

  const handleRestore = async () => {
    if (!suite) return;
    if (
      !confirm(
        `Restore v${suite.version} as a new head version? The current code becomes the new head; history stays intact.`,
      )
    ) {
      return;
    }
    setIsWorking(true);
    setError(null);
    try {
      const restored = await restoreTestSuiteVersion(suite.id);
      router.push(`/dashboard/code-review/${restored.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to restore version");
    } finally {
      setIsWorking(false);
    }
  };

  const handleSelectForRun = async () => {
    if (!suite || !suite.is_active) return;
    setIsWorking(true);
    setError(null);
    try {
      const updated = await selectTestSuiteForRun(suite.id);
      setSuite(updated);
      setActiveHead(updated);
      setHistory((prev) => prev.map((r) => (r.id === updated.id ? updated : r)));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to select for run");
    } finally {
      setIsWorking(false);
    }
  };

  const handleCopy = async () => {
    await navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  const handleDownload = () => {
    if (!suite) return;
    const blob = new Blob([code], { type: "text/plain" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = suite.filename;
    a.click();
  };

  const handleGoRun = () => {
    if (!suite || !suite.selected_for_run) return;
    const qs = new URLSearchParams({
      suite: suite.id,
      framework: suite.framework,
    });
    router.push(`/dashboard/execution?${qs.toString()}`);
  };

  if (isLoading) {
    return (
      <div className="h-screen bg-slate-900 text-slate-300 flex items-center justify-center">
        <Loader2 className="w-5 h-5 animate-spin mr-2" />
        Loading suite…
      </div>
    );
  }

  if (!suite) {
    return (
      <div className="h-screen bg-slate-900 text-slate-300 flex flex-col items-center justify-center gap-3">
        <p>{error ?? "Suite not found."}</p>
        <Link
          href="/dashboard/code-review"
          className="text-purple-400 hover:text-purple-300 text-sm"
        >
          Back to Code Review
        </Link>
      </div>
    );
  }

  return (
    <div className="h-screen flex flex-col bg-slate-900 text-slate-100">
      {/* Top bar */}
      <div className="flex items-center gap-3 px-5 py-3 border-b border-slate-700 bg-slate-800">
        <Link
          href="/dashboard/code-review"
          className="flex items-center gap-1.5 text-slate-300 hover:text-white text-sm"
        >
          <ChevronLeft className="w-4 h-4" />
          Suites
        </Link>

        <div className="h-5 w-px bg-slate-700 mx-2" />

        <span className="text-sm font-mono text-slate-200">{suite.filename}</span>
        <span className="text-[10px] text-slate-400 uppercase tracking-wider">
          {suite.framework} · {suite.language}
        </span>

        {/* Version dropdown */}
        <div className="ml-4 flex items-center gap-2">
          <GitBranch className="w-3.5 h-3.5 text-slate-400" />
          <select
            value={suite.id}
            onChange={(e) => handleVersionChange(e.target.value)}
            className="bg-slate-700 border border-slate-600 text-slate-200 text-xs rounded px-2 py-1 focus:outline-none focus:ring-1 focus:ring-purple-500"
          >
            {history.map((row) => (
              <option key={row.id} value={row.id}>
                v{row.version} {row.is_active ? "(current)" : ""}{" "}
                · {formatRelative(row.updated_at)}
              </option>
            ))}
          </select>
          <span className="text-[10px] text-slate-500">
            {history.length} version{history.length === 1 ? "" : "s"}
          </span>
        </div>

        {/* Autosave indicator */}
        {!isHistorical && (
          <div className="ml-3 text-[11px] text-slate-400 flex items-center gap-1.5 min-w-[80px]">
            {savingStatus === "saving" && (
              <>
                <Loader2 className="w-3 h-3 animate-spin" />
                Saving…
              </>
            )}
            {savingStatus === "saved" && (
              <>
                <CheckCircle2 className="w-3 h-3 text-emerald-400" />
                Saved
              </>
            )}
            {savingStatus === "idle" && dirty && (
              <span className="text-amber-400">Unsaved</span>
            )}
          </div>
        )}

        <div className="ml-auto flex items-center gap-2">
          {suite.selected_for_run && (
            <button
              onClick={handleGoRun}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-purple-600 hover:bg-purple-700 text-white text-xs font-medium rounded transition-all"
            >
              <PlayCircle className="w-3.5 h-3.5" />
              Run via GitHub Actions
            </button>
          )}
          {!suite.selected_for_run && suite.is_active && (
            <button
              onClick={handleSelectForRun}
              disabled={isWorking}
              className="flex items-center gap-1.5 px-3 py-1.5 border border-slate-600 hover:border-purple-500 hover:bg-slate-700 text-slate-200 text-xs font-medium rounded transition-all disabled:opacity-50"
            >
              <Sparkles className="w-3.5 h-3.5" />
              Set Active for Run
            </button>
          )}

          {isHistorical ? (
            <button
              onClick={handleRestore}
              disabled={isWorking}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-amber-600 hover:bg-amber-700 text-white text-xs font-medium rounded transition-all disabled:opacity-50"
              title="Copy this version's code to a new head version"
            >
              {isWorking ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <RotateCcw className="w-3.5 h-3.5" />
              )}
              Restore as new version
            </button>
          ) : (
            <button
              onClick={handleSaveAsNewVersion}
              disabled={isWorking}
              className="flex items-center gap-1.5 px-3 py-1.5 border border-slate-600 hover:border-slate-500 hover:bg-slate-700 text-slate-200 text-xs font-medium rounded transition-all disabled:opacity-50"
              title={`Snapshot current code as v${(activeHead?.version ?? suite.version) + 1}`}
            >
              {isWorking ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Save className="w-3.5 h-3.5" />
              )}
              Save as new version
            </button>
          )}

          <button
            onClick={handleCopy}
            className="flex items-center gap-1.5 px-2.5 py-1.5 text-slate-300 hover:text-white hover:bg-slate-700 text-xs rounded transition-all"
          >
            {copied ? (
              <>
                <Check className="w-3.5 h-3.5 text-emerald-400" /> Copied
              </>
            ) : (
              <>
                <Copy className="w-3.5 h-3.5" /> Copy
              </>
            )}
          </button>
          <button
            onClick={handleDownload}
            className="flex items-center gap-1.5 px-2.5 py-1.5 text-slate-300 hover:text-white hover:bg-slate-700 text-xs rounded transition-all"
          >
            <Download className="w-3.5 h-3.5" />
            Download
          </button>
        </div>
      </div>

      {/* Status row */}
      <div className="flex items-center gap-3 px-5 py-1.5 bg-slate-800 border-b border-slate-700 text-[11px]">
        <span className="inline-flex items-center gap-1 text-slate-300 font-mono bg-slate-700 px-1.5 py-0.5 rounded">
          <GitBranch className="w-3 h-3" /> v{suite.version}
        </span>
        {suite.is_active ? (
          <span className="text-emerald-400">Head (current)</span>
        ) : (
          <span className="text-amber-400 inline-flex items-center gap-1">
            <History className="w-3 h-3" /> Historical — read-only
          </span>
        )}
        {suite.selected_for_run && (
          <span className="text-purple-300 inline-flex items-center gap-1">
            <CheckCircle2 className="w-3 h-3" /> Selected for run
          </span>
        )}
        <span className="text-slate-400 ml-auto">
          {suite.source_scenario_count} scenario
          {suite.source_scenario_count === 1 ? "" : "s"} · saved{" "}
          {formatRelative(suite.updated_at)}
        </span>
      </div>

      {/* Stale banner */}
      {suite.is_stale && suite.is_active && (
        <div className="px-5 py-2 bg-amber-900/30 border-b border-amber-800/40 text-amber-200 text-xs flex items-center gap-2">
          <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
          Gherkin scenarios or DOM elements have changed since this version was generated.
          Regenerate from the Suites page to refresh.
        </div>
      )}

      {error && (
        <div className="px-5 py-2 bg-red-900/30 border-b border-red-800/40 text-red-200 text-xs">
          {error}
        </div>
      )}

      {/* Editor */}
      <div className="flex-1 min-h-0">
        <MonacoEditor
          height="100%"
          language={suite.language}
          theme="vs-dark"
          value={code}
          onChange={(value) => {
            setCode(value ?? "");
            if (!isHistorical) setDirty(true);
          }}
          options={{
            readOnly: isHistorical,
            fontSize: 13,
            lineHeight: 22,
            minimap: { enabled: true },
            wordWrap: "off",
            scrollBeyondLastLine: false,
            padding: { top: 12 },
            fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
            fontLigatures: true,
            automaticLayout: true,
          }}
        />
      </div>
    </div>
  );
}
