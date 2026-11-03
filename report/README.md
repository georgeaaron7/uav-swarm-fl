# B.Tech project report (NIT Warangal)

LaTeX source of the Phase I project report. [`main.pdf`](main.pdf) is the latest
compiled copy. The layout follows the institute's LaTeX thesis template
(*Template_for_Thesis*, 2024), adapted from a PhD thesis to a B.Tech report:
- Computer Modern 12 pt, 1.5 line spacing, 30 mm left and 20 mm right margins
- title page with the institute emblem; viva-voce approval, certificate, declaration,
  acknowledgements, abstract with index terms
- blue linked contents, then lists of figures, tables, abbreviations and symbols
- left-aligned "Chapter N" heads, running headers with rules on continuation pages
- author-year references, followed by the appendices

Chapter and front-page positions were measured against the template PDF and match it
to within a few points.

| Path | What it is |
|---|---|
| `info.tex` | **Edit this first:** title, students and roll numbers, guide, HOD, department, month and year |
| `main.tex` | Page layout and document order |
| `frontmatter/` | Title, approval, certificate, declaration, acknowledgements, abstract, abbreviations and symbols |
| `chapters/` | Introduction, Literature Review, Theoretical Study, Experimental Study, Conclusions and Future Scope of Study, Appendices A and B |
| `refs.bib` | References |
| `figures/nitw_logo.jpg` | Institute emblem, taken from the template |
| `figures/` (others), `generated/` | Copied in by `python scripts/make_paper_figures.py`; do not edit by hand |

## Compile

**Overleaf:** zip this `report/` folder, then choose *New Project → Upload Project*.
The default compiler (pdfLaTeX) and BibTeX work without changes.

**Locally:** `tectonic -X compile main.tex`.

## Before submission

- Fill in the remaining placeholders in `info.tex`: the HOD's name, and confirm the
  roll numbers and the guide's title.
- The certificate is meant to be printed on departmental letterhead.
- Check the plagiarism score. The report is written separately from the paper, but
  both describe the same study.
- Confirm the literature-review entries for the IEEE letters against their full texts.
  Table 2.1's caption says these entries still need checking.
