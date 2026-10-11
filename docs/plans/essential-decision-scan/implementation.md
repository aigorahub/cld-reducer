# Essential decisions before HiGHS

PR: https://github.com/aigorahub/cld-reducer/pull/8.
Implementation starts from the reviewed plan at
`3e643fe982f7d66550ef28d0530892a163fb5353`.
The PR depends on PR 7, with base
`e3d2b1cce3e91544e43ab13af07fdf73d613c693`.

## Delivered behavior

Python, R, and JavaScript each add an essential decision operation to the existing
strategy registry. The sigma scan uses group membership alternatives and edge
endpoint alternatives. The C scan uses vertex and edge covering clique lists.
Each returns sorted unique native decision column indices.

The shared canonical engine starts its deadline before scanning. It validates
the scan result, fixes required lower bounds to 1, and passes those bounds to
the first solver call and every trial. Optional decisions stay free initially.
The first call has no objective cap. HiGHS still runs when all decisions are
required. The existing result checks reject an essential bound violation.

The weighted vertex reduction, objectives, canonical order, public API shapes,
mean ordering, original labels and counts, and legacy Python helper remain
unchanged. R uses the row count of each two column endpoint matrix. Auxiliary
variables are excluded from both scans.

The full maximal cover still gives the existing upper bounds and before counts.
There is no greedy sweep, initial feasible solution, variable elimination, or
FIND-AM search. Versions stay at unreleased 0.3.0. Published 0.2.0 artifacts
and all frozen reduction fixtures remain unchanged.

## Validation

The new independent standard library oracle enumerates cliques by vertex subsets.
For each candidate decision, it reconstructs the entire Boolean relationship
matrix after deletion. It generates 2,206 scan cases for both methods. These
cover all 1,099 labeled graphs with one through five vertices, before and after
an independent true twin quotient. Named witnesses cover joint conflicts for
both objectives, no essential decisions, and interleaved weighted classes.

All three scans match these cases. The existing 2,894 reduction fixtures also
pass unchanged. Python and JavaScript exercise presolve on and off. Generator
checks preserve the standard library boundary and frozen fixture bytes.

Focused tests inspect first and later adapter bounds, free initial choices,
essential bound violations, malformed scan output, and scan time in the deadline.
The six synthetic canonical tests explicitly replace the scan operation with
an empty result and keep their prior expected outputs and purposes.

Local validation includes Python 3.10 with minimum dependencies and Python 3.13,
JavaScript on Node 26, R 4.6.1 tests and shared conformance, package builds and
clean installs, generator checks, and release tests. The R archive passes PDF
and HTML manual checks with zero errors, zero warnings, and one new submission
note. GitHub checks and exact head reviews are recorded on the PR and in the
submission artifact directory. Plan reviews do not replace implementation reviews.

## Performance evidence

The scan finds twelve required decisions among fifteen reduced wheat sigma
memberships, and all four wheat C variables. It also finds eight of nine ABC
memberships and all three ABC C variables. The nine vertex complete tripartite
graph has no required decisions, so HiGHS receives all choices free.

Benchmarks compare the same explicit methods and full API outputs before and
after the scan. Each case uses warmup and nine batches of five calls. Python
and R record first solve time, decision counts, and solve counts. Python also
records scan time. All compared outputs are identical.

The observed performance effect varies by case and language. The scan does not
establish a general speed gain. Measurements and machine/dependency versions
are saved in the submission artifacts. This change makes the paper's exact
required decision test explicit in the common BIP framework.

## Review and release boundary

Independent implementation reviews must cover the exact committed head.
Every Agy review uses `/boost` in plan mode. Every child gets the same absolute
worktree and commits. Valid findings require fixes and another exact head review.
The PR remains separate from publication and requires explicit merge approval.
