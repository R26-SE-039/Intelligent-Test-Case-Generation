"use client";

import DashboardLayoutWrapper from "@/components/dashboard-layout-wrapper";
import { BarChart3, ArrowLeft } from "lucide-react";
import Link from "next/link";

export default function TestManagementPage() {
  return (
    <DashboardLayoutWrapper>
      {/* Header */}
      <div className="sticky top-0 bg-white border-b border-slate-200 px-8 py-6 shadow-sm">
        <Link
          href="/dashboard"
          className="flex items-center gap-2 text-purple-600 hover:text-purple-700 mb-4 font-medium"
        >
          <ArrowLeft className="w-4 h-4" />
          Back to Dashboard
        </Link>
        <h1 className="text-3xl font-bold text-slate-900">Test Management</h1>
        <p className="text-slate-600 mt-1">
          Organize and manage all your test cases
        </p>
      </div>

      {/* Content Area */}
      <div className="p-8">
        <div className="bg-white rounded-lg border border-slate-200 p-8">
          <div className="flex items-start gap-6 mb-8">
            <div className="p-4 bg-purple-100 rounded-lg text-purple-600">
              <BarChart3 className="w-8 h-8" />
            </div>
            <div>
              <h2 className="text-2xl font-bold text-slate-900 mb-2">
                Test Management Dashboard
              </h2>
              <p className="text-slate-600">
                Create, manage, and track all your test cases across different
                testing frameworks and methodologies.
              </p>
            </div>
          </div>

          <div className="bg-slate-50 rounded-lg p-6">
            <p className="text-slate-600">
              Test management details and controls will appear here...
            </p>
          </div>
        </div>
      </div>
    </DashboardLayoutWrapper>
  );
}
