# Viva Presentation – Overview

## Application Name
**NextGenQA – Intelligent Test Case Generation**

## What is this project?
This is a web application that helps QA engineers automatically generate test cases from user stories. It uses AI to convert plain English user stories into Gherkin scenarios, and then into runnable test code in Selenium, Playwright, or Cypress.

## Pages the user will see (in order)
1. **Projects Page** – where you create or open a project
2. **User Story Intake (Dashboard)** – where you add user stories
3. **Gherkin Editor** – where you review AI-generated Gherkin scenarios
4. **Mode Setup** – where you choose test mode and framework
5. **DOM Inspector** – where you crawl the website and pick UI elements
6. **Code Review** – where you see the final test code
7. **Execution** – where you run the tests and see results
8. **Agent Explorer** *(novelty)* – where one short intent triggers an autonomous AI agent that explores the app and discovers test scenarios on its own

## Simple flow to remember
> "I create a project, I add user stories, AI writes Gherkin, I check it, I tell the system which website and framework, the system reads the website, AI writes test code, I run the tests, I see the results."

## The novelty flow (the research contribution)
> "I open Agent Explorer, I type one sentence like 'check the login flow', I click Run, an autonomous AI opens a real browser with red numbered boxes on every clickable element, it plans sub-goals, it clicks and types and watches what happens, it discovers scenarios I never asked for — and it stops by itself when it stops finding new things."
