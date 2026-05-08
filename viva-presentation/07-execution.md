# Page 7 – Execution

**URL:** `/dashboard/execution`
**This is the final stage of the pipeline.**

---

## Simple Speech for Viva

> "This is the Execution page. This is the last page in the pipeline. Here the user actually runs the generated tests and sees the results.
>
> When the user clicks the *Run Tests* button, the system connects to GitHub Actions, sends the generated test code, and runs it on a clean cloud runner. We do this so that the tests run in a controlled, reproducible environment.
>
> While the tests are running, the user sees a live log view, just like a real terminal. The logs show every step:
> - Connecting to the runner
> - Checking out the code
> - Installing the framework (for example Playwright and pytest)
> - Installing the browser (Chromium)
> - Running each test one by one
> - Capturing screenshots and video
> - Generating the Allure HTML report
>
> Each log entry has a timestamp and a status icon – green tick for passed, red cross for failed, blue clock for running.
>
> On the right side, we show a pie chart that summarises the results – how many tests passed and how many failed. We use the Recharts library for this chart.
>
> Below the chart, we show a gallery of screenshots, one for each scenario. The QA engineer can click any screenshot to see the visual result of that test, which is very useful for failed scenarios.
>
> At the bottom there are buttons to:
> - **Download** the full report
> - **Re-run** the tests
> - Go back to the Code Review page if any change is needed
>
> This page completes the full journey – from a written user story all the way to a real test result with screenshots."

---

## Key points to mention
- Cloud execution via GitHub Actions
- Live streaming logs
- Pie chart visualisation (Recharts)
- Screenshot gallery for visual proof
- Allure HTML reports
- Closes the loop: story → Gherkin → code → result
