# Implementation record

The public Python, R, and JavaScript paths now build coverage plans before they
allocate solver arrays. The exact essential scan and positive-cost certificate
use semantic decision positions. A certified result returns through the normal
decoder and relationship checks without compiling a BIP or calling HiGHS.

Fallback compiles the same ordered BIP from the plan. It maps the recorded
semantic essentials to native columns and calls the shared canonical trial loop.
Only compilation pauses the remaining solver budget. Legacy direct model calls
retain native scan indices and their defensive certificate checks.

The common graph context builds ordered incidence in one pass. Sigma membership
positions share that pass. Endpoint intersections provide pairs of decision
positions for both coverage and compilation. R no longer allocates the dense
membership lookup matrix. The three compilers omit redundant witness lookup lists.

Diagnostic drivers support the new path and the earlier compiled-model runtime.
Profile schema 2 reports skipped model dimensions as null and compilation as
false. Explicit preprocessing still compiles the BIP without solving. Capture
hooks use semantic decision costs. The JavaScript conformance capture hook uses
the same distinction. Saved timing evidence and source pins remain unchanged.

## Verification

New tests cover compiler and solver non-invocation, one scan and one compilation
on fallback, elapsed scan/proof time, excluded compilation time, expiry before
compilation, malformed indices, cost guards, and noncontiguous native mappings.
Existing conformance tests compare full public results and canonical vectors with
the forced BIP path. Python and JavaScript exercise presolve on and off.

An independent comparison with runtime base
`19d5698b4ef77af2d0080d50cac725f368097e65` checked both compiled models for every
simple graph on one through five vertices, with nonuniform vertex weights.
All 2,198 compiled models per language match the pinned base, including costs,
column mappings, row order, bounds, and sparse coefficients.

Logs, comparison scripts, and exact-head review reports are stored outside the
source tree at
`/Users/john/aigora/dev/cld-reducer-submission-artifacts/pre-model-certificate-implementation/`.
The pull request records the final checks and reviewed commit. Package versions
and frozen submission artifacts remain unchanged. This work does not resume the
cloud timing study or add a secondary optimization objective.
