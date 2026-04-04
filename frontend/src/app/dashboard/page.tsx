"use client";

import DashboardLayoutWrapper from "@/components/dashboard-layout-wrapper";
import TestCard from "@/components/test-card";
import StatsGrid from "@/components/stats-grid";
import {
  CheckCircle,
  AlertCircle,
  Clock,
  PlayCircle,
  TrendingUp,
  Target,
} from "lucide-react";

interface TestCard {
  title: string;
  testsCount: number;
  passedCount: number;
  icon: React.ReactNode;
  tool: string;
  description: string;
  url?: string;
}

const testCards: TestCard[] = [
  {
    title: "Accessibility",
    testsCount: 17,
    passedCount: 8,
    icon: <AlertCircle className="w-8 h-8" />,
    tool: "Axe-Core & Playwright",
    description: "Comprehensive WCAG 2.1 accessibility audit engine",
    url: "https://www.qa-automation.com",
  },
  {
    title: "508 Compliance",
    testsCount: 12,
    passedCount: 10,
    icon: <CheckCircle className="w-8 h-8" />,
    tool: "Axe-Core Backend Live",
    description:
      "Comprehensive WCAG 2.1 & Section 508 accessibility audit engine powered by Playwright and axe-core.",
  },
  {
    title: "Performance Testing",
    testsCount: 24,
    passedCount: 22,
    icon: <Clock className="w-8 h-8" />,
    tool: "Lighthouse & WebVitals",
    description: "Real user monitoring and performance metrics tracking",
  },
];

export default function DashboardPage() {
  return (
    <DashboardLayoutWrapper>
      {/* Header */}
      <div className="sticky top-0 bg-white border-b border-slate-200 px-8 py-6 shadow-sm">
        <div className="flex justify-between items-center">
          <div>
            <h1 className="text-3xl font-bold text-slate-900">
              Testing Dashboard
            </h1>
            <p className="text-slate-600 mt-1">
              Monitor all your test executions and results
            </p>
          </div>
          <button className="bg-purple-600 hover:bg-purple-700 text-white px-6 py-2 rounded-lg font-medium transition-colors duration-200 flex items-center gap-2">
            <PlayCircle className="w-5 h-5" />
            Run All Tests
          </button>
        </div>
      </div>

      {/* Content Area */}
      <div className="p-8">
        {/* Test Cards Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-6 mb-12">
          {testCards.map((test, idx) => (
            <TestCard
              key={idx}
              title={test.title}
              testsCount={test.testsCount}
              passedCount={test.passedCount}
              icon={test.icon}
              tool={test.tool}
              description={test.description}
              url={test.url}
              onRunClick={() => console.log(`Running ${test.title}`)}
              onReportClick={() =>
                console.log(`Viewing report for ${test.title}`)
              }
            />
          ))}
        </div>

        {/* Quick Stats Section */}
        <StatsGrid
          title="Overall Statistics"
          items={[
            {
              label: "Total Tests",
              value: 53,
              color: "purple",
              icon: <Target className="w-5 h-5" />,
            },
            {
              label: "Passed",
              value: 40,
              color: "emerald",
              icon: <CheckCircle className="w-5 h-5" />,
            },
            {
              label: "Failed",
              value: 13,
              color: "red",
              icon: <AlertCircle className="w-5 h-5" />,
            },
            {
              label: "Success Rate",
              value: "75%",
              color: "blue",
              icon: <TrendingUp className="w-5 h-5" />,
            },
          ]}
        />
      </div>
    </DashboardLayoutWrapper>
  );
}
