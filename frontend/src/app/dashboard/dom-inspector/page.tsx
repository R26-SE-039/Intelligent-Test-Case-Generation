"use client";

import { useEffect, useState, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import DashboardLayoutWrapper from "@/components/dashboard-layout-wrapper";
import {
  ChevronLeft,
  ChevronRight,
  Loader2,
  Search,
  Globe,
  CheckCircle,
  Trash2,
  Plus,
  RefreshCw,
  AlertTriangle,
  Pencil,
  X,
  Save,
  Terminal,
} from "lucide-react";
import {
  crawlDom,
  listDomElements,
  updateDomElement,
  addDomElement,
  deleteDomElement,
  type DomElement,
} from "@/lib/api";
import { useProject } from "@/lib/project-context";

type EditPatch = Partial<Pick<DomElement, "selector" | "role" | "tag" | "text">>;

function DomInspectorContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const modeParam = searchParams.get("mode") || "dom";
  const fwParam = searchParams.get("framework") || "playwright";
  const urlParam = searchParams.get("url") || "";

  const { activeProject } = useProject();

  const [elements, setElements] = useState<DomElement[]>([]);
  const [logs, setLogs] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isCrawling, setIsCrawling] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [editingId, setEditingId] = useState<string | null>(null);
  const [editPatch, setEditPatch] = useState<EditPatch>({});
  const [savingId, setSavingId] = useState<string | null>(null);

  const [newRow, setNewRow] = useState<{ selector: string; role: string; tag: string } | null>(null);
  const [addingNew, setAddingNew] = useState(false);

  // Load saved elements on mount — no crawl, no LLM cost.
  useEffect(() => {
    if (!activeProject || !urlParam) return;
    let cancelled = false;
    setIsLoading(true);
    setError(null);
    listDomElements(activeProject.id, urlParam)
      .then((els) => {
        if (cancelled) return;
        setElements(els);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load elements");
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [activeProject, urlParam]);

  const runCrawl = async () => {
    if (!activeProject || !urlParam) return;
    setIsCrawling(true);
    setError(null);
    setLogs(["Starting Playwright crawler…"]);
    try {
      const result = await crawlDom(activeProject.id, urlParam);
      setElements(result.elements);
      setLogs(result.logs);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Crawl failed";
      setError(message);
      setLogs((prev) => [...prev, `ERROR: ${message}`]);
    } finally {
      setIsCrawling(false);
    }
  };

  const startEdit = (el: DomElement) => {
    setEditingId(el.id);
    setEditPatch({
      selector: el.selector,
      role: el.role,
      tag: el.tag,
      text: el.text ?? "",
    });
  };

  const cancelEdit = () => {
    setEditingId(null);
    setEditPatch({});
  };

  const saveEdit = async (id: string) => {
    setSavingId(id);
    setError(null);
    try {
      const updated = await updateDomElement(id, editPatch);
      setElements((prev) => prev.map((e) => (e.id === id ? updated : e)));
      cancelEdit();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSavingId(null);
    }
  };

  const removeRow = async (id: string) => {
    setError(null);
    try {
      await deleteDomElement(id);
      setElements((prev) => prev.filter((e) => e.id !== id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    }
  };

  const toggleApprove = async (el: DomElement) => {
    setSavingId(el.id);
    try {
      const updated = await updateDomElement(el.id, { approved: !el.approved });
      setElements((prev) => prev.map((e) => (e.id === el.id ? updated : e)));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSavingId(null);
    }
  };

  const beginAdd = () => {
    setNewRow({ selector: "", role: "", tag: "DIV" });
  };

  const cancelAdd = () => {
    setNewRow(null);
  };

  const submitAdd = async () => {
    if (!activeProject || !newRow) return;
    if (!newRow.selector || !newRow.role) {
      setError("Selector and role are required");
      return;
    }
    setAddingNew(true);
    setError(null);
    try {
      const created = await addDomElement({
        project_id: activeProject.id,
        url: urlParam,
        selector: newRow.selector,
        role: newRow.role,
        tag: newRow.tag || "DIV",
        attributes: {},
        text: null,
        source_step: "manual",
        confidence: 1.0,
      });
      // Replace if role collided (server upserts by role); otherwise append.
      setElements((prev) => {
        const idx = prev.findIndex((e) => e.id === created.id);
        if (idx >= 0) {
          const next = [...prev];
          next[idx] = created;
          return next;
        }
        return [...prev, created].sort((a, b) => a.role.localeCompare(b.role));
      });
      setNewRow(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Add failed");
    } finally {
      setAddingNew(false);
    }
  };

  const continueHref = `/dashboard/code-review?mode=${modeParam}&framework=${fwParam}&url=${encodeURIComponent(urlParam)}`;

  const elementCount = elements.length;
  const editedCount = elements.filter((e) => e.edited_by_qa).length;
  const approvedCount = elements.filter((e) => e.approved).length;

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
              <span className="text-xs text-slate-500">Pipeline Stage 4 of 6</span>
            </div>
            <h1 className="text-2xl font-bold text-slate-900">DOM Inspector</h1>
            <p className="text-slate-600 text-sm mt-0.5 flex items-center gap-2">
              <Globe className="w-3.5 h-3.5 text-slate-400" />
              <span className="font-mono text-xs text-slate-700">{urlParam || "(no URL)"}</span>
            </p>
          </div>
          <div className="flex items-center gap-3">
            <Link
              href={`/dashboard/mode-setup`}
              className="flex items-center gap-2 px-4 py-2 border border-slate-300 text-slate-600 hover:text-slate-900 hover:border-slate-400 hover:bg-slate-50 rounded-lg text-sm transition-all"
            >
              <ChevronLeft className="w-4 h-4" />
              Back
            </Link>
            <button
              onClick={() => router.push(continueHref)}
              disabled={elementCount === 0}
              className="flex items-center gap-2 px-5 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg font-medium text-sm transition-all shadow-lg shadow-purple-600/30 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Continue to Code Review
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>

      {error && (
        <div className="mx-6 mt-4 p-3 bg-red-50 text-red-600 text-sm rounded border border-red-200 flex items-center gap-2">
          <AlertTriangle className="w-4 h-4" />
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_360px] gap-5 p-6">
        {/* Element table */}
        <div className="rounded-xl border border-slate-200 bg-white shadow-sm flex flex-col min-h-[500px]">
          <div className="flex items-center justify-between px-5 py-3 border-b border-slate-200">
            <div className="flex items-center gap-3">
              <h2 className="text-sm font-semibold text-slate-800">Extracted Elements</h2>
              <span className="text-xs text-slate-500">
                {elementCount} total · {editedCount} edited · {approvedCount} approved
              </span>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={beginAdd}
                disabled={!activeProject || !urlParam}
                className="flex items-center gap-1.5 text-xs text-slate-700 bg-slate-100 hover:bg-slate-200 px-3 py-1.5 rounded-md transition-all disabled:opacity-50"
              >
                <Plus className="w-3.5 h-3.5" />
                Add element
              </button>
              <button
                onClick={runCrawl}
                disabled={isCrawling || !activeProject || !urlParam}
                className="flex items-center gap-1.5 text-xs text-white bg-purple-600 hover:bg-purple-700 px-3 py-1.5 rounded-md transition-all disabled:opacity-50"
              >
                {isCrawling ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                ) : elementCount === 0 ? (
                  <Search className="w-3.5 h-3.5" />
                ) : (
                  <RefreshCw className="w-3.5 h-3.5" />
                )}
                {elementCount === 0 ? "Crawl now" : "Re-crawl"}
              </button>
            </div>
          </div>

          <div className="flex-1 overflow-auto">
            {isLoading ? (
              <div className="h-full flex items-center justify-center text-sm text-slate-500">
                <Loader2 className="w-4 h-4 animate-spin mr-2" /> Loading saved elements…
              </div>
            ) : elementCount === 0 && !newRow ? (
              <div className="h-full flex flex-col items-center justify-center text-center px-6 py-16">
                <Search className="w-8 h-8 text-purple-500 mb-3" />
                <p className="text-sm font-medium text-slate-800 mb-1">No elements extracted yet</p>
                <p className="text-xs text-slate-500 max-w-sm mb-4">
                  Click <strong>Crawl now</strong> to launch headless Chromium against{" "}
                  <span className="font-mono text-slate-700">{urlParam || "this URL"}</span> and
                  extract real selectors. Phase 2 — auth-protected pages need Phase 4.
                </p>
                <button
                  onClick={runCrawl}
                  disabled={isCrawling || !activeProject || !urlParam}
                  className="flex items-center gap-2 px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white text-sm rounded-md transition-all disabled:opacity-50"
                >
                  {isCrawling ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
                  Crawl now
                </button>
              </div>
            ) : (
              <table className="w-full text-xs">
                <thead className="bg-slate-50 border-b border-slate-200 sticky top-0">
                  <tr className="text-left text-slate-600 uppercase tracking-wider text-[10px]">
                    <th className="px-3 py-2 font-semibold">Role</th>
                    <th className="px-3 py-2 font-semibold">Selector</th>
                    <th className="px-3 py-2 font-semibold">Tag</th>
                    <th className="px-3 py-2 font-semibold">Text / Source</th>
                    <th className="px-3 py-2 font-semibold w-32">Status</th>
                    <th className="px-3 py-2 font-semibold w-24 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {newRow && (
                    <tr className="bg-purple-50/40">
                      <td className="px-3 py-2">
                        <input
                          autoFocus
                          value={newRow.role}
                          onChange={(e) => setNewRow({ ...newRow, role: e.target.value })}
                          placeholder="e.g. login_button"
                          className="w-full px-2 py-1 border border-slate-300 rounded font-mono text-xs"
                        />
                      </td>
                      <td className="px-3 py-2">
                        <input
                          value={newRow.selector}
                          onChange={(e) => setNewRow({ ...newRow, selector: e.target.value })}
                          placeholder="#login-button"
                          className="w-full px-2 py-1 border border-slate-300 rounded font-mono text-xs"
                        />
                      </td>
                      <td className="px-3 py-2">
                        <input
                          value={newRow.tag}
                          onChange={(e) => setNewRow({ ...newRow, tag: e.target.value.toUpperCase() })}
                          className="w-20 px-2 py-1 border border-slate-300 rounded font-mono text-xs"
                        />
                      </td>
                      <td className="px-3 py-2 text-slate-400 text-xs italic">manual</td>
                      <td className="px-3 py-2 text-slate-400 text-xs">new</td>
                      <td className="px-3 py-2 text-right">
                        <div className="flex justify-end gap-1">
                          <button
                            onClick={submitAdd}
                            disabled={addingNew}
                            className="p-1 text-emerald-600 hover:bg-emerald-50 rounded"
                            title="Save"
                          >
                            {addingNew ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
                          </button>
                          <button
                            onClick={cancelAdd}
                            className="p-1 text-slate-500 hover:bg-slate-100 rounded"
                            title="Cancel"
                          >
                            <X className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  )}
                  {elements.map((el) => {
                    const isEditing = editingId === el.id;
                    return (
                      <tr key={el.id} className="hover:bg-slate-50">
                        <td className="px-3 py-2 font-mono text-purple-700 align-top">
                          {isEditing ? (
                            <input
                              value={editPatch.role ?? ""}
                              onChange={(e) => setEditPatch({ ...editPatch, role: e.target.value })}
                              className="w-full px-2 py-1 border border-slate-300 rounded font-mono text-xs"
                            />
                          ) : (
                            el.role
                          )}
                        </td>
                        <td className="px-3 py-2 font-mono text-emerald-700 align-top max-w-xs">
                          {isEditing ? (
                            <input
                              value={editPatch.selector ?? ""}
                              onChange={(e) => setEditPatch({ ...editPatch, selector: e.target.value })}
                              className="w-full px-2 py-1 border border-slate-300 rounded font-mono text-xs"
                            />
                          ) : (
                            <span className="break-all">{el.selector}</span>
                          )}
                        </td>
                        <td className="px-3 py-2 align-top">
                          {isEditing ? (
                            <input
                              value={editPatch.tag ?? ""}
                              onChange={(e) => setEditPatch({ ...editPatch, tag: e.target.value.toUpperCase() })}
                              className="w-20 px-2 py-1 border border-slate-300 rounded font-mono text-xs"
                            />
                          ) : (
                            <span className="text-[10px] bg-slate-100 px-1.5 py-0.5 rounded font-mono text-slate-600">
                              {el.tag}
                            </span>
                          )}
                        </td>
                        <td className="px-3 py-2 text-slate-600 align-top max-w-xs">
                          <div className="truncate">{el.text || <span className="text-slate-400 italic">—</span>}</div>
                          <div className="text-[10px] text-slate-400 mt-0.5 font-mono truncate">
                            {el.source_step ?? "—"}
                            {typeof el.confidence === "number" && (
                              <span className="ml-1">· {(el.confidence * 100).toFixed(0)}%</span>
                            )}
                          </div>
                        </td>
                        <td className="px-3 py-2 align-top">
                          <div className="flex flex-col gap-1">
                            {el.edited_by_qa && (
                              <span className="text-[10px] bg-amber-50 text-amber-700 border border-amber-200 px-1.5 py-0.5 rounded inline-flex items-center gap-1 w-fit">
                                <Pencil className="w-2.5 h-2.5" /> edited
                              </span>
                            )}
                            <button
                              onClick={() => toggleApprove(el)}
                              disabled={savingId === el.id}
                              className={`text-[10px] px-1.5 py-0.5 rounded border inline-flex items-center gap-1 w-fit transition-colors ${
                                el.approved
                                  ? "bg-emerald-50 text-emerald-700 border-emerald-200 hover:bg-emerald-100"
                                  : "bg-slate-50 text-slate-500 border-slate-200 hover:bg-slate-100"
                              }`}
                            >
                              {savingId === el.id ? (
                                <Loader2 className="w-2.5 h-2.5 animate-spin" />
                              ) : (
                                <CheckCircle className="w-2.5 h-2.5" />
                              )}
                              {el.approved ? "approved" : "approve"}
                            </button>
                          </div>
                        </td>
                        <td className="px-3 py-2 text-right align-top">
                          <div className="flex justify-end gap-1">
                            {isEditing ? (
                              <>
                                <button
                                  onClick={() => saveEdit(el.id)}
                                  disabled={savingId === el.id}
                                  className="p-1 text-emerald-600 hover:bg-emerald-50 rounded"
                                  title="Save"
                                >
                                  {savingId === el.id ? (
                                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                  ) : (
                                    <Save className="w-3.5 h-3.5" />
                                  )}
                                </button>
                                <button
                                  onClick={cancelEdit}
                                  className="p-1 text-slate-500 hover:bg-slate-100 rounded"
                                  title="Cancel"
                                >
                                  <X className="w-3.5 h-3.5" />
                                </button>
                              </>
                            ) : (
                              <>
                                <button
                                  onClick={() => startEdit(el)}
                                  className="p-1 text-slate-500 hover:text-purple-700 hover:bg-purple-50 rounded"
                                  title="Edit"
                                >
                                  <Pencil className="w-3.5 h-3.5" />
                                </button>
                                <button
                                  onClick={() => removeRow(el.id)}
                                  className="p-1 text-slate-500 hover:text-red-600 hover:bg-red-50 rounded"
                                  title="Delete"
                                >
                                  <Trash2 className="w-3.5 h-3.5" />
                                </button>
                              </>
                            )}
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>
        </div>

        {/* Crawl log panel */}
        <div className="rounded-xl border border-slate-200 bg-slate-900 shadow-sm flex flex-col min-h-[500px]">
          <div className="flex items-center gap-2 px-4 py-3 border-b border-slate-700/50">
            <div className="relative w-2 h-2">
              <span
                className={`absolute inline-flex h-full w-full rounded-full opacity-30 ${
                  isCrawling ? "bg-emerald-400 animate-ping" : "bg-slate-500"
                }`}
              />
              <span
                className={`relative w-2 h-2 rounded-full ${
                  isCrawling ? "bg-emerald-400" : "bg-slate-500"
                }`}
              />
            </div>
            <Terminal className="w-3.5 h-3.5 text-emerald-400" />
            <span className="text-[11px] font-bold text-emerald-400 uppercase tracking-widest">
              Crawler Log
            </span>
            <span className="ml-auto text-[10px] font-mono text-slate-400 bg-slate-800 px-2 py-0.5 rounded">
              Playwright Headless
            </span>
          </div>
          <div className="flex-1 overflow-auto px-4 py-3 font-mono text-[11px] space-y-1.5 text-slate-300">
            {logs.length === 0 ? (
              <div className="text-slate-500 italic">No crawler runs yet. Click "Crawl now" to start.</div>
            ) : (
              logs.map((line, i) => {
                const isError = line.toLowerCase().includes("error");
                const isFound = line.toLowerCase().startsWith("extracted") || line.includes("Found ");
                return (
                  <div
                    key={i}
                    className={`flex gap-2 ${isError ? "text-red-400" : isFound ? "text-emerald-300" : "text-slate-300"}`}
                  >
                    <span className="text-purple-400 shrink-0">{isError ? "!" : isFound ? "✓" : "→"}</span>
                    <span className="leading-relaxed break-all">{line}</span>
                  </div>
                );
              })
            )}
            {isCrawling && (
              <div className="flex items-center gap-2 text-amber-300 animate-pulse">
                <Loader2 className="w-3 h-3 animate-spin" />
                <span>Crawling…</span>
              </div>
            )}
          </div>
        </div>
      </div>
    </DashboardLayoutWrapper>
  );
}

export default function DomInspectorPage() {
  return (
    <Suspense fallback={<div className="p-8">Loading DOM Inspector…</div>}>
      <DomInspectorContent />
    </Suspense>
  );
}
