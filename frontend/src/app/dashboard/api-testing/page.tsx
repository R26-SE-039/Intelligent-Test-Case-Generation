"use client";

import DashboardLayoutWrapper from "@/components/dashboard-layout-wrapper";
import { Server, ArrowLeft } from "lucide-react";
import Link from "next/link";

export default function ApiTestingPage() {
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
        <h1 className="text-3xl font-bold text-slate-900">API Testing</h1>
        <p className="text-slate-600 mt-1">
          RESTful API & GraphQL Endpoint Testing
        </p>
      </div>

      {/* Content Area */}
      <div className="p-8">
        <div className="bg-white rounded-lg border border-slate-200 p-8">
          <div className="flex items-start gap-6 mb-8">
            <div className="p-4 bg-blue-100 rounded-lg text-blue-600">
              <Server className="w-8 h-8" />
            </div>
            <div>
              <h2 className="text-2xl font-bold text-slate-900 mb-2">
                API Test Suite
              </h2>
              <p className="text-slate-600">
                Comprehensive API testing with response validation,
                authentication, and performance monitoring.
              </p>
            </div>
          </div>

          <div className="bg-slate-50 rounded-lg p-6">
            <p className="text-slate-600">
              API test details and results will appear here...
            </p>
          </div>
        </div>
      </div>
    </DashboardLayoutWrapper>
  );
}
