# Essential cover certificate

Status: implementation contract. Correctness and speed acceptance remain open.

Benchmark base: `0b6562856b532769b9adfb13308daa718fac5e94`.
Reference runtime: `0f5a707d65d3fa019269e79279c09786792a1911`.
The accepted design is `../clique-performance/design.md`.

## Selection evidence

The fresh reference pilot passed 216 solve cases. The full capture passed 8,907 result and canonical vector checks in Python, R, and JavaScript. All 240 profiles completed. They contain 216 successful solves, 16 successful preprocessing cases, two bounded R sigma preprocessing timeouts, and six expected clique cap errors. Raw source, code, version, output, dimension, pilot, and resource checks passed.

The fixed eligibility rule selects every case whose essential set covers the graph and whose solver calls use at least 25 percent of total API time after probe cost is removed. All six language and method groups have enough distinct inputs in both sets. Median solver shares on eligible cases range from 47.1 to 73.3 percent. These costs support this candidate. They do not prove a speed gain.

| Language | Method | Development cases | Validation cases |
| --- | --- | ---: | ---: |
| Python | C | 13 | 12 |
| Python | sigma | 12 | 12 |
| R | C | 14 | 11 |
| R | sigma | 12 | 10 |
| JavaScript | C | 16 | 13 |
| JavaScript | sigma | 14 | 13 |

Use the recorded profile rule without retuning on candidate results. All six groups are gain targets. All timed cases remain regression checks. A/A calibration and the frozen manifest must precede candidate timing. Implementation and correctness checks can proceed while calibration waits for an idle host.

## Proof

Let D be the ordered binary decisions. Let E be the essential decisions returned by the existing exact scan. Every feasible decision vector contains E. Every decision has a positive integer primary cost. Every auxiliary variable has zero primary cost.

Let x_E select exactly E. If the existing strategy coverage predicate accepts x_E, it has feasible witnesses in the existing model. Every feasible solution has cost at least the sum of the costs in E. Any different feasible decision vector selects at least one more positive cost decision. Thus x_E is the unique primary optimum. It is also the canonical optimum. Auxiliary witness ties do not affect that claim.

This proof applies to C and weighted sigma. It does not claim that optional decisions can be removed independently when E fails to cover the graph.

## Shared engine contract

1. Keep the existing validation of ordered decision columns and the exact essential scan output. Keep current errors for malformed outputs.
2. Start the shared deadline before the essential scan. Check it after scan validation and after the certificate attempt. Use the existing method failure prefix and time limit error.
3. Use one private certificate helper per language. It receives the model, ordered decisions, essential indices, and strategy. It checks finite positive integer costs for every decision and zero costs for all other columns. It returns no certificate when those cost assumptions do not hold. It must not silently discard nonzero auxiliary cost.
4. Build the selected vector in decision order. Use the existing coverage predicate. When coverage holds, return that vector and the exact sum of selected original costs. When it fails, use the existing BIP and canonical loop with the same essential bounds.
5. Keep a private engine argument to disable the certificate for differential tests. The public API has no new option. Use `_certificate=True` in Python, `certificate = TRUE` in R, and a fourth internal `certificate = true` argument in JavaScript.
6. Return through the existing expansion, rendering, statistics, and final relationship checks. Preserve labels, C default, method aliases, weights, clique ordering and cap behavior. Preserve JavaScript module and WASM loading.
7. Keep benchmark acceptance code fixed. Existing profiles must show zero actual solves on certified calls. Record certificate time separately with temporary diagnostic wrappers around the private helper. Such diagnostics do not enter the full API speed gate.

Private helper names: Python `_essential_cover_certificate`, R `essential_cover_certificate`, JavaScript `essentialCoverCertificate`. Each returns either the selected vector and minimum or no certificate. It has no clock, solver call, global cache, or public output side effect. The canonical engine owns the deadline.

## Verification

Compare full output, objective, and ordered decision vector with the forced reference on the shared exhaustive fixtures. Keep independent oracle checks. Exercise both methods, weighted true twins, isolates, noncontiguous decision columns, empty essential sets, and essential sets that fail coverage. Test nonpositive decision costs, nonzero auxiliary costs, malformed scan outputs, and timeout after both the scan and the certificate attempt.

Keep solver fault assertions reachable. Use K(2,2,2), whose essential set is empty for both methods, where an old all-essential input would bypass the solver. Keep simple inputs for no-solver certificate tests. Do not delete, skip, or weaken fault assertions.

Python and JavaScript conformance must use presolve on and off. R stays off. Keep package loading and archive rules unchanged. Add a release note under the existing untagged 0.3.0 version. Keep 0.2.0 submission artifacts unchanged.

Run the frozen capture and resource gates, two independent quiet timing comparisons, and the unchanged gain and regression gates. Keep the reference if this candidate fails. Obtain exact-head reviews from Grok, Agy with Boost in plan mode, Fugu, and Claude before merge readiness. This contract grants no merge or publication authority.
