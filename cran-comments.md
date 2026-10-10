## Submission

This is a new package, not yet on CRAN.

## Test environments

- Local: Ubuntu 26.04 (WSL), R 4.6.1, `R CMD check --as-cran --no-manual` on the built tarball in a folder outside the source tree
- GitHub Actions: macOS (release), Windows (release), Ubuntu (devel, release, oldrel-1)
- GitHub Actions: Ubuntu (release), `R CMD check --as-cran` with the PDF manual, on the built tarball in a folder outside the checkout
- win-builder (R-devel and R-release): to be run by the maintainer before submission

## R CMD check results

- Local (Ubuntu 26.04 on WSL, R 4.6.1), `--as-cran --no-manual --timings` on the built tarball: 0 errors | 0 warnings | 2 notes.
  - CRAN incoming feasibility: "New submission". This is expected for a new package.
  - "Files 'README.md' or 'NEWS.md' cannot be checked without 'pandoc' being installed". This machine has no pandoc; the GitHub Actions jobs install it, so the note does not appear there.
  - Every example runs in under 2 s (the slowest, `reduce_letters`, takes about 1.5 s, most of it loading the Matrix package). The tests take about 6 s.
- GitHub Actions, macOS (release), Windows (release), and Ubuntu (devel, release, oldrel-1): 0 errors | 0 warnings | 0 notes.
- GitHub Actions, Ubuntu 24.04 (release), `R CMD check --as-cran` with the PDF manual, on the built tarball in a folder under `RUNNER_TEMP`, outside the checkout: 0 errors | 0 warnings | 1 note.
  - "checking HTML version of manual ... NOTE: Skipping checking HTML validation: no command 'tidy' found." The runner has no HTML Tidy, so R skips the HTML validation. The PDF manual builds without problems.
  - The tests take about 3 s and the slowest example, `reduce_letters`, about 0.8 s.
- All GitHub Actions jobs fail on a warning.
- win-builder (R-devel and R-release): to be run by the maintainer before submission; the results go here.

## Notes for the reviewer

- The package imports `highs` (GPL >= 2) and `Matrix`, as the sibling package turfLP does. The package itself is MIT licensed.
- Possibly misspelled words in DESCRIPTION: Ennis, Fayle, and Piepho are author names in the references, and "CLDs" is the common abbreviation for compact letter displays.

## Data

The package includes the data of the wheat yield example (Piepho 2004, as tabulated in Table 7 of Ennis, Fayle, and Ennis 2012): the significance of all 190 pairwise comparisons of 20 treatments. The help page cites the sources.
