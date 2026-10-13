# Benchmark driver protocol

This is development code. Each driver accepts `--repo ABSOLUTE_PATH` and optional `--presolve on|off` (R supports off only). Python: python_driver.py. R: r_driver.R. JavaScript: js_driver.mjs. The JavaScript source repository must have js/dist built. Drivers resolve runtime code and data from --repo, never from the current directory.

Use UTF-8 JSON lines on stdin and stdout. One response per request, no other stdout. Send diagnostics to stderr. Flush after each response. Continue after a package error; malformed requests return an error. EOF stops. Do not open output files. The coordinator supplies an explicit external output directory.

## Requests

All solve requests carry `case`, using the existing conformance shape: `{id, call: "adjacency"|"pairs", input: {adjacency?, groups?, pairs?, means?}, options: {method, max_cliques?, time_limit?, group1?, group2?, significant?}}`. Method is always explicit, letter_minimum or assignment_minimum. Input conversion to language-native containers happens before timing. The public API's own normalization and validation remain inside timing.

- `{"action":"version"}` loads the package and solver without a reduction. Return runtime, dependency and solver versions, `module_load_ns`, `solver_load_ns`, declared settings, and language. Mark settings as `declared_contract`. Profiles must observe actual native solver settings before those declarations can support acceptance. Module and solver load are separate where supported; otherwise mark the unavailable split with a reason.
- `{"action":"measure","case":CASE,"iterations":N}` times N consecutive complete public API calls with a monotonic clock. Return `elapsed_ns`, `iterations`, and the final normalized `result`. No profiling, captures, monkeypatches, result serialization, comparisons or assertions inside the timed region. The first such call after version is the first solve after loading. The pilot uses adaptive warmup calls to select the replay schedule. In comparisons, the coordinator sends the frozen per-case replay warmup requests before the measured requests. Warmup does not prove that JIT compilation or time drift has stopped.
- `{"action":"capture","case":CASE}` calls the real API with a temporary internal hook to capture the final canonical decision vector and primary minimum. Return normalized `result`, and `canonical: {selected:[0,1,...], objective:INTEGER}`. Restore all hooks even on error. Capture no auxiliary decisions.
- `{"action":"profile","case":CASE}` returns result, canonical, `metrics` and `phases_ns`. Profiles may use temporary wrappers or a disposable instrumented build, never shipped runtime edits. Record unavailable details with a reason; never fabricate zero for an unobserved metric. The coordinator makes three profile warmup requests before collecting the final request. All requests use the same profile module. Before hook setup, run one uninstrumented reference call and record `profile_notes.full_call_overhead` with reference_ns, instrumented_ns, their signed difference, and ratio. This diagnostic includes timing noise. Do not run this reference call for preprocessing. Separate profile results from uninstrumented measurement.
- `{"action":"preprocess","case":CASE}` builds and scans through graph reduction, clique enumeration and model construction, without optimization. Return metrics and phases. This bounds the multipartite 6 to 8 part cases. It must honor the production clique cap.

## Responses

Success: `{ok:true, action:ACTION, ...}`. Failure: `{ok:false, action:ACTION, error:{kind:CLASS_NAME, message:TEXT}}`. Errors must never carry a successful result.

Normalized result contains every public value in a common shape: groups array; assignments and letters as arrays in group order (avoid empty-key JSON object hazards); adjacency boolean rows; method; relationship_preserved; stats with snake_case keys including objective, solver_status and reduction_pct; rows array with group, letters and space-joined assignments (from JS rows or corresponding R/Python frame helper). Keep numeric values unrounded.

Metrics: vertices_before, vertices_after, edges (input graph), edges_after (reduced graph), maximal_cliques, decision_variables, auxiliary_variables, constraints, nonzeros, essential_decisions, solve_count, canonical_feasible_trials, canonical_infeasible_trials, final_zero_decisions, essential_cover (boolean coverage of the essential-only vector), selected, objective, solver_counters (unavailable with reason if unsupported). Collect model structure from the actual builders, not an independent approximate model.

All drivers report these nanosecond values under `metrics`: `solver_total_ns`, `probe_ns`, `canonical_feasible_trials_ns`, and `canonical_infeasible_trials_ns`. `solver_total_ns` sums the full adapter call intervals, less the measured diagnostic probe intervals inside those calls. `probe_ns` sums added native option and counter observations, including their record assembly. Subtract each measured interval once. Keep production reads in solver time. For example, R observes the result of the production `solver_info` call. Its native call time stays in solver time; only the added counter record callback is a probe.

The feasible and infeasible trial values sum adapter call time after probe subtraction for each status. Their sum equals `phases_ns.canonical_trials` on a successful profile that runs the solver. On a certified call with zero solves, Python reports `phases_ns.canonical_trials` as null because its trial timer did not run. R and JavaScript report zero. The separate trial counts and nanosecond metrics are zero in all three drivers. No acceptance gate uses this phase value for certified calls. `phases_ns.total` includes all probe time. Native optimization timers exclude probe work. Do not subtract the signed full-call reference difference from any phase. Wrapper and timer overhead outside the measured probe intervals remains in diagnostic timings. These corrections apply only to profiles; `measure` stays uninstrumented.

Target eligibility uses `solver_total_ns / (phases_ns.total - metrics.probe_ns) >= 0.25` with essential-only coverage. The numerator already excludes measured diagnostic probes. Remove those same probes from the full API denominator. Require finite, nonnegative probe time and a positive corrected total. Keep the recorded total unchanged. The uninstrumented reference difference is not a correction to this ratio.

Phase keys: input, vertex_reduction, enumeration, model_construction, essential_scan, adapter_setup, model_load, initial_optimization, canonical_trials, output_expansion, final_validation, total. Drivers emit integers on their clock's nanosecond scale. For nested inclusive timings state that fact in `profile_notes`; do not sum overlapping stages. Report missing phases as null with a reason. Do not change presolve or thread settings between profile and measurement.

R requires `microbenchmark::get_nanotime`; a missing microbenchmark package stops the driver. There is no proc.time fallback. `timer.warnings` retains clock initialization and resolution warnings in the version response. These reads occur outside measured calls. `timer.resolution_ns` is an observed minimum read interval and includes read overhead. The driver does not calibrate absolute timing accuracy, as recorded by `timer.absolute_accuracy_calibrated: false`. Treat elapsed values as observations from that clock, subject to its recorded platform warnings. Do not claim calibrated physical nanoseconds. Version identity omits observed warnings and resolution values, but retains the clock name, method, and accuracy statement.

R loads repository source functions into a private environment. Its module load includes source evaluation and Matrix loading. Its measured API calls execute those source functions. The timing scope is this source environment, not an installed package.

The external profile wall limit covers the whole request. This includes the uninstrumented reference and instrumented full call. Preprocessing has no reference call.

A profile-only temporary source patch must have its hash and source head in profile_notes. The measurement build must stay unmodified. Drivers must also work on the later runtime branch.

Profiles report `metrics.solver_settings`. It contains one ordered record per actual native solve. Each record contains stable native values. Store the changing shared deadline value separately under `excluded_values.time_limit`. Record no observed settings when no solver runs. JavaScript records its single thread API constraint separately because that API has no native thread option. R records both native and package global thread settings. The acceptance gate checks these observations against the declared settings.

An unlimited `excluded_values.time_limit` is null. Preprocessing has no uninstrumented reference call, so `profile_notes.full_call_overhead` is null. JavaScript total time includes per-model hook installation inside adapter calls. Initial profile hook setup stays outside total time.


## Lazy compilation profile schema

Profiles and preprocessing responses include `profile_schema`. Version 2 describes
the decision-plan runtime. Version 1 describes the earlier compiled-model runtime.
Existing saved records without this field retain their earlier meaning. Do not
rewrite archived records or pinned study inputs.

Version 2 adds the `decision_plan` phase and the boolean `metrics.model_compiled`.
Decision-plan time includes graph context and coverage data. Model-construction
time measures only BIP compilation. A certified public call reports
`model_compiled: false`, null model-construction time, and null
`auxiliary_variables`, `constraints`, and `nonzeros`, with reasons in profile notes.
Those nulls mean that no compiled model was observed. They are not zero dimensions.
Decision count, essentials, result, and canonical vector remain available. Solver
counts and measured solver work are zero when no solver runs.

Fallback profiles retain actual compiled dimensions. The explicit `preprocess`
request forces BIP compilation through the private compiler and scans the plan
without solving. It measures that diagnostic path, not the certified public path.
Capture reads decision costs and selections without requiring a compiled problem.
Drivers also retain support for the earlier runtime and its native column mapping.
These schema changes apply to local driver checks. They do not resume the stopped
cloud timing study.
