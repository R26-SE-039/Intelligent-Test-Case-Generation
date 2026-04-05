import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { SidebarProvider } from "@/lib/sidebar-context";
import { ProjectProvider } from "@/lib/project-context";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "NextGen QA — Intelligent Test Case Generation",
  description: "AI-powered Gherkin + Multi-Framework Code Generation with CI/CD Integration | R26-SE-039 | SLIIT",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        <SidebarProvider>
          <ProjectProvider>{children}</ProjectProvider>
        </SidebarProvider>
      </body>
    </html>
  );
}
