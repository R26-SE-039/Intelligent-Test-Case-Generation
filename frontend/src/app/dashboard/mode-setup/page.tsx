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
} from "lucide-react";
import Link from "next/link";

type Mode = "abstract" | "dom";
type Framework = "selenium" | "playwright" | "cypress";

const frameworks: { id: Framework; label: string; lang: string; color: string }[] = [
  { id: "selenium", label: "Selenium", lang: "Python", color: "text-blue-400" },
  { id: "playwright", label: "Playwright", lang: "Python / JS", color: "text-emerald-400" },
  { id: "cypress", label: "Cypress", lang: "JavaScript", color: "text-amber-400" },
];

export default function ModeSetupPage() {
  const [mode, setMode] = useState<Mode>("dom");
  const [framework, setFramework] = useState<Framework>("playwright");
  const [url, setUrl] = useState("https://www.saucedemo.com");
  const [urlStatus, setUrlStatus] = useState<"idle" | "checking" | "ok" | "error">("idle");

  const validateUrl = async () => {
    setUrlStatus("checking");
    await new Promise((r) => setTimeout(r, 1500));
    setUrlStatus(url.startsWith("http") ? "ok" : "error");
  };

  return (
    <DashboardLayoutWrapper>
      {/* Header */}
      <div className="sticky top-0 z-10 bg-slate-950/80 backdrop-blur-sm border-b border-slate-800 px-8 py-5">
        <div className="flex justify-between items-center">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="text-xs font-bold text-purple-400 bg-purple-500/10 border border-purple-500/20 px-2 py-0.5 rounded-full tracking-wider">
                S3
              </span>
              <span className="text-xs text-slate-500">Pipeline Stage 3 of 5</span>
            </div>
            <h1 className="text-2xl font-bold text-white">Mode &amp; URL Setup</h1>
            <p className="text-slate-400 text-sm mt-0.5">
              Choose generation mode, target framework, and staging URL
            </p>
          </div>
          <div className="flex items-center gap-3">
            <Link
              href="/dashboard/gherkin-editor"
              className="flex items-center gap-2 px-4 py-2 border border-slate-700 text-slate-400 hover:text-white hover:border-slate-600 rounded-lg text-sm transition-all"
            >
              <ChevronLeft className="w-4 h-4" />
              Back
            </Link>
            <Link
              href="/dashboard/code-review"
              className="flex items-center gap-2 px-5 py-2 bg-purple-600 hover:bg-purple-500 text-white rounded-lg font-medium text-sm transition-all shadow-lg shadow-purple-600/30"
            >
              <Zap className="w-4 h-4" />
              Generate Code
              <ChevronRight className="w-4 h-4" />
            </Link>
          </div>
        </div>
      </div>

      <div className="p-8 max-w-4xl">
        {/* Mode Selection */}
        <section className="mb-10">
          <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-widest mb-4">
            Step 1 — Generation Mode
          </h2>
          <div className="grid grid-cols-2 gap-4">
            {/* Mode A */}
            <button
              onClick={() => setMode("abstract")}
              className={`relative text-left p-6 rounded-2xl border-2 transition-all duration-200 ${
                mode === "abstract"
                  ? "border-purple-500 bg-purple-500/10 shadow-lg shadow-purple-500/10"
                  : "border-slate-700 bg-slate-800/30 hover:border-slate-600"
              }`}
            >
              <div className="flex items-start justify-between mb-4">
                <div className="w-10 h-10 rounded-xl bg-slate-700 flex items-center justify-center">
                  <Code2 className="w-5 h-5 text-slate-300" />
                </div>
                <span
                  className={`text-xs font-bold px-2.5 py-1 rounded-full transition-all ${
                    mode === "abstract"
                      ? "bg-purple-500 text-white"
                      : "bg-slate-700 text-slate-500"
                  }`}
                >
                  MODE A
                </span>
              </div>
              <h3 className="text-base font-bold text-white mb-1">Abstract Generation</h3>
              <p className="text-sm text-slate-400 leading-relaxed mb-4">
                No staging URL needed. Generates Gherkin and code with{" "}
                <code className="text-amber-400 text-xs bg-slate-700 px-1.5 py-0.5 rounded">
                  &lt;&lt;PLACEHOLDER&gt;&gt;
                </code>{" "}
                locators. QA fills in real selectors later.
              </p>
              <div className="flex items-center gap-2 text-xs text-slate-500">
                <Shield className="w-3.5 h-3.5" />
                Best when app is still in development
              </div>
              {mode === "abstract" && (
                <div className="absolute top-4 right-4">
                  <CheckCircle className="w-5 h-5 text-purple-400" />
                </div>
              )}
            </button>

            {/* Mode B */}
            <button
              onClick={() => setMode("dom")}
              className={`relative text-left p-6 rounded-2xl border-2 transition-all duration-200 ${
                mode === "dom"
                  ? "border-purple-500 bg-purple-500/10 shadow-lg shadow-purple-500/10"
                  : "border-slate-700 bg-slate-800/30 hover:border-slate-600"
              }`}
            >
              <div className="flex items-start justify-between mb-4">
                <div className="w-10 h-10 rounded-xl bg-linear-to-br from-purple-500/30 to-indigo-500/30 flex items-center justify-center">
                  <Globe className="w-5 h-5 text-purple-300" />
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-[10px] font-bold text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-2 py-0.5 rounded-full">
                    RECOMMENDED
                  </span>
                  <span
                    className={`text-xs font-bold px-2.5 py-1 rounded-full transition-all ${
                      mode === "dom"
                        ? "bg-purple-500 text-white"
                        : "bg-slate-700 text-slate-500"
                    }`}
                  >
                    MODE B
                  </span>
                </div>
              </div>
              <h3 className="text-base font-bold text-white mb-1">DOM-Aware Generation</h3>
              <p className="text-sm text-slate-400 leading-relaxed mb-4">
                Crawls the live staging URL with headless Playwright. Extracts real CSS/XPath
                selectors. Produces immediately runnable tests.
              </p>
              <div className="flex items-center gap-2 text-xs text-emerald-500">
                <Zap className="w-3.5 h-3.5" />
                Highest impact — full end-to-end automation
              </div>
              {mode === "dom" && (
                <div className="absolute top-4 right-4">
                  <CheckCircle className="w-5 h-5 text-purple-400" />
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
                className={`flex-1 py-4 px-5 rounded-xl border-2 transition-all duration-200 text-left ${
                  framework === fw.id
                    ? "border-purple-500 bg-purple-500/10"
                    : "border-slate-700 bg-slate-800/30 hover:border-slate-600"
                }`}
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm font-bold text-white">{fw.label}</span>
                  {framework === fw.id && (
                    <CheckCircle className="w-4 h-4 text-purple-400" />
                  )}
                </div>
                <span className={`text-xs font-medium ${fw.color}`}>{fw.lang}</span>
              </button>
            ))}
          </div>
          <p className="text-xs text-slate-500 mt-3 ml-1">
            💡 All three frameworks are generated simultaneously — you can switch in the Code Review step.
          </p>
        </section>

        {/* URL Input (Mode B only) */}
        {mode === "dom" && (
          <section className="mb-10">
            <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-widest mb-4">
              Step 3 — Staging URL
            </h2>
            <div className="p-6 bg-slate-800/30 border border-slate-700 rounded-2xl">
              <div className="flex gap-3 mb-3">
                <div className="relative flex-1">
                  <Globe className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
                  <input
                    value={url}
                    onChange={(e) => { setUrl(e.target.value); setUrlStatus("idle"); }}
                    placeholder="https://your-staging-app.com"
                    className="w-full pl-10 pr-4 py-3 bg-slate-900 border border-slate-600 rounded-xl text-sm text-white placeholder-slate-500 focus:outline-none focus:border-purple-500 transition-colors"
                  />
                </div>
                <button
                  onClick={validateUrl}
                  disabled={urlStatus === "checking"}
                  className="flex items-center gap-2 px-5 py-3 bg-slate-700 hover:bg-slate-600 text-white rounded-xl text-sm font-medium transition-all disabled:opacity-60"
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
                <div className="flex items-center gap-2 text-sm text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 rounded-lg px-3 py-2">
                  <CheckCircle className="w-4 h-4" />
                  URL is reachable · DOM crawler is ready to launch
                </div>
              )}
              {urlStatus === "error" && (
                <div className="flex items-center gap-2 text-sm text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">
                  <AlertTriangle className="w-4 h-4" />
                  Unable to reach URL · Please check the address or use Mode A
                </div>
              )}

              {/* Element map preview */}
              <div className="mt-5 pt-4 border-t border-slate-700">
                <p className="text-xs font-semibold text-slate-500 uppercase tracking-widest mb-3">
                  SauceDemo Element Map Preview
                </p>
                <div className="rounded-lg overflow-hidden border border-slate-700">
                  <table className="w-full text-xs">
                    <thead className="bg-slate-800">
                      <tr>
                        {["Element", "CSS Selector", "Gherkin Step Matched"].map((h) => (
                          <th key={h} className="px-3 py-2 text-left text-slate-400 font-semibold">
                            {h}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-700/50">
                      {[
                        ["Username input", "#user-name", "When I enter valid username"],
                        ["Password input", "#password", "When I enter valid password"],
                        ["Login button", "#login-button", "And I click the login button"],
                        ["Error message", ".error-message-container", "Then I should see an error message"],
                        ["Add to cart", "#add-to-cart-sauce-labs-backpack", "When I add item to cart"],
                      ].map(([el, css, step]) => (
                        <tr key={el} className="bg-slate-900/50 hover:bg-slate-800/50 transition-colors">
                          <td className="px-3 py-2 text-slate-300">{el}</td>
                          <td className="px-3 py-2 font-mono text-emerald-400">{css}</td>
                          <td className="px-3 py-2 text-slate-400">{step}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </section>
        )}

        {/* Summary & CTA */}
        <div className="p-5 bg-slate-800/50 border border-slate-700 rounded-2xl flex items-center justify-between">
          <div className="flex items-center gap-6 text-sm text-slate-400">
            <span>
              Mode:{" "}
              <span className="text-white font-semibold">
                {mode === "dom" ? "B — DOM-Aware" : "A — Abstract"}
              </span>
            </span>
            <span>
              Framework:{" "}
              <span className="text-white font-semibold capitalize">{framework}</span>
            </span>
            {mode === "dom" && (
              <span>
                URL:{" "}
                <span className="text-emerald-400 font-mono text-xs">{url}</span>
              </span>
            )}
          </div>
          <Link
            href="/dashboard/code-review"
            className="flex items-center gap-2 px-6 py-3 bg-linear-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white rounded-xl font-semibold text-sm transition-all shadow-lg shadow-purple-600/30"
          >
            <Zap className="w-4 h-4" />
            Generate Code
            <ChevronRight className="w-4 h-4" />
          </Link>
        </div>
      </div>
    </DashboardLayoutWrapper>
  );
}
