# Development status

Status on 2026-10-14. Registry publication is recorded separately in
[submission status](submission-status.md).

## Version and delivery

PRs #7 through #11 are merged into `main`. They raise the common package
version from 0.2.0 to 0.3.0. The final 0.3.0 candidate is merge commit
`7d9b923ed1e5c867e97f485071e1d1f742a0aeaa`.
Its source tree matches reviewed head
`2fe4f9a5c7f679f4c05b8b1b18d4a9e98dde3c4b`.

Version 0.3.1 follows that candidate. It adds the browser page in `dashboard/`
and no algorithm or public API change. PR #13 merged it as commit
`b12423098d288496d4364ceeb6e094ada984a613`.
Its source tree matches reviewed head
`4d362e82a6bdddb8cdb4eec1537eb00724ed5314`.

Version 0.3.2 adds a second stage, simulated examples, and the letters before reduction
to the browser page, and no package algorithm or public API change. PR #15 merged it as commit
`60bb68819591d7dc35a8c3e50dd808c4b56ca3a7`.
Its source tree matches reviewed head
`02f29a7f206b779cc392acb6dd64ec1eafaa130f`.

The next development version is 0.3.3. This metadata update adds no algorithm
or public API changes. Neither merge nor a version update publishes a package.
Tags and registry uploads remain separate. Keep the 0.3.0 candidate commit when
preparing a later authorized release.

## Implemented behavior

CLD-C is the default and minimizes distinct letters. CLD-sigma remains available
as `assignment_minimum` and minimizes assignments. Neither method has a second
optimization objective. Equal primary optima use the fixed canonical rule.

Both methods combine vertices with identical closed neighborhoods. Sigma uses
the original class sizes as decision costs. The result expands back to the
original vertices before labels, statistics, and relationship checks.

The pipeline enumerates the complete maximal-clique set and builds ordered
coverage data. The essential scan finds decisions forced by unique coverage.
If those decisions cover every required vertex and edge, their positive costs
prove the unique optimum. This path builds no solver model and calls no solver.
Otherwise, the pipeline compiles the existing BIP once and uses HiGHS with the
essential decisions fixed. The compiler interval does not consume the shared
solve budget. The scan, proof, and canonical solves do consume it.

The code uses the structural results of Ennis, Fayle, and Ennis (2012).
It does not implement FIND-AM backtracking. The exact contracts are in
[the algorithm specification](algorithm.md).

## Browser page

`dashboard/` holds a private package that builds one offline HTML file. The
page runs the JavaScript package and the HiGHS WebAssembly solver in a worker.
It reads pairwise decisions, solves with CLD-C or CLD-sigma, and shows both
quantities for each result. It changes no package solver code and adds no
public API. It is not part of the R, Python, or npm archives. The page of
version 0.3.2 is hosted at <https://cld.aigora.ai>, the Vercel project
`cld-reducer` of the Aigora AI team.
See [the dashboard README](../dashboard/README.md).

The page also shows the letters before reduction next to the reduced letters,
with the time of each solve. It has simulated experiments with the model of
Gramm et al. (2007), which Section 8 of the 2012 paper uses (its footnote 7
names Gramm et al. [2006], whose reference is another paper), and a simulation
study view. That model gives larger maximal displays than Table X of the 2012
paper reports; the dashboard README gives the figures. An experimental second
stage minimizes the other quantity at the minimum of the first method. It is
solver code of the page: it builds on the package model, canonical engine, and
HiGHS, and it exists in the page only. A change of the
specification or of the R and Python packages for it is a separate decision.

The first review of the page found four defects: a late file read could
replace newer input, the reply check did not cover the display string, a long
file name widened the narrow page, and one sentence on group order was inexact.
Commit `4d362e82a6bdddb8cdb4eec1537eb00724ed5314` fixes them. Two independent
reviews report no remaining findings at that commit. All 49 GitHub checks pass
there. [PR #13](https://github.com/aigorahub/cld-reducer/pull/13) contains the
local test record.

Fourteen adversarial review rounds of version 0.3.2 found no wrong letter
display from the second stage. Their findings were in the reply checks of the
page, the time limits, the study, the tests, and the documents. Each fix has a test that fails
without it. At `02f29a7f206b779cc392acb6dd64ec1eafaa130f`, Astra reports no
actionable findings and all 49 GitHub checks pass. Fugu did not review that
head because of a provider usage limit; its findings of the round before are
fixed there. [PR #15](https://github.com/aigorahub/cld-reducer/pull/15)
contains the review and test record.

## Review and verification

The review at `3bfe66683612085e7fe73855aefc03686db20583` found no runtime defect.
It found missing tests for compiled-model validation, a weak native-column
mapping test, and a stale plan status line. Commit
`8e9464b63d8c1ddddc87d07420db6bfab46b555c` fixes all three. It changes tests and
documentation only. Three independent reviews report no remaining findings at
that commit. All 47 GitHub checks pass there.

Local tests at that commit pass 14,110 Python cases, 194 JavaScript cases, and
631 R assertions. Separate copies with removed compiler validation or an
incorrect essential-column mapping fail the new tests in all three languages.
The prior runtime checks also compare full results with the forced BIP path,
use independent graph oracles, and compare compiled models with the pinned base.

An additional provider run ended with a cleanup failure. Its partial finding
requires a replacement internal compiler with nonzero auxiliary costs. That
violates the private decision-plan contract. Independent code inspection and a
reproduction confirmed that the built-in compilers retain zero auxiliary costs.
The legacy compiled-model path still rejects that false certificate. The failed
provider run does not count as a completed review.

The final documentation review at
`2fe4f9a5c7f679f4c05b8b1b18d4a9e98dde3c4b` has no remaining findings from the
three reviewers. All 47 GitHub checks pass. Fresh local tests pass the same
14,110 Python cases, 194 JavaScript cases, and 631 R assertions.
[PR #11](https://github.com/aigorahub/cld-reducer/pull/11) contains the exact
local test record and check results. Later metadata changes require checks and
reviews on their own exact commit before merging.

## Timing study

The user stopped the timing study. All owned cloud machines and associated
resources were deleted. Partial evidence remains outside the repository under
`cld-reducer-submission-artifacts/clique-performance-benchmarks/`.
The batched cloud cleanup record is
`batched-study/cloud-20261013/cleanup-complete.json` in that directory.

The frozen plans and contracts under `docs/plans/clique-performance/` and
`docs/plans/essential-cover/` describe the earlier research stages. Their timing
acceptance requirements remain unproven. They are retained as historical
records. The later approved scope is correctness with less work on certified
inputs, without a measured speed-factor claim. A new timing run is not a
condition for this merge.
