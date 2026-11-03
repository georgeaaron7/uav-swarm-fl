# Paper: IEEE letter draft

`main.tex` is a four-page IEEE two-column letter (`IEEEtran`, journal mode) written for
IEEE Communications Letters, IEEE Wireless Communications Letters, or IEEE Networking
Letters. [`main.pdf`](main.pdf) is the latest compiled copy.

| Path | What it is |
|---|---|
| `main.tex` | The letter |
| `refs.bib` | References; venues, volumes, and pages were checked against Crossref |
| `figures/` | Figures (PDF for LaTeX, PNG for slides and README) |
| `generated/numbers.tex` | Every result quoted in the text, as LaTeX macros |
| `generated/table_outcomes.tex` | Table I |

Do not edit `figures/` or `generated/` by hand. All of them are produced from the
committed 720-run study CSV:

```bash
python scripts/make_paper_figures.py
```

## Compile

**Overleaf:** zip this `paper/` folder, then choose *New Project → Upload Project*.
The default compiler (pdfLaTeX) and BibTeX work without changes. After you regenerate
figures or numbers, upload the changed files again.

**Locally:** with [Tectonic](https://tectonic-typesetting.github.io/) installed, run

```bash
tectonic -X compile main.tex
```

Tectonic uses XeTeX, so it prints harmless `TU/ptm` font warnings that pdfLaTeX
does not.

## Before submission

- Replace the placeholder author names and confirm the affiliation.
- The comparison of mask-only against FLTrust is exploratory (not prespecified);
  keep it labeled that way.
