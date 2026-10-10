## Submission status

Version 0.2.0 is a candidate for a new CRAN package. It has not been submitted.
Data reuse confirmation and maintainer/author confirmation remain release
conditions. See `docs/releasing.md` and the installed `COPYRIGHTS` notice.

## Candidate checked locally

- Date: 2026-10-09 in America/New_York (2026-10-10 UTC).
- Source: `b54fb49b2dbd0738f4c3fea78707d966d62e00f1`. The archive was built from
  the same packaged files before this commit. Later changes to this file and
  `docs/` do not enter the R archive.
- File: `cldreducer_0.2.0.tar.gz`.
- SHA-256: `7e053dcd8007ed70bf3b647fc259cd24fae7fae9277b4321566ea1220174daac`.
- System: macOS Tahoe 26.6.2, aarch64-apple-darwin23, R 4.6.1 (2026-06-24).
- Command: `R CMD check --as-cran --timings`, through `rcmdcheck`, on the built
  archive outside the checkout. PDF manual enabled. Pandoc, TinyTeX, and HTML
  Tidy 5.8.0 available.

Result: **0 errors, 0 warnings, 1 NOTE**.

The NOTE is from CRAN incoming feasibility: `New submission`. This is expected
for a new package. The PDF manual and HTML manual checks pass. The longest
example, `reduce_letters`, took 0.336 seconds elapsed. All 310 local testthat
checks pass without warnings or skips. All 1,505 shared conformance cases and
the three data comparisons also pass from the repository.

An earlier check of the same archive used the old macOS system `tidy`. It had
one additional NOTE because that validator was too old. The repeat with Tidy
5.8.0 removed that NOTE. Do not treat the old validator NOTE as an outstanding
package defect.

## CI and external checks

CI retains macOS release, Windows release, and Ubuntu devel, release, and
oldrel-1 checks. A separate Ubuntu job checks the built archive with the PDF
manual and HTML Tidy. The generated-file job checks help, namespace, and data.
Record results from the final candidate commit before submission. Earlier PR
results do not certify a later archive.

Win-builder R-devel and R-release: pending. No archive has been sent. With
separate authorization, send the frozen archive and record its result links and
hash here. The proposed maintainer receives the result emails. If packaged bytes
change, rebuild and repeat the checks before submission.

## Notes for the reviewer

The package imports `highs` and `Matrix`. The package code is MIT licensed.
Ennis, Fayle, and Piepho in DESCRIPTION are author names. CLDs is the abbreviation
for compact letter displays.

## Data

The wheat example contains the significance decisions for 190 pairwise
comparisons of 20 treatments. It comes from Piepho (2004), as reproduced in
Table 7 of Ennis, Fayle, and Ennis (2012). The simple example contains ten pair
comparisons and five means. `COPYRIGHTS` records sources, CSV-to-R transformations,
and the reuse confirmation that is still required. Citations do not establish
data redistribution rights. Resolve this condition before any submission.
