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
  GitBranch,
  Image as ImageIcon,
  Loader2,
  MinusCircle,
  Plug,
  Server,
  Terminal,
  XCircle,
  Zap,
} from "lucide-react";
import {
  executeSuite,
  getGitHubConnection,
  getRun,
  getTestSuites,
  openExecutionStream,
  runLatestFrameUrl,
  runLogUrl,
  type ExecutionEvent,
  type GitHubConnection,
  type RunDetail,
  type RunScreenshot,
  type TestSuite,
} from "@/lib/api";
import { useProject } from "@/lib/project-context";

type RunMode = "local" | "github";
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
  if (status === "skipped" || status === "cancelled") return <MinusCircle className="w-3.5 h-3.5 text-slate-400" />;
  return <Terminal className="w-3.5 h-3.5 text-slate-500" />;
};

function statusColor(status: string): string {
  if (status === "passed") return "text-emerald-700";
  if (status === "failed") return "text-red-700";
  if (status === "error")  return "text-amber-700";
  if (status === "running" || status === "queued") return "text-blue-700";
  return "text-slate-700";
}

function ExecutionContent() {
  const searchParams = useSearchParams();
  const { activeProject } = useProject();
  const suiteIdParam = searchParams.get("suite") || "";
  const frameworkParam = searchParams.get("framework") || "";

  const [selectedSuite, setSelectedSuite] = useState<TestSuite | null>(null);
  const [suiteLoading, setSuiteLoading] = useState(false);
  const [suiteError, setSuiteError] = useState<string | null>(null);

  const [ghConnection, setGhConnection] = useState<GitHubConnection | null>(null);
  const [ghLoading, setGhLoading] = useState(false);

  // Each runner panel pushes its detail back here when its run finishes so
  // the bottom summary strip can render side-by-side numbers.
  const [localSummary, setLocalSummary] = useState<RunDetail | null>(null);
  const [githubSummary, setGithubSummary] = useState<RunDetail | null>(null);

  // Incremented by the "Run Both" header button — both panels watch this
  // key and fire their own runs in parallel when it changes.
  const [runBothKey, setRunBothKey] = useState(0);
  const handleRunBoth = useCallback(() => setRunBothKey((k) => k + 1), []);

  // Load the suite metadata up front so both panels know what's about to run.
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
          const fallback = suites.find((s) => s.framework === frameworkParam);
          if (fallback) setSelectedSuite(fallback);
        }
      })
      .catch((e) => setSuiteError(e instanceof Error ? e.message : "Failed to load suite"))
      .finally(() => {
        if (!cancelled) setSuiteLoading(false);
      });
    return () => { cancelled = true; };
  }, [activeProject, suiteIdParam, frameworkParam]);

  // Load the GitHub connection so the GitHub panel knows whether to show the
  // run button or the "Connect first" CTA.
  useEffect(() => {
    if (!activeProject) return;
    let cancelled = false;
    setGhLoading(true);
    getGitHubConnection(activeProject.id)
      .then((c) => { if (!cancelled) setGhConnection(c); })
      .catch(() => { if (!cancelled) setGhConnection(null); })
      .finally(() => { if (!cancelled) setGhLoading(false); });
    return () => { cancelled = true; };
  }, [activeProject]);

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
              Run the same suite locally or via GitHub Actions · Raw log + PDF saved to DB per run
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
            <button
              onClick={handleRunBoth}
              disabled={!selectedSuite || !activeProject}
              className="flex items-center gap-2 px-5 py-2.5 rounded-lg font-semibold text-sm transition-all bg-linear-to-r from-purple-600 to-indigo-600 hover:from-purple-700 hover:to-indigo-700 text-white shadow-lg shadow-purple-600/30 disabled:opacity-40 disabled:cursor-not-allowed disabled:shadow-none"
              title="Trigger both runners in parallel"
            >
              <Zap className="w-4 h-4" />
              Run Both
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
          </>
        )}
      </div>

      {/* Two runner panels side by side */}
      <div className="px-6 pt-5 grid grid-cols-2 gap-5">
        <RunnerPanel
          mode="local"
          suite={selectedSuite}
          projectId={activeProject?.id ?? null}
          onSummary={setLocalSummary}
          runTriggerKey={runBothKey}
        />
        <RunnerPanel
          mode="github"
          suite={selectedSuite}
          projectId={activeProject?.id ?? null}
          ghConnection={ghConnection}
          ghLoading={ghLoading}
          onSummary={setGithubSummary}
          runTriggerKey={runBothKey}
        />
      </div>

      {/* Summary strip BELOW the two panels */}
      <SummaryStrip local={localSummary} github={githubSummary} />
    </DashboardLayoutWrapper>
  );
}

// ─── RunnerPanel — one column per mode ──────────────────────────────────────

interface RunnerPanelProps {
  mode: RunMode;
  suite: TestSuite | null;
  projectId: string | null;
  ghConnection?: GitHubConnection | null;
  ghLoading?: boolean;
  onSummary: (detail: RunDetail | null) => void;
  /**
   * Incremented by the parent's "Run Both" button. When it changes, the
   * panel fires its run automatically (alongside its own header button).
   * Initial value 0 is ignored.
   */
  runTriggerKey?: number;
}

function RunnerPanel({ mode, suite, projectId, ghConnection, ghLoading, onSummary, runTriggerKey }: RunnerPanelProps) {
  const [runId, setRunId] = useState<string | null>(null);
  const [status, setStatus] = useState<Status>("idle");
  const [logs, setLogs] = useState<LiveLog[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [pdfReady, setPdfReady] = useState(false);
  const [ghRunUrl, setGhRunUrl] = useState<string | null>(null);
  const [runDetail, setRunDetail] = useState<RunDetail | null>(null);

  const [livePreviewSrc, setLivePreviewSrc] = useState<string | null>(null);
  const [livePreviewLoaded, setLivePreviewLoaded] = useState(false);

  const logRef = useRef<HTMLDivElement>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const livePollTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  // Bubble summary up whenever the local detail changes.
  useEffect(() => { onSummary(runDetail); }, [runDetail, onSummary]);

  // Cleanup WS on unmount.
  useEffect(() => () => { wsRef.current?.close(); }, []);

  // Auto-scroll the live log.
  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [logs]);

  // Live preview poller for this panel.
  useEffect(() => {
    if (!runId || (status !== "running" && status !== "queued")) {
      if (livePollTimer.current) {
        clearInterval(livePollTimer.current);
        livePollTimer.current = null;
      }
      return;
    }
    const tick = () => setLivePreviewSrc(`${runLatestFrameUrl(runId)}?t=${Date.now()}`);
    tick();
    livePollTimer.current = setInterval(tick, 600);
    return () => {
      if (livePollTimer.current) {
        clearInterval(livePollTimer.current);
        livePollTimer.current = null;
      }
    };
  }, [runId, status]);

  // One final preview pull after completion.
  useEffect(() => {
    if (!runId) return;
    if (status === "passed" || status === "failed" || status === "error") {
      setLivePreviewSrc(`${runLatestFrameUrl(runId)}?t=${Date.now()}`);
    }
  }, [runId, status]);

  const fetchRunDetail = useCallback(async (id: string) => {
    try {
      const d = await getRun(id);
      setRunDetail(d);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load run details");
    }
  }, []);

  const handleEvent = useCallback((evt: ExecutionEvent) => {
    if (evt.type === "step") {
      // Dedupe by step text — replace any prior row with the same name.
      setLogs((prev) => {
        const incoming: LiveLog = {
          ts: Date.now(), kind: "step", step: evt.step, status: evt.status,
        };
        const i = prev.findIndex((e) => e.kind === "step" && e.step === evt.step);
        if (i === -1) return [...prev, incoming];
        const next = prev.slice();
        next[i] = incoming;
        return next;
      });
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
    if (!suite || !projectId) return;
    // Guard: if this is the GitHub panel and no connection exists, skip
    // silently so the parent's "Run Both" button can still fire local.
    if (mode === "github" && !ghConnection) return;
    setLogs([]);
    setRunDetail(null);
    setPdfReady(false);
    setGhRunUrl(null);
    setError(null);
    setLivePreviewSrc(null);
    setLivePreviewLoaded(false);
    setStatus("queued");
    try {
      const resp = await executeSuite({
        suiteId: suite.id,
        projectId,
        mode,                                  // force THIS panel's mode
      });
      setRunId(resp.run_id);
      setStatus("running");
      wsRef.current?.close();
      wsRef.current = openExecutionStream(resp.run_id, handleEvent);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to start run");
      setStatus("error");
    }
  }, [suite, projectId, mode, ghConnection, handleEvent]);

  // Parent's "Run Both" button bumps runTriggerKey. Fire startRun whenever
  // it changes (skip initial 0/undefined). Both panels watch the same key
  // so a single click kicks off both modes in parallel.
  useEffect(() => {
    if (!runTriggerKey || runTriggerKey === 0) return;
    void startRun();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runTriggerKey]);

  const resetRun = () => {
    wsRef.current?.close();
    setRunId(null);
    setLogs([]);
    setStatus("idle");
    setError(null);
    setPdfReady(false);
    setGhRunUrl(null);
    setLivePreviewSrc(null);
    setLivePreviewLoaded(false);
    setRunDetail(null);
  };

  const isDone = status === "passed" || status === "failed" || status === "error";
  const isBusy = status === "queued" || status === "running";

  // ── Header colours per mode ──────────────────────────────────────────────
  const accent =
    mode === "local"
      ? { bg: "from-emerald-600 to-teal-600", chip: "bg-emerald-50 text-emerald-700 border-emerald-200", icon: <Server className="w-4 h-4" />, name: "Local Playwright" }
      : { bg: "from-purple-600 to-indigo-600", chip: "bg-purple-50 text-purple-700 border-purple-200", icon: <GitBranch className="w-4 h-4" />, name: "GitHub Actions" };

  // ── GitHub-not-connected CTA ─────────────────────────────────────────────
  const ghNotConnected = mode === "github" && !ghConnection && !ghLoading;

  return (
    <div className="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden flex flex-col">
      {/* Panel header */}
      <div className={`px-4 py-3 bg-linear-to-r ${accent.bg} text-white flex items-center justify-between`}>
        <div className="flex items-center gap-2">
          <span className="opacity-90">{accent.icon}</span>
          <p className="text-sm font-bold tracking-wide">{accent.name}</p>
          <span className="text-[10px] uppercase tracking-widest px-1.5 py-0.5 rounded bg-white/15">
            {mode}
          </span>
        </div>
        <div className="flex items-center gap-2">
          {ghRunUrl && (
            <a
              href={ghRunUrl}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1 text-[11px] underline hover:no-underline"
            >
              Open on GitHub <ExternalLink className="w-3 h-3" />
            </a>
          )}
          {isDone && (
            <button
              onClick={resetRun}
              className="text-[11px] px-2 py-1 rounded bg-white/15 hover:bg-white/25 transition-all"
            >
              Reset
            </button>
          )}
          <button
            onClick={startRun}
            disabled={!suite || !projectId || isBusy || ghNotConnected}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-white text-slate-900 text-xs font-semibold rounded-md hover:bg-slate-100 disabled:opacity-40 disabled:cursor-not-allowed transition-all"
          >
            {isBusy ? (
              <><Clock className="w-3.5 h-3.5 animate-spin" /> Running…</>
            ) : (
              <><Zap className="w-3.5 h-3.5" /> Run on {mode === "local" ? "Local" : "GitHub"}</>
            )}
          </button>
        </div>
      </div>

      {/* Sub-header: connection status / suite info */}
      <div className="px-4 py-2 bg-slate-50 border-b border-slate-200 flex items-center justify-between text-[11px]">
        <div className="flex items-center gap-2">
          <span className={`px-1.5 py-0.5 rounded border ${accent.chip} font-semibold`}>
            {mode === "local" ? "subprocess + Playwright" : "workflow_dispatch"}
          </span>
          {mode === "github" && ghConnection && (
            <span className="text-slate-500">
              → <span className="font-mono">{ghConnection.repo_full}</span>
            </span>
          )}
        </div>
        <span className={`font-semibold uppercase tracking-wider ${statusColor(status)}`}>
          {status}
        </span>
      </div>

      {/* GH not-connected CTA — replaces the body when applicable */}
      {ghNotConnected ? (
        <div className="p-8 flex flex-col items-center text-center gap-3 bg-slate-50/60">
          <Plug className="w-8 h-8 text-purple-500" />
          <p className="text-sm font-semibold text-slate-800">No GitHub repo connected</p>
          <p className="text-xs text-slate-500 max-w-xs">
            Connect this project to a repo from the Settings screen to enable real CI/CD runs via GitHub Actions.
          </p>
          <Link
            href="/dashboard/settings/github"
            className="inline-flex items-center gap-1.5 px-3 py-2 bg-purple-600 hover:bg-purple-700 text-white text-xs font-medium rounded-md transition-all"
          >
            <Plug className="w-3.5 h-3.5" />
            Connect GitHub
          </Link>
        </div>
      ) : (
        <>
          {error && (
            <div className="mx-3 mt-3 p-2 bg-red-50 text-red-700 text-xs rounded border border-red-200">
              {error}
            </div>
          )}

          {/* Live browser preview — local only. GitHub Actions runs on a
              remote Ubuntu runner, so frame capture isn't possible from
              our side. The execution log below shows step-level progress
              and the "Open on GitHub" link goes to the real run page. */}
          {mode === "local" && (runId || isDone) && (
            <div className="p-3">
              <LiveBrowserPreview
                src={livePreviewSrc}
                status={status}
                loaded={livePreviewLoaded}
                onLoad={() => setLivePreviewLoaded(true)}
                mode={mode}
              />
            </div>
          )}
          {mode === "github" && (runId || isDone) && (
            <div className="px-3 pt-3">
              <div className="text-[11px] text-slate-500 italic flex items-start gap-2 px-3 py-2 bg-slate-50 border border-slate-200 rounded-md">
                <ExternalLink className="w-3.5 h-3.5 shrink-0 mt-0.5 text-purple-600" />
                <span>
                  Running on GitHub-hosted Ubuntu runner — no live frame capture available remotely.
                  Open the run on GitHub to watch step-level progress in their UI, or follow the log
                  stream below.
                </span>
              </div>
            </div>
          )}

          {/* Live execution log */}
          <div className="px-3 pb-3 flex-1 flex flex-col min-h-0">
            <div className="flex items-center gap-2 py-2 text-[11px] text-slate-600">
              <Terminal className="w-3.5 h-3.5 text-purple-600" />
              <span className="font-semibold">Live Execution Log</span>
              {status === "running" && (
                <span className="flex items-center gap-1 text-blue-600">
                  <span className="w-1.5 h-1.5 rounded-full bg-blue-500 animate-pulse" />
                  streaming
                </span>
              )}
              <span className="ml-auto text-slate-400">{logs.length} events</span>
            </div>
            <div
              ref={logRef}
              className="h-56 overflow-y-auto p-3 font-mono text-[11px] space-y-1 bg-slate-900 text-slate-200 rounded-md"
              style={{ scrollbarWidth: "none" }}
            >
              {status === "idle" && (
                <p className="text-slate-500 italic">Click <strong>Run on {mode === "local" ? "Local" : "GitHub"}</strong> to start.</p>
              )}
              {logs.map((log, i) => (
                <div key={i} className="flex items-start gap-2 group">
                  <span className="mt-0.5 shrink-0">{statusIcon(log.status)}</span>
                  <span
                    className={`flex-1 break-all ${
                      log.status === "failed" ? "text-red-300" :
                      log.status === "skipped" || log.status === "cancelled" ? "text-slate-500 line-through decoration-slate-600" :
                      log.status === "passed" ? "text-slate-200" :
                      log.kind === "log" ? "text-slate-400" : "text-slate-200"
                    }`}
                  >
                    {log.step || log.line}
                    {log.status === "skipped" && (
                      <span className="ml-1.5 text-[9px] text-slate-500 uppercase tracking-wider no-underline">
                        skipped
                      </span>
                    )}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

// ─── Live Browser Preview ───────────────────────────────────────────────────

interface LiveBrowserPreviewProps {
  src: string | null;
  status: Status;
  loaded: boolean;
  onLoad: () => void;
  mode: RunMode;
}

function LiveBrowserPreview({ src, status, loaded, onLoad, mode }: LiveBrowserPreviewProps) {
  const isLive = status === "running" || status === "queued";
  const tone =
    status === "passed" ? "bg-emerald-500" :
    status === "failed" ? "bg-red-500" :
    status === "error"  ? "bg-amber-500" :
    isLive              ? "bg-blue-500"   : "bg-slate-400";
  const label =
    status === "passed" ? "final · passed" :
    status === "failed" ? "final · failed" :
    status === "error"  ? "final · error" :
    status === "queued" ? "waiting" : "live";

  return (
    <div className="rounded-lg border border-slate-200 bg-slate-900 overflow-hidden">
      <div className="flex items-center gap-2 px-3 py-1.5 bg-slate-800 border-b border-slate-700">
        <div className="flex gap-1">
          <span className="w-2 h-2 rounded-full bg-red-500/80" />
          <span className="w-2 h-2 rounded-full bg-amber-500/80" />
          <span className="w-2 h-2 rounded-full bg-emerald-500/80" />
        </div>
        <div className="flex-1 mx-2 px-2 py-0.5 bg-slate-900/70 border border-slate-700 rounded text-[10px] font-mono text-slate-400 truncate">
          {mode === "github" ? "github-actions://runner" : "playwright://headless-chromium"}
        </div>
        <span className="flex items-center gap-1 text-[10px] text-slate-300">
          <span className={`w-1.5 h-1.5 rounded-full ${tone} ${isLive ? "animate-pulse" : ""}`} />
          {label}
        </span>
      </div>
      <div className="relative bg-black" style={{ aspectRatio: "16 / 9" }}>
        {src && (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            key={src}
            src={src}
            alt="Browser preview"
            onLoad={onLoad}
            className={`absolute inset-0 w-full h-full object-contain transition-opacity duration-300 ${loaded ? "opacity-100" : "opacity-0"}`}
          />
        )}
        {(!src || !loaded) && (
          <div className="absolute inset-0 flex flex-col items-center justify-center text-slate-500 text-xs gap-1.5">
            <Loader2 className="w-5 h-5 animate-spin text-slate-600" />
            {isLive ? "Capturing first frame…" : "No preview"}
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Summary strip — sits below the two panels ──────────────────────────────

interface SummaryStripProps {
  local: RunDetail | null;
  github: RunDetail | null;
}

function SummaryStrip({ local, github }: SummaryStripProps) {
  const anyDone = local || github;
  return (
    <div className="px-6 py-5 grid grid-cols-2 gap-5">
      <SummaryCard mode="local" detail={local} />
      <SummaryCard mode="github" detail={github} />

      {/* Per-side screenshots underneath the cards. We render the failed
          run's screenshots first if any, otherwise the most-recent one. */}
      {anyDone && (
        <div className="col-span-2 grid grid-cols-2 gap-5">
          {local && <ScreenshotGrid title="Local screenshots" screenshots={local.screenshots} />}
          {github && <ScreenshotGrid title="GitHub Actions screenshots" screenshots={github.screenshots} />}
        </div>
      )}
    </div>
  );
}

function SummaryCard({ mode, detail }: { mode: RunMode; detail: RunDetail | null }) {
  const accent =
    mode === "local"
      ? { name: "Local Playwright", icon: <Server className="w-4 h-4 text-emerald-600" />, border: "border-emerald-200" }
      : { name: "GitHub Actions",  icon: <GitBranch className="w-4 h-4 text-purple-600" />, border: "border-purple-200" };

  if (!detail) {
    return (
      <div className={`rounded-xl border ${accent.border} bg-white p-5`}>
        <div className="flex items-center gap-2 mb-3">
          {accent.icon}
          <p className="text-sm font-bold text-slate-900">{accent.name}</p>
          <span className="text-[10px] uppercase tracking-widest text-slate-400 ml-auto">no run yet</span>
        </div>
        <p className="text-xs text-slate-500">Run this side to populate stats here.</p>
      </div>
    );
  }

  const total = Math.max(detail.total_count, 1);
  const successRate = Math.round((detail.passed_count / total) * 100);
  const chartData = [
    { name: "Passed", value: detail.passed_count, color: "#10b981" },
    { name: "Failed", value: detail.failed_count, color: "#ef4444" },
  ].filter((d) => d.value > 0);

  return (
    <div className={`rounded-xl border ${accent.border} bg-white p-5`}>
      <div className="flex items-center gap-2 mb-4">
        {accent.icon}
        <p className="text-sm font-bold text-slate-900">{accent.name}</p>
        <span className={`text-[10px] font-bold uppercase tracking-widest ml-auto ${statusColor(detail.status)}`}>
          {detail.status}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-4">
        {/* Stats column */}
        <div className="space-y-2 text-sm">
          {[
            { label: "Total Tests",  value: String(detail.total_count),   color: "text-slate-900" },
            { label: "Passed",       value: String(detail.passed_count),  color: "text-emerald-700" },
            { label: "Failed",       value: String(detail.failed_count),  color: "text-red-700" },
            { label: "Success Rate", value: `${successRate}%`,            color: "text-purple-700" },
            { label: "Duration",     value: detail.duration_ms ? `${(detail.duration_ms / 1000).toFixed(1)}s` : "—", color: "text-slate-700" },
            { label: "Framework",    value: detail.framework,             color: "text-emerald-700" },
          ].map((s) => (
            <div key={s.label} className="flex items-center justify-between">
              <span className="text-xs text-slate-500">{s.label}</span>
              <span className={`text-sm font-bold ${s.color}`}>{s.value}</span>
            </div>
          ))}
        </div>

        {/* Chart column */}
        <div className="flex flex-col items-center">
          {chartData.length > 0 ? (
            <ResponsiveContainer width="100%" height={140}>
              <PieChart>
                <Pie
                  data={chartData}
                  cx="50%" cy="50%"
                  innerRadius={36} outerRadius={58}
                  paddingAngle={3} dataKey="value"
                >
                  {chartData.map((entry, i) => <Cell key={i} fill={entry.color} />)}
                </Pie>
                <Tooltip
                  contentStyle={{ background: "#ffffff", border: "1px solid #e2e8f0", borderRadius: 8 }}
                  itemStyle={{ color: "#0f172a" }}
                />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <p className="text-xs text-slate-400 italic py-10">No counts captured</p>
          )}
        </div>
      </div>

      {/* Download row — log only. The PDF still gets generated server-side
          and lives at run.pdf_path in the DB; we just don't expose it from
          this card. Add it back via `runPdfUrl(detail.id)` if needed. */}
      <div className="mt-4">
        <a
          href={runLogUrl(detail.id)}
          target="_blank"
          rel="noreferrer"
          className="w-full flex items-center justify-center gap-2 py-2.5 bg-purple-600 hover:bg-purple-700 text-white text-xs font-semibold rounded-md transition-all shadow-sm"
        >
          <Download className="w-3.5 h-3.5" />
          Download Raw Log (saved in DB)
        </a>
      </div>

      {detail.failed_count > 0 && (
        <div className="mt-3 p-2 bg-amber-50 border border-amber-200 rounded text-[11px] text-amber-800 flex items-start gap-1.5">
          <AlertTriangle className="w-3 h-3 mt-0.5 shrink-0" />
          <span>{detail.failed_count} scenario{detail.failed_count === 1 ? "" : "s"} failed — see the raw log for full traces.</span>
        </div>
      )}
    </div>
  );
}

// ─── Screenshot grid ─────────────────────────────────────────────────────────

function ScreenshotGrid({ title, screenshots }: { title: string; screenshots: RunScreenshot[] }) {
  if (screenshots.length === 0) return null;
  return (
    <div className="rounded-xl border border-slate-200 bg-white overflow-hidden shadow-sm">
      <div className="flex items-center justify-between px-4 py-3 border-b border-slate-200 bg-slate-50">
        <div className="flex items-center gap-2">
          <ImageIcon className="w-4 h-4 text-purple-600" />
          <p className="text-sm font-semibold text-slate-800">{title}</p>
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
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={s.image_url}
              alt={s.label}
              className="w-full h-24 object-cover bg-slate-50"
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
