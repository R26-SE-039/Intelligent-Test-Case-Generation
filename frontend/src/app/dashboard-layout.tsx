"use client";

import Sidebar from "@/components/sidebar";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="flex bg-slate-50">
      <Sidebar />
      <main className="flex-1 ml-64">
        <div className="min-h-screen">{children}</div>
      </main>
    </div>
  );
}
