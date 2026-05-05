"use client";

import { useState } from "react";
import DashboardLayoutWrapper from "@/components/dashboard-layout-wrapper";
import {
  ChevronRight,
  ChevronLeft,
  Globe,
  CheckCircle,
  AlertTriangle,
  Loader2,
  Zap,
  Shield,
  Code2,
  Search,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { probeUrl } from "@/lib/api";

type Mode = "abstract" | "dom";
type Framework = "selenium" | "playwright" | "cypress";

const frameworks: { id: Framework; label: string; lang: string; color: string }[] = [
  { id: "selenium", label: "Selenium", lang: "Python", color: "text-blue-600" },
  { id: "playwright", label: "Playwright", lang: "Python / JS", color: "text-emerald-600" },
  { id: "cypress", label: "Cypress", lang: "JavaScript", color: "text-amber-600" },
];

type ProbeStatus = "idle" | "checking" | "ok" | "error";

export default function ModeSetupPage() {
  const router = useRouter();

  const [mode, setMode] = useState<Mode>("dom");
  const [framework, setFramework] = useState<Framework>("playwright");
  const [url, setUrl] = useState("https://www.saucedemo.com");

  const [probeStatus, setProbeStatus] = useState<ProbeStatus>("idle");
  const [probeMessage, setProbeMessage] = useState<string | null>(null);
  const [probeTitle, setProbeTitle] = useState<string | null>(null);

  const validateUrl = async () => {
    setProbeStatus("checking");
    setProbeMessage(null);
    setProbeTitle(null);
    try {
      const result = await probeUrl(url);
      if (result.ok) {
        setProbeStatus("ok");
        setProbeTitle(result.title ?? null);
        setProbeMessage(`HTTP ${result.status} — reachable`);
      } else {
        setProbeStatus("error");
        setProbeMessage(result.error ?? `HTTP ${result.status}`);
      }
    } catch (err) {
      setProbeStatus("error");
      setProbeMessage(err instanceof Error ? err.message : "Probe failed");
    }
  };

  // Mode B → DOM Inspector to extract elements first.
  // Mode A → straight to Code Review (placeholder selectors, no DOM needed).
  const continueHref =
    mode === "dom"
      ? `/dashboard/dom-inspector?mode=${mode}&framework=${framework}&url=${encodeURIComponent(url)}`
      : `/dashboard/code-review?mode=${mode}&framework=${framework}&url=${encodeURIComponent(url)}`;

  const continueDisabled = mode === "dom" && probeStatus !== "ok";

  const handleContinue = (e: React.MouseEvent) => {
    if (continueDisabled) {
      e.preventDefault();
      setProbeMessage("Validate the URL before continuing");
      return;
    }
    router.push(continueHref);
  };

  return (
    <DashboardLayoutWrapper>
      {/* Header */}
      <div className="sticky top-0 z-20 bg-white/80 backdrop-blur-sm border-b border-slate-200 px-8 py-5">
        <div className="flex justify-between items-center">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="text-xs font-bold text-purple-700 bg-purple-50 border border-purple-200 px-2 py-0.5 rounded-full tracking-wider">
                S3
              </span>
              <span className="text-xs text-slate-500">
                Pipeline Stage 3 of {mode === "dom" ? 6 : 5}
              </span>
            </div>
            <h1 className="text-2xl font-bold text-slate-900">Mode &amp; URL Setup</h1>
            <p className="text-slate-600 text-sm mt-0.5">
              Pick a generation mode, validate the staging URL, and choose a framework.
            </p>
          </div>
          <div className="flex items-center gap-3">
            <Link
              href="/dashboard/gherkin-editor"
              className="flex items-center gap-2 px-4 py-2 border border-slate-300 text-slate-600 hover:text-slate-900 hover:border-slate-400 hover:bg-slate-50 rounded-lg text-sm transition-all"
            >
              <ChevronLeft className="w-4 h-4" />
              Back
            </Link>
            <button
              onClick={handleContinue}
              disabled={continueDisabled}
              className="flex items-center gap-2 px-5 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg font-medium text-sm transition-all shadow-lg shadow-purple-600/30 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {mode === "dom" ? <Search className="w-4 h-4" /> : <Zap className="w-4 h-4" />}
              {mode === "dom" ? "Inspect DOM" : "Generate Code"}
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>

      <div className="p-8 max-w-275 mx-auto space-y-10">
        {/* Step 1 — Mode */}
        <section>
          <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-widest mb-4">
            Step 1 — Generation Mode
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <button
              onClick={() => setMode("abstract")}
              className={`relative text-left p-6 rounded-2xl border-2 transition-all duration-200 ${
                mode === "abstract"
                  ? "border-purple-500 bg-purple-50 shadow-lg shadow-purple-500/10"
                  : "border-slate-200 bg-white hover:border-slate-300"
              }`}
            >
              <div className="flex items-start justify-between mb-4">
                <div className="w-10 h-10 rounded-xl bg-slate-100 flex items-center justify-center">
                  <Code2 className="w-5 h-5 text-slate-600" />
                </div>
                <span
                  className={`text-[10px] font-bold px-2 py-0.5 rounded-full transition-all ${
                    mode === "abstract" ? "bg-purple-600 text-white" : "bg-slate-100 text-slate-500"
                  }`}
                >
                  MODE A
                </span>
              </div>
              <h3 className="text-sm font-bold text-slate-900 mb-1">Abstract Generation</h3>
              <p className="text-xs text-slate-600 leading-relaxed mb-4 min-h-15">
                No staging URL needed. Generates code with{" "}
                <code className="text-amber-700 bg-amber-50 border border-amber-200 px-1 py-0.5 rounded">
                  &lt;&lt;PLACEHOLDER&gt;&gt;
                </code>{" "}
                locators.
              </p>
              <div className="flex items-center gap-2 text-xs text-slate-500">
                <Shield className="w-3.5 h-3.5" />
                Best for early dev
              </div>
              {mode === "abstract" && (
                <div className="absolute top-4 right-4">
                  <CheckCircle className="w-5 h-5 text-purple-600" />
                </div>
              )}
            </button>

            <button
              onClick={() => setMode("dom")}
              className={`relative text-left p-6 rounded-2xl border-2 transition-all duration-200 ${
                mode === "dom"
                  ? "border-purple-500 bg-purple-50 shadow-lg shadow-purple-500/10"
                  : "border-slate-200 bg-white hover:border-slate-300"
              }`}
            >
              <div className="flex items-start justify-between mb-4">
                <div className="w-10 h-10 rounded-xl bg-linear-to-br from-purple-100 to-indigo-100 flex items-center justify-center">
                  <Globe className="w-5 h-5 text-purple-600" />
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-[9px] font-bold text-emerald-700 bg-emerald-50 border border-emerald-200 px-1.5 py-0.5 rounded-full">
                    RECOMMENDED
                  </span>
                  <span
                    className={`text-[10px] font-bold px-2 py-0.5 rounded-full transition-all ${
                      mode === "dom" ? "bg-purple-600 text-white" : "bg-slate-100 text-slate-500"
                    }`}
                  >
                    MODE B
                  </span>
                </div>
              </div>
              <h3 className="text-sm font-bold text-slate-900 mb-1">DOM-Aware Generation</h3>
              <p className="text-xs text-slate-600 leading-relaxed mb-4 min-h-15">
                Crawls the live URL with Playwright, extracts real selectors, and lets you edit
                them before code generation.
              </p>
              <div className="flex items-center gap-2 text-xs text-emerald-700">
                <Zap className="w-3.5 h-3.5" />
                Highest fidelity · works on any site
              </div>
              {mode === "dom" && (
                <div className="absolute top-4 right-4">
                  <CheckCircle className="w-5 h-5 text-purple-600" />
                </div>
              )}
            </button>
          </div>
        </section>

        {/* Step 2 — Staging URL (Mode B only) */}
        {mode === "dom" && (
          <section>
            <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-widest mb-4">
              Step 2 — Staging URL
            </h2>
            <div className="p-6 bg-white border border-slate-200 rounded-2xl shadow-sm">
              <div className="flex gap-3 mb-3">
                <div className="relative flex-1">
                  <Globe className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                  <input
                    value={url}
                    onChange={(e) => {
                      setUrl(e.target.value);
                      setProbeStatus("idle");
                      setProbeMessage(null);
                    }}
                    placeholder="https://your-staging-app.com"
                    className="w-full pl-10 pr-4 py-3 bg-white border border-slate-300 rounded-xl text-sm text-slate-900 placeholder-slate-400 focus:outline-none focus:border-purple-500 focus:ring-2 focus:ring-purple-100 transition-colors"
                  />
                </div>
                <button
                  onClick={validateUrl}
                  disabled={probeStatus === "checking" || !url}
                  className="flex items-center gap-2 px-5 py-3 bg-slate-100 hover:bg-slate-200 text-slate-800 rounded-xl text-sm font-medium transition-all disabled:opacity-60 border border-slate-200"
                >
                  {probeStatus === "checking" ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <CheckCircle className="w-4 h-4" />
                  )}
                  Validate
                </button>
              </div>

              {probeStatus === "ok" && (
                <div className="flex flex-col gap-1 text-sm text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-lg px-3 py-2">
                  <div className="flex items-center gap-2">
                    <CheckCircle className="w-4 h-4" />
                    {probeMessage ?? "URL is reachable"}
                  </div>
                  {probeTitle && (
                    <span className="text-[11px] text-emerald-700/80 ml-6 font-mono truncate">
                      &lt;title&gt; {probeTitle}
                    </span>
                  )}
                </div>
              )}
              {probeStatus === "error" && (
                <div className="flex items-center gap-2 text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
                  <AlertTriangle className="w-4 h-4" />
                  {probeMessage ?? "Unable to reach URL"}
                </div>
              )}
              {probeStatus === "idle" && (
                <p className="text-xs text-slate-500">
                  Plain HTTP probe — no browser launched yet. The crawler runs on the next step.
                </p>
              )}
            </div>
          </section>
        )}

        {/* Step 3 — Framework */}
        <section>
          <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-widest mb-4">
            Step {mode === "dom" ? 3 : 2} — Test Framework
          </h2>
          <div className="flex gap-3">
            {frameworks.map((fw) => (
              <button
                key={fw.id}
                onClick={() => setFramework(fw.id)}
                className={`flex-1 py-4 px-4 rounded-xl border-2 transition-all duration-200 text-left ${
                  framework === fw.id
                    ? "border-purple-500 bg-purple-50"
                    : "border-slate-200 bg-white hover:border-slate-300"
                }`}
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="text-sm font-bold text-slate-900">{fw.label}</span>
                  {framework === fw.id && <CheckCircle className="w-4 h-4 text-purple-600" />}
                </div>
                <span className={`text-[10px] font-medium ${fw.color}`}>{fw.lang}</span>
              </button>
            ))}
          </div>
          <p className="text-[11px] text-slate-500 mt-3 ml-1">
            All three frameworks share the same DOM elements — pick one to focus on; you can switch
            tabs in Code Review.
          </p>
        </section>

        {/* Summary CTA */}
        <div className="pt-2">
          <div className="p-5 bg-white border border-slate-200 rounded-2xl flex items-center justify-between shadow-sm">
            <div className="flex flex-col gap-1 text-sm text-slate-600">
              <div className="flex items-center gap-2">
                <span className="font-semibold text-slate-900">
                  {mode === "dom" ? "DOM-Aware" : "Abstract"}
                </span>
                <span className="text-slate-300">•</span>
                <span className="capitalize">{framework}</span>
                {mode === "dom" && probeStatus === "ok" && (
                  <>
                    <span className="text-slate-300">•</span>
                    <span className="text-[11px] font-mono text-emerald-700 truncate max-w-65">
                      {url}
                    </span>
                  </>
                )}
              </div>
              <span className="text-[11px] text-slate-500">
                Next: {mode === "dom" ? "DOM Inspector — extract & edit selectors" : "Code Review — generate placeholder suite"}
              </span>
            </div>
            <button
              onClick={handleContinue}
              disabled={continueDisabled}
              className="flex items-center gap-2 px-6 py-3 bg-linear-to-r from-purple-600 to-indigo-600 hover:from-purple-700 hover:to-indigo-700 text-white rounded-xl font-semibold text-sm transition-all shadow-lg shadow-purple-600/30 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {mode === "dom" ? <Search className="w-4 h-4" /> : <Zap className="w-4 h-4" />}
              {mode === "dom" ? "Inspect DOM" : "Generate Code"}
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>
    </DashboardLayoutWrapper>
  );
}
