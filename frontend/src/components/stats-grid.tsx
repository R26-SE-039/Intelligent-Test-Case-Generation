"use client";

import { ReactNode } from "react";

interface StatItem {
  label: string;
  value: string | number;
  color?: "purple" | "emerald" | "red" | "blue";
  icon?: ReactNode;
}

interface StatsGridProps {
  title?: string;
  items: StatItem[];
}

const colorClasses = {
  purple: "text-purple-600",
  emerald: "text-emerald-600",
  red: "text-red-600",
  blue: "text-blue-600",
};

const bgColorClasses = {
  purple: "bg-purple-50 text-purple-600",
  emerald: "bg-emerald-50 text-emerald-600",
  red: "bg-red-50 text-red-600",
  blue: "bg-blue-50 text-blue-600",
};

export default function StatsGrid({ title, items }: StatsGridProps) {
  return (
    <div className="bg-white rounded-lg border border-slate-200 p-8">
      {title && (
        <h3 className="text-lg font-bold text-slate-900 mb-6">{title}</h3>
      )}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
        {items.map((item, idx) => (
          <div key={idx} className="text-center">
            {item.icon && (
              <div
                className={`inline-block p-3 rounded-lg mb-3 ${bgColorClasses[item.color || "purple"]}`}
              >
                {item.icon}
              </div>
            )}
            <p
              className={`text-3xl font-bold ${colorClasses[item.color || "purple"]}`}
            >
              {item.value}
            </p>
            <p className="text-sm text-slate-600 mt-2">{item.label}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
