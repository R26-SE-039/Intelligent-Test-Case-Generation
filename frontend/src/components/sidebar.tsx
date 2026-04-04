"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BookOpen,
  FileText,
  Settings2,
  Code2,
  PlayCircle,
  ChevronLeft,
  ChevronRight,
  LogOut,
} from "lucide-react";
import { useSidebar } from "@/lib/sidebar-context";

interface NavItem {
  label: string;
  icon: React.ReactNode;
  href: string;
  step: string;
}

const navItems: NavItem[] = [
  {
    label: "User Stories",
    icon: <BookOpen className="w-5 h-5" />,
    href: "/dashboard",
    step: "S1",
  },
  {
    label: "Gherkin Editor",
    icon: <FileText className="w-5 h-5" />,
    href: "/dashboard/gherkin-editor",
    step: "S2",
  },
  {
    label: "Mode & URL Setup",
    icon: <Settings2 className="w-5 h-5" />,
    href: "/dashboard/mode-setup",
    step: "S3",
  },
  {
    label: "Code Review",
    icon: <Code2 className="w-5 h-5" />,
    href: "/dashboard/code-review",
    step: "S4",
  },
  {
    label: "Execution & Report",
    icon: <PlayCircle className="w-5 h-5" />,
    href: "/dashboard/execution",
    step: "S5",
  },
];

export default function Sidebar() {
  const pathname = usePathname();
  const { isOpen, setIsOpen } = useSidebar();

  const isActive = (href: string) => {
    if (href === "/dashboard") return pathname === "/dashboard";
    return pathname.startsWith(href);
  };

  return (
    <>
      <div
        className={`${
          isOpen ? "w-64" : "w-20"
        } bg-slate-900 text-white h-screen flex flex-col fixed left-0 top-0 shadow-xl transition-all duration-300 ease-in-out z-40`}
      >
        {/* Brand Section */}
        <div
          className={`py-5 border-b border-slate-700/60 shrink-0 relative ${
            isOpen ? "px-5" : "px-0 flex justify-center"
          }`}
        >
          <div className="flex items-center gap-3 min-w-0">
            <div className="w-10 h-10 bg-linear-to-br from-purple-500 to-indigo-600 rounded-xl flex items-center justify-center font-bold text-lg shrink-0 shadow-lg shadow-purple-500/30">
              ⚡
            </div>
            {isOpen && (
              <div className="min-w-0">
                <span className="text-lg font-bold whitespace-nowrap block leading-tight">
                  NexGen QA
                </span>
                <span className="text-xs text-purple-400 font-medium tracking-wider">
                  COMPONENT 2
                </span>
              </div>
            )}
          </div>
        </div>

        {/* Absolute Toggle Button */}
        <button
          onClick={() => setIsOpen(!isOpen)}
          className="absolute -right-3.5 top-7 h-7 w-7 bg-slate-800 border border-slate-600 rounded-full flex items-center justify-center text-slate-300 hover:text-white hover:bg-purple-600 hover:border-purple-500 transition-all z-50 shadow-md"
          aria-label={isOpen ? "Collapse sidebar" : "Expand sidebar"}
          aria-expanded={isOpen}
        >
          {isOpen ? (
            <ChevronLeft className="w-3.5 h-3.5" />
          ) : (
            <ChevronRight className="w-3.5 h-3.5" />
          )}
        </button>

        {/* Pipeline label */}
        {isOpen && (
          <div className="px-5 pt-6 pb-2">
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-widest">
              Pipeline Stages
            </p>
          </div>
        )}

        {/* Navigation */}
        <nav
          className="flex-1 overflow-y-auto px-2 py-3 space-y-1"
          style={{ scrollbarWidth: "none", msOverflowStyle: "none" }}
        >
          {navItems.map((item, index) => {
            const active = isActive(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                title={!isOpen ? `${item.step}: ${item.label}` : undefined}
                className={`group flex items-center w-full min-h-11 ${
                  isOpen ? "gap-3 px-4" : "justify-center px-0"
                } py-2.5 rounded-xl transition-all duration-200 relative ${
                  active
                    ? "bg-purple-600 text-white shadow-md shadow-purple-600/30"
                    : "text-slate-400 hover:bg-slate-800 hover:text-white"
                }`}
              >
                {/* Step indicator dot */}
                {isOpen && (
                  <span
                    className={`absolute left-0 top-1/2 -translate-y-1/2 w-1 h-6 rounded-r-full transition-all duration-200 ${
                      active ? "bg-purple-300" : "bg-transparent group-hover:bg-slate-600"
                    }`}
                  />
                )}
                <span className="shrink-0 relative">
                  {item.icon}
                  {!isOpen && (
                    <span
                      className={`absolute -top-1.5 -right-1.5 text-[9px] font-bold px-1 rounded ${
                        active
                          ? "bg-purple-400 text-white"
                          : "bg-slate-700 text-slate-400"
                      }`}
                    >
                      {index + 1}
                    </span>
                  )}
                </span>
                {isOpen && (
                  <div className="flex items-center justify-between flex-1 min-w-0">
                    <span className="text-sm font-medium whitespace-nowrap truncate">
                      {item.label}
                    </span>
                    <span
                      className={`text-[10px] font-bold px-1.5 py-0.5 rounded-md ${
                        active
                          ? "bg-purple-500/50 text-purple-200"
                          : "bg-slate-700/80 text-slate-500 group-hover:bg-slate-700 group-hover:text-slate-400"
                      }`}
                    >
                      {item.step}
                    </span>
                  </div>
                )}
              </Link>
            );
          })}
        </nav>

        {/* User Section */}
        <div className="p-3 border-t border-slate-700/60 shrink-0">
          <div
            className={`flex items-center ${
              isOpen ? "gap-3 px-3" : "justify-center px-0"
            } py-2.5 rounded-xl bg-slate-800/60 mb-2`}
          >
            <div className="w-8 h-8 rounded-full bg-linear-to-br from-purple-500 to-indigo-600 flex items-center justify-center text-xs font-bold shrink-0">
              D
            </div>
            {isOpen && (
              <div className="min-w-0">
                <span className="text-sm font-medium block truncate">
                  Dasun T
                </span>
                <span className="text-xs text-slate-400 block truncate">
                  IT22303684
                </span>
              </div>
            )}
          </div>
          <button
            className={`w-full flex items-center ${
              isOpen ? "gap-3 px-3 justify-start" : "justify-center px-0"
            } py-2 rounded-xl text-slate-400 hover:bg-slate-800 hover:text-white transition-all duration-200`}
            title="Sign Out"
          >
            <LogOut className="w-4 h-4 shrink-0" />
            {isOpen && (
              <span className="text-sm font-medium whitespace-nowrap">
                Sign Out
              </span>
            )}
          </button>
        </div>
      </div>
    </>
  );
}
