"use client";

import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import DashboardLayoutWrapper from "@/components/dashboard-layout-wrapper";
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from "recharts";
import {
  AlertTriangle,
  CheckCircle,
  ChevronLeft,
  Clock,
  Download,
  ExternalLink,
  FileText,
  GitBranch,
  Image as ImageIcon,
  Loader2,
  PlayCircle,
  RotateCcw,
  Terminal,
  XCircle,
  Zap,
} from "lucide-react";
import {
  executeSuite,
  getRun,
  getTestSuites,
  openExecutionStream,
  runLogUrl,
  runPdfUrl,
  type ExecutionEvent,
  type RunDetail,
  type RunScreenshot,
  type TestSuite,
} from "@/lib/api";
import { useProject } from "@/lib/project-context";

type Status = "idle" | "queued" | "running" | "passed" | "failed" | "error";

interface LiveLog {
  ts: number;
  kind: "step" | "log" | "info";
  step?: string;
  line?: string;
  status?: string;
}

const statusIcon = (status: string | undefined) => {
  if (status === "passed" || status === "success") return <CheckCircle className="w-3.5 h-3.5 text-emerald-600" />;
  if (status === "failed" || status === "failure") return <XCircle className="w-3.5 h-3.5 text-red-600" />;
  if (status === "running") return <Clock className="w-3.5 h-3.5 text-blue-600 animate-pulse" />;
  return <Terminal className="w-3.5 h-3.5 text-slate-500" />;
};

function ExecutionContent() {
  const searchParams = useSearchParams();
  const { activeProject } = useProject();
  const suiteIdParam = searchParams.get("suite") || "";
  const frameworkParam = searchParams.get("framework") || "";

  const [selectedSuite, setSelectedSuite] = useState<TestSuite | null>(null);
  const [suiteLoading, setSuiteLoading] = useState(false);
  const [suiteError, setSuiteError] = useState<string | null>(null);

  const [runId, setRunId] = useState<string | null>(null);
  const [runMode, setRunMode] = useState<string | null>(null);
  const [runDetail, setRunDetail] = useState<RunDetail | null>(null);
  const [logs, setLogs] = useState<LiveLog[]>([]);
  const [status, setStatus] = useState<Status>("idle");
  const [error, setError] = useState<string | null>(null);
  const [pdfReady, setPdfReady] = useState(false);
  const [ghRunUrl, setGhRunUrl] = useState<string | null>(null);

  const logRef = useRef<HTMLDivElement>(null);
  const wsRef = useRef<WebSocket | null>(null);

  // Load the suite metadata up front so we can show the user what's about to run.
  useEffect(() => {
    if (!activeProject || !suiteIdParam) return;
    let cancelled = false;
    setSuiteLoading(true);
    setSuiteError(null);
    getTestSuites(activeProject.id)
      .then((suites) => {
        if (cancelled) return;
        const match = suites.find((s) => s.id === suiteIdParam);
        if (match) setSelectedSuite(match);
        else if (frameworkParam) {
          // Suite id stale — fall back to the active suite for that framework.
          const fallback = suites.find((s) => s.framework === frameworkParam);
          if (fallback) setSelectedSuite(fallback);
        }
      })
      .catch((e) => setSuiteError(e instanceof Error ? e.message : "Failed to load suite"))
      .finally(() => {
        if (!cancelled) setSuiteLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [activeProject, suiteIdParam, frameworkParam]);

  // Auto-scroll the live log.
  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [logs]);

  // Cleanup WS on unmount.
  useEffect(() => () => { wsRef.current?.close(); }, []);

  const fetchRunDetail = useCallback(async (id: string) => {
    try {
      const detail = await getRun(id);
      setRunDetail(detail);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load run details");
    }
  }, []);

  const handleEvent = useCallback((evt: ExecutionEvent) => {
    if (evt.type === "step") {
      setLogs((prev) => [...prev, {
        ts: Date.now(), kind: "step", step: evt.step, status: evt.status,
      }]);
    } else if (evt.type === "log") {
      setLogs((prev) => [...prev, { ts: Date.now(), kind: "log", line: evt.line }]);
    } else if (evt.type === "github") {
      setGhRunUrl(evt.run_url);
      setLogs((prev) => [...prev, {
        ts: Date.now(), kind: "info",
        step: `GitHub Actions run started — branch ${evt.branch}`,
      }]);
    } else if (evt.type === "pdf_ready") {
      setPdfReady(true);
      setLogs((prev) => [...prev, {
        ts: Date.now(), kind: "info", step: "PDF report ready",
      }]);
    } else if (evt.type === "done") {
      const final = evt.status === "passed" ? "passed" : evt.status === "failed" ? "failed" : "error";
      setStatus(final);
      if (runId) void fetchRunDetail(runId);
    } else if (evt.type === "error") {
      setStatus("error");
      setError(evt.message);
    }
  }, [runId, fetchRunDetail]);

  const startRun = useCallback(async () => {
    if (!selectedSuite || !activeProject) return;
    setLogs([]);
    setRunDetail(null);
    setPdfReady(false);
    setGhRunUrl(null);
    setError(null);
    setStatus("queued");

    try {
      const resp = await executeSuite({
        suiteId: selectedSuite.id,
        projectId: activeProject.id,
      });
      setRunId(resp.run_id);
      setRunMode(resp.mode);
      setStatus("running");

      // Open the live stream.
      wsRef.current?.close();
      wsRef.current = openExecutionStream(resp.run_id, handleEvent);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to start run");
      setStatus("error");
    }
  }, [selectedSuite, activeProject, handleEvent]);

  const resetRun = () => {
    wsRef.current?.close();
    setRunId(null);
    setRunDetail(null);
    setLogs([]);
    setStatus("idle");
    setError(null);
    setPdfReady(false);
    setGhRunUrl(null);
  };

  const isDone = status === "passed" || status === "failed" || status === "error";
  const isBusy = status === "queued" || status === "running";

  const summary = useMemo(() => {
    if (!runDetail) return null;
    const total = runDetail.total_count;
    const passed = runDetail.passed_count;
    const failed = runDetail.failed_count;
    return {
      total,
      passed,
      failed,
      successRate: total ? Math.round((passed / total) * 100) : 0,
      durationSec: runDetail.duration_ms ? (runDetail.duration_ms / 1000).toFixed(1) : "—",
    };
  }, [runDetail]);

  const chartData = useMemo(
    () => summary
      ? [
          { name: "Passed", value: summary.passed, color: "#10b981" },
          { name: "Failed", value: summary.failed, color: "#ef4444" },
        ].filter((d) => d.value > 0)
      : [],
    [summary],
  );

  return (
    <DashboardLayoutWrapper>
      {/* Header */}
      <div className="sticky top-0 z-10 bg-white/80 backdrop-blur-sm border-b border-slate-200 px-8 py-5">
        <div className="flex justify-between items-center">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="text-xs font-bold text-purple-700 bg-purple-50 border border-purple-200 px-2 py-0.5 rounded-full tracking-wider">
                S6
              </span>
              <span className="text-xs text-slate-500">Pipeline Stage 6 of 6</span>
            </div>
            <h1 className="text-2xl font-bold text-slate-900">Execution &amp; Report</h1>
            <p className="text-slate-600 text-sm mt-0.5">
              Run the selected suite · Live log streamed via WebSocket · Raw log saved to DB · PDF report on completion
            </p>
          </div>
          <div className="flex items-center gap-3">
            <Link
              href="/dashboard/code-review"
              className="flex items-center gap-2 px-4 py-2 border border-slate-300 text-slate-600 hover:text-slate-900 hover:border-slate-400 hover:bg-slate-50 rounded-lg text-sm transition-all"
            >
              <ChevronLeft className="w-4 h-4" />
              Back
            </Link>
            {isDone && (
              <button
                onClick={resetRun}
                className="flex items-center gap-2 px-4 py-2 border border-slate-300 text-slate-600 hover:text-slate-900 hover:bg-slate-50 rounded-lg text-sm transition-all"
              >
                <RotateCcw className="w-4 h-4" />
                Reset
              </button>
            )}
            <button
              onClick={startRun}
              disabled={!selectedSuite || isBusy}
              className={`flex items-center gap-2 px-6 py-2.5 rounded-lg font-semibold text-sm transition-all ${
                isBusy
                  ? "bg-slate-200 text-slate-500 cursor-not-allowed"
                  : !selectedSuite
                  ? "bg-slate-200 text-slate-400 cursor-not-allowed"
                  : "bg-linear-to-r from-purple-600 to-indigo-600 hover:from-purple-700 hover:to-indigo-700 text-white shadow-lg shadow-purple-600/30"
              }`}
            >
              {isBusy ? (
                <><Clock className="w-4 h-4 animate-spin" /> Running…</>
              ) : (
                <><Zap className="w-4 h-4" /> Run Tests</>
              )}
            </button>
          </div>
        </div>
      </div>

      {/* Suite info bar */}
      <div className="mx-6 mt-4 flex items-center gap-3 text-xs">
        {suiteLoading ? (
          <span className="text-slate-500"><Loader2 className="w-3 h-3 inline animate-spin mr-1" />Loading suite…</span>
        ) : suiteError ? (
          <span className="text-red-600">{suiteError}</span>
        ) : !selectedSuite ? (
          <span className="text-amber-700">
            No suite selected. Go to{" "}
            <Link href="/dashboard/code-review" className="underline">Code Review</Link>{" "}
            and pick a framework first.
          </span>
        ) : (
          <>
            <span className="px-2 py-0.5 rounded bg-purple-50 text-purple-700 border border-purple-200 font-semibold">
              {selectedSuite.framework} v{selectedSuite.version}
            </span>
            <span className="font-mono text-slate-600">{selectedSuite.filename}</span>
            <span className="text-slate-400">·</span>
            <span className="text-slate-500">{selectedSuite.url}</span>
            {runMode && (
              <span className="ml-auto px-2 py-0.5 rounded bg-slate-100 text-slate-600 border border-slate-200">
                Runner: {runMode === "github" ? (
                  <span className="inline-flex items-center gap-1"><GitBranch className="w-3 h-3" /> GitHub Actions</span>
                ) : "Local Playwright"}
              </span>
            )}
          </>
        )}
      </div>

      {error && (
        <div className="mx-6 mt-3 p-3 bg-red-50 text-red-600 text-sm rounded border border-red-200">
          {error}
        </div>
      )}

      <div className="p-6 grid grid-cols-3 gap-5">
        {/* Left: Log + Screenshots */}
        <div className="col-span-2 flex flex-col gap-5">
          {/* Live Log */}
          <div className="rounded-xl border border-slate-200 overflow-hidden bg-white shadow-sm">
            <div className="flex items-center justify-between px-4 py-3 border-b border-slate-200 bg-slate-50">
              <div className="flex items-center gap-2">
                <Terminal className="w-4 h-4 text-purple-600" />
                <p className="text-sm font-semibold text-slate-800">Live Execution Log</p>
                {status === "running" && (
                  <span className="flex items-center gap-1.5 text-xs text-blue-600">
                    <span className="w-1.5 h-1.5 rounded-full bg-blue-500 animate-pulse" />
                    Streaming via WebSocket
                  </span>
                )}
                {ghRunUrl && (
                  <a
                    href={ghRunUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="ml-2 inline-flex items-center gap-1 text-xs text-purple-700 hover:text-purple-900 underline"
                  >
                    <GitBranch className="w-3 h-3" /> Open on GitHub
                    <ExternalLink className="w-3 h-3" />
                  </a>
                )}
              </div>
              <span className="text-xs text-slate-500">
                {logs.length} event{logs.length === 1 ? "" : "s"}
              </span>
            </div>
            <div
              ref={logRef}
              className="h-72 overflow-y-auto p-4 font-mono text-xs space-y-1 bg-slate-50/40"
              style={{ scrollbarWidth: "none" }}
            >
              {status === "idle" && (
                <p className="text-slate-400 italic">Press Run Tests to start execution…</p>
              )}
              {logs.map((log, i) => (
                <div key={i} className="flex items-start gap-2.5 group">
                  <span className="mt-0.5 shrink-0">{statusIcon(log.status)}</span>
                  <span
                    className={`flex-1 break-all ${
                      log.status === "failed"
                        ? "text-red-600"
                        : log.status === "passed"
                        ? "text-slate-700"
                        : log.kind === "log"
                        ? "text-slate-500"
                        : "text-slate-700"
                    }`}
                  >
                    {log.step || log.line}
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* Screenshots */}
          {isDone && runDetail && runDetail.screenshots.length > 0 && (
            <ScreenshotGrid screenshots={runDetail.screenshots} />
          )}

          {/* Failed test AI explanation */}
          {isDone && runDetail && runDetail.failed_count > 0 && (
            <div className="rounded-xl border border-amber-200 bg-amber-50 p-4">
              <div className="flex items-center gap-2 mb-2">
                <AlertTriangle className="w-3.5 h-3.5 text-amber-600" />
                <p className="text-xs font-semibold text-amber-800">AI Failure Summary</p>
              </div>
              <p className="text-xs text-slate-700 leading-relaxed">
                {runDetail.failed_count} scenario
                {runDetail.failed_count === 1 ? "" : "s"} failed. Open the raw log for the full
                stack trace; C3 Self-Healing will analyse the broken selectors and propose fixes.
              </p>
              {runDetail.scenarios.filter((s) => s.status === "failed").slice(0, 3).map((s) => (
                <p key={s.scenario_name} className="text-[11px] text-amber-900 mt-1 font-mono">
                  • {s.scenario_name}
                </p>
              ))}
            </div>
          )}
        </div>

        {/* Right: Stats + Chart + Report */}
        <div className="flex flex-col gap-4">
          {/* Summary Stats */}
          <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-widest mb-4">
              Run Summary
            </p>
            <div className="space-y-3">
              {[
                { label: "Status",       value: runDetail ? runDetail.status.toUpperCase() : status.toUpperCase(), color: statusColor(runDetail?.status ?? status) },
                { label: "Total Tests",  value: summary ? String(summary.total) : "—",   color: "text-slate-900" },
                { label: "Passed",       value: summary ? String(summary.passed) : "—",  color: "text-emerald-700" },
                { label: "Failed",       value: summary ? String(summary.failed) : "—",  color: "text-red-700" },
                { label: "Success Rate", value: summary ? `${summary.successRate}%` : "—", color: "text-purple-700" },
                { label: "Duration",     value: summary ? `${summary.durationSec}s` : "—", color: "text-slate-700" },
                { label: "Framework",    value: selectedSuite?.framework ?? "—",   color: "text-emerald-700" },
              ].map((s) => (
                <div key={s.label} className="flex items-center justify-between">
                  <span className="text-xs text-slate-500">{s.label}</span>
                  <span className={`text-sm font-bold ${s.color}`}>{s.value}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Donut chart */}
          {summary && chartData.length > 0 && (
            <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
              <p className="text-xs font-semibold text-slate-500 uppercase tracking-widest mb-3">
                Pass / Fail Chart
              </p>
              <ResponsiveContainer width="100%" height={160}>
                <PieChart>
                  <Pie
                    data={chartData}
                    cx="50%"
                    cy="50%"
                    innerRadius={45}
                    outerRadius={70}
                    paddingAngle={3}
                    dataKey="value"
                  >
                    {chartData.map((entry, i) => (
                      <Cell key={i} fill={entry.color} />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{ background: "#ffffff", border: "1px solid #e2e8f0", borderRadius: 8 }}
                    labelStyle={{ color: "#475569" }}
                    itemStyle={{ color: "#0f172a" }}
                  />
                </PieChart>
              </ResponsiveContainer>
              <div className="flex justify-center gap-5 mt-1">
                {chartData.map((d) => (
                  <div key={d.name} className="flex items-center gap-1.5 text-xs text-slate-600">
                    <span className="w-2.5 h-2.5 rounded-full" style={{ background: d.color }} />
                    {d.name}: <span className="text-slate-900 font-semibold">{d.value}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Download PDF + Log */}
          {runId && (
            <div className="flex flex-col gap-2">
              <a
                href={runPdfUrl(runId)}
                target="_blank"
                rel="noreferrer"
                aria-disabled={!pdfReady}
                onClick={(e) => { if (!pdfReady) e.preventDefault(); }}
                className={`w-full flex items-center justify-center gap-2 py-3 border rounded-xl text-sm font-medium transition-all shadow-sm ${
                  pdfReady
                    ? "bg-purple-600 hover:bg-purple-700 border-purple-700 text-white"
                    : "bg-white border-slate-200 text-slate-400 cursor-not-allowed"
                }`}
              >
                <FileText className="w-4 h-4" />
                {pdfReady ? "Download PDF Report" : "PDF generating…"}
              </a>
              <a
                href={runLogUrl(runId)}
                target="_blank"
                rel="noreferrer"
                className="w-full flex items-center justify-center gap-2 py-2.5 bg-white hover:bg-slate-50 border border-slate-300 hover:border-slate-400 text-slate-700 hover:text-slate-900 rounded-xl text-sm font-medium transition-all shadow-sm"
              >
                <Download className="w-4 h-4" />
                Download Raw Log (saved in DB)
              </a>
            </div>
          )}

          {/* Pipeline complete */}
          {isDone && status === "passed" && (
            <div className="p-4 bg-emerald-50 border border-emerald-200 rounded-xl text-center">
              <CheckCircle className="w-6 h-6 text-emerald-600 mx-auto mb-2" />
              <p className="text-xs font-semibold text-emerald-800">Pipeline Complete</p>
              <p className="text-[11px] text-slate-600 mt-1">
                Results, log, and screenshots written to PostgreSQL · C3 &amp; C4 notified
              </p>
              <Link
                href="/dashboard"
                className="inline-flex items-center gap-1.5 mt-3 text-xs text-purple-700 hover:text-purple-800 transition-colors"
              >
                <PlayCircle className="w-3.5 h-3.5" />
                Start new pipeline
              </Link>
            </div>
          )}
        </div>
      </div>
    </DashboardLayoutWrapper>
  );
}

function statusColor(status: string): string {
  if (status === "passed") return "text-emerald-700";
  if (status === "failed") return "text-red-700";
  if (status === "error")  return "text-amber-700";
  if (status === "running" || status === "queued") return "text-blue-700";
  return "text-slate-700";
}

function ScreenshotGrid({ screenshots }: { screenshots: RunScreenshot[] }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white overflow-hidden shadow-sm">
      <div className="flex items-center justify-between px-4 py-3 border-b border-slate-200 bg-slate-50">
        <div className="flex items-center gap-2">
          <ImageIcon className="w-4 h-4 text-purple-600" />
          <p className="text-sm font-semibold text-slate-800">Captured Screenshots</p>
        </div>
        <span className="text-xs text-slate-500">{screenshots.length} frame{screenshots.length === 1 ? "" : "s"}</span>
      </div>
      <div className="p-4 grid grid-cols-3 gap-3">
        {screenshots.map((s) => (
          <div
            key={s.scenario}
            className={`rounded-lg border overflow-hidden ${
              s.status === "failed" ? "border-red-300" : "border-slate-200"
            }`}
          >
            {/* Use <img> not Next/Image so the backend-served PNG works without
                Next.js needing a remotePattern allow-list. */}
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={s.image_url}
              alt={s.label}
              className="w-full h-28 object-cover bg-slate-50"
            />
            <div className="px-2.5 py-2 bg-white flex items-center justify-between">
              <p className="text-[11px] text-slate-600 truncate">{s.label}</p>
              {s.status === "passed" ? (
                <CheckCircle className="w-3.5 h-3.5 text-emerald-600 shrink-0" />
              ) : (
                <XCircle className="w-3.5 h-3.5 text-red-600 shrink-0" />
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function ExecutionPage() {
  return (
    <Suspense fallback={<div className="p-8">Loading Execution…</div>}>
      <ExecutionContent />
    </Suspense>
  );
}
