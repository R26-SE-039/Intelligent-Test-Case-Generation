"use client";

import { useState, useEffect } from "react";
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
  Terminal,
} from "lucide-react";
import Link from "next/link";

type Mode = "abstract" | "dom";
type Framework = "selenium" | "playwright" | "cypress";

const frameworks: { id: Framework; label: string; lang: string; color: string }[] = [
  { id: "selenium", label: "Selenium", lang: "Python", color: "text-blue-600" },
  { id: "playwright", label: "Playwright", lang: "Python / JS", color: "text-emerald-600" },
  { id: "cypress", label: "Cypress", lang: "JavaScript", color: "text-amber-600" },
];

export default function ModeSetupPage() {
  const [mode, setMode] = useState<Mode>("dom");
  const [framework, setFramework] = useState<Framework>("playwright");
  const [url, setUrl] = useState("https://www.saucedemo.com");
  const [urlStatus, setUrlStatus] = useState<"idle" | "checking" | "ok" | "error">("idle");
  const [crawlerLogs, setCrawlerLogs] = useState<{ text: string; type: "info" | "success" | "wait" }[]>([]);

  const validateUrl = async () => {
    setUrlStatus("checking");
    setCrawlerLogs([]);
    await new Promise((r) => setTimeout(r, 1500));
    const isOk = url.startsWith("http");
    setUrlStatus(isOk ? "ok" : "error");
    
    if (isOk) {
      simulateCrawling();
    }
  };

  const simulateCrawling = () => {
    const sequence = [
      { text: `Navigating to ${url}...`, type: "info", delay: 500 },
      { text: `DOM Loaded. Injecting CSS selector engine.`, type: "success", delay: 1500 },
      { text: `Story US-001: Extracting 'Username input'...`, type: "info", delay: 2500 },
      { text: `Found element matching #user-name`, type: "success", delay: 3500 },
      { text: `Story US-001: Extracting 'Password input'...`, type: "info", delay: 4000 },
      { text: `Found element matching #password`, type: "success", delay: 4800 },
      { text: `Story US-001: Extracting 'Login button'...`, type: "info", delay: 5500 },
      { text: `Found element matching #login-button`, type: "success", delay: 6200 },
      { text: `Story US-002: Extracting 'Add to cart'...`, type: "info", delay: 7200 },
      { text: `Found element matching .btn_inventory`, type: "success", delay: 8000 },
      { text: `Continuing extraction for all stories...`, type: "wait", delay: 9000 },
    ] as const;

    sequence.forEach((log) => {
      setTimeout(() => {
        setCrawlerLogs((prev) => [...prev, { text: log.text, type: log.type }]);
      }, log.delay);
    });
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
              <span className="text-xs text-slate-500">Pipeline Stage 3 of 5</span>
            </div>
            <h1 className="text-2xl font-bold text-slate-900">Mode &amp; URL Setup</h1>
            <p className="text-slate-600 text-sm mt-0.5">
              Choose generation mode, target framework, and staging URL
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
            <Link
              href={`/dashboard/code-review?mode=${mode}&framework=${framework}&url=${encodeURIComponent(url)}`}
              className="flex items-center gap-2 px-5 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg font-medium text-sm transition-all shadow-lg shadow-purple-600/30"
            >
              <Zap className="w-4 h-4" />
              Generate Code
              <ChevronRight className="w-4 h-4" />
            </Link>
          </div>
        </div>
      </div>

      <div className="p-8 max-w-[1600px] mx-auto">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-10">
          
          {/* Left Column - Setup */}
          <div className="flex flex-col">
            {/* Mode Selection */}
            <section className="mb-10">
              <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-widest mb-4">
                Step 1 — Generation Mode
              </h2>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {/* Mode A */}
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
                        mode === "abstract"
                          ? "bg-purple-600 text-white"
                          : "bg-slate-100 text-slate-500"
                      }`}
                    >
                      MODE A
                    </span>
                  </div>
                  <h3 className="text-sm font-bold text-slate-900 mb-1">Abstract Generation</h3>
                  <p className="text-xs text-slate-600 leading-relaxed mb-4 min-h-[60px]">
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

                {/* Mode B */}
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
                          mode === "dom"
                            ? "bg-purple-600 text-white"
                            : "bg-slate-100 text-slate-500"
                        }`}
                      >
                        MODE B
                      </span>
                    </div>
                  </div>
                  <h3 className="text-sm font-bold text-slate-900 mb-1">DOM-Aware Generation</h3>
                  <p className="text-xs text-slate-600 leading-relaxed mb-4 min-h-[60px]">
                    Crawls the live staging URL with Playwright to extract real selectors.
                  </p>
                  <div className="flex items-center gap-2 text-xs text-emerald-700">
                    <Zap className="w-3.5 h-3.5" />
                    Highest impact
                  </div>
                  {mode === "dom" && (
                    <div className="absolute top-4 right-4">
                      <CheckCircle className="w-5 h-5 text-purple-600" />
                    </div>
                  )}
                </button>
              </div>
            </section>

            {/* Framework Selection */}
            <section className="mb-10">
              <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-widest mb-4">
                Step 2 — Test Framework
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
                      {framework === fw.id && (
                        <CheckCircle className="w-4 h-4 text-purple-600" />
                      )}
                    </div>
                    <span className={`text-[10px] font-medium ${fw.color}`}>{fw.lang}</span>
                  </button>
                ))}
              </div>
              <p className="text-[11px] text-slate-500 mt-3 ml-1">
                💡 All three frameworks are generated simultaneously — you can switch in Code Review.
              </p>
            </section>

            {/* URL Input (Mode B only) */}
            {mode === "dom" && (
              <section className="mb-6">
                <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-widest mb-4">
                  Step 3 — Staging URL
                </h2>
                <div className="p-6 bg-white border border-slate-200 rounded-2xl shadow-sm">
                  <div className="flex gap-3 mb-3">
                    <div className="relative flex-1">
                      <Globe className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                      <input
                        value={url}
                        onChange={(e) => { setUrl(e.target.value); setUrlStatus("idle"); }}
                        placeholder="https://your-staging-app.com"
                        className="w-full pl-10 pr-4 py-3 bg-white border border-slate-300 rounded-xl text-sm text-slate-900 placeholder-slate-400 focus:outline-none focus:border-purple-500 focus:ring-2 focus:ring-purple-100 transition-colors"
                      />
                    </div>
                    <button
                      onClick={validateUrl}
                      disabled={urlStatus === "checking"}
                      className="flex items-center gap-2 px-5 py-3 bg-slate-100 hover:bg-slate-200 text-slate-800 rounded-xl text-sm font-medium transition-all disabled:opacity-60 border border-slate-200"
                    >
                      {urlStatus === "checking" ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                      ) : (
                        <CheckCircle className="w-4 h-4" />
                      )}
                      Validate
                    </button>
                  </div>

                  {urlStatus === "ok" && (
                    <div className="flex items-center gap-2 text-sm text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-lg px-3 py-2">
                      <CheckCircle className="w-4 h-4" />
                      URL is reachable · DOM crawler is ready
                    </div>
                  )}
                  {urlStatus === "error" && (
                    <div className="flex items-center gap-2 text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
                      <AlertTriangle className="w-4 h-4" />
                      Unable to reach URL
                    </div>
                  )}
                </div>
              </section>
            )}

            {/* Summary & CTA */}
            <div className="mt-auto pt-6">
              <div className="p-5 bg-white border border-slate-200 rounded-2xl flex items-center justify-between shadow-sm">
                <div className="flex flex-col gap-1 text-sm text-slate-600">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-slate-900">
                      {mode === "dom" ? "DOM-Aware" : "Abstract"}
                    </span>
                    <span className="text-slate-300">•</span>
                    <span className="capitalize">{framework}</span>
                  </div>
                  {mode === "dom" && (
                    <span className="text-[11px] font-mono text-emerald-700 truncate max-w-[200px]">
                      {url}
                    </span>
                  )}
                </div>
                <Link
                  href={`/dashboard/code-review?mode=${mode}&framework=${framework}&url=${encodeURIComponent(url)}`}
                  className="flex items-center gap-2 px-6 py-3 bg-linear-to-r from-purple-600 to-indigo-600 hover:from-purple-700 hover:to-indigo-700 text-white rounded-xl font-semibold text-sm transition-all shadow-lg shadow-purple-600/30"
                >
                  <Zap className="w-4 h-4" />
                  Generate Code
                  <ChevronRight className="w-4 h-4" />
                </Link>
              </div>
            </div>
          </div>

          {/* Right Column - Live Preview */}
          <div className="hidden lg:flex flex-col min-h-[600px]">
            {mode === "dom" ? (
              <div className="flex-1 flex flex-col border border-slate-200 rounded-2xl overflow-hidden bg-white shadow-xl shadow-slate-200/50 relative">
                {/* Browser Top Bar */}
                <div className="flex items-center gap-2 px-4 py-3 bg-slate-100 border-b border-slate-200 shrink-0">
                  <div className="flex gap-1.5">
                    <div className="w-3 h-3 rounded-full bg-red-400"></div>
                    <div className="w-3 h-3 rounded-full bg-amber-400"></div>
                    <div className="w-3 h-3 rounded-full bg-green-400"></div>
                  </div>
                  <div className="mx-auto flex items-center justify-center gap-2 px-4 py-1.5 bg-white border border-slate-200 rounded-md text-xs text-slate-500 font-mono w-2/3 shadow-sm truncate">
                    <Globe className="w-3.5 h-3.5 shrink-0" />
                    <span className="truncate">{urlStatus === "ok" ? url : "Waiting for URL..."}</span>
                  </div>
                </div>
                
                {/* Browser Content */}
                <div className="flex-1 relative bg-slate-50 overflow-hidden flex flex-col">
                  {urlStatus === "idle" && (
                    <div className="flex-1 flex items-center justify-center text-slate-400 flex-col gap-3 p-8 text-center">
                      <div className="w-16 h-16 bg-white rounded-2xl shadow-sm flex items-center justify-center border border-slate-200 mb-2">
                        <Globe className="w-8 h-8 text-slate-300" />
                      </div>
                      <h3 className="text-lg font-semibold text-slate-900">Live Web Interface</h3>
                      <p className="text-sm">Enter and validate a staging URL to preview the site and watch the DOM crawler extract elements for your stories.</p>
                    </div>
                  )}
                  {urlStatus === "checking" && (
                    <div className="flex-1 flex items-center justify-center text-slate-500 flex-col gap-3">
                      <Loader2 className="w-8 h-8 animate-spin text-purple-500" />
                      <p className="text-sm">Validating connection...</p>
                    </div>
                  )}
                  {urlStatus === "error" && (
                    <div className="flex-1 flex items-center justify-center text-slate-500 flex-col gap-3 p-8 text-center">
                      <AlertTriangle className="w-10 h-10 text-red-400" />
                      <p className="text-sm text-red-600 font-medium">Failed to connect to URL</p>
                      <p className="text-xs text-slate-400 mt-2">The site may be unreachable or block iframes. You can still proceed with DOM mode, but the preview won't be visible.</p>
                    </div>
                  )}
                  {urlStatus === "ok" && (
                    <>
                      <div className="flex-1 relative bg-white">
                        <iframe 
                          src={url} 
                          className="w-full h-full border-none opacity-90 transition-opacity duration-1000"
                          sandbox="allow-scripts allow-same-origin"
                          title="Target Website Preview"
                        />
                        {/* Overlay to dim the background slightly so the terminal stands out */}
                        <div className="absolute inset-0 bg-indigo-900/10 pointer-events-none"></div>
                        
                        {/* Floating DOM Crawler Terminal */}
                        <div className="absolute bottom-6 left-6 right-6 bg-slate-900/95 backdrop-blur-md border border-slate-700/50 p-5 rounded-xl shadow-2xl overflow-hidden transition-all duration-500 transform translate-y-0 opacity-100">
                          <div className="flex items-center justify-between mb-4 border-b border-slate-700/50 pb-3">
                            <div className="flex items-center gap-2.5">
                              <div className="relative flex items-center justify-center w-5 h-5">
                                <span className="absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-20 animate-ping"></span>
                                <div className="w-2 h-2 rounded-full bg-emerald-400"></div>
                              </div>
                              <span className="text-[11px] font-bold text-emerald-400 uppercase tracking-widest flex items-center gap-2">
                                <Terminal className="w-3.5 h-3.5" />
                                Live DOM Crawler
                              </span>
                            </div>
                            <span className="text-[10px] font-mono text-slate-400 bg-slate-800 px-2 py-1 rounded">Playwright Headless</span>
                          </div>
                          
                          <div className="space-y-2.5 h-[180px] overflow-y-auto font-mono text-xs pr-2" style={{ scrollbarWidth: "thin", scrollbarColor: "#475569 transparent" }}>
                            {crawlerLogs.length === 0 ? (
                              <div className="text-slate-500 animate-pulse flex items-center gap-2">
                                <Loader2 className="w-3 h-3 animate-spin" />
                                Initializing crawler engine...
                              </div>
                            ) : (
                              crawlerLogs.map((log, i) => (
                                <div 
                                  key={i} 
                                  className={`flex items-start gap-2.5 animate-in fade-in slide-in-from-bottom-2 duration-300 ${
                                    log.type === "info" ? "text-slate-300" : 
                                    log.type === "success" ? "text-emerald-300" : "text-amber-300 animate-pulse"
                                  }`}
                                >
                                  <span className="text-purple-400 shrink-0 mt-0.5">
                                    {log.type === "info" ? "→" : log.type === "success" ? "✓" : "⟳"}
                                  </span>
                                  <span className="leading-relaxed">{log.text}</span>
                                </div>
                              ))
                            )}
                          </div>
                        </div>
                      </div>
                    </>
                  )}
                </div>
              </div>
            ) : (
              <div className="flex-1 flex items-center justify-center flex-col gap-5 p-12 text-center border border-slate-200 rounded-2xl bg-slate-50/50 shadow-sm">
                <div className="w-20 h-20 bg-white rounded-full shadow-sm flex items-center justify-center border border-slate-200 mb-2">
                  <Code2 className="w-10 h-10 text-slate-400" />
                </div>
                <div>
                  <h3 className="text-lg font-semibold text-slate-900 mb-2">Abstract Mode Selected</h3>
                  <p className="text-sm text-slate-500 max-w-sm mx-auto leading-relaxed">
                    No live DOM preview is available in abstract mode. The engine will generate test structures using placeholder locators for you to fill in later.
                  </p>
                </div>
                <button 
                  onClick={() => setMode("dom")}
                  className="mt-4 text-sm font-medium text-purple-600 hover:text-purple-700 bg-purple-50 hover:bg-purple-100 px-4 py-2 rounded-lg transition-colors"
                >
                  Switch to DOM-Aware Mode
                </button>
              </div>
            )}
          </div>

        </div>
      </div>
    </DashboardLayoutWrapper>
  );
}
