## Submission

This is a new package, not yet on CRAN.

## Test environments

- Local: Ubuntu 26.04 (WSL), R 4.6.1, `R CMD check --as-cran --no-manual` on the built tarball in a folder outside the source tree
- GitHub Actions: macOS (release), Windows (release), Ubuntu (devel, release, oldrel-1)
- GitHub Actions: Ubuntu (release), `R CMD check --as-cran` with the PDF manual, on the built tarball in a folder outside the checkout
- win-builder (R-devel and R-release): to be run by the maintainer before submission

## R CMD check results

To be filled in from the final CI runs (see below).

## Notes for the reviewer

- The package imports `highs` (GPL >= 2) and `Matrix`, as the sibling package turfLP does. The package itself is MIT licensed.
- Possibly misspelled words in DESCRIPTION: Ennis, Fayle, and Piepho are author names in the references, and "CLDs" is the common abbreviation for compact letter displays.

## Data

The package includes the data of the wheat yield example (Piepho 2004, as tabulated in Table 7 of Ennis, Fayle, and Ennis 2012): the significance of all 190 pairwise comparisons of 20 treatments. The help page cites the sources.
