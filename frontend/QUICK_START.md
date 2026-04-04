# 🚀 Quick Start Guide - NexGen QA Dashboard

## 30-Second Setup

```bash
cd frontend
npm install
npm run dev
```

Then open **http://localhost:3000** in your browser.

---

## What You'll See

### 🎯 Main Dashboard (`/dashboard`)

- **Dark Sidebar** on the left with NexGen QA logo
- **Test Cards** showing test results
- **Statistics Panel** with overall metrics
- **Responsive Layout** that works on mobile

### 📋 Navigation

Click sidebar items to explore:

- **Test Management** - Manage all tests
- **API Testing** - API endpoint testing
- **Database Testing** - SQL and data integrity tests
- **Security Testing** - OWASP vulnerability scanning
- And 6 more test categories...

---

## File Organization

### Components (Reusable UI pieces)

```
src/components/
├── sidebar.tsx              # Main navigation sidebar
├── test-card.tsx            # Test result card
├── dashboard-header.tsx     # Page headers
├── stats-grid.tsx           # Statistics display
└── breadcrumb.tsx           # Navigation breadcrumb
```

### Pages (Routes)

```
src/app/dashboard/
├── page.tsx                 # Main dashboard (/dashboard)
├── accessibility/page.tsx   # Accessibility tests
├── api-testing/page.tsx     # API tests
├── test-management/page.tsx # Test management
├── database-testing/page.tsx # Database tests
└── security-testing/page.tsx # Security tests

# For any new testing category:
src/app/dashboard/[category-name]/page.tsx
```

---

## Common Tasks

### ➕ Add a New Testing Category

1. **Create folder:** `src/app/dashboard/new-category/`

2. **Create file:** `src/app/dashboard/new-category/page.tsx`

```tsx
"use client";
import Sidebar from "@/components/sidebar";
import { AlertCircle, ArrowLeft } from "lucide-react";
import Link from "next/link";

export default function NewCategoryPage() {
  return (
    <div className="flex bg-slate-50 min-h-screen">
      <Sidebar />
      <div className="flex-1 ml-64">
        <div className="sticky top-0 bg-white border-b border-slate-200 px-8 py-6 shadow-sm">
          <Link
            href="/dashboard"
            className="flex items-center gap-2 text-purple-600 hover:text-purple-700 mb-4 font-medium"
          >
            <ArrowLeft className="w-4 h-4" />
            Back to Dashboard
          </Link>
          <h1 className="text-3xl font-bold text-slate-900">
            New Test Category
          </h1>
        </div>
        <div className="p-8">{/* Your content here */}</div>
      </div>
    </div>
  );
}
```

3. **Update sidebar:** Add to `src/components/sidebar.tsx` in the appropriate section:

```tsx
{
  label: 'New Category',
  icon: <AlertCircle className="w-5 h-5" />,
  href: '/dashboard/new-category'
}
```

### 🎨 Display Test Results

Use the `TestCard` component:

```tsx
import TestCard from "@/components/test-card";
import { CheckCircle } from "lucide-react";

<div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-6">
  <TestCard
    title="My Test"
    testsCount={20}
    passedCount={18}
    icon={<CheckCircle className="w-8 h-8" />}
    tool="Playwright"
    description="Testing description"
    url="https://example.com"
    onRunClick={() => console.log("Run clicked")}
    onReportClick={() => console.log("Report clicked")}
  />
</div>;
```

### 📊 Show Statistics

Use the `StatsGrid` component:

```tsx
import StatsGrid from "@/components/stats-grid";
import { Target, CheckCircle, AlertCircle, TrendingUp } from "lucide-react";

<StatsGrid
  title="Overall Statistics"
  items={[
    { label: "Total Tests", value: 53, color: "purple", icon: <Target /> },
    { label: "Passed", value: 40, color: "emerald", icon: <CheckCircle /> },
    { label: "Failed", value: 13, color: "red", icon: <AlertCircle /> },
    {
      label: "Success Rate",
      value: "75%",
      color: "blue",
      icon: <TrendingUp />,
    },
  ]}
/>;
```

---

## Colors & Styling

### Color Classes (Use Tailwind)

```
Text Colors:          Background Colors:       Border:
text-slate-900       bg-slate-50              border border-slate-200
text-slate-600       bg-slate-900
text-purple-600      bg-purple-100
text-emerald-600     bg-emerald-50
text-red-600         bg-red-50
text-blue-600        bg-blue-50
```

### Quick Layouts

```
Flexbox:
<div className="flex gap-4">         {/* Row, spaced */}
<div className="flex flex-col gap-4">  {/* Column, spaced */}

Grid:
<div className="grid grid-cols-3 gap-4"> {/* 3 columns */}
<div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3"> {/* Responsive */}

Spacing:
p-4         {/* Padding all sides */}
px-6 py-4   {/* Padding: horizontal vertical */}
mb-4        {/* Margin bottom */}
gap-6       {/* Gap between flex/grid items */}
```

---

## Icons Available

From **Lucide React** (https://lucide.dev):

```
BarChart3         - Analytics
Zap               - Speed/AI
Clock             - Time/Scheduler
Server            - APIs
Database          - Databases
Smartphone        - Mobile
Shield            - Security
AlertTriangle     - Warnings
CheckCircle       - Success
AlertCircle       - Alerts
PlayCircle        - Play/Run
TrendingUp        - Growth
Target            - Goals
ArrowLeft         - Back
ChevronRight      - Right arrow
LogOut            - Sign out
```

Usage: `import { IconName } from 'lucide-react'`

---

## Responsive Breakpoints

```
Default (mobile)
sm: (640px)      - Small tablets
md: (768px)      - Tablets
lg: (1024px)     - Laptops
xl: (1280px)     - Large screens
2xl: (1536px)    - Extra large
```

Example: `grid-cols-1 md:grid-cols-2 lg:grid-cols-3` (1 col mobile, 2 tablet, 3 desktop)

---

## Troubleshooting

### Sidebar not showing?

- Make sure you import: `import Sidebar from '@/components/sidebar';`
- Wrap content in flex: `<div className="flex">`
- Add margin to main: `<main className="ml-64">` (256px = sidebar width)

### Route not working?

- File must be named `page.tsx` (Next.js convention)
- Must be in `src/app/dashboard/[route-name]/` folder
- Add to sidebar navigation items

### Styling not applying?

- Check Tailwind class name spelling
- Use utility classes, not custom CSS
- Rebuild dev server: `npm run dev`

---

## Next Steps

1. ✅ Dashboard is ready
2. 🔌 Connect to backend API
3. 📡 Add WebSocket for live updates
4. 🔐 Add authentication
5. 📊 Implement real test data
6. 🎯 Add more features (filters, search, etc.)

---

## Resources

- **Tailwind Docs:** https://tailwindcss.com/docs
- **Lucide Icons:** https://lucide.dev
- **Next.js Guide:** https://nextjs.org/docs
- **Full Guide:** See `DASHBOARD_GUIDE.md`

---

**Happy coding! 🎉**
