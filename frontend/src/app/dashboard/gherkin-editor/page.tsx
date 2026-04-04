"use client";

import { useState } from "react";
import DashboardLayoutWrapper from "@/components/dashboard-layout-wrapper";
import dynamic from "next/dynamic";
import {
  FileText,
  ChevronRight,
  ChevronLeft,
  Edit3,
  CheckCircle,
  Info,
  Copy,
  Check,
} from "lucide-react";
import Link from "next/link";

const MonacoEditor = dynamic(() => import("@monaco-editor/react"), { ssr: false });

interface GherkinStory {
  id: string;
  title: string;
  actor: string;
  content: string;
  edited: boolean;
}

const gherkinData: GherkinStory[] = [
  {
    id: "US-001",
    title: "User Authentication",
    actor: "registered customer",
    edited: false,
    content: `Feature: User Authentication
  As a registered customer
  I want to log in to the system
  So that I can access my order history

  Scenario: Successful login with valid credentials
    Given I am on the login page
    When I enter valid username "standard_user"
    And I enter valid password "secret_sauce"
    And I click the login button
    Then I should be redirected to the products page
    And I should see my account dashboard

  Scenario: Failed login with invalid credentials
    Given I am on the login page
    When I enter invalid username "wrong_user"
    And I enter invalid password "wrong_pass"
    And I click the login button
    Then I should see an error message "Epic sadface: Username and password do not match"
    And I should remain on the login page`,
  },
  {
    id: "US-002",
    title: "Shopping Cart",
    actor: "shopper",
    edited: false,
    content: `Feature: Shopping Cart Management
  As a shopper
  I want to add items to the shopping cart
  So that I can purchase multiple products in one transaction

  Scenario: Add item to cart
    Given I am on the products page
    When I click "Add to cart" on "Sauce Labs Backpack"
    Then the cart badge should show "1"
    And the button label should change to "Remove"

  Scenario: Remove item from cart
    Given I have "Sauce Labs Backpack" in my cart
    When I click "Remove" on that item
    Then the cart badge should show "0"
    And the item should no longer be in the cart`,
  },
  {
    id: "US-003",
    title: "Checkout Process",
    actor: "registered customer",
    edited: false,
    content: `Feature: Checkout Process
  As a registered customer
  I want to complete the checkout process
  So that I can receive order confirmation

  Scenario: Successful checkout
    Given I have items in my cart
    When I proceed to checkout
    And I fill in first name "John"
    And I fill in last name "Doe"
    And I fill in postal code "12345"
    And I click Continue
    Then I should see the order summary
    When I click Finish
    Then I should see "Thank you for your order!"

  Scenario: Checkout with missing information
    Given I have items in my cart
    When I proceed to checkout
    And I leave the first name empty
    And I click Continue
    Then I should see error "First Name is required"`,
  },
];

export default function GherkinEditorPage() {
  const [stories, setStories] = useState<GherkinStory[]>(gherkinData);
  const [activeId, setActiveId] = useState(gherkinData[0].id);
  const [copied, setCopied] = useState(false);
  const [approved, setApproved] = useState<Set<string>>(new Set());

  const activeStory = stories.find((s) => s.id === activeId)!;

  const handleChange = (value: string | undefined) => {
    setStories((prev) =>
      prev.map((s) =>
        s.id === activeId ? { ...s, content: value ?? s.content, edited: true } : s
      )
    );
  };

  const handleCopy = async () => {
    await navigator.clipboard.writeText(activeStory.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleApprove = () => {
    setApproved((prev) => {
      const next = new Set(prev);
      next.add(activeId);
      return next;
    });
  };

  return (
    <DashboardLayoutWrapper>
      {/* Header */}
      <div className="sticky top-0 z-10 bg-slate-950/80 backdrop-blur-sm border-b border-slate-800 px-8 py-5">
        <div className="flex justify-between items-center">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="text-xs font-bold text-purple-400 bg-purple-500/10 border border-purple-500/20 px-2 py-0.5 rounded-full tracking-wider">
                S2
              </span>
              <span className="text-xs text-slate-500">Pipeline Stage 2 of 5</span>
            </div>
            <h1 className="text-2xl font-bold text-white">Gherkin Editor</h1>
            <p className="text-slate-400 text-sm mt-0.5">
              Review and edit AI-generated Given/When/Then scenarios
            </p>
          </div>
          <div className="flex items-center gap-3">
            <Link
              href="/dashboard"
              className="flex items-center gap-2 px-4 py-2 border border-slate-700 text-slate-400 hover:text-white hover:border-slate-600 rounded-lg text-sm transition-all"
            >
              <ChevronLeft className="w-4 h-4" />
              Back
            </Link>
            <Link
              href="/dashboard/mode-setup"
              className="flex items-center gap-2 px-5 py-2 bg-purple-600 hover:bg-purple-500 text-white rounded-lg font-medium text-sm transition-all shadow-lg shadow-purple-600/30"
            >
              Mode & URL Setup
              <ChevronRight className="w-4 h-4" />
            </Link>
          </div>
        </div>
      </div>

      {/* Human-in-the-loop info banner */}
      <div className="mx-8 mt-6 flex items-start gap-3 px-4 py-3 bg-blue-500/10 border border-blue-500/20 rounded-xl">
        <Info className="w-4 h-4 text-blue-400 mt-0.5 shrink-0" />
        <p className="text-sm text-blue-300">
          <span className="font-semibold">Human-in-the-loop:</span> You can edit these
          Gherkin scenarios before generating code. Changes are saved automatically. Approve
          each scenario when satisfied.
        </p>
      </div>

      {/* Main editor layout */}
      <div className="flex gap-0 h-[calc(100vh-230px)] mx-8 mt-6 mb-8 rounded-xl border border-slate-700 overflow-hidden">
        {/* Left panel — story list */}
        <div className="w-60 shrink-0 bg-slate-900 border-r border-slate-700 flex flex-col">
          <div className="px-4 py-3 border-b border-slate-700">
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-widest">
              Stories ({stories.length})
            </p>
          </div>
          <div className="flex-1 overflow-y-auto py-2" style={{ scrollbarWidth: "none" }}>
            {stories.map((story) => {
              const isActive = story.id === activeId;
              const isApproved = approved.has(story.id);
              return (
                <button
                  key={story.id}
                  onClick={() => setActiveId(story.id)}
                  className={`w-full text-left px-4 py-3 transition-all border-l-2 ${
                    isActive
                      ? "border-purple-500 bg-purple-500/10 text-white"
                      : "border-transparent text-slate-400 hover:bg-slate-800 hover:text-slate-200"
                  }`}
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs font-mono text-purple-400">{story.id}</span>
                    <div className="flex items-center gap-1">
                      {story.edited && (
                        <Edit3 className="w-3 h-3 text-amber-400" />
                      )}
                      {isApproved && (
                        <CheckCircle className="w-3 h-3 text-emerald-400" />
                      )}
                    </div>
                  </div>
                  <p className="text-xs font-medium leading-tight">{story.title}</p>
                  <p className="text-[10px] text-slate-500 mt-0.5 truncate">
                    as {story.actor}
                  </p>
                </button>
              );
            })}
          </div>
        </div>

        {/* Right panel — Monaco editor */}
        <div className="flex-1 flex flex-col bg-slate-950">
          {/* Editor toolbar */}
          <div className="flex items-center justify-between px-4 py-2.5 border-b border-slate-700 bg-slate-900/50">
            <div className="flex items-center gap-2">
              <FileText className="w-4 h-4 text-purple-400" />
              <span className="text-sm font-medium text-slate-200">
                {activeStory.title}.feature
              </span>
              {activeStory.edited && (
                <span className="text-[10px] bg-amber-500/20 text-amber-400 border border-amber-500/30 px-1.5 py-0.5 rounded">
                  MODIFIED
                </span>
              )}
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={handleCopy}
                className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-white transition-colors px-2.5 py-1.5 rounded-md hover:bg-slate-700"
              >
                {copied ? (
                  <><Check className="w-3.5 h-3.5 text-emerald-400" /> Copied</>
                ) : (
                  <><Copy className="w-3.5 h-3.5" /> Copy</>
                )}
              </button>
              <button
                onClick={handleApprove}
                className={`flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-md font-medium transition-all ${
                  approved.has(activeId)
                    ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30"
                    : "bg-purple-600 hover:bg-purple-500 text-white"
                }`}
              >
                <CheckCircle className="w-3.5 h-3.5" />
                {approved.has(activeId) ? "Approved" : "Approve"}
              </button>
            </div>
          </div>

          {/* Monaco */}
          <div className="flex-1">
            <MonacoEditor
              height="100%"
              defaultLanguage="gherkin"
              language="plaintext"
              theme="vs-dark"
              value={activeStory.content}
              onChange={handleChange}
              options={{
                fontSize: 13,
                lineHeight: 22,
                minimap: { enabled: false },
                wordWrap: "on",
                scrollBeyondLastLine: false,
                padding: { top: 16, bottom: 16 },
                fontFamily: "'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace",
                fontLigatures: true,
              }}
            />
          </div>

          {/* Bottom status bar */}
          <div className="flex items-center justify-between px-4 py-2 border-t border-slate-700 bg-slate-900/50">
            <div className="flex items-center gap-4 text-[11px] text-slate-500">
              <span>{activeStory.content.split("\n").length} lines</span>
              <span>Gherkin · Given/When/Then</span>
            </div>
            <div className="text-[11px] text-slate-500">
              {approved.size}/{stories.length} approved
            </div>
          </div>
        </div>
      </div>
    </DashboardLayoutWrapper>
  );
}
