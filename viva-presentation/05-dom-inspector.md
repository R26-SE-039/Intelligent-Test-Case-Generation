# Page 5 – DOM Inspector

**URL:** `/dashboard/dom-inspector`
**This is Stage 4 of the pipeline (only in DOM mode).**

---

## Simple Speech for Viva

> "This is the DOM Inspector page. This page only opens when the user has chosen DOM mode in the previous step.
>
> The purpose of this page is to crawl the website and capture all the interactive elements – like buttons, input fields, links, and forms – and store them in our database. These real selectors will later be used to generate accurate test code.
>
> When the page opens, the user clicks the *Crawl* button. The backend uses Playwright to open a real browser, load the website, and read its DOM. We also stream live logs to the page so the user can see what is happening in real time – which page is being visited, which elements are being captured, and so on.
>
> If the website needs login, the user can configure an authentication strategy. For example, they can provide a username, password, and the selectors for the login form. The crawler will log in first and then crawl the protected pages.
>
> After crawling is complete, the page shows a table of all DOM elements. For each element, we display:
> - The CSS selector
> - The HTML tag
> - The role
> - The visible text
>
> The user can:
> - **Edit** any element if the selector is wrong
> - **Add** a new element manually
> - **Delete** elements that are not useful
> - **Bulk approve** all elements at once
>
> Once the elements are approved, the user clicks *Continue* to go to the Code Review page, where the AI will use these real selectors to generate test code."

---

## Key points to mention
- Uses Playwright for real browser crawling
- Live log streaming via Server-Sent Events
- Supports authenticated crawling
- QA can edit/add/delete elements before approval
- Real selectors → real working tests
