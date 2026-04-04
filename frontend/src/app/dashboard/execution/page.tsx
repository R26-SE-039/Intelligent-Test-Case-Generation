"use client";

import { useState, useRef, useEffect } from "react";
import DashboardLayoutWrapper from "@/components/dashboard-layout-wrapper";
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from "recharts";
import {
  PlayCircle,
  ChevronLeft,
  CheckCircle,
  XCircle,
  Clock,
  Download,
  Terminal,
  Image as ImageIcon,
  Zap,
  RotateCcw,
  AlertTriangle,
} from "lucide-react";
import Link from "next/link";

type RunStatus = "idle" | "running" | "done" | "failed";

interface LogEntry {
  step: string;
  status: "running" | "passed" | "failed" | "info";
  timestamp: string;
  duration?: string;
}

const simulatedLogs: LogEntry[] = [
  { step: "Connecting to GitHub Actions runner...", status: "info", timestamp: "00:00" },
  { step: "Checking out generated tests", status: "passed", timestamp: "00:01", duration: "1.2s" },
  { step: "Setting up Python 3.10", status: "passed", timestamp: "00:03", duration: "2.1s" },
  { step: "Installing Playwright + pytest", status: "passed", timestamp: "00:07", duration: "4.0s" },
  { step: "Installing Chromium browser", status: "passed", timestamp: "00:12", duration: "5.3s" },
  { step: "Running test_successful_login", status: "passed", timestamp: "00:15", duration: "3.1s" },
  { step: "Running test_failed_login_invalid_credentials", status: "passed", timestamp: "00:18", duration: "2.7s" },
  { step: "Running test_add_item_to_cart", status: "passed", timestamp: "00:21", duration: "3.3s" },
  { step: "Running test_remove_item_from_cart", status: "passed", timestamp: "00:24", duration: "2.9s" },
  { step: "Running test_checkout_success", status: "passed", timestamp: "00:27", duration: "4.2s" },
  { step: "Running test_checkout_missing_info", status: "failed", timestamp: "00:31", duration: "1.8s" },
  { step: "Capturing screenshots and video", status: "passed", timestamp: "00:33", duration: "0.9s" },
  { step: "Generating Allure HTML report", status: "passed", timestamp: "00:34", duration: "1.4s" },
  { step: "Posting results via webhook", status: "passed", timestamp: "00:36", duration: "0.3s" },
];

const chartData = [
  { name: "Passed", value: 5, color: "#10b981" },
  { name: "Failed", value: 1, color: "#ef4444" },
];

const screenshots = [
  { label: "Login Success", scenario: "test_successful_login", status: "passed" },
  { label: "Login Failure", scenario: "test_failed_login_invalid_credentials", status: "passed" },
  { label: "Add to Cart", scenario: "test_add_item_to_cart", status: "passed" },
  { label: "Remove from Cart", scenario: "test_remove_item_from_cart", status: "passed" },
  { label: "Checkout Success", scenario: "test_checkout_success", status: "passed" },
  { label: "Checkout Error", scenario: "test_checkout_missing_info", status: "failed" },
];

const statusIcon: Record<LogEntry["status"], React.ReactNode> = {
  info: <Terminal className="w-3.5 h-3.5 text-slate-500" />,
  running: <Clock className="w-3.5 h-3.5 text-blue-400 animate-pulse" />,
  passed: <CheckCircle className="w-3.5 h-3.5 text-emerald-400" />,
  failed: <XCircle className="w-3.5 h-3.5 text-red-400" />,
};

export default function ExecutionPage() {
  const [runStatus, setRunStatus] = useState<RunStatus>("idle");
  const [visibleLogs, setVisibleLogs] = useState<LogEntry[]>([]);
  const [currentStep, setCurrentStep] = useState(0);
  const logRef = useRef<HTMLDivElement>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const startRun = () => {
    setRunStatus("running");
    setVisibleLogs([]);
    setCurrentStep(0);

    let idx = 0;
    timerRef.current = setInterval(() => {
      if (idx >= simulatedLogs.length) {
        clearInterval(timerRef.current!);
        const hasFailed = simulatedLogs.some((l) => l.status === "failed");
        setRunStatus(hasFailed ? "failed" : "done");
        return;
      }
      setVisibleLogs((prev) => [...prev, simulatedLogs[idx]]);
      setCurrentStep(idx + 1);
      idx++;
    }, 600);
  };

  const resetRun = () => {
    if (timerRef.current) clearInterval(timerRef.current);
    setRunStatus("idle");
    setVisibleLogs([]);
    setCurrentStep(0);
  };

  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [visibleLogs]);

  useEffect(() => () => { if (timerRef.current) clearInterval(timerRef.current); }, []);

  const isDone = runStatus === "done" || runStatus === "failed";
  const passed = chartData[0].value;
  const failed = chartData[1].value;
  const total = passed + failed;
  const successRate = Math.round((passed / total) * 100);

  return (
    <DashboardLayoutWrapper>
      {/* Header */}
      <div className="sticky top-0 z-10 bg-slate-950/80 backdrop-blur-sm border-b border-slate-800 px-8 py-5">
        <div className="flex justify-between items-center">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="text-xs font-bold text-purple-400 bg-purple-500/10 border border-purple-500/20 px-2 py-0.5 rounded-full tracking-wider">
                S5
              </span>
              <span className="text-xs text-slate-500">Pipeline Stage 5 of 5</span>
            </div>
            <h1 className="text-2xl font-bold text-white">Execution &amp; Report</h1>
            <p className="text-slate-400 text-sm mt-0.5">
              Run tests via GitHub Actions · Live log streaming · Download PDF report
            </p>
          </div>
          <div className="flex items-center gap-3">
            <Link
              href="/dashboard/code-review"
              className="flex items-center gap-2 px-4 py-2 border border-slate-700 text-slate-400 hover:text-white hover:border-slate-600 rounded-lg text-sm transition-all"
            >
              <ChevronLeft className="w-4 h-4" />
              Back
            </Link>
            {isDone && (
              <button
                onClick={resetRun}
                className="flex items-center gap-2 px-4 py-2 border border-slate-700 text-slate-400 hover:text-white rounded-lg text-sm transition-all"
              >
                <RotateCcw className="w-4 h-4" />
                Reset
              </button>
            )}
            <button
              onClick={runStatus === "idle" || isDone ? startRun : undefined}
              disabled={runStatus === "running"}
              className={`flex items-center gap-2 px-6 py-2.5 rounded-lg font-semibold text-sm transition-all ${
                runStatus === "running"
                  ? "bg-slate-700 text-slate-400 cursor-not-allowed"
                  : "bg-linear-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white shadow-lg shadow-purple-600/30"
              }`}
            >
              {runStatus === "running" ? (
                <><Clock className="w-4 h-4 animate-spin" /> Running…</>
              ) : (
                <><Zap className="w-4 h-4" /> Run Tests</>
              )}
            </button>
          </div>
        </div>
      </div>

      <div className="p-6 grid grid-cols-3 gap-5">
        {/* Left: Log + Screenshots */}
        <div className="col-span-2 flex flex-col gap-5">
          {/* Live Log */}
          <div className="rounded-xl border border-slate-700 overflow-hidden bg-slate-900">
            <div className="flex items-center justify-between px-4 py-3 border-b border-slate-700 bg-slate-800/50">
              <div className="flex items-center gap-2">
                <Terminal className="w-4 h-4 text-purple-400" />
                <p className="text-sm font-semibold text-slate-200">Live Execution Log</p>
                {runStatus === "running" && (
                  <span className="flex items-center gap-1.5 text-xs text-blue-400">
                    <span className="w-1.5 h-1.5 rounded-full bg-blue-400 animate-pulse" />
                    Streaming via WebSocket...
                  </span>
                )}
              </div>
              <span className="text-xs text-slate-500">
                {currentStep}/{simulatedLogs.length} steps
              </span>
            </div>
            <div
              ref={logRef}
              className="h-64 overflow-y-auto p-4 font-mono text-xs space-y-1.5"
              style={{ scrollbarWidth: "none" }}
            >
              {runStatus === "idle" && (
                <p className="text-slate-600 italic">Press Run Tests to start execution...</p>
              )}
              {visibleLogs.map((log, i) => (
                <div key={i} className="flex items-start gap-2.5 group">
                  <span className="mt-0.5 shrink-0">{statusIcon[log.status]}</span>
                  <span
                    className={`flex-1 ${
                      log.status === "failed"
                        ? "text-red-400"
                        : log.status === "passed"
                        ? "text-slate-300"
                        : "text-slate-500"
                    }`}
                  >
                    {log.step}
                  </span>
                  {log.duration && (
                    <span className="text-slate-600 shrink-0">{log.duration}</span>
                  )}
                  <span className="text-slate-700 shrink-0">{log.timestamp}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Screenshots */}
          {isDone && (
            <div className="rounded-xl border border-slate-700 bg-slate-900 overflow-hidden">
              <div className="flex items-center justify-between px-4 py-3 border-b border-slate-700 bg-slate-800/50">
                <div className="flex items-center gap-2">
                  <ImageIcon className="w-4 h-4 text-purple-400" />
                  <p className="text-sm font-semibold text-slate-200">Test Screenshots</p>
                </div>
              </div>
              <div className="p-4 grid grid-cols-3 gap-3">
                {screenshots.map((s) => (
                  <div
                    key={s.label}
                    className={`rounded-lg border overflow-hidden ${
                      s.status === "failed" ? "border-red-500/40" : "border-slate-700"
                    }`}
                  >
                    <div
                      className={`h-24 flex items-center justify-center text-xs font-mono text-slate-600 ${
                        s.status === "failed" ? "bg-red-500/5" : "bg-slate-800"
                      }`}
                    >
                      {s.status === "passed" ? (
                        <span className="text-emerald-500/40">[ screenshot ]</span>
                      ) : (
                        <span className="text-red-500/40">[ assertion error ]</span>
                      )}
                    </div>
                    <div className="px-2.5 py-2 bg-slate-900/60 flex items-center justify-between">
                      <p className="text-[11px] text-slate-400 truncate">{s.label}</p>
                      {s.status === "passed" ? (
                        <CheckCircle className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                      ) : (
                        <XCircle className="w-3.5 h-3.5 text-red-400 shrink-0" />
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Right: Stats + Chart + Report */}
        <div className="flex flex-col gap-4">
          {/* Summary Stats */}
          <div className="rounded-xl border border-slate-700 bg-slate-900 p-5">
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-widest mb-4">
              Run Summary
            </p>
            <div className="space-y-3">
              {[
                { label: "Total Tests", value: isDone ? String(total) : "—", color: "text-white" },
                { label: "Passed", value: isDone ? String(passed) : "—", color: "text-emerald-400" },
                { label: "Failed", value: isDone ? String(failed) : "—", color: "text-red-400" },
                { label: "Success Rate", value: isDone ? `${successRate}%` : "—", color: "text-purple-400" },
                { label: "Duration", value: isDone ? "36.4s" : "—", color: "text-slate-300" },
                { label: "Framework", value: "Playwright", color: "text-emerald-400" },
              ].map((s) => (
                <div key={s.label} className="flex items-center justify-between">
                  <span className="text-xs text-slate-500">{s.label}</span>
                  <span className={`text-sm font-bold ${s.color}`}>{s.value}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Donut Chart */}
          {isDone && (
            <div className="rounded-xl border border-slate-700 bg-slate-900 p-5">
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
                    contentStyle={{ background: "#1e293b", border: "1px solid #334155", borderRadius: 8 }}
                    labelStyle={{ color: "#94a3b8" }}
                    itemStyle={{ color: "#e2e8f0" }}
                  />
                </PieChart>
              </ResponsiveContainer>
              <div className="flex justify-center gap-5 mt-1">
                {chartData.map((d) => (
                  <div key={d.name} className="flex items-center gap-1.5 text-xs text-slate-400">
                    <span className="w-2.5 h-2.5 rounded-full" style={{ background: d.color }} />
                    {d.name}: <span className="text-white font-semibold">{d.value}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Failed test AI explanation */}
          {isDone && (
            <div className="rounded-xl border border-amber-500/20 bg-amber-500/5 p-4">
              <div className="flex items-center gap-2 mb-2">
                <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />
                <p className="text-xs font-semibold text-amber-300">AI Failure Explanation</p>
              </div>
              <p className="text-xs text-slate-400 leading-relaxed">
                <span className="text-amber-400 font-mono">test_checkout_missing_info</span> failed
                because the error message selector{" "}
                <span className="font-mono text-red-400">[data-test=&apos;error&apos;]</span> was
                not found in the DOM. The element may have a dynamic class. C3 Self-Healing will
                attempt to locate an alternative selector.
              </p>
            </div>
          )}

          {/* Download */}
          {isDone && (
            <button className="w-full flex items-center justify-center gap-2 py-3 bg-slate-800 hover:bg-slate-700 border border-slate-700 hover:border-slate-600 text-slate-300 hover:text-white rounded-xl text-sm font-medium transition-all">
              <Download className="w-4 h-4" />
              Download PDF Report
            </button>
          )}

          {/* Pipeline complete */}
          {isDone && (
            <div className="p-4 bg-emerald-500/10 border border-emerald-500/20 rounded-xl text-center">
              <CheckCircle className="w-6 h-6 text-emerald-400 mx-auto mb-2" />
              <p className="text-xs font-semibold text-emerald-300">Pipeline Complete</p>
              <p className="text-[11px] text-slate-500 mt-1">
                Results written to PostgreSQL · C3 &amp; C4 notified
              </p>
              <Link
                href="/dashboard"
                className="inline-flex items-center gap-1.5 mt-3 text-xs text-purple-400 hover:text-purple-300 transition-colors"
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
