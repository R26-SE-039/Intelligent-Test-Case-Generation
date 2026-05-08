# Page 3 – Gherkin Editor

**URL:** `/dashboard/gherkin-editor`
**This is Stage 2 of the pipeline.**

---

## Simple Speech for Viva

> "This is the Gherkin Editor page. After the user clicks *Generate Gherkin* on the previous page, the AI converts each user story into Gherkin format and saves it in the database. Then this page opens.
>
> Gherkin is a simple language used in Behaviour Driven Development. It uses keywords like *Given*, *When*, and *Then* to describe how the system should behave. For example:
> - **Given** the user is on the login page
> - **When** the user enters valid username and password
> - **Then** the user should see the home page
>
> On the left side of this page, there is a list of all stories. The user can click on any story to view its Gherkin scenario.
>
> On the right side, there is a code editor – we use the Monaco editor, which is the same editor used in VS Code. The QA engineer can read the Gherkin and edit it directly if any sentence is wrong or unclear.
>
> There are three main buttons:
> 1. **Save** – saves the edited Gherkin back to the database
> 2. **Regenerate** – asks the AI to generate the Gherkin again, in case the user is not happy with the result
> 3. **Approve** – marks this Gherkin as approved by QA. Only approved Gherkin scenarios will be used to generate test code in the next stage.
>
> The user can also copy the Gherkin to the clipboard.
>
> This page gives full control to the QA engineer – the AI gives a draft, but the human gives the final approval."

---

## Key points to mention
- AI generates first draft, human reviews and approves
- Monaco editor (same as VS Code)
- Approval state is saved in PostgreSQL
- Only approved scenarios go to test code generation
- Regenerate button calls the LLM again
