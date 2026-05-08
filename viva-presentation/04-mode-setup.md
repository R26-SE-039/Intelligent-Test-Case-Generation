# Page 4 – Mode Setup

**URL:** `/dashboard/mode-setup`
**This is Stage 3 of the pipeline.**

---

## Simple Speech for Viva

> "This is the Mode Setup page. After the Gherkin scenarios are approved, the user comes here to configure how the test code should be generated.
>
> The user has to make three choices on this page:
>
> **1. Test Mode**
> The user can choose between two modes:
> - **Abstract Mode** – the system generates test code with placeholder selectors. This is faster, but the QA engineer has to fill in real CSS selectors later. Good for early planning.
> - **DOM Mode** – the system actually opens the website, reads its real HTML, and uses the real selectors in the test code. This gives ready-to-run code.
>
> **2. Framework**
> The user can choose between three popular automation frameworks:
> - **Selenium** – Python
> - **Playwright** – Python or JavaScript
> - **Cypress** – JavaScript
>
> **3. Target URL**
> The user enters the URL of the website they want to test. For example, `https://www.saucedemo.com`. There is a *Probe URL* button next to it. When clicked, the backend tries to reach the URL and returns the HTTP status and the page title. This confirms that the URL is reachable before continuing.
>
> When the user is in DOM mode, they must validate the URL first. Otherwise the *Continue* button stays disabled.
>
> Once everything is filled, the user clicks *Continue*. If the mode is DOM, it goes to the DOM Inspector page. If the mode is Abstract, it goes directly to the Code Review page."

---

## Key points to mention
- Two modes: Abstract (placeholder) vs DOM (real selectors)
- Three frameworks supported
- URL probe ensures the site is reachable before crawling
- Smart routing: DOM mode → Inspector, Abstract mode → Code Review directly
