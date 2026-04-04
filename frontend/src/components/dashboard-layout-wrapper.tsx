"use client";

import Sidebar from "@/components/sidebar";
import { useSidebar } from "@/lib/sidebar-context";

interface DashboardLayoutProps {
  children: React.ReactNode;
}

export default function DashboardLayoutWrapper({
  children,
}: DashboardLayoutProps) {
  const { isOpen } = useSidebar();
  const sidebarWidth = isOpen ? "256px" : "96px";

  return (
    <div className="flex bg-slate-950 min-h-screen">
      <Sidebar />
      <main
        className="flex-1 transition-all duration-300 ease-in-out overflow-y-auto h-screen"
        style={{
          marginLeft: sidebarWidth,
        }}
      >
        <div className="min-h-screen ">{children}</div>
      </main>
    </div>
  );
}
