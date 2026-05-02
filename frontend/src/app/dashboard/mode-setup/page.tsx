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
  { id: "selenium", label: "Selenium", lang: "Python", color: "text-blue-600" },
  { id: "playwright", label: "Playwright", lang: "Python / JS", color: "text-emerald-600" },
  { id: "cypress", label: "Cypress", lang: "JavaScript", color: "text-amber-600" },
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
      <div className="sticky top-0 z-10 bg-white/80 backdrop-blur-sm border-b border-slate-200 px-8 py-5">
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
              href="/dashboard/code-review"
              className="flex items-center gap-2 px-5 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg font-medium text-sm transition-all shadow-lg shadow-purple-600/30"
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
                  ? "border-purple-500 bg-purple-50 shadow-lg shadow-purple-500/10"
                  : "border-slate-200 bg-white hover:border-slate-300"
              }`}
            >
              <div className="flex items-start justify-between mb-4">
                <div className="w-10 h-10 rounded-xl bg-slate-100 flex items-center justify-center">
                  <Code2 className="w-5 h-5 text-slate-600" />
                </div>
                <span
                  className={`text-xs font-bold px-2.5 py-1 rounded-full transition-all ${
                    mode === "abstract"
                      ? "bg-purple-600 text-white"
                      : "bg-slate-100 text-slate-500"
                  }`}
                >
                  MODE A
                </span>
              </div>
              <h3 className="text-base font-bold text-slate-900 mb-1">Abstract Generation</h3>
              <p className="text-sm text-slate-600 leading-relaxed mb-4">
                No staging URL needed. Generates Gherkin and code with{" "}
                <code className="text-amber-700 text-xs bg-amber-50 border border-amber-200 px-1.5 py-0.5 rounded">
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
                  <span className="text-[10px] font-bold text-emerald-700 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded-full">
                    RECOMMENDED
                  </span>
                  <span
                    className={`text-xs font-bold px-2.5 py-1 rounded-full transition-all ${
                      mode === "dom"
                        ? "bg-purple-600 text-white"
                        : "bg-slate-100 text-slate-500"
                    }`}
                  >
                    MODE B
                  </span>
                </div>
              </div>
              <h3 className="text-base font-bold text-slate-900 mb-1">DOM-Aware Generation</h3>
              <p className="text-sm text-slate-600 leading-relaxed mb-4">
                Crawls the live staging URL with headless Playwright. Extracts real CSS/XPath
                selectors. Produces immediately runnable tests.
              </p>
              <div className="flex items-center gap-2 text-xs text-emerald-700">
                <Zap className="w-3.5 h-3.5" />
                Highest impact — full end-to-end automation
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
                className={`flex-1 py-4 px-5 rounded-xl border-2 transition-all duration-200 text-left ${
                  framework === fw.id
                    ? "border-purple-500 bg-purple-50"
                    : "border-slate-200 bg-white hover:border-slate-300"
                }`}
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm font-bold text-slate-900">{fw.label}</span>
                  {framework === fw.id && (
                    <CheckCircle className="w-4 h-4 text-purple-600" />
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
                  URL is reachable · DOM crawler is ready to launch
                </div>
              )}
              {urlStatus === "error" && (
                <div className="flex items-center gap-2 text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
                  <AlertTriangle className="w-4 h-4" />
                  Unable to reach URL · Please check the address or use Mode A
                </div>
              )}

              {/* Element map preview */}
              <div className="mt-5 pt-4 border-t border-slate-200">
                <p className="text-xs font-semibold text-slate-500 uppercase tracking-widest mb-3">
                  SauceDemo Element Map Preview
                </p>
                <div className="rounded-lg overflow-hidden border border-slate-200">
                  <table className="w-full text-xs">
                    <thead className="bg-slate-50">
                      <tr>
                        {["Element", "CSS Selector", "Gherkin Step Matched"].map((h) => (
                          <th key={h} className="px-3 py-2 text-left text-slate-600 font-semibold">
                            {h}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-200">
                      {[
                        ["Username input", "#user-name", "When I enter valid username"],
                        ["Password input", "#password", "When I enter valid password"],
                        ["Login button", "#login-button", "And I click the login button"],
                        ["Error message", ".error-message-container", "Then I should see an error message"],
                        ["Add to cart", "#add-to-cart-sauce-labs-backpack", "When I add item to cart"],
                      ].map(([el, css, step]) => (
                        <tr key={el} className="bg-white hover:bg-slate-50 transition-colors">
                          <td className="px-3 py-2 text-slate-800">{el}</td>
                          <td className="px-3 py-2 font-mono text-emerald-700">{css}</td>
                          <td className="px-3 py-2 text-slate-600">{step}</td>
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
        <div className="p-5 bg-white border border-slate-200 rounded-2xl flex items-center justify-between shadow-sm">
          <div className="flex items-center gap-6 text-sm text-slate-600">
            <span>
              Mode:{" "}
              <span className="text-slate-900 font-semibold">
                {mode === "dom" ? "B — DOM-Aware" : "A — Abstract"}
              </span>
            </span>
            <span>
              Framework:{" "}
              <span className="text-slate-900 font-semibold capitalize">{framework}</span>
            </span>
            {mode === "dom" && (
              <span>
                URL:{" "}
                <span className="text-emerald-700 font-mono text-xs">{url}</span>
              </span>
            )}
          </div>
          <Link
            href="/dashboard/code-review"
            className="flex items-center gap-2 px-6 py-3 bg-linear-to-r from-purple-600 to-indigo-600 hover:from-purple-700 hover:to-indigo-700 text-white rounded-xl font-semibold text-sm transition-all shadow-lg shadow-purple-600/30"
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
