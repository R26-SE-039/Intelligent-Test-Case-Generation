"use client";

import { ReactNode } from "react";

interface TestCardProps {
  title: string;
  testsCount: number;
  passedCount: number;
  icon: ReactNode;
  tool: string;
  description: string;
  url?: string;
  framework?: string;
  onRunClick?: () => void;
  onReportClick?: () => void;
}

export default function TestCard({
  title,
  testsCount,
  passedCount,
  icon,
  tool,
  description,
  url,
  framework,
  onRunClick,
  onReportClick,
}: TestCardProps) {
  const successRate = Math.round((passedCount / testsCount) * 100);

  return (
    <div className="bg-white rounded-lg border border-slate-200 overflow-hidden hover:shadow-lg transition-shadow duration-200">
      {/* Card Header */}
      <div className="p-6 border-b border-slate-200 bg-gradient-to-r from-slate-50 to-white">
        <div className="flex items-start justify-between mb-4">
          <h2 className="text-xl font-bold text-slate-900">{title}</h2>
          <div className="p-3 bg-purple-100 rounded-lg text-purple-600">
            {icon}
          </div>
        </div>
        <p className="text-sm text-slate-600">{tool}</p>
      </div>

      {/* Card Body */}
      <div className="p-6">
        {/* Test Stats */}
        <div className="grid grid-cols-2 gap-4 mb-6">
          <div className="bg-slate-50 rounded-lg p-4">
            <p className="text-xs text-slate-600 uppercase tracking-wide font-semibold mb-1">
              Total Tests
            </p>
            <p className="text-2xl font-bold text-slate-900">{testsCount}</p>
          </div>
          <div className="bg-emerald-50 rounded-lg p-4">
            <p className="text-xs text-emerald-600 uppercase tracking-wide font-semibold mb-1">
              Passed
            </p>
            <p className="text-2xl font-bold text-emerald-600">{passedCount}</p>
          </div>
        </div>

        {/* Progress Bar */}
        <div className="mb-6">
          <div className="flex justify-between items-center mb-2">
            <p className="text-sm font-medium text-slate-700">Success Rate</p>
            <p className="text-sm font-bold text-purple-600">{successRate}%</p>
          </div>
          <div className="w-full bg-slate-200 rounded-full h-2">
            <div
              className="bg-gradient-to-r from-purple-500 to-blue-500 h-2 rounded-full transition-all duration-300"
              style={{
                width: `${successRate}%`,
              }}
            />
          </div>
        </div>

        <p className="text-sm text-slate-600 mb-6">{description}</p>

        {url && (
          <div className="bg-slate-50 rounded-lg p-3 mb-6">
            <p className="text-xs text-slate-600 mb-1">Target URL</p>
            <p className="text-sm font-mono text-purple-600 break-all">{url}</p>
          </div>
        )}

        {framework && (
          <div className="bg-blue-50 rounded-lg p-3 mb-6">
            <p className="text-xs text-blue-600 mb-1">Framework</p>
            <p className="text-sm font-semibold text-blue-700">{framework}</p>
          </div>
        )}

        {/* Action Buttons */}
        <div className="flex gap-3">
          <button
            onClick={onRunClick}
            className="flex-1 bg-purple-600 hover:bg-purple-700 text-white px-4 py-2 rounded-lg font-medium transition-colors duration-200"
          >
            Run Test
          </button>
          <button
            onClick={onReportClick}
            className="flex-1 bg-slate-100 hover:bg-slate-200 text-slate-900 px-4 py-2 rounded-lg font-medium transition-colors duration-200"
          >
            View Report
          </button>
        </div>
      </div>
    </div>
  );
}
