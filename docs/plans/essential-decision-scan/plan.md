# Exact essential decision scan before HiGHS

## Goal and PR boundary

Add the paper's exact removal test as a preliminary scan in Python, R, and
JavaScript. Use the existing BIP models to optimize the remaining decisions.
Preserve every public result and the canonical optimum for each method.

This document defines the reviewed implementation contract. The plan reviews
completed at `3e643fe982f7d66550ef28d0530892a163fb5353` before implementation.
Implementation and validation are recorded in `implementation.md`.

Branch: `plan/essential-decision-scan`.
Absolute worktree: `/Users/john/aigora/dev/cld-reducer-essential-scan`.
Dependency: PR 7, branch `plan/cld-c-option`.
Implementation baseline: `e3d2b1cce3e91544e43ab13af07fdf73d613c693`.
The draft PR targets `plan/cld-c-option` until PR 7 lands. Then target `main`
and check the resulting diff and exact head again. This plan grants no merge
or publication authority.

## Mathematical contract

1. Build the original graph from the validated input.
2. Apply the existing true twin reduction. Combine equal closed neighborhoods,
   including the diagonal. Preserve class members and class sizes.
3. Enumerate all maximal cliques of the reduced graph in the existing order.
4. Treat all maximal cliques with all memberships present as the full cover.
5. Scan that unchanged full cover for essential decisions of the selected method.
6. Fix exactly those decision variables to 1 before the first HiGHS solve.
7. Run the existing minimum solve and canonical selection procedure.
8. Expand class members, assign letters, and check the original relationships.

An original vertex represents an item being compared, such as a treatment.
The API calls item labels `groups`. A reduced vertex represents a class of
original vertices. A clique is a candidate letter column.

Let K be the number of maximal cliques and w[v] a reduced vertex's class size.
The full cover gives a letter upper bound K and an assignment upper bound
sum over cliques c of sum over members v in c of w[v]. The existing before
statistics already report these counts after expansion. Keep those statistics.
Every decision's upper bound is already 1, so these full cover objective bounds
are implied by the current model. Do not add a redundant objective cap or change
the first solve's existing `sum_limit = None / NULL / null` marker.

### Exact membership test for CLD-sigma

Start from the full maximal cover. A membership (c, v) is essential exactly when
deleting it leaves either vertex v without a membership or some edge {v, u}
without a shared column. Deletion cannot create a forbidden relationship.

Compute the set of cliques containing each vertex and each edge. A membership
(c, v) is essential if either condition holds:

- c is the only clique containing v.
- Some edge {v, u} in c occurs in c alone.

For an edge covered by one clique c, both endpoint memberships in c are essential.
Vertex coverage also handles isolates. Class weights affect objective costs,
but do not change this removal test on the reduced graph.

The shared membership matrix condition is M *B transpose(M) = adjacency.
Removing M[v, c] can change row v and column v of the Boolean product.
Symmetry makes a check of row v sufficient. This is the correction to the
paper's Section 4 wording already recorded for PR 7.

### Exact clique test for CLD-C

A whole clique c is essential exactly when deleting it leaves a vertex or edge
uncovered. Thus c is essential if it uniquely covers a vertex or an edge.
Fix the clique selection variable z[c] to 1. Keep selected cliques in full.
Keep the pure minimum letter objective; add no assignment objective.

### Why fixing these values is safe and exact

All candidate memberships are present in the reference full cover. If deleting
a decision loses a required relationship there, a subcover with fewer decisions
cannot restore that relationship. Every valid subcover therefore contains that
decision. Conversely, if deletion preserves full coverage, the resulting full
cover minus that one decision is a valid subcover without it. The scan identifies
exactly the universally required decisions within this candidate model.

Each decision is tested against the same full cover. The scan does not remove
optional decisions. Individually removable decisions can conflict when removed
together. HiGHS resolves these choices under all coverage constraints.
The scan preserves the full feasible set, optimum cost, and canonical selection
on the existing reduced model. The prior true twin proof establishes that its
canonical optimum expands to the original canonical optimum.

## Common implementation framework

Keep the existing graph context, strategy registry, model boundary, canonical
engine, and solver adapter in each language. Add one pure strategy operation,
`essential_decisions(model)`, with the corresponding existing naming convention
in R and JavaScript. Return a sorted unique list of model column indices.
Every returned column must belong to the ordered `decision_columns` set.
An empty list is a valid result. No public API or new solver option is required.

The sigma operation uses the existing group membership columns and edge endpoint
alternatives. A group with one alternative forces its membership. An edge with
one endpoint pair alternative forces both memberships. The C operation uses the
existing vertex and edge coverage column lists. A singleton list forces its
clique. Reuse these structures; do not enumerate cliques or rebuild a matrix
product again in the scan. Keep auxiliary sigma y variables outside the scan
result, objective support, and canonical decision order.

In R, each edge endpoint alternative set is a two column matrix. Test
`nrow(ends) == 1L` for a single covering clique, then take both endpoint indices.
Do not use `length(ends) == 1L`. Do not infer essential decisions from raw
singleton matrix rows; a row can constrain a zero cost auxiliary column.

The common canonical engine starts its existing deadline, computes essential
decisions, validates their indices, and sets their lower bounds to 1. All upper
bounds remain 1 initially. Run HiGHS even when every decision is essential.
Reuse these bounds on every canonical trial. Keep existing solution validation;
it must reject a returned solution that violates an essential bound, including
on the first solve. Invalid internal scan indices use the existing solver error
path. Keep R presolve off and Python/JavaScript presolve settings unchanged.

Apply lower bounds to the actual vector passed to the solver adapter. Canonical
trials copy that vector and keep every essential bound. Do not mutate the model's
coverage lists or decision order.

Expected runtime files:

- Python: `reduction.py`, `canonical.py`, and the two algorithm modules.
- R: `model.R`, `reduce.R`, and `canonical.R`.
- JavaScript: `model.ts` and `canonical.ts`.

Add focused tests in each language and a shared independent scan reference.
Update the six tests that call canonical engines with synthetic models:

- `python/tests/test_reduction_graph.py`
- `python/tests/test_letter_minimum.py`
- `tests/testthat/test-reduction-graph.R`
- `tests/testthat/test-letter-minimum.R`
- `js/test/reduction-graph.test.ts`
- `js/test/letter-minimum.test.ts`

These tests replace coverage checks, use bare problem models or empty coverage
lists, and inherit the production strategy. Replace the new essential scan
operation too, with an explicit empty result. Preserve their expected outputs
and purpose. Keep their noncontiguous decision indices, weighted caps, and
zero cost auxiliary column checks. Add malformed scan result tests to prove
that an auxiliary or absent column is rejected before the adapter runs.

Update `docs/algorithm.md` and the unreleased `NEWS.md` entry during implementation.
Do not change versions in this planning PR. The dependency already prepares
unreleased version 0.3.0; confirm release state before any implementation bump.

## Implementation sequence

1. Add the pure exact scans and registry operations in all three languages.
2. Apply and validate essential bounds in the common canonical engines.
3. Add independent deletion checks and tests that inspect first solve bounds.
4. Run conformance with unchanged fixture bytes and canonical expected outputs.
   Adapt the synthetic test strategies as specified above.
5. Measure the same inputs with and without the scan.
6. Update algorithm documentation and obtain exact head implementation reviews.

## Acceptance and validation

- For every labeled graph with 1 through 5 vertices, derive maximal cliques by
  independent vertex subset enumeration. Test each membership and each whole
  clique by direct deletion and full coverage reconstruction. Compare the exact
  essential sets with the production scans, both before and after true twin
  reduction. Keep this oracle independent of singleton coverage logic.
- Cover isolates, complete graphs, separate components, no essential decisions,
  all essential decisions, overlapping cliques, weighted classes, and interleaved
  original class members. Keep ordinary cycles as all essential cases. Use the
  following separate witnesses for optional choices that conflict together.
- Sigma conflict: use vertices 0 through 4 and edges 01, 02, 03, 04, 13, 14,
  23, 24. Maximal cliques are {0,1,3}, {0,1,4}, {0,2,3}, {0,2,4}. The four
  memberships of vertex 0 are individually removable. Removing its memberships
  in {0,1,3} and {0,2,3} together uncovers edge 03. The other eight memberships
  and all four C clique selections are essential.
- C conflict: use the existing six vertex fixture in
  `python/tests/test_letter_minimum.py`. Verify that {0,2,3} and {1,2,3} are
  each removable as whole cliques from the full maximal cover. Removing both
  uncovers edge 23. Check this witness separately from the 1 through 5 census.
- No essential decisions: use the complete tripartite graph with parts {0,1},
  {2,3}, and {4,5}. Include every edge between different parts and no edge
  within a part. Its eight maximal cliques are triples with one vertex from
  each part. All 24 sigma memberships and all eight C clique variables are
  individually removable. Removing both covering cliques of an edge loses it.
- The five item ABC example must force eight of nine sigma memberships and all
  three C clique variables. Group 3's B membership must remain optional.
- Instrument the solver boundary in all three languages. Verify essential
  lower bounds on the first call and subsequent calls. Verify optional bounds
  stay free on the first call. Reject a corrupted first result that violates
  an essential bound. Check deadline behavior, including scan time.
- Preserve all frozen sigma, C, and weighted fixture bytes. Run all 2,894
  reduction cases in all three languages. Run Python and JavaScript with
  presolve on and off. Keep errors, labels, means, public counts, default C,
  historical Python sigma helper behavior, and canonical choices unchanged.
- Run the normal Python lint, format, full tests, minimum dependency checks,
  examples, and wheel/source distribution checks. Run JavaScript typecheck,
  build, unit tests, conformance, and clean package install checks. Run R tests,
  conformance, and archive checks with PDF/HTML manuals. Run generator and
  release checks. Require the existing CI matrix on the implementation head.
- Benchmark wheat, ABC, complete graphs, repeated classes, and graphs with
  many overlapping cliques. Use the same model and data at the baseline and
  new head. Record essential/free decision counts, scan time, first solve time,
  canonical solve count, and full API time. Use warmup and repeated batches.
  State machine and dependency versions. Report regressions as well as gains.
  Timing is evidence, not a general speed guarantee.

## Scope limits

No FIND-AM search, greedy removal pass, warm start, variable elimination,
solver replacement, new public method, version publication, or merge is part
of this change. Preserve original group labels and data. Keep the preliminary
scan deterministic and internal. A future removal heuristic or warm start needs
its own contract and evidence.

## Review gate

Planning and implementation have separate review gates. Review the committed
plan with three independent reviewers. Verify the mathematical claims against
the paper and code. Resolve valid findings and obtain reviews of each revised
exact head until no actionable findings remain. A plan review does not establish
implementation correctness.

Before implementation merge readiness, repeat the required independent reviews
at the exact implementation head. Each review receives the absolute worktree,
exact base/head commits, scoped files, and findings-only rules. Check seated
reviewer readiness before sending. Every Agy review uses `/boost` in plan mode.
Every child receives the same workspace and commits. Wait for complete reports
and children, then verify their evidence. This gate grants no merge authority.
