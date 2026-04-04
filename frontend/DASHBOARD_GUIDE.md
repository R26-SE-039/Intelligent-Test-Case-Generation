# NexGen QA Dashboard - Implementation Guide

## Overview

A modern, responsive testing dashboard built with Next.js, Tailwind CSS, and shadcn-inspired components. The dashboard features a dark sidebar navigation, white content area, and purple/blue accent colors matching the NexGen QA brand.

## Project Structure

```
frontend/src/
├── app/
│   ├── page.tsx                           # Root page (redirects to /dashboard)
│   ├── layout.tsx                         # Root layout wrapper
│   ├── globals.css                        # Global styles
│   └── dashboard/
│       ├── page.tsx                       # Main dashboard with test cards
│       ├── accessibility/
│       │   └── page.tsx                   # Accessibility testing page
│       ├── api-testing/
│       │   └── page.tsx                   # API testing page
│       ├── test-management/
│       │   └── page.tsx                   # Test management page
│       ├── database-testing/
│       │   └── page.tsx                   # Database testing page
│       ├── security-testing/
│       │   └── page.tsx                   # Security testing page
│       └── [other testing categories]/    # Add more pages as needed
│
├── components/
│   ├── sidebar.tsx                        # Main sidebar navigation component
│   ├── test-card.tsx                      # Reusable test result card component
│   ├── dashboard-header.tsx               # Reusable dashboard header component
│   └── [other components]/
│
└── lib/
    └── [utilities]/                       # Helper functions and constants

```

## Key Components

### 1. **Sidebar Component** (`sidebar.tsx`)

Main navigation sidebar with:

- Brand logo and name
- Navigation sections (MANAGEMENT, TESTING)
- Menu items with Lucide React icons
- User profile section
- Active state highlighting
- Responsive layout

**Features:**

- Dark navy background (#1e293b - slate-900)
- Purple accent on active links (#9333ea - purple-600)
- Smooth transitions
- Sticky positioning

**Usage:**

```tsx
import Sidebar from "@/components/sidebar";

export default function Layout() {
  return (
    <div className="flex">
      <Sidebar />
      <main className="flex-1 ml-64">{children}</main>
    </div>
  );
}
```

### 2. **Test Card Component** (`test-card.tsx`)

Reusable card for displaying test results:

- Test title and statistics
- Pass/fail counts
- Success rate with progress bar
- Target URL (optional)
- Framework info (optional)
- Action buttons (Run Test, View Report)

**Props:**

```tsx
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
```

**Usage:**

```tsx
<TestCard
  title="Accessibility"
  testsCount={17}
  passedCount={8}
  icon={<AlertCircle className="w-8 h-8" />}
  tool="Axe-Core & Playwright"
  description="WCAG 2.1 Compliance Testing"
  url="https://www.qa-automation.com"
  onRunClick={() => console.log("Run test")}
  onReportClick={() => console.log("View report")}
/>
```

### 3. **Dashboard Header Component** (`dashboard-header.tsx`)

Reusable header for dashboard pages:

- Title and optional subtitle
- Optional action button with icon
- Sticky positioning
- Clean white background

**Props:**

```tsx
interface DashboardHeaderProps {
  title: string;
  subtitle?: string;
  actionButton?: {
    label: string;
    icon?: ReactNode;
    onClick?: () => void;
  };
}
```

**Usage:**

```tsx
<DashboardHeader
  title="Testing Dashboard"
  subtitle="Monitor all your test executions"
  actionButton={{
    label: "Run All Tests",
    icon: <PlayCircle className="w-5 h-5" />,
    onClick: () => console.log("Running tests"),
  }}
/>
```

## Color Scheme

```
Primary Colors:
- Dark Navy (Sidebar): #1e293b (slate-900)
- White (Content): #ffffff
- Light Gray (Background): #f8fafc (slate-50)

Accent Colors:
- Purple (Primary): #9333ea (purple-600)
- Purple Light: #e9d5ff (purple-100)
- Blue: #3b82f6 (blue-600)
- Green (Success): #10b981 (emerald-600)
- Red (Error): #ef4444 (red-600)

Text Colors:
- Dark: #0f172a (slate-900)
- Medium: #64748b (slate-500)
- Light: #cbd5e1 (slate-300)
```

## Navigation Structure

### MANAGEMENT Section

- Test Management
- AI Walkthrough
- Test Scheduler

### TESTING Section

- API Testing
- Database Testing
- Performance
- Load Testing
- Mobile & Responsive
- Security Testing
- SAST Scanner
- Chaos & Resilience
- Blockchain Testing

### Other

- User Management (in user section)
- Sign Out (in user section)

## Styling

All components use **Tailwind CSS** for styling. No CSS-in-JS or external CSS files needed.

### Tailwind Configuration

- Uses Tailwind v4 (with PostCSS integration)
- Responsive breakpoints: sm, md, lg, xl, 2xl
- Custom color scales: slate, purple, blue, emerald, red

### Responsive Behavior

- Sidebar: Fixed on desktop, could add mobile drawer
- Main content: Full width on all screen sizes
- Cards: Grid layout (1 col mobile → 2 col tablet → 3 col desktop)

## Getting Started

### Installation

1. **Install dependencies:**

```bash
cd frontend
npm install
```

2. **Run development server:**

```bash
npm run dev
```

3. **Open browser:**
   Navigate to `http://localhost:3000`

### Adding New Testing Categories

1. Create a new folder in `src/app/dashboard/[category-name]/`
2. Create a `page.tsx` file inside:

```tsx
'use client';

import Sidebar from '@/components/sidebar';
import { [IconName], ArrowLeft } from 'lucide-react';
import Link from 'next/link';

export default function [CategoryName]Page() {
  return (
    <div className="flex bg-slate-50 min-h-screen">
      <Sidebar />
      <div className="flex-1 ml-64">
        {/* Your content here */}
      </div>
    </div>
  );
}
```

3. Add menu item to `sidebar.tsx` in the appropriate section:

```tsx
{
  label: 'Your Test Name',
  icon: <IconName className="w-5 h-5" />,
  href: '/dashboard/category-name'
}
```

## Icons

Uses **Lucide React** for all icons. Available icons can be found at: https://lucide.dev

**Common dashboard icons:**

- BarChart3, BarChartIcon - Analytics/Performance
- Zap - AI/Speed
- Clock - Scheduler/Timing
- Server - API
- Database - Database
- Smartphone - Mobile
- Shield - Security
- AlertTriangle - Warnings/Chaos
- CheckCircle - Success
- AlertCircle - Alerts

## Advanced Features to Add

### 1. **Real-time Test Updates**

- Use WebSocket for live test execution updates
- Show real-time log streaming

### 2. **Test Result Filtering**

- Filter by status (passed/failed/running)
- Sort by date, priority, success rate

### 3. **Test Reports**

- Modal/drawer for detailed test reports
- Screenshots and video playback

### 4. **User Management**

- Edit user profile
- Preferences/settings panel
- Team management

### 5. **Dark Mode**

- Toggle dark/light theme
- Persist preference to localStorage

### 6. **Export Functionality**

- Export test results as PDF
- Export reports as CSV
- Share test results via email

## Performance Optimization

1. **Code Splitting:** Each dashboard page is lazy-loaded
2. **Image Optimization:** Use Next.js Image component
3. **CSS:** Tailwind PurgeCSS removes unused styles in production
4. **Icons:** Lucide React icons are tree-shakeable

## Accessibility

- Semantic HTML structure
- Color contrast meets WCAG AA standards
- Keyboard navigation support (via sidebar)
- ARIA labels on interactive elements

## Browser Support

- Chrome/Edge (latest)
- Firefox (latest)
- Safari (latest)
- Mobile browsers (iOS Safari, Chrome Mobile)

## Future Considerations

- Consider adding shadcn/ui components for more advanced UI needs
- Add Zod validation for form inputs
- Implement React Query for server state management
- Add error boundaries for robustness
- Create custom hooks for common dashboard operations

---

## Quick Reference

### File Locations

- Routes: `src/app/dashboard/[route]/page.tsx`
- Components: `src/components/[component-name].tsx`
- Styles: Inline Tailwind classes (no CSS files)

### Common Tailwind Classes

```
Layout:
- flex, flex-col, grid
- gap-2 through gap-8
- px-4 through px-8, py-2 through py-6
- ml-64 (main content margin for sidebar)

Colors:
- bg-slate-50, bg-slate-900
- text-slate-900, text-slate-600
- text-purple-600

Spacing:
- mb-4, mt-4 (margin)
- p-4, p-6 (padding)
- border border-slate-200

Effects:
- rounded-lg
- shadow-sm, shadow-lg
- hover:, transition-all

Responsive:
- grid-cols-1 md:grid-cols-2 lg:grid-cols-3
```

---

**Last Updated:** April 2026  
**Version:** 1.0.0  
**Status:** Production Ready
