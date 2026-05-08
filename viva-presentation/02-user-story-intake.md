# Page 2 – User Story Intake (Dashboard)

**URL:** `/dashboard`
**This is Stage 1 of the pipeline.**

---

## Simple Speech for Viva

> "After the user opens a project, this is the first stage of the pipeline – the User Story Intake page.
>
> Here, the user manages all the user stories for this project. A user story is a small sentence that describes what a user wants to do. For example: *‘As a customer, I want to log in, so that I can see my orders.’*
>
> At the top of the page, we show four boxes with statistics:
> - Total stories
> - Pending stories
> - Processing stories
> - Completed stories
>
> The user can add a story manually by clicking the *Add Story* button. A small form opens with three fields: Actor (who), Action (what), and Goal (why). After the user fills these, the story is saved to the database.
>
> The user can also filter stories by priority – High, Medium, or Low. There is a *Select All* option, and each story has a checkbox.
>
> When the user selects one or more stories, a button appears at the bottom: *Generate Gherkin*. When the user clicks this button, the selected stories are sent to the AI, and the system creates Gherkin test scenarios for them. After this, the user is automatically taken to the Gherkin Editor page.
>
> User stories can also come from Component 1 of our research project, where they are extracted automatically from documents."

---

## Key points to mention
- Two sources of stories: **manual entry** or **imported from Component 1**
- Stories are saved in the database immediately
- Each story has a priority and a status (pending / processing / done)
- The "Generate Gherkin" button is the bridge to the next stage
