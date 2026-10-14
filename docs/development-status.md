# Development status

Status on 2026-10-13. Registry publication is recorded separately in
[submission status](submission-status.md).

## Version and delivery

PRs #7 through #11 are merged into `main`. They raise the common package
version from 0.2.0 to 0.3.0. The final 0.3.0 candidate is merge commit
`7d9b923ed1e5c867e97f485071e1d1f742a0aeaa`.
Its source tree matches reviewed head
`2fe4f9a5c7f679f4c05b8b1b18d4a9e98dde3c4b`.

The next development version is 0.3.1. This metadata update adds no algorithm
or public API changes. Neither merge nor the development version bump publishes
a package. Tags and registry uploads remain separate. Keep the 0.3.0 candidate
commit when preparing a later authorized release.

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
