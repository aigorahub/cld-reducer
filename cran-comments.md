## Submission status

The maintainer submitted and confirmed cldreducer 0.2.0 on 2026-10-10.
That archive remains frozen. The 0.3.0 source candidate adds CLD-C as the default,
weighted vertex reduction, essential decisions, and a certificate that can avoid
BIP construction. Its merged source commit is
`7d9b923ed1e5c867e97f485071e1d1f742a0aeaa`. It has not been submitted to CRAN.
Versions 0.3.1 and 0.3.2 add and extend a browser page outside the R package
and do not change the R code. The current checkout is version 0.3.2. Use the retained
candidate commit for new 0.3.0 submission checks.

John Ennis is the sole package author and maintainer. The package code is MIT
licensed. See `docs/submission-status.md` for the registry and email records.

## Frozen 0.2.0 archive

Source commit: `54ec3703ae96fc910aab8d7103c36d4798fc49e5`.
Archive: `cldreducer_0.2.0.tar.gz`.
SHA-256: `11b68758ac001659237998568a8d0d0bf11d27548cf6441851cf07eb7dccbeb0`.

The local `R CMD check --as-cran --timings` run completed with zero errors,
zero warnings, and one new-submission NOTE. PDF and HTML manual checks passed.
The longest example took 0.333 seconds. The old source passed 310 testthat
checks and 1,505 conformance cases.

Both win-builder checks passed on 2026-10-10. CRAN's automated Windows and
Debian pretests also reported one NOTE each, with no errors or warnings.
Manual review was pending in the last recorded email. The public CRAN package
index did not list cldreducer on 2026-10-13.

## 0.3.0 candidate checks

The local source tests at `8e9464b63d8c1ddddc87d07420db6bfab46b555c`
pass 631 R assertions. All 47 GitHub checks pass at that commit, including
R package checks and the PDF manual check. The preceding implementation
archive check reported zero errors, zero warnings, and one new-submission NOTE.

These checks do not certify a new frozen submission file. Before submitting
0.3.0, build the archive from its approved release commit. Record its SHA-256,
R version, local archive checks, example times, and new win-builder results.
Do not use the frozen 0.2.0 hash or results as evidence for that file.

## Notes for the reviewer

The package imports `highs` and `Matrix`. Ennis, Fayle, and Piepho in
DESCRIPTION are author names. CLD and CLDs refer to compact letter displays.
CLD-C minimizes distinct letters. The optional CLD-sigma method minimizes
assignments. Neither method uses a secondary optimization objective.

## Data

The wheat example contains 190 pairwise significance decisions for 20
treatments. It comes from Piepho (2004), reproduced in Table VIII of Ennis,
Fayle, and Ennis (2012). The simple example contains ten pair comparisons and
five means from Ennis, Fayle, and Ennis (2012). `COPYRIGHTS` records the sources
and CSV-to-R transformations. On 2026-10-10, John Ennis confirmed that the
example data are public and approved their inclusion.
