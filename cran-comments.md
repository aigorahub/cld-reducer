## Submission status

Version 0.2.0 is a candidate for a new CRAN package. It has not been submitted.
Data reuse confirmation remains a release condition. John Ennis is the sole
package author and maintainer, as directed on 2026-10-09. See `docs/releasing.md` and the installed `COPYRIGHTS` notice.

## Candidate checked locally

- Date: 2026-10-09 in America/New_York (2026-10-10 UTC).
- Source: `eaee0e55243577ed3f36cb5c55f3e5ebcb5d22c5`. Later changes to this file
  and `docs/` do not enter the R archive.
- File: `cldreducer_0.2.0.tar.gz`.
- SHA-256: `3f50237fc8400cd1504590e93d4082b738cbbedb8a5a51d1663b4bcc330a4c73`.
- System: macOS Tahoe 26.6.2, aarch64-apple-darwin23, R 4.6.1 (2026-06-24).
- Command: `R CMD check --as-cran --timings`, through `rcmdcheck`, on the built
  archive outside the checkout. PDF manual enabled. Pandoc, TinyTeX, and HTML
  Tidy 5.8.0 available.

Result: **0 errors, 0 warnings, 1 NOTE**.

The NOTE is from CRAN incoming feasibility: `New submission`. This is expected
for a new package. The PDF manual and HTML manual checks pass. The longest
example, `reduce_letters`, took 0.357 seconds elapsed. All 310 local testthat
checks pass without warnings or skips. All 1,505 shared conformance cases and
the three data comparisons also pass from the repository.

## CI and external checks

CI retains macOS release, Windows release, and Ubuntu devel, release, and
oldrel-1 checks. A separate Ubuntu job checks the built archive with the PDF
manual and HTML Tidy. The generated-file job checks help, namespace, and data.
Record results from the final candidate commit before submission. Earlier PR
results do not certify a later archive.

The R-release and R-devel win-builder queues accepted the archive with the
SHA-256 above on 2026-10-10 at 12:40 UTC. Both FTP transfers returned 226.
Results remain pending. These requests use the current sole-author archive;
earlier requests do not certify this file. Record both result links before
submission.

## Notes for the reviewer

The package imports `highs` and `Matrix`. The package code is MIT licensed.
Ennis, Fayle, and Piepho in DESCRIPTION are author names. CLDs is the abbreviation
for compact letter displays.

## Data

The wheat example contains the significance decisions for 190 pairwise
comparisons of 20 treatments. It comes from Piepho (2004), as reproduced in
Table 7 of Ennis, Fayle, and Ennis (2012). The simple example contains ten pair
comparisons and five means from Ennis, Fayle, and Ennis (2012). `COPYRIGHTS` records sources, CSV-to-R transformations,
and the reuse confirmation that is still required. Citations do not establish
data redistribution rights. Resolve this condition before any submission.
