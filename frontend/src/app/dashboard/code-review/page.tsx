"use client";

import { useState, useEffect, Suspense, useCallback } from "react";
import { useSearchParams } from "next/navigation";
import DashboardLayoutWrapper from "@/components/dashboard-layout-wrapper";
import dynamic from "next/dynamic";
import {
  Code2,
  ChevronRight,
  ChevronLeft,
  Copy,
  Check,
  Download,
  PlayCircle,
  Database,
  Loader2,
  Layers
} from "lucide-react";
import Link from "next/link";
import { generateTestCode } from "@/lib/api";
import { useProject } from "@/lib/project-context";

const MonacoEditor = dynamic(() => import("@monaco-editor/react"), { ssr: false });

type Framework = "selenium" | "playwright" | "cypress";

const initialCodeMap: Record<Framework, { language: string; filename: string; code: string; generated: boolean }> = {
  selenium: { language: "python", filename: "test_suite_selenium.py", code: "# Click 'Generate' to generate Selenium code...", generated: false },
  playwright: { language: "python", filename: "test_suite_playwright.py", code: "# Click 'Generate' to generate Playwright code...", generated: false },
  cypress: { language: "javascript", filename: "test_suite_cypress.cy.js", code: "// Click 'Generate' to generate Cypress code...", generated: false },
};

const frameworkTabs: { id: Framework; label: string; badge: string; color: string }[] = [
  { id: "selenium", label: "Selenium", badge: "Python", color: "text-blue-600" },
  { id: "playwright", label: "Playwright", badge: "Python", color: "text-emerald-600" },
  { id: "cypress", label: "Cypress", badge: "JavaScript", color: "text-amber-600" },
];

const domElements = [
  { selector: "#user-name", tag: "INPUT", step: "fill username" },
  { selector: "#password", tag: "INPUT", step: "fill password" },
  { selector: "#login-button", tag: "INPUT", step: "click login" },
  { selector: ".error-message-container", tag: "H3", step: "check error" },
  { selector: "#add-to-cart-sauce-labs-backpack", tag: "BUTTON", step: "add to cart" },
  { selector: ".shopping_cart_badge", tag: "SPAN", step: "verify cart count" },
];

function CodeReviewContent() {
  const searchParams = useSearchParams();
  const modeParam = searchParams.get("mode") || "dom";
  const fwParam = (searchParams.get("framework") as Framework) || "playwright";
  const urlParam = searchParams.get("url") || "https://www.saucedemo.com";

  const { activeProject } = useProject();

  const [activeFramework, setActiveFramework] = useState<Framework>(fwParam);
  const [codeMap, setCodeMap] = useState(initialCodeMap);
  const [copied, setCopied] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const generateCode = useCallback(async (frameworksToGenerate: Framework[]) => {
    if (!activeProject) return;
    setIsGenerating(true);
    setError(null);
    
    // Set loading text
    setCodeMap(prev => {
      const next = { ...prev };
      frameworksToGenerate.forEach(fw => {
        next[fw] = { ...next[fw], code: `/* Generating ${fw} code using LLM... Please wait... */` };
      });
      return next;
    });

    try {
      const results = await generateTestCode(activeProject.id, urlParam, modeParam, frameworksToGenerate);
      
      setCodeMap(prev => {
        const next = { ...prev };
        results.forEach(res => {
          const fw = res.framework as Framework;
          next[fw] = {
            language: res.language,
            filename: res.filename,
            code: res.code,
            generated: true
          };
        });
        return next;
      });
    } catch (err: any) {
      console.error(err);
      setError(err.message || "Failed to generate code");
      
      // Reset text on error
      setCodeMap(prev => {
        const next = { ...prev };
        frameworksToGenerate.forEach(fw => {
          next[fw] = { ...next[fw], code: `/* Generation failed for ${fw}. Please try again. */` };
        });
        return next;
      });
    } finally {
      setIsGenerating(false);
    }
  }, [activeProject, urlParam, modeParam]);

  // Initial generation for active tab
  useEffect(() => {
    if (activeProject && !codeMap[activeFramework].generated && !isGenerating) {
      generateCode([activeFramework]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeFramework, activeProject]);

  const active = codeMap[activeFramework];

  const handleCopy = async () => {
    await navigator.clipboard.writeText(active.code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownload = () => {
    const blob = new Blob([active.code], { type: "text/plain" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = active.filename;
    a.click();
  };

  const handleCodeChange = (value: string | undefined) => {
    setCodeMap((prev) => ({
      ...prev,
      [activeFramework]: { ...prev[activeFramework], code: value ?? prev[activeFramework].code },
    }));
  };

  return (
    <DashboardLayoutWrapper>
      {/* Header */}
      <div className="sticky top-0 z-10 bg-white/80 backdrop-blur-sm border-b border-slate-200 px-8 py-5">
        <div className="flex justify-between items-center">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="text-xs font-bold text-purple-700 bg-purple-50 border border-purple-200 px-2 py-0.5 rounded-full tracking-wider">
                S4
              </span>
              <span className="text-xs text-slate-500">Pipeline Stage 4 of 5</span>
            </div>
            <h1 className="text-2xl font-bold text-slate-900">Code Review</h1>
            <p className="text-slate-600 text-sm mt-0.5">
              Review and edit generated test code · Mode {modeParam === "dom" ? "B DOM-Aware" : "A Abstract"} · {urlParam}
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
            <Link
              href="/dashboard/execution"
              className="flex items-center gap-2 px-5 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg font-medium text-sm transition-all shadow-lg shadow-purple-600/30"
            >
              <PlayCircle className="w-4 h-4" />
              Run Tests
              <ChevronRight className="w-4 h-4" />
            </Link>
          </div>
        </div>
      </div>

      {error && (
        <div className="mx-6 mt-4 p-3 bg-red-50 text-red-600 text-sm rounded border border-red-200">
          {error}
        </div>
      )}

      <div className="flex gap-5 h-[calc(100vh-145px)] p-6">
        {/* Main Editor Area */}
        <div className="flex-1 flex flex-col min-w-0 rounded-xl border border-slate-200 overflow-hidden bg-white shadow-sm">
          {/* Framework Tabs */}
          <div className="flex items-center bg-slate-50 border-b border-slate-200 px-2">
            {frameworkTabs.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveFramework(tab.id)}
                className={`flex items-center gap-2 px-5 py-3 text-sm font-medium border-b-2 transition-all ${
                  activeFramework === tab.id
                    ? "border-purple-500 text-slate-900 bg-white"
                    : "border-transparent text-slate-500 hover:text-slate-800"
                }`}
              >
                <Code2 className="w-4 h-4" />
                {tab.label}
                <span className={`text-[10px] font-semibold ${tab.color}`}>{tab.badge}</span>
              </button>
            ))}
            <div className="ml-auto flex items-center gap-2 pr-2">
              <button
                onClick={() => generateCode(["selenium", "playwright", "cypress"])}
                disabled={isGenerating}
                className="flex items-center gap-1.5 text-xs text-purple-700 bg-purple-50 border border-purple-200 hover:bg-purple-100 px-3 py-1.5 rounded-md transition-all disabled:opacity-50"
              >
                {isGenerating ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Layers className="w-3.5 h-3.5" />}
                Generate All Frameworks
              </button>
              
              <div className="w-px h-5 bg-slate-200 mx-1"></div>

              <button
                onClick={handleCopy}
                className="flex items-center gap-1.5 text-xs text-slate-600 hover:text-slate-900 px-2.5 py-1.5 rounded-md hover:bg-white transition-all"
              >
                {copied ? (
                  <><Check className="w-3.5 h-3.5 text-emerald-600" /> Copied</>
                ) : (
                  <><Copy className="w-3.5 h-3.5" /> Copy</>
                )}
              </button>
              <button
                onClick={handleDownload}
                className="flex items-center gap-1.5 text-xs text-slate-600 hover:text-slate-900 px-2.5 py-1.5 rounded-md hover:bg-white transition-all"
              >
                <Download className="w-3.5 h-3.5" /> Download
              </button>
            </div>
          </div>

          {/* Filename bar */}
          <div className="px-4 py-1.5 bg-slate-50 border-b border-slate-200 flex items-center gap-2">
            <span className="text-[11px] text-slate-500 font-mono">{active.filename}</span>
            <span className="text-[10px] bg-emerald-50 text-emerald-700 border border-emerald-200 px-1.5 py-0.5 rounded">
              Mode {modeParam === "dom" ? "B · DOM-Aware" : "A · Abstract"}
            </span>
          </div>

          {/* Monaco */}
          <div className="flex-1 relative">
            {isGenerating && (
              <div className="absolute inset-0 z-10 bg-white/50 backdrop-blur-[1px] flex flex-col items-center justify-center">
                 <Loader2 className="w-8 h-8 text-purple-600 animate-spin mb-3" />
                 <p className="text-sm font-medium text-slate-700">Generating automation code via LLM...</p>
                 <p className="text-xs text-slate-500">This might take a few seconds.</p>
              </div>
            )}
            <MonacoEditor
              height="100%"
              language={active.language}
              theme="vs"
              value={active.code}
              onChange={handleCodeChange}
              options={{
                fontSize: 12.5,
                lineHeight: 22,
                minimap: { enabled: true },
                wordWrap: "off",
                scrollBeyondLastLine: false,
                padding: { top: 12 },
                fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
                fontLigatures: true,
              }}
            />
          </div>
        </div>

        {/* Right panel — DOM Element Map */}
        <div className="w-64 shrink-0 flex flex-col gap-4">
          <div className="rounded-xl border border-slate-200 overflow-hidden bg-white flex flex-col shadow-sm">
            <div className="px-4 py-3 border-b border-slate-200 flex items-center gap-2 bg-slate-50">
              <Database className="w-3.5 h-3.5 text-purple-600" />
              <p className="text-xs font-semibold text-slate-700">DOM Element Map</p>
            </div>
            <div
              className="flex-1 overflow-y-auto py-2"
              style={{ scrollbarWidth: "none" }}
            >
              {domElements.map((el) => (
                <div
                  key={el.selector}
                  className="px-4 py-2.5 hover:bg-slate-50 transition-colors border-b border-slate-100 last:border-0"
                >
                  <p className="text-[11px] font-mono text-emerald-700 mb-0.5">{el.selector}</p>
                  <div className="flex items-center justify-between">
                    <span className="text-[10px] text-slate-500 bg-slate-100 px-1.5 py-0.5 rounded font-mono">
                      {el.tag}
                    </span>
                    <span className="text-[10px] text-slate-500">{el.step}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Risk badges */}
          <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
            <p className="text-xs font-semibold text-slate-600 mb-3 flex items-center gap-2">
              ML Risk Prediction
            </p>
            {[
              { label: "Login Flow", risk: "HIGH", color: "text-red-700 bg-red-50 border-red-200" },
              { label: "Cart Operations", risk: "MEDIUM", color: "text-amber-700 bg-amber-50 border-amber-200" },
              { label: "Checkout", risk: "HIGH", color: "text-red-700 bg-red-50 border-red-200" },
              { label: "Search", risk: "LOW", color: "text-emerald-700 bg-emerald-50 border-emerald-200" },
            ].map((item) => (
              <div
                key={item.label}
                className="flex items-center justify-between py-2 border-b border-slate-100 last:border-0"
              >
                <span className="text-xs text-slate-700">{item.label}</span>
                <span className={`text-[10px] font-bold px-2 py-0.5 rounded border ${item.color}`}>
                  {item.risk}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
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
