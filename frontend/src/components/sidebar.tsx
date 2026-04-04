"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BarChart3,
  Zap,
  Clock,
  Smartphone,
  Shield,
  Database,
  Server,
  AlertTriangle,
  Scan,
  BarChartIcon,
  ChevronLeft,
  ChevronRight,
  LogOut,
} from "lucide-react";
import { useSidebar } from "@/lib/sidebar-context";

interface NavItem {
  label: string;
  icon: React.ReactNode;
  href: string;
}

interface NavSection {
  title: string;
  items: NavItem[];
}

const navSections: NavSection[] = [
  {
    title: "MANAGEMENT",
    items: [
      {
        label: "Test Management",
        icon: <BarChart3 className="w-5 h-5" />,
        href: "/dashboard/test-management",
      },
      {
        label: "AI Walkthrough",
        icon: <Zap className="w-5 h-5" />,
        href: "/dashboard/ai-walkthrough",
      },
      {
        label: "Test Scheduler",
        icon: <Clock className="w-5 h-5" />,
        href: "/dashboard/test-scheduler",
      },
    ],
  },
  {
    title: "TESTING",
    items: [
      {
        label: "API Testing",
        icon: <Server className="w-5 h-5" />,
        href: "/dashboard/api-testing",
      },
      {
        label: "Database Testing",
        icon: <Database className="w-5 h-5" />,
        href: "/dashboard/database-testing",
      },
      {
        label: "Performance",
        icon: <BarChartIcon className="w-5 h-5" />,
        href: "/dashboard/performance",
      },
      {
        label: "Load Testing",
        icon: <BarChartIcon className="w-5 h-5" />,
        href: "/dashboard/load-testing",
      },
      {
        label: "Mobile & Responsive",
        icon: <Smartphone className="w-5 h-5" />,
        href: "/dashboard/mobile-responsive",
      },
      {
        label: "Security Testing",
        icon: <Shield className="w-5 h-5" />,
        href: "/dashboard/security-testing",
      },
      {
        label: "SAST Scanner",
        icon: <Scan className="w-5 h-5" />,
        href: "/dashboard/sast-scanner",
      },
      {
        label: "Chaos & Resilience",
        icon: <AlertTriangle className="w-5 h-5" />,
        href: "/dashboard/chaos-resilience",
      },
      {
        label: "Blockchain Testing",
        icon: <Zap className="w-5 h-5" />,
        href: "/dashboard/blockchain-testing",
      },
    ],
  },
];

export default function Sidebar() {
  const pathname = usePathname();
  const { isOpen, setIsOpen } = useSidebar();

  const isActive = (href: string) => {
    return pathname === href || pathname.startsWith(href);
  };

  return (
    <>
      {/* Sidebar */}
      <div
        className={`${
          isOpen ? "w-64" : "w-24"
        } bg-slate-900 text-white h-screen flex flex-col fixed left-0 top-0 shadow-lg transition-all duration-300 ease-in-out z-40`}
      >
        {/* Brand Section */}
        <div className={`py-5 border-b border-slate-700 shrink-0 relative ${isOpen ? "px-4" : "px-0 flex justify-center"}`}>
          <div className="flex items-center gap-3 min-w-0">
            <div className="w-10 h-10 bg-linear-to-br from-purple-500 to-blue-500 rounded-xl flex items-center justify-center font-bold text-sm shrink-0">
              ⚡
            </div>
            {isOpen && (
              <span className="text-xl font-bold whitespace-nowrap">
                NexGen QA
              </span>
            )}
          </div>
        </div>

        {/* Absolute Toggle Button */}
        <button
          onClick={() => setIsOpen(!isOpen)}
          className="absolute -right-3.5 top-7 h-7 w-7 bg-slate-800 border border-slate-700 rounded-full flex items-center justify-center text-slate-300 hover:text-white hover:bg-slate-700 transition-all z-50 shadow-md"
          aria-label={isOpen ? "Collapse sidebar" : "Expand sidebar"}
          aria-expanded={isOpen}
        >
          {isOpen ? (
            <ChevronLeft className="w-4 h-4" />
          ) : (
            <ChevronRight className="w-4 h-4" />
          )}
        </button>

        {/* Navigation Sections - Custom Scrollbar Hidden */}
        <nav 
          className="flex-1 overflow-y-auto px-2 py-6 space-y-8 [&::-webkit-scrollbar]:hidden"
          style={{ scrollbarWidth: "none", msOverflowStyle: "none" }}
        >
          {navSections.map((section) => (
            <div key={section.title}>
              {isOpen && (
                <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-4 px-2">
                  {section.title}
                </h3>
              )}
              <ul className="space-y-2">
                {section.items.map((item) => (
                  <li key={item.href}>
                    <Link
                      href={item.href}
                      className={`flex items-center w-full min-h-11 ${isOpen ? "gap-3 px-4" : "justify-center px-0"} py-2 rounded-lg transition-all duration-200 ${
                        isActive(item.href)
                          ? "bg-purple-600 text-white shadow-md"
                          : "text-slate-300 hover:bg-slate-800 hover:text-white"
                      }`}
                      title={!isOpen ? item.label : undefined}
                    >
                      <span className="shrink-0">{item.icon}</span>
                      {isOpen && (
                        <span className="text-sm font-medium whitespace-nowrap">
                          {item.label}
                        </span>
                      )}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </nav>

        {/* User Section */}
        <div className="p-4 border-t border-slate-700 shrink-0">
          <div
            className={`flex items-center ${isOpen ? "gap-3 px-4" : "justify-center px-0"} py-3 rounded-lg bg-slate-800 mb-3`}
          >
            <div className="w-8 h-8 rounded-full bg-purple-600 flex items-center justify-center text-xs font-bold shrink-0">
              F
            </div>
            {isOpen && (
              <div className="min-w-0">
                <span className="text-sm font-medium block truncate">
                  Feroz
                </span>
                <span className="text-xs text-slate-400 block truncate">
                  ENTERPRISE
                </span>
              </div>
            )}
          </div>
          <button
            className={`w-full flex items-center ${isOpen ? "gap-3 px-4 justify-start" : "justify-center px-0"} py-2 rounded-lg text-slate-300 hover:bg-slate-800 hover:text-white transition-all duration-200`}
            title="Sign Out"
          >
            <LogOut className="w-5 h-5 shrink-0" />
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
