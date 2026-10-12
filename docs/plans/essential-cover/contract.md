# Essential cover certificate

Status: implementation contract. Correctness and speed acceptance remain open.

Benchmark base: `3cb93d8d8842fe8ccf4d1ac957e3a1b0706088eb`.
Reference runtime: `0f5a707d65d3fa019269e79279c09786792a1911`.
The accepted design is `../clique-performance/design.md`.

## Historical selection evidence

The earlier host reference pilot passed 216 solve cases. The full capture passed 8,907 result and canonical vector checks in Python, R, and JavaScript. All 240 profiles completed. They contain 216 successful solves, 16 successful preprocessing cases, two bounded R sigma preprocessing timeouts, and six expected clique cap errors. Raw source, code, version, output, dimension, pilot, and resource checks passed.

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

The historical selection table comes from `baseline-v5-preflight.json` in the external evidence directory. Its SHA256 is `7eadab1cdbeed99523e154b47fee08599b6799132d227981d183e5b5f17962ce`. It supersedes the historical table in `../clique-performance/baseline.md`. The preflight record binds the source, harness, pilot, capture and profile resource evidence.

## Final timing protocol

The historical host evidence selected this candidate. It cannot validate the new measurement code or a cloud machine. Collect a fresh reference pilot, full output capture, profiles and A/A calibration on each machine. Keep the eligibility rule and all six language and method gain targets fixed. The fresh reference profiles determine eligible membership before candidate timing.

Use one dedicated cloud machine for each language. Each machine retains the full case corpus for that language. Verify each official solve key set and the complete union of 216 solve keys. Compare full result values and canonical vectors across all three captures. Keep each language's reference and candidate on the same machine. Do not pool times or transfer calibration evidence between machines.

Start with 16 fresh process pairs and 36 measured batches. Use the reviewed warm pilot to target 100 ms batches. Freeze the per-case replay warmup count from reference measurements. Run the same count on both sides. The baseline measured batch median must meet the 50 ms floor, except at the fixed iteration cap. Record side and paired drift as diagnostics. These values do not add a pass limit, trigger a retry or change the estimator.

Run one reference calibration per language. Do not repeat a pilot or a collection, change the design, or restart an interrupted collection. A failed or interrupted stage stops the lane and prevents candidate observations in every lane. Keep partial evidence for diagnosis. Do not use incomplete rows for acceptance.

Review all reference trajectories and evidence. All three A/A calibrations must pass the existing limits. Freeze all three manifests before any candidate capture, profile or timing. Host receipts bind the three source commits, complete input inventories and the reviewed evidence hashes. The fresh frozen manifests define final target membership. Before releasing any candidate stage, require each machine to have time for twice its measured A/A duration, its measured capture and profile durations, and a fixed three hour margin. Check all three machines before dispatch and check each machine again before its first candidate observation. Run two independent candidate comparisons per language. Require every case, target group, correctness and resource gate to pass in both runs. Missing evidence cannot pass. Compare candidate captures across languages as well.

Retain the final source hashes, raw measurements, host receipts, profiles, captures, diagnostics and audits in the external cloud evidence archive. Verify its hash after download before deleting the temporary machines and disks. Report the result from these records without changing the candidate commit after measurement. Keep the reference if the candidate fails the fixed speed gates.

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

The external evidence directory contains `diagnostics/certificate_python.py`, `diagnostics/certificate_r.R`, and `diagnostics/certificate_js.mjs`. These temporary wrappers are syntax checked. Their measurements remain pending until calibration and freeze pass. Each output records the source, script, case and frozen manifest hashes.

Private helper names: Python `_essential_cover_certificate`, R `essential_cover_certificate`, JavaScript `essentialCoverCertificate`. Each returns either the selected vector and minimum or no certificate. It has no clock, solver call, global cache, or public output side effect. The canonical engine owns the deadline.

## Verification

Compare full output, objective, and ordered decision vector with the forced reference on the shared exhaustive fixtures. Keep independent oracle checks. Exercise both methods, weighted true twins, isolates, noncontiguous decision columns, empty essential sets, and essential sets that fail coverage. Test nonpositive decision costs, nonzero auxiliary costs, malformed scan outputs, and timeout after both the scan and the certificate attempt.

Keep solver fault assertions reachable. Use K(2,2,2), whose essential set is empty for both methods, where an old all-essential input would bypass the solver. Keep simple inputs for no-solver certificate tests. Do not delete, skip, or weaken fault assertions.

Python and JavaScript conformance must use presolve on and off. R stays off. Keep package loading and archive rules unchanged. Add a release note under the existing untagged 0.3.0 version. Keep 0.2.0 submission artifacts unchanged.

Run the frozen capture and resource gates, two independent quiet timing comparisons, and the unchanged gain and regression gates. Keep the reference if this candidate fails. Obtain exact-head reviews from Grok, Agy with Boost in plan mode, Fugu, and Claude before merge readiness. This contract grants no merge or publication authority.
