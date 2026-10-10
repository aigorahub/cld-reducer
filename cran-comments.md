## Submission

This is the first CRAN submission of cldreducer, version 0.2.0.
The package has not yet been submitted. John Ennis is the sole package author
and maintainer. The package code is MIT licensed.

## Test environments

- macOS Tahoe 26.6.2, aarch64-apple-darwin23, R 4.6.1 (2026-06-24).
- GitHub Actions covers macOS release, Windows release, and Ubuntu devel,
  release, and oldrel-1. Final candidate results must be recorded before submission.
- Both win-builder queues accepted the candidate below on 2026-10-10 at
  12:57 UTC. Results are pending. Earlier candidate results do not certify it.

## R CMD check results

Local command: `R CMD check --as-cran --timings cldreducer_0.2.0.tar.gz`.
The complete check reached `* DONE`. PDF and HTML manual checks passed.

0 errors | 0 warnings | 1 NOTE

The NOTE is `New submission`. The longest example, `reduce_letters`, took
0.333 seconds. All 310 local testthat checks passed without warnings or skips.
The repository conformance suite passed all 1,505 cases and three data comparisons.

Candidate source: `54ec3703ae96fc910aab8d7103c36d4798fc49e5`.
Candidate SHA-256:
`11b68758ac001659237998568a8d0d0bf11d27548cf6441851cf07eb7dccbeb0`.
Later changes to this file and `docs/` do not enter the R archive.

## Notes for the reviewer

The package imports `highs` and `Matrix`. Ennis, Fayle, and Piepho in
DESCRIPTION are author names. CLD and CLDs refer to compact letter displays.

## Data

The wheat example contains 190 pairwise significance decisions for 20
treatments. It comes from Piepho (2004), reproduced in Table 7 of Ennis, Fayle,
and Ennis (2012). The simple example contains ten pair comparisons and five
means from Ennis, Fayle, and Ennis (2012). `COPYRIGHTS` records the sources and
CSV-to-R transformations. On 2026-10-10, John Ennis confirmed that the example
data are public and approved their inclusion.
