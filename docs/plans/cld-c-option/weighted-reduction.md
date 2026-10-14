# Weighted vertex reduction and the C default

This extension applies to PR 7 on `plan/cld-c-option`. The prior implementation is commit `23925580b91f0a87468d602387183f51754936d9`.

The user approved two changes: apply Lemma 2.5 vertex reduction and make CLD-C the default in R, Python, JavaScript, and the Python command line. FIND-AM is not part of this extension. A performance comparison with HiGHS would be needed before choosing that search algorithm.

## Contract

- Merge equal adjacency rows, including the unit diagonal. Retain the original members of each class in input order.
- Build both models on the reduced graph. Give each sigma membership its original class size as cost. Give each C clique cost 1.
- Use the same positive integer costs in the objective, canonical cap, and returned solution checks.
- Expand selected columns before mean ordering, label assignment, relationship checks, and public statistics. Preserve the existing canonical result for each explicit method.
- Preserve isolated vertices and the original maximal clique count. Keep the existing clique cap and solver deadline contract.
- Change the public default to `letter_minimum`. Keep the historical Python assignment-minimum helper on sigma. Update examples and package text.

The proof that reduction preserves the canonical result is in `docs/algorithm.md`, section 3. It uses equality of assignment counts within a true twin class at an optimum. Copying the greatest membership row to the whole class preserves cost and raises the full decision vector unless the rows already agree.

## Checks

The existing sigma and C fixtures stay unchanged. The runners explicitly select sigma for historical sigma records. Thirty new exact reference cases exercise repeated vertices, interleaved class members, distinct isolated vertices, and the new C default. One weighted witness gives a sigma cost of 19; ignoring weights would select a cover costing 23 after expansion.

Each language has direct tests of class membership, original counts, the default method, and weighted canonical caps. The independent paper audit corpus checks both objectives and canonical columns on 1,104 graphs. Package builds and clean installs must use the new defaults. Benchmark the old and new code with the same inputs and explicit methods. Timing results describe the test machine and inputs only.

## Review gate

Before merge readiness, obtain independent findings from the seated Grok and Agy reviewers at the exact committed head. Check that both are idle before sending. Use `/boost` and plan mode for every Agy review. Every child must receive the same absolute workspace, base, and head. Verify evidence and obtain another review after any valid fix. This extension grants no merge authority.

## Local measurements

A Python benchmark compares the prior commit with this extension. Each result is a median of nine batches of five complete API calls, after a warmup. Explicit methods and outputs are the same in both runs. On this machine, wheat sigma changed from 15.96 ms to 1.00 ms. Its first model changed from 447 to 36 binary variables and from 974 to 63 rows. Membership decisions changed from 56 to 15. The observed solve count changed from 17 to 3. These times do not compare FIND-AM with HiGHS.

On the same run, a complete graph with 100 vertices improved by 7.4 times for sigma and 4.0 times for C. A repeated path with 30 vertices improved by 4.6 times for sigma and 1.9 times for C. The five vertex example without any reducible class had similar times. These are local measurements, not a performance guarantee.
