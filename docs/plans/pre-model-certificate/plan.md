# Prove the essential cover before building the BIP

Status: proposed, awaiting Agy plan review. No runtime implementation in this change.

Workspace: `/Users/john/aigora/dev/cld-reducer-pre-model-certificate`.
Branch: `plan/pre-model-certificate`.
Base runtime: `19d5698b4ef77af2d0080d50cac725f368097e65`.
Proposed implementation PR: **Avoid BIP construction for certified essential covers**.

## Goal and scope

Return exactly the same minimum, canonical decisions, letters, statistics, and errors for the two existing objectives. Avoid constructing a solver problem when the essential decisions already prove the unique optimum. Apply the same design in Python, R, and JavaScript.

Keep CLD-C as the default. Keep sigma as the optional assignment objective. Secondary optimization is deferred. Bitsets, new solver algorithms, incremental solver reuse, dependency changes, and new public options are outside this change.

The user stopped the timing study. Its cloud resources have been deleted. Do not resume it, provision machines, or make a large timing study a requirement for this PR. Keep its saved results and pinned sources unchanged. This plan authorizes no merge or publication.

## Current code and avoidable work

`reduce_validated` in Python, with matching R and JavaScript pipelines, currently performs:

1. Validate inputs and controls; reduce identical closed neighborhoods.
2. Enumerate and sort the maximal cliques.
3. Build graph context and the full method-specific BIP.
4. Find essential decisions; test whether they cover the graph.
5. Return a certified result, or call HiGHS and apply the canonical tie-break.
6. Expand vertex classes, name letters, and validate the original relationships.

The graph-context builder currently searches the clique list separately for each vertex. Sigma also constructs edge witnesses, constraint rows, sparse arrays, and objective arrays before the certificate can return. Certified cases need the combinatorial coverage information but do not need those solver arrays.

Source entry points: Python `context.py`, `reduction.py`, `canonical.py`, and `algorithms/{assignment_minimum,letter_minimum}.py`; JavaScript `model.ts`, `reduce.ts`, and `canonical.ts`; R `model.R`, `reduce.R`, and `canonical.R`.

## Proposed common framework

Separate the method's decision and coverage data from its solver representation. Use one small internal decision-plan contract per language. The names below describe responsibilities; use the repository's existing naming style during implementation.

The decision plan holds:

- The reduced graph context, original class weights, and canonical maximal cliques.
- The ordered semantic decisions: clique indices for C, or `(clique, vertex)` memberships for sigma.
- The objective cost of each decision, without auxiliary columns.
- Vertex and edge coverage alternatives in decision positions.

Do not put a solver `Problem`, sparse coefficient arrays, or sigma auxiliary variable allocation in this object. It is ordinary method data, not another general optimization framework. Retain only coverage structures needed by the scan, coverage check, decoder, and fallback compiler. Avoid duplicate edge-alternative representations.

The strategy supplies the decision-plan builder, coverage predicate, essential scan, decoder, and lazy BIP compiler. The shared engine validates the plan, attempts the certificate, and dispatches the fallback. The returned selection is always in semantic decision order. R retains native one-based indexing; Python and JavaScript retain zero-based indexing.

### Build membership incidence once

Initialize one clique-membership list per reduced vertex. Visit cliques in canonical order and append the clique index to each member's list. This costs one append per membership and produces sorted lists without a later sort.

For an edge, intersect its endpoints' sorted clique lists to obtain the covering alternatives. Implement a simple ordered intersection, with the same ordering in all languages. Retain these alternatives for the fallback compiler instead of recomputing them. Do not introduce bitsets or a size-based representation policy in this PR.

### Run the exact scan and certificate on the decision plan

Keep the existing rules:

- C: a single alternative for a vertex or edge forces that clique decision.
- Sigma: a vertex with one membership forces it; an edge with one covering clique forces both endpoint memberships.
- Isolates remain covered. Adjacent identical-neighborhood classes retain their weights. Nonadjacent twins do not merge.

Validate that the scan returns sorted, unique, valid decision positions. Preserve the existing invalid-solution error for malformed scan results. Do not treat an invalid plan or malformed scan as permission to return a certificate.

Construct the selection containing exactly the essentials. Check complete vertex and edge coverage using the same strategy predicate used by the fallback result validator. If the coverage test fails, continue to BIP construction.

For a successful certificate, require finite positive integer costs and an exactly representable objective under the existing language contract. C costs are 1. Sigma costs are the original class sizes. The built-in strategies declare their auxiliary costs to be zero; their compiler tests must enforce that declaration. A generic/custom model with different costs cannot use this graph-only proof. Keep the existing model-based certificate helper and its defensive tests for direct internal engine calls, or adapt them through a shared proof kernel without weakening their guarantees.

Proof: every feasible decision vector contains the essentials. If those essentials cover the graph, they form a feasible vector. Any different feasible vector adds a positive-cost decision. Thus this vector is the unique optimum and is already canonical. Sigma edge witnesses can be supplied by the coverage predicate; their choices do not change the objective or the output vector.

### Compile only on fallback

If the certificate does not apply, compile the existing C or sigma BIP from the decision plan. Keep the mathematical constraints, costs, solver settings, canonical order, and public output unchanged.

Return an explicit mapping from semantic decision positions to native solver columns. Validate that it is ordered as intended, unique, in range, and consistent with the plan's costs and coverage. Auxiliary columns must remain outside canonical decisions and objective caps. Preserve support for noncontiguous native column indices in the shared engine.

Map the already computed essentials to native columns and fix them to 1. Do not rescan the graph or run the same certificate again on this public fallback path. Run the existing initial solve and canonical trials once, then decode through the common result path. Keep a private test route that forces the full BIP path for differential checks; add no public option.

### Preserve the time budget

Today graph reduction, enumeration, and BIP construction occur before the deadline starts. The documented budget covers the essential scan, certificate check, and canonical solver work.

Build the combinatorial decision plan before starting this budget. Start the budget before the essential scan. Check it after scan validation and after the certificate attempt. Return no certified result after the budget has expired.

On fallback, preserve the remaining budget across lazy BIP construction. Exclude only that construction interval, as the existing API does. Resume the same remaining budget for the initial solve and all canonical trials; never grant a new full limit. Prefer a small shared budget helper or an explicit remaining-budget handoff over separate per-stage limits. Keep unlimited time behavior and error prefixes unchanged. Test the clock behavior with controlled clocks, not wall-clock thresholds.

### Preserve all result checks

Both paths use existing expansion, rendering, counts, and exact adjacency reconstruction. Check the reported objective against assignments for sigma and letters for C. Preserve original vertex counts, weights, ordering, clique cap behavior, aliases, and input-error precedence. Keep current dependency loading, including JavaScript WASM loading, unchanged.

## Implementation sequence

1. Add shared decision-plan data and one-pass membership incidence. Keep the existing runtime output through adapters until the representation is checked.
2. Move public essential scanning and certificate evaluation ahead of the lazy BIP compiler. Reuse the plan on fallback and pass the remaining time budget correctly.
3. Apply the same contract in Python, R, and JavaScript. Update the algorithm specification and release notes. Keep existing package versions and frozen submission artifacts unchanged.
4. Run correctness and structural checks. Get the existing required independent implementation reviews on the exact proposed merge head. No merge without current user approval.

## Verification and acceptance

The acceptance claim is correct output with less work on certified inputs. This PR does not claim a measured speed factor.

- Run the existing shared reduction fixtures across all three languages. Compare complete public output and canonical decisions against the pinned base and the forced BIP path. Use presolve on and off for Python and JavaScript; retain R's existing setting.
- Keep the independent small-graph oracle checks. Include C and sigma, weighted and interleaved classes, isolates, and graphs with several optimal covers. Do not replace independent expected answers with outputs from the new code.
- For certified complete graphs, isolates, and the five-vertex example, instrument the BIP compiler and solver adapter to fail if called. Check exact outputs. This proves that the intended work is skipped.
- For K(2,2,2) and a graph whose nonempty essential set does not cover it, prove fallback occurs. Check essential lower bounds, native-column mapping, exact objective, canonical decisions, and final adjacency.
- Compare fallback model dimensions, costs, bounds, ordered decision mapping, and sparse coefficients against the pinned implementation on representative C and sigma inputs. A semantically equivalent representation change needs an explicit explanation; do not accept a different feasible problem.
- Cover malformed scan output, zero/noninteger/nonfinite costs, language-specific exact-integer limits, nonzero auxiliary cost in the legacy custom-model path, and noncontiguous solver decision columns. Preserve the existing solver fault checks.
- Use controlled-clock tests for expiry during scan and certificate, remaining-budget handoff, exclusion of model-build time, expiry before a canonical trial, and unlimited time.
- Run package checks relevant to touched source and docs. Do not rerun submission services or restart cloud measurements.

A short local allocation/profile diagnostic is optional if correctness checks show that a fallback representation duplicates work. It must not become another timing campaign or a condition for completion. Record any performance claim as unmeasured unless supported by a separate agreed test.

## Risks and review questions

The main risks are moving work without actually avoiding BIP allocations, doing duplicate work on fallback, changing decision order, bypassing cost validation, and resetting or widening the solve budget. Review the decision-plan boundary and budget handoff before coding. The two objectives remain single-objective; this refactor does not add lexicographic C/sigma optimization.
