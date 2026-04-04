"use client";

import { ReactNode } from "react";

interface DashboardHeaderProps {
  title: string;
  subtitle?: string;
  actionButton?: {
    label: string;
    icon?: ReactNode;
    onClick?: () => void;
  };
}

export default function DashboardHeader({
  title,
  subtitle,
  actionButton,
}: DashboardHeaderProps) {
  return (
    <div className="sticky top-0 bg-slate-950/80 backdrop-blur-sm border-b border-slate-800 px-8 py-6">
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold text-white">{title}</h1>
          {subtitle && <p className="text-slate-400 mt-1">{subtitle}</p>}
        </div>
        {actionButton && (
          <button
            onClick={actionButton.onClick}
            className="bg-purple-600 hover:bg-purple-500 text-white px-6 py-2 rounded-lg font-medium transition-colors duration-200 flex items-center gap-2 shadow-lg shadow-purple-600/30"
          >
            {actionButton.icon}
            {actionButton.label}
          </button>
        )}
      </div>
    </div>
  );
}
