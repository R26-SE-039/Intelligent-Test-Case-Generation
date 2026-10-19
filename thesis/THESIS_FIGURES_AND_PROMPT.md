# Thesis companion: figures to attach and the prompt for Claude web

## 1. Files to upload together with the thesis markdown

Upload `THESIS_Component2_Intelligent_Test_Case_Generation.md` plus these images (all already exist in the repo):

| Figure | File |
|---|---|
| 6.1 Coverage funnel | `backend/app/ml/reports/coverage_funnel.png` |
| 6.2 Run outcomes | `backend/app/ml/reports/run_outcomes.png` |
| 6.3 Pass rate by flow | `backend/app/ml/reports/pass_rate_by_flow.png` |
| 6.4 Confusion matrix | `backend/app/ml/reports/confusion_matrix.png` |
| 6.5 Per-class metrics | `backend/app/ml/reports/per_class_metrics.png` |
| 6.6 Feature importance | `backend/app/ml/reports/feature_importance.png` |
| 6.7 Class distribution | `backend/app/ml/reports/class_distribution.png` |

Screenshots you still need to capture from the running dashboard (Figures 6.8 to 6.10 and Appendix F):

1. Suite editor with the validation panel open (score ring, per-scenario prediction, findings).
2. Auto-fix diff dialog with the change log.
3. Code Review page with validation badges and the summary strip.
4. Gherkin editor with the validation panel and acceptance-criteria coverage.
5. Agent Explorer live view with the red numbered Set-of-Mark boxes and the four reasoning cards.
6. Execution page with live log, screenshots and the PDF button.
7. Public Swagger at `https://nextgenqasliit.duckdns.org/testcase-docs/docs`.

Mermaid diagrams (Figures 4.1 to 4.7, 5.1) are embedded as code in the markdown. If the PDF tool does not render Mermaid, paste each block into https://mermaid.live, export PNG, and ask Claude to place the image where the block is.

## 2. Placeholders to fill before generating the PDF

Search the thesis for `[` and fill:

- Signature and date lines in the Declaration.
- Final before/after validation score after you apply an auto-fix in the UI (Section 6.1.2).
- Predicted vs actual pass rate and MAE from `GET /api/v1/validation/projects/{project_id}/summary` (Section 6.1.2).
- Agent explorer run statistics (Section 6.1.4) if you log a few runs.
- Measured generation latency (Table 6.5).
- Human evaluation result, or mark it as future work (Table 6.5).
- Verify the reference list (Section 8).

Re-run before filling numbers so they match the final database state:

```
cd Intelligent-Test-Case-Generation/backend
./.venv/Scripts/python.exe -m app.ml.reports.generation_eval
./.venv/Scripts/python.exe -m app.ml.reports.make_charts
```

## 3. Prompt to paste into Claude web (Claude.ai) with the files attached

```
You are formatting a final-year undergraduate research dissertation for SLIIT (Faculty of Computing,
B.Sc. (Hons) in IT specialising in Software Engineering). The attached markdown file is the complete
content. Produce a print-ready PDF that follows this structure exactly, in this order, each top-level
section starting on a new page:

Title page, Declaration, Abstract, Acknowledgement, Table of Contents (with page numbers), List of
Figures, List of Tables, List of Abbreviations, then chapters 1 Introduction (1.1 Background,
1.2 Literature Survey with its five subsections, 1.3 Research Gap), 2 Research Problem,
3 Research Objectives (3.1, 3.2), 4 Methodology (4.1 to 4.7 with all subsections), 5 Implementation
and Testing (5.1, 5.2), 6 Results and Discussion (6.1, 6.2, 6.3), 7 Conclusion, 8 References,
9 Appendices.

Formatting rules:
- A4, 1-inch margins, Times New Roman 12 pt body, 1.5 line spacing, justified text.
- Chapter headings 16 pt bold, section headings 14 pt bold, subsection headings 12 pt bold.
- Front matter pages numbered in lowercase roman numerals; chapters numbered from 1.
- Number every figure and table as in the markdown ("Figure 4.1", "Table 6.2") with the caption
  below figures and above tables. Keep all tables; do not drop columns.
- Render the Mermaid code blocks as diagrams if you can; otherwise use the PNG images I attach
  for them and keep the captions.
- Place the attached PNG charts where the markdown references them.
- Code blocks in a 9 pt monospace font with a light grey background.
- References in IEEE style, numbered as in the markdown.
- Do not change the technical content or the numbers. Do not add content that is not in the file.
- Keep the text inside square brackets visible and highlighted in yellow so I can see what is
  still to be filled in.

After the PDF, list every square-bracket placeholder you found with its page number.
```
