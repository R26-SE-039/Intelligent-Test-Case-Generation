"use client";

import { useState } from "react";
import DashboardLayoutWrapper from "@/components/dashboard-layout-wrapper";
import {
  CheckCircle,
  Clock,
  Zap,
  ChevronRight,
  Plus,
  RefreshCw,
  Filter,
  User,
} from "lucide-react";
import Link from "next/link";

type Priority = "high" | "medium" | "low";
type Status = "pending" | "processing" | "done";

interface UserStory {
  id: string;
  actor: string;
  action: string;
  goal: string;
  priority: Priority;
  status: Status;
  acceptanceCriteria: string[];
  source: "C1" | "manual";
}

const mockStories: UserStory[] = [
  {
    id: "US-001",
    actor: "registered customer",
    action: "log in to the system",
    goal: "access my order history",
    priority: "high",
    status: "pending",
    source: "C1",
    acceptanceCriteria: [
      "Login succeeds with valid credentials",
      "Login fails with invalid credentials showing error",
      "Session persists across page refresh",
    ],
  },
  {
    id: "US-002",
    actor: "shopper",
    action: "add items to the shopping cart",
    goal: "purchase multiple products in one transaction",
    priority: "high",
    status: "done",
    source: "C1",
    acceptanceCriteria: [
      "Item appears in cart after clicking Add to Cart",
      "Cart count badge updates immediately",
      "Item can be removed from cart",
    ],
  },
  {
    id: "US-003",
    actor: "registered customer",
    action: "complete the checkout process",
    goal: "receive order confirmation",
    priority: "medium",
    status: "pending",
    source: "C1",
    acceptanceCriteria: [
      "User can fill in shipping details",
      "Order summary is shown before final confirmation",
      "Confirmation email is triggered on success",
    ],
  },
  {
    id: "US-004",
    actor: "guest user",
    action: "search for products",
    goal: "find items without creating an account",
    priority: "medium",
    status: "processing",
    source: "C1",
    acceptanceCriteria: [
      "Search returns relevant results",
      "Empty state is shown with no results",
      "Filters work correctly",
    ],
  },
  {
    id: "US-005",
    actor: "admin",
    action: "reset a user password",
    goal: "help locked-out customers regain access",
    priority: "low",
    status: "pending",
    source: "C1",
    acceptanceCriteria: [
      "Admin can search user by email",
      "Reset link is sent to user email",
      "Old password is invalidated immediately",
    ],
  },
];

const priorityConfig: Record<Priority, { label: string; color: string; bg: string }> = {
  high: { label: "HIGH", color: "text-red-400", bg: "bg-red-500/10 border border-red-500/20" },
  medium: { label: "MED", color: "text-amber-400", bg: "bg-amber-500/10 border border-amber-500/20" },
  low: { label: "LOW", color: "text-emerald-400", bg: "bg-emerald-500/10 border border-emerald-500/20" },
};

const statusConfig: Record<Status, { label: string; icon: React.ReactNode; color: string }> = {
  pending: { label: "Pending", icon: <Clock className="w-3.5 h-3.5" />, color: "text-slate-400" },
  processing: { label: "Processing", icon: <RefreshCw className="w-3.5 h-3.5 animate-spin" />, color: "text-blue-400" },
  done: { label: "Done", icon: <CheckCircle className="w-3.5 h-3.5" />, color: "text-emerald-400" },
};

export default function UserStoryIntakePage() {
  const [stories, setStories] = useState<UserStory[]>(mockStories);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [showManual, setShowManual] = useState(false);
  const [manualInput, setManualInput] = useState("");
  const [filterPriority, setFilterPriority] = useState<Priority | "all">("all");

  const toggle = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const toggleAll = () => {
    if (selected.size === stories.length) setSelected(new Set());
    else setSelected(new Set(stories.map((s) => s.id)));
  };

  const addManualStory = () => {
    if (!manualInput.trim()) return;
    const newStory: UserStory = {
      id: `US-${String(stories.length + 1).padStart(3, "0")}`,
      actor: "QA engineer",
      action: manualInput.trim(),
      goal: "validate expected behaviour",
      priority: "medium",
      status: "pending",
      source: "manual",
      acceptanceCriteria: ["Scenario behaves as described by the user"],
    };
    setStories((prev) => [newStory, ...prev]);
    setManualInput("");
    setShowManual(false);
  };

  const filtered =
    filterPriority === "all"
      ? stories
      : stories.filter((s) => s.priority === filterPriority);

  const stats = {
    total: stories.length,
    pending: stories.filter((s) => s.status === "pending").length,
    processing: stories.filter((s) => s.status === "processing").length,
    done: stories.filter((s) => s.status === "done").length,
  };

  return (
    <DashboardLayoutWrapper>
      {/* Page Header */}
      <div className="sticky top-0 z-10 bg-slate-950/80 backdrop-blur-sm border-b border-slate-800 px-8 py-5">
        <div className="flex justify-between items-center">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="text-xs font-bold text-purple-400 bg-purple-500/10 border border-purple-500/20 px-2 py-0.5 rounded-full tracking-wider">
                S1
              </span>
              <span className="text-xs text-slate-500">Pipeline Stage 1 of 5</span>
            </div>
            <h1 className="text-2xl font-bold text-white">User Story Intake</h1>
            <p className="text-slate-400 text-sm mt-0.5">
              Review stories from Component 1 · Select to generate test cases
            </p>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={() => setShowManual((v) => !v)}
              className="flex items-center gap-2 px-4 py-2 rounded-lg border border-slate-700 text-slate-300 hover:border-purple-500 hover:text-purple-300 transition-all text-sm font-medium"
            >
              <Plus className="w-4 h-4" />
              Add Manually
            </button>
            {selected.size > 0 && (
              <Link
                href="/dashboard/gherkin-editor"
                className="flex items-center gap-2 px-5 py-2 bg-purple-600 hover:bg-purple-500 text-white rounded-lg font-medium text-sm transition-all shadow-lg shadow-purple-600/30"
              >
                <Zap className="w-4 h-4" />
                Generate Gherkin ({selected.size})
                <ChevronRight className="w-4 h-4" />
              </Link>
            )}
          </div>
        </div>
      </div>

      <div className="p-8">
        {/* Stats Row */}
        <div className="grid grid-cols-4 gap-4 mb-8">
          {[
            {
              label: "Total Stories",
              value: stats.total,
              color: "text-violet-400",
              bg: "bg-violet-500/10 border-violet-500/30",
              dot: "bg-violet-400",
            },
            {
              label: "Pending",
              value: stats.pending,
              color: "text-slate-200",
              bg: "bg-slate-800/60 border-slate-700",
              dot: "bg-slate-400",
            },
            {
              label: "Processing",
              value: stats.processing,
              color: "text-sky-400",
              bg: "bg-sky-500/10 border-sky-500/30",
              dot: "bg-sky-400",
            },
            {
              label: "Completed",
              value: stats.done,
              color: "text-emerald-400",
              bg: "bg-emerald-500/10 border-emerald-500/30",
              dot: "bg-emerald-400",
            },
          ].map((s) => (
            <div
              key={s.label}
              className={`rounded-xl border ${s.bg} p-4 transition-all hover:scale-[1.02]`}
            >
              <div className="flex items-center gap-2 mb-2">
                <span className={`w-2 h-2 rounded-full ${s.dot}`} />
                <p className="text-xs text-slate-400 font-medium">{s.label}</p>
              </div>
              <p className={`text-3xl font-bold ${s.color}`}>{s.value}</p>
            </div>
          ))}
        </div>

        {/* Manual Input Panel */}
        {showManual && (
          <div className="mb-6 p-5 bg-slate-800/50 border border-slate-700 rounded-xl">
            <div className="flex items-center gap-2 mb-3">
              <User className="w-4 h-4 text-purple-400" />
              <p className="text-sm font-semibold text-white">Add Story Manually</p>
              <span className="text-xs text-slate-500 ml-1">
                — Type a plain-English test description
              </span>
            </div>
            <div className="flex gap-3">
              <input
                value={manualInput}
                onChange={(e) => setManualInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && addManualStory()}
                placeholder='e.g. "test that login fails with wrong password"'
                className="flex-1 bg-slate-900 border border-slate-600 rounded-lg px-4 py-2.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-purple-500 transition-colors"
              />
              <button
                onClick={addManualStory}
                className="px-4 py-2.5 bg-purple-600 hover:bg-purple-500 text-white rounded-lg text-sm font-medium transition-all"
              >
                Add Story
              </button>
              <button
                onClick={() => setShowManual(false)}
                className="px-4 py-2.5 border border-slate-600 text-slate-400 hover:text-white rounded-lg text-sm transition-all"
              >
                Cancel
              </button>
            </div>
          </div>
        )}

        {/* Toolbar */}
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <button
              onClick={toggleAll}
              className="text-xs text-slate-400 hover:text-white transition-colors flex items-center gap-1.5"
            >
              <div
                className={`w-4 h-4 rounded border transition-all ${
                  selected.size === stories.length
                    ? "bg-purple-600 border-purple-600"
                    : "border-slate-600"
                }`}
              >
                {selected.size === stories.length && (
                  <CheckCircle className="w-4 h-4 text-white" />
                )}
              </div>
              Select All
            </button>
            <span className="text-slate-700">|</span>
            <div className="flex items-center gap-1.5 text-xs text-slate-400">
              <Filter className="w-3.5 h-3.5" />
              {(["all", "high", "medium", "low"] as const).map((p) => (
                <button
                  key={p}
                  onClick={() => setFilterPriority(p)}
                  className={`px-2.5 py-1 rounded-md transition-all capitalize ${
                    filterPriority === p
                      ? "bg-slate-700 text-white"
                      : "text-slate-500 hover:text-slate-300"
                  }`}
                >
                  {p}
                </button>
              ))}
            </div>
          </div>
          <p className="text-xs text-slate-500">
            {selected.size > 0 ? `${selected.size} selected` : `${filtered.length} stories`}
          </p>
        </div>

        {/* Story Cards */}
        <div className="space-y-3">
          {filtered.map((story) => {
            const pCfg = priorityConfig[story.priority];
            const sCfg = statusConfig[story.status];
            const isSelected = selected.has(story.id);

            return (
              <div
                key={story.id}
                onClick={() => toggle(story.id)}
                className={`group relative rounded-xl border cursor-pointer transition-all duration-200 ${
                  isSelected
                    ? "border-purple-500/60 bg-purple-500/5 shadow-md shadow-purple-500/10"
                    : "border-slate-700/60 bg-slate-800/30 hover:border-slate-600 hover:bg-slate-800/50"
                }`}
              >
                <div className="p-5">
                  <div className="flex items-start gap-4">
                    {/* Checkbox */}
                    <div
                      className={`mt-0.5 w-5 h-5 rounded-md border-2 flex items-center justify-center shrink-0 transition-all ${
                        isSelected
                          ? "bg-purple-600 border-purple-600"
                          : "border-slate-600 group-hover:border-slate-500"
                      }`}
                    >
                      {isSelected && <CheckCircle className="w-4 h-4 text-white" />}
                    </div>

                    {/* Content */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap mb-2">
                        <span className="text-xs font-mono font-bold text-purple-400">
                          {story.id}
                        </span>
                        <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${pCfg.bg} ${pCfg.color}`}>
                          {pCfg.label}
                        </span>
                        <span className={`flex items-center gap-1 text-[11px] ${sCfg.color}`}>
                          {sCfg.icon} {sCfg.label}
                        </span>
                        {story.source === "manual" && (
                          <span className="text-[10px] text-amber-400 bg-amber-500/10 border border-amber-500/20 px-2 py-0.5 rounded-full">
                            MANUAL
                          </span>
                        )}
                      </div>

                      <p className="text-sm text-white font-medium mb-1">
                        As a{" "}
                        <span className="text-purple-300">{story.actor}</span>, I want to{" "}
                        <span className="text-white">{story.action}</span>, so that I can{" "}
                        <span className="text-slate-300">{story.goal}</span>.
                      </p>

                      <div className="mt-3 flex flex-wrap gap-2">
                        {story.acceptanceCriteria.map((ac, i) => (
                          <span
                            key={i}
                            className="text-[11px] bg-slate-700/50 text-slate-400 px-2.5 py-1 rounded-lg border border-slate-700"
                          >
                            ✓ {ac}
                          </span>
                        ))}
                      </div>
                    </div>

                    {/* Right action */}
                    <div className="shrink-0 flex items-center gap-2">
                      {story.status === "done" && (
                        <span className="text-[11px] text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-2.5 py-1 rounded-lg">
                          Tests Generated
                        </span>
                      )}
                      <ChevronRight
                        className={`w-4 h-4 transition-all ${
                          isSelected ? "text-purple-400" : "text-slate-600 group-hover:text-slate-400"
                        }`}
                      />
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>

        {/* Bottom CTA */}
        {selected.size > 0 && (
          <div className="mt-8 flex justify-center">
            <Link
              href="/dashboard/gherkin-editor"
              className="flex items-center gap-3 px-8 py-4 bg-linear-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white rounded-xl font-semibold text-base transition-all shadow-xl shadow-purple-600/30 hover:shadow-purple-500/40 hover:scale-[1.02]"
            >
              <Zap className="w-5 h-5" />
              Generate Gherkin for {selected.size} stor{selected.size > 1 ? "ies" : "y"}
              <ChevronRight className="w-5 h-5" />
            </Link>
          </div>
        )}
      </div>
    </DashboardLayoutWrapper>
  );
}
