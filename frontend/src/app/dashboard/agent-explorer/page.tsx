"use client";

import { useEffect, useRef, useState } from "react";
import DashboardLayoutWrapper from "@/components/dashboard-layout-wrapper";
import {
  Sparkles,
  Play,
  StopCircle,
  Brain,
  MousePointerClick,
  Eye,
  Lightbulb,
  Compass,
  AlertTriangle,
  CheckCircle2,
  Loader2,
} from "lucide-react";
import {
  startExploration,
  openAgentEventStream,
  type AgentEvent,
  type AgentRole,
} from "@/lib/api";
import { useProject } from "@/lib/project-context";

interface ThoughtEntry {
  step: number;
  role: AgentRole;
  text: string;
  ts: number;
}

interface ActionEntry {
  step: number;
  action_type: string;
  reason?: string;
  success: boolean;
  message: string;
  ts: number;
}

interface ScenarioEntry {
  step: number;
  title: string;
  steps: string[];
}

const ROLE_META: Record<AgentRole, { label: string; color: string; icon: React.ReactNode }> = {
  planner: {
    label: "Planner",
    color: "text-blue-700 bg-blue-50 border-blue-200",
    icon: <Compass className="w-3.5 h-3.5" />,
  },
  actor: {
    label: "Actor",
    color: "text-purple-700 bg-purple-50 border-purple-200",
    icon: <MousePointerClick className="w-3.5 h-3.5" />,
  },
  observer: {
    label: "Observer",
    color: "text-emerald-700 bg-emerald-50 border-emerald-200",
    icon: <Eye className="w-3.5 h-3.5" />,
  },
  critic: {
    label: "Critic",
    color: "text-amber-700 bg-amber-50 border-amber-200",
    icon: <Brain className="w-3.5 h-3.5" />,
  },
};

export default function AgentExplorerPage() {
  const { activeProject } = useProject();

  const [intent, setIntent] = useState("Check the login flow thoroughly — try valid login, invalid password, empty fields, and any account lockout behavior.");
  const [url, setUrl] = useState("https://www.saucedemo.com");
  const [maxSteps, setMaxSteps] = useState(12);
  const [headless, setHeadless] = useState(false);

  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [runId, setRunId] = useState<string | null>(null);

  const [screenshotB64, setScreenshotB64] = useState<string | null>(null);
  const [pageMeta, setPageMeta] = useState<{ url: string; title: string; step: number } | null>(null);
  const [novelStates, setNovelStates] = useState(0);
  const [currentStep, setCurrentStep] = useState(0);
  const [doneReason, setDoneReason] = useState<string | null>(null);

  const [thoughts, setThoughts] = useState<ThoughtEntry[]>([]);
  const [actions, setActions] = useState<ActionEntry[]>([]);
  const [scenarios, setScenarios] = useState<ScenarioEntry[]>([]);
  const [lessons, setLessons] = useState<string[]>([]);

  const wsRef = useRef<WebSocket | null>(null);
  const thoughtsScrollRef = useRef<HTMLDivElement | null>(null);

  // Auto-scroll thought log when new entries arrive.
  useEffect(() => {
    const el = thoughtsScrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [thoughts.length, actions.length]);

  useEffect(() => {
    return () => {
      wsRef.current?.close();
    };
  }, []);

  const reset = () => {
    setError(null);
    setScreenshotB64(null);
    setPageMeta(null);
    setNovelStates(0);
    setCurrentStep(0);
    setDoneReason(null);
    setThoughts([]);
    setActions([]);
    setScenarios([]);
    setLessons([]);
  };

  const handleEvent = (evt: AgentEvent) => {
    switch (evt.type) {
      case "screenshot":
        setScreenshotB64(evt.b64);
        setPageMeta({ url: evt.url, title: evt.title, step: evt.step });
        setNovelStates(evt.total_novel_states);
        setCurrentStep(evt.step);
        break;
      case "thought":
        setThoughts((prev) => [...prev, { step: evt.step, role: evt.role, text: evt.text, ts: evt.ts }]);
        break;
      case "action":
        setActions((prev) => [...prev, {
          step: evt.step,
          action_type: evt.action_type,
          reason: evt.reason,
          success: evt.success,
          message: evt.message,
          ts: evt.ts,
        }]);
        break;
      case "scenario_discovered":
        setScenarios((prev) => [...prev, {
          step: evt.step,
          title: evt.title,
          steps: evt.steps,
        }]);
        break;
      case "lesson":
        setLessons((prev) => [...prev, evt.text]);
        break;
      case "done":
        setDoneReason(evt.reason);
        setRunning(false);
        // Replace any in-flight scenarios with the authoritative final list.
        if (evt.scenarios?.length) {
          setScenarios(evt.scenarios.map((s, i) => ({ step: -1, title: s.title, steps: s.steps })));
        }
        break;
      case "error":
        setError(evt.message);
        setRunning(false);
        break;
      case "end":
        setRunning(false);
        break;
    }
  };

  const handleStart = async () => {
    if (!intent.trim() || !url.trim()) {
      setError("Intent and URL are required.");
      return;
    }
    reset();
    setRunning(true);
    try {
      const { run_id } = await startExploration({
        intent,
        url,
        projectId: activeProject?.id,
        maxSteps,
        headless,
      });
      setRunId(run_id);
      const ws = openAgentEventStream(run_id, handleEvent);
      ws.onclose = () => {
        // If the run ended with no explicit done event (e.g. socket dropped),
        // make sure the UI doesn't get stuck in "running" forever.
        setRunning((wasRunning) => {
          if (wasRunning && !doneReason) setDoneReason("connection closed");
          return false;
        });
      };
      wsRef.current = ws;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setRunning(false);
    }
  };

  const handleStop = () => {
    wsRef.current?.close();
    setRunning(false);
    setDoneReason("stopped by user");
  };

  return (
    <DashboardLayoutWrapper>
      <div className="p-6 max-w-[1600px] mx-auto">
        {/* Header */}
        <div className="mb-6">
          <div className="flex items-center gap-3 mb-2">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-purple-500 to-indigo-600 flex items-center justify-center shadow-lg shadow-purple-500/30">
              <Sparkles className="w-5 h-5 text-white" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-slate-900">Agent Explorer</h1>
              <p className="text-sm text-slate-500">
                Goal-driven autonomous test exploration · Set-of-Mark visual grounding · Coverage-driven termination
              </p>
            </div>
          </div>
        </div>

        {/* Control bar */}
        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-5 mb-5">
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
            <div className="lg:col-span-7">
              <label className="block text-xs font-semibold text-slate-600 uppercase tracking-wider mb-1.5">
                QA Intent
              </label>
              <textarea
                value={intent}
                onChange={(e) => setIntent(e.target.value)}
                disabled={running}
                rows={2}
                className="w-full px-3 py-2 border border-slate-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-purple-500 disabled:bg-slate-50"
                placeholder="e.g. check the login flow"
              />
            </div>
            <div className="lg:col-span-3">
              <label className="block text-xs font-semibold text-slate-600 uppercase tracking-wider mb-1.5">
                Target URL
              </label>
              <input
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                disabled={running}
                className="w-full px-3 py-2 border border-slate-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-purple-500 disabled:bg-slate-50"
                placeholder="https://..."
              />
              <div className="flex items-center gap-3 mt-2 text-xs text-slate-600">
                <label className="flex items-center gap-1.5">
                  <span className="font-semibold">Max steps</span>
                  <input
                    type="number"
                    value={maxSteps}
                    min={3}
                    max={30}
                    onChange={(e) => setMaxSteps(parseInt(e.target.value) || 12)}
                    disabled={running}
                    className="w-14 px-1.5 py-0.5 border border-slate-300 rounded text-xs"
                  />
                </label>
                <label className="flex items-center gap-1.5 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={headless}
                    onChange={(e) => setHeadless(e.target.checked)}
                    disabled={running}
                  />
                  <span>Headless</span>
                </label>
              </div>
            </div>
            <div className="lg:col-span-2 flex flex-col justify-end gap-2">
              {!running ? (
                <button
                  onClick={handleStart}
                  className="flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-purple-600 hover:bg-purple-700 text-white font-semibold text-sm shadow-md shadow-purple-600/30 transition-all"
                >
                  <Play className="w-4 h-4" />
                  Run Agent
                </button>
              ) : (
                <button
                  onClick={handleStop}
                  className="flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-red-600 hover:bg-red-700 text-white font-semibold text-sm shadow-md shadow-red-600/30 transition-all"
                >
                  <StopCircle className="w-4 h-4" />
                  Stop
                </button>
              )}
              <div className="text-[11px] text-slate-500 text-center">
                {runId ? `run · ${runId.slice(0, 8)}` : "no run yet"}
              </div>
            </div>
          </div>

          {error && (
            <div className="mt-3 flex items-start gap-2 px-3 py-2 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm">
              <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
              <div>{error}</div>
            </div>
          )}
          {doneReason && !running && !error && (
            <div className="mt-3 flex items-start gap-2 px-3 py-2 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-800 text-sm">
              <CheckCircle2 className="w-4 h-4 mt-0.5 shrink-0" />
              <div>
                Exploration finished — <span className="font-semibold">{doneReason}</span>.{" "}
                {scenarios.length} scenario{scenarios.length === 1 ? "" : "s"} discovered.
              </div>
            </div>
          )}
        </div>

        {/* Three panels */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
          {/* LEFT: live screenshot */}
          <div className="lg:col-span-5 bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
            <div className="px-4 py-3 border-b border-slate-200 flex items-center justify-between">
              <div className="flex items-center gap-2 text-sm font-semibold text-slate-700">
                <Eye className="w-4 h-4 text-purple-600" />
                Live View (with SoM overlay)
              </div>
              <div className="text-[11px] text-slate-500 font-mono truncate max-w-[200px]">
                {pageMeta ? `step ${pageMeta.step} · ${pageMeta.title}` : "—"}
              </div>
            </div>
            <div className="bg-slate-100 aspect-[16/10] flex items-center justify-center overflow-hidden">
              {screenshotB64 ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={`data:image/png;base64,${screenshotB64}`}
                  alt="Agent live view"
                  className="w-full h-full object-contain"
                />
              ) : running ? (
                <div className="flex flex-col items-center gap-2 text-slate-400">
                  <Loader2 className="w-8 h-8 animate-spin" />
                  <span className="text-sm">Launching browser…</span>
                </div>
              ) : (
                <div className="text-slate-400 text-sm">Click <span className="font-semibold">Run Agent</span> to begin</div>
              )}
            </div>
            {pageMeta && (
              <div className="px-4 py-2 border-t border-slate-200 text-[11px] text-slate-500 font-mono truncate">
                {pageMeta.url}
              </div>
            )}
          </div>

          {/* MIDDLE: agent thought log */}
          <div className="lg:col-span-4 bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden flex flex-col">
            <div className="px-4 py-3 border-b border-slate-200 flex items-center justify-between">
              <div className="flex items-center gap-2 text-sm font-semibold text-slate-700">
                <Brain className="w-4 h-4 text-purple-600" />
                Agent Reasoning
              </div>
              <div className="text-[11px] text-slate-500">
                step {currentStep}
              </div>
            </div>
            <div
              ref={thoughtsScrollRef}
              className="flex-1 overflow-y-auto p-3 space-y-2 max-h-[640px] min-h-[320px]"
            >
              {thoughts.length === 0 && actions.length === 0 && (
                <div className="text-slate-400 text-sm italic px-2 py-4 text-center">
                  Waiting for the agent to reason…
                </div>
              )}
              {/* Interleave thoughts and actions in step order. */}
              {[...thoughts.map((t) => ({ ...t, kind: "thought" as const })),
                ...actions.map((a) => ({ ...a, kind: "action" as const }))]
                .sort((a, b) => a.ts - b.ts)
                .map((entry, i) => {
                  if (entry.kind === "thought") {
                    const meta = ROLE_META[entry.role];
                    return (
                      <div
                        key={`th-${i}`}
                        className={`border rounded-xl px-3 py-2 ${meta.color}`}
                      >
                        <div className="flex items-center gap-1.5 mb-1">
                          {meta.icon}
                          <span className="text-[10px] font-bold uppercase tracking-wider">
                            {meta.label}
                          </span>
                          <span className="ml-auto text-[10px] opacity-60">
                            step {entry.step}
                          </span>
                        </div>
                        <div className="text-[13px] leading-relaxed">{entry.text}</div>
                      </div>
                    );
                  }
                  return (
                    <div
                      key={`ac-${i}`}
                      className={`border rounded-xl px-3 py-2 ${
                        entry.success
                          ? "bg-slate-50 border-slate-200 text-slate-700"
                          : "bg-red-50 border-red-200 text-red-700"
                      }`}
                    >
                      <div className="flex items-center gap-1.5 mb-1">
                        <MousePointerClick className="w-3.5 h-3.5" />
                        <span className="text-[10px] font-bold uppercase tracking-wider">
                          Action · {entry.action_type}
                        </span>
                        <span className="ml-auto text-[10px] opacity-60">step {entry.step}</span>
                      </div>
                      <div className="text-[12px] font-mono">{entry.message}</div>
                      {entry.reason && (
                        <div className="text-[12px] mt-1 italic opacity-80">
                          “{entry.reason}”
                        </div>
                      )}
                    </div>
                  );
                })}
            </div>
          </div>

          {/* RIGHT: discoveries + coverage */}
          <div className="lg:col-span-3 space-y-5">
            {/* Coverage */}
            <div className="bg-white rounded-2xl border border-slate-200 shadow-sm">
              <div className="px-4 py-3 border-b border-slate-200 flex items-center gap-2 text-sm font-semibold text-slate-700">
                <Compass className="w-4 h-4 text-purple-600" />
                Coverage
              </div>
              <div className="p-4 grid grid-cols-2 gap-3">
                <div className="text-center">
                  <div className="text-2xl font-bold text-purple-600">{novelStates}</div>
                  <div className="text-[11px] text-slate-500 mt-0.5">Novel states</div>
                </div>
                <div className="text-center">
                  <div className="text-2xl font-bold text-purple-600">{scenarios.length}</div>
                  <div className="text-[11px] text-slate-500 mt-0.5">Scenarios found</div>
                </div>
              </div>
            </div>

            {/* Discovered scenarios */}
            <div className="bg-white rounded-2xl border border-slate-200 shadow-sm">
              <div className="px-4 py-3 border-b border-slate-200 flex items-center gap-2 text-sm font-semibold text-slate-700">
                <Sparkles className="w-4 h-4 text-purple-600" />
                Discovered Scenarios
              </div>
              <div className="p-3 space-y-2 max-h-[300px] overflow-y-auto">
                {scenarios.length === 0 ? (
                  <div className="text-slate-400 text-xs italic px-2 py-4 text-center">
                    None yet — agent will report scenarios as it validates them.
                  </div>
                ) : (
                  scenarios.map((s, i) => (
                    <div
                      key={i}
                      className="border border-purple-200 bg-purple-50 rounded-xl px-3 py-2"
                    >
                      <div className="text-[13px] font-semibold text-purple-900 mb-1">
                        {i + 1}. {s.title}
                      </div>
                      <ul className="text-[11px] text-purple-800 space-y-0.5 list-disc pl-4">
                        {s.steps.map((st, j) => (
                          <li key={j}>{st}</li>
                        ))}
                      </ul>
                    </div>
                  ))
                )}
              </div>
            </div>

            {/* Reflexion lessons */}
            {lessons.length > 0 && (
              <div className="bg-white rounded-2xl border border-slate-200 shadow-sm">
                <div className="px-4 py-3 border-b border-slate-200 flex items-center gap-2 text-sm font-semibold text-slate-700">
                  <Lightbulb className="w-4 h-4 text-amber-500" />
                  Reflexion Memory
                </div>
                <div className="p-3 space-y-1.5 max-h-[200px] overflow-y-auto">
                  {lessons.map((l, i) => (
                    <div
                      key={i}
                      className="text-[12px] text-amber-900 bg-amber-50 border border-amber-200 rounded-lg px-2.5 py-1.5"
                    >
                      {l}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </DashboardLayoutWrapper>
  );
}
