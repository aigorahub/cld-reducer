# Driver checks. Run: Rscript benchmarks/test_r_driver.R --repo /absolute/repo
args <- commandArgs(trailingOnly = TRUE)
stopifnot(length(args) == 2L, identical(args[[1L]], "--repo"))
repo <- normalizePath(args[[2L]], mustWork = TRUE)
source(file.path(repo, "benchmarks", "r_driver.R"))
driver <- bench_driver(repo)
handle <- driver$handle
version <- handle(list(action = "version"))
stopifnot(version$ok, identical(version$settings$presolve, "off"),
          identical(version$settings_kind, "declared_contract"),
          version$module_load_ns >= 0, version$solver_load_ns >= 0,
          isTRUE(version$timer$monotonic), version$timer$resolution_ns > 0)
runtime <- driver$state$runtime
highs <- asNamespace("highs")

snapshot <- function(env) {
  names <- ls(env, all.names = TRUE)
  stats::setNames(lapply(names, function(name) {
    list(value = get(name, env, inherits = FALSE), locked = bindingIsLocked(name, env))
  }), names)
}
unchanged <- function(env, previous) {
  stopifnot(identical(ls(env, all.names = TRUE), names(previous)))
  for (name in names(previous)) {
    stopifnot(identical(get(name, env, inherits = FALSE), previous[[name]]$value),
              identical(bindingIsLocked(name, env), previous[[name]]$locked))
  }
}
original_runtime <- snapshot(runtime)
original_highs <- snapshot(highs)
case <- list(id = "path3", call = "adjacency", input = list(
  adjacency = list(list(1, 1, 0), list(1, 1, 1), list(0, 1, 1)),
  groups = list("a", "", "c")), options = list(method = "assignment_minimum"))
request <- function(action, input = case, ...) handle(c(list(action = action, case = input), list(...)))
measure <- request("measure", iterations = 2L)
capture <- request("capture")
profile <- request("profile")
preprocess <- request("preprocess")
for (answer in list(measure, capture, profile, preprocess)) stopifnot(answer$ok)
stopifnot(identical(measure$result, capture$result), identical(measure$result, profile$result),
          identical(capture$canonical, profile$canonical),
          identical(capture$canonical$selected, list(1L, 1L, 1L, 1L)),
          profile$metrics$decision_variables == 4L, profile$metrics$auxiliary_variables == 2L,
          profile$metrics$constraints == 9L, profile$metrics$nonzeros == 14L,
          profile$metrics$solve_count == 1L, profile$metrics$essential_cover,
          preprocess$metrics$solve_count == 0L, is.null(preprocess$metrics$selected),
          is.null(preprocess$result), is.null(preprocess$phases_ns$initial_optimization),
          profile$phases_ns$final_validation >= 0,
          profile$phases_ns$final_validation <= profile$profile_notes$render_result_total_ns,
          grepl("^[a-f0-9]{64}$", profile$profile_notes$temporary_patch$sha256),
          profile$metrics$solver_counters$available)
stopifnot(profile$metrics$probe_ns >= 0,
          profile$metrics$solver_total_ns + profile$metrics$probe_ns <= profile$phases_ns$total,
          preprocess$metrics$probe_ns == 0)
settings <- profile$metrics$solver_settings
stopifnot(settings$available, length(settings$records) == profile$metrics$solve_count,
          identical(settings$excluded_from_stable_comparison, list("time_limit")),
          identical(settings$records[[1L]]$solve, 1L),
          identical(settings$records[[1L]]$values$presolve, "off"),
          identical(settings$records[[1L]]$values$parallel, "off"),
          settings$records[[1L]]$values$mip_rel_gap == 0,
          settings$records[[1L]]$values$mip_abs_gap == 0,
          settings$records[[1L]]$values$primal_feasibility_tolerance == 1e-9,
          settings$records[[1L]]$values$mip_feasibility_tolerance == 1e-9,
          settings$records[[1L]]$values$r_global_threads == get("get_number_of_threads", highs)(),
          is.numeric(settings$records[[1L]]$values$threads),
          !"time_limit" %in% names(settings$records[[1L]]$values),
          identical(settings$records[[1L]]$excluded_values$time_limit, "Inf"),
          !preprocess$metrics$solver_settings$available,
          !length(preprocess$metrics$solver_settings$records))
overhead <- profile$profile_notes$full_call_overhead
stopifnot(overhead$reference_ns >= 0,
          overhead$instrumented_ns == profile$phases_ns$total,
          overhead$instrumented_minus_reference_ns == profile$phases_ns$total - overhead$reference_ns,
          overhead$ratio == profile$phases_ns$total / overhead$reference_ns,
          overhead$uninstrumented_calls == 1L)
unchanged(runtime, original_runtime)
unchanged(highs, original_highs)

# The two middle vertices are true twins. Profile counts must distinguish
# original edges from edges after the twin reduction.
twin_case <- list(id = "true_twins4", call = "adjacency", input = list(
  adjacency = list(list(1, 1, 1, 0), list(1, 1, 1, 1),
                   list(1, 1, 1, 1), list(0, 1, 1, 1)),
  groups = list("a", "b", "c", "d")))
for (method in c("letter_minimum", "assignment_minimum")) {
  twin_case$options <- list(method = method)
  twin_profile <- request("profile", twin_case)
  stopifnot(isTRUE(twin_profile$ok),
            isTRUE(twin_profile$metrics$vertices_before == 4L),
            isTRUE(twin_profile$metrics$vertices_after == 3L),
            isTRUE(twin_profile$metrics$edges == 5L),
            isTRUE(twin_profile$metrics$edges_after == 2L))
}
unchanged(runtime, original_runtime)
unchanged(highs, original_highs)

# Read native values independently. The package global setting and native option
# are separate observations; neither is copied from the version declaration.
real_native_run <- get("solver_run", highs)
native_threads <- NULL
unlockBinding("solver_run", highs)
assign("solver_run", function(solver) {
  native_threads <<- highs::hi_solver_get_int_option(solver, "threads")
  real_native_run(solver)
}, highs)
lockBinding("solver_run", highs)
stopifnot(request("measure", iterations = 1L)$ok,
          identical(settings$records[[1L]]$values$threads, native_threads))
unlockBinding("solver_run", highs)
assign("solver_run", real_native_run, highs)
lockBinding("solver_run", highs)

# Changing actual production setup must be visible even if version stays fixed.
production_lp <- runtime$solve_lp
mutated_lp <- production_lp
source_text <- paste(deparse(body(mutated_lp)), collapse = "\n")
stopifnot(grepl("mip_rel_gap = 0", source_text, fixed = TRUE))
body(mutated_lp) <- parse(text = sub("mip_rel_gap = 0", "mip_rel_gap = 0.025",
                                   source_text, fixed = TRUE))[[1L]]
runtime$solve_lp <- mutated_lp
mutated_profile <- request("profile")
stopifnot(mutated_profile$ok, mutated_profile$metrics$solver_settings$available,
          mutated_profile$metrics$solver_settings$records[[1L]]$values$mip_rel_gap == 0.025,
          handle(list(action = "version"))$settings$mip_rel_gap == 0,
          identical(runtime$solve_lp, mutated_lp))
runtime$solve_lp <- production_lp

# Native option getters are profiling hooks only. Capture, measure and version
# must work when observations are unavailable. Failed profile reads must restore.
getter <- get("hi_solver_get_str_option", highs)
unlockBinding("hi_solver_get_str_option", highs)
assign("hi_solver_get_str_option", function(...) stop("injected getter failure"), highs)
lockBinding("hi_solver_get_str_option", highs)
before_getter_failure <- snapshot(highs)
for (action in c("measure", "capture", "preprocess", "version")) {
  stopifnot(request(action, iterations = 1L)$ok)
}
missing_settings <- request("profile")
stopifnot(missing_settings$ok, !missing_settings$metrics$solver_settings$available,
          length(missing_settings$metrics$solver_settings$errors) == missing_settings$metrics$solve_count)
unchanged(highs, before_getter_failure)
unlockBinding("hi_solver_get_str_option", highs)
assign("hi_solver_get_str_option", getter, highs)
lockBinding("hi_solver_get_str_option", highs)
unchanged(runtime, original_runtime)
unchanged(highs, original_highs)

# Capture must use the actual canonical API return, without deriving decisions
# from displayed letters. A sentinel minimum verifies the internal hook seam.
real_canonical <- runtime$solve_canonical
real_render <- runtime$render_result
runtime$solve_canonical <- function(...) {
  answer <- real_canonical(...)
  answer$minimum <- 123L
  answer
}
runtime$render_result <- function(graph, cliques, model, solution, columns, strategy) {
  solution$minimum <- 4L
  real_render(graph, cliques, model, solution, columns, strategy)
}
sentinel <- request("capture")
stopifnot(sentinel$ok, sentinel$canonical$objective == 123L,
          sentinel$result$stats$objective == 4L)
runtime$solve_canonical <- real_canonical
runtime$render_result <- real_render

# A failure after all hooks are installed must restore package and native hooks.
real_lp <- runtime$solve_lp
runtime$solve_lp <- function(...) stop("injected solver failure")
before_failure <- snapshot(runtime)
for (action in c("capture", "profile")) {
  answer <- request(action)
  stopifnot(!answer$ok, grepl("injected solver failure", answer$error$message),
            is.null(answer$result), is.null(answer$canonical))
  unchanged(runtime, before_failure)
  unchanged(highs, original_highs)
}
# Preprocessing must still work when any optimizer use would fail.
stopifnot(request("preprocess")$ok)
runtime$solve_lp <- real_lp
unchanged(runtime, original_runtime)
unchanged(highs, original_highs)
stopifnot(identical(request("measure", iterations = 1L)$result, measure$result))

# Canonical counts and times must describe both accepted and rejected trials.
fixtures <- jsonlite::fromJSON(file.path(repo, "conformance", "fixtures", "reduce.json"),
                              simplifyVector = FALSE)$cases
trial_case <- fixtures[[which(vapply(fixtures, function(x) identical(x$id, "n5-0495"), logical(1)))]]
trial_case$options$method <- "assignment_minimum"
trial_profile <- request("profile", trial_case)
stopifnot(trial_profile$ok, trial_profile$metrics$canonical_feasible_trials > 0,
          trial_profile$metrics$canonical_infeasible_trials > 0,
          trial_profile$metrics$solve_count == 1L + trial_profile$metrics$canonical_feasible_trials +
            trial_profile$metrics$canonical_infeasible_trials,
          trial_profile$metrics$final_zero_decisions == trial_profile$metrics$canonical_infeasible_trials,
          trial_profile$phases_ns$canonical_trials == trial_profile$metrics$canonical_feasible_trials_ns +
            trial_profile$metrics$canonical_infeasible_trials_ns,
          identical(trial_profile$canonical, request("capture", trial_case)$canonical))
stopifnot(trial_profile$metrics$solver_settings$available,
          identical(vapply(trial_profile$metrics$solver_settings$records, function(x) x$solve, integer(1)),
                    seq_len(trial_profile$metrics$solve_count)))
limited_case <- trial_case
limited_case$options$time_limit <- 10
limited_profile <- request("profile", limited_case)
stopifnot(limited_profile$ok, limited_profile$metrics$solver_settings$available)
for (record in limited_profile$metrics$solver_settings$records) {
  stopifnot(is.numeric(record$excluded_values$time_limit), record$excluded_values$time_limit > 0,
            record$excluded_values$time_limit <= 10,
            identical(record$values, settings$records[[1L]]$values))
}

# Advance a fake clock at native calls. This does not sleep or apply timing
# thresholds. Production solver_info time must remain in the adapter total.
check_probe_clock <- function() {
  ticks <- new.env(parent = emptyenv())
  ticks$ns <- 0
  ticks$reads <- 0L
  original_clock <- bench_clock
  bench_clock <<- function() list(now = function() ticks$ns,
                                  description = list(name = "test clock", monotonic = TRUE,
                                                     fallback = FALSE, resolution_ns = 1))
  on.exit({ bench_clock <<- original_clock }, add = TRUE)
  delayed <- bench_driver(repo)
  stopifnot(delayed$handle(list(action = "version"))$ok)
  natives <- list()
  on.exit({
    for (name in names(natives)) {
      unlockBinding(name, highs)
      assign(name, natives[[name]], highs)
      lockBinding(name, highs)
    }
  }, add = TRUE)
  delay <- function(name, ns, diagnostic = FALSE) {
    force(ns)
    force(diagnostic)
    native <- get(name, highs)
    natives[[name]] <<- native
    unlockBinding(name, highs)
    assign(name, function(...) {
      ticks$ns <- ticks$ns + ns
      if (diagnostic) ticks$reads <- ticks$reads + 1L
      native(...)
    }, highs)
    lockBinding(name, highs)
  }
  delay("solver_run", 500)
  delay("solver_info", 700)
  for (name in c("hi_solver_get_str_option", "hi_solver_get_int_option", "hi_solver_get_dbl_option")) {
    delay(name, 100000, TRUE)
  }
  original_lp <- delayed$state$runtime$solve_lp
  delayed$state$runtime$solve_lp <- function(...) {
    ticks$ns <- ticks$ns + 900
    original_lp(...)
  }
  answer <- delayed$handle(list(action = "profile", case = trial_case))
  stopifnot(answer$ok)
  metrics <- answer$metrics
  stopifnot(metrics$canonical_feasible_trials > 0L, metrics$canonical_infeasible_trials > 0L,
            ticks$reads == 11L * metrics$solve_count,
            metrics$probe_ns == 100000 * ticks$reads,
            metrics$solver_total_ns == 2100 * metrics$solve_count,
            answer$phases_ns$initial_optimization == 500,
            metrics$canonical_feasible_trials_ns == 2100 * metrics$canonical_feasible_trials,
            metrics$canonical_infeasible_trials_ns == 2100 * metrics$canonical_infeasible_trials,
            answer$phases_ns$total == metrics$solver_total_ns + metrics$probe_ns,
            answer$phases_ns$canonical_trials == metrics$canonical_feasible_trials_ns +
              metrics$canonical_infeasible_trials_ns)
}
check_probe_clock()
unchanged(highs, original_highs)

for (iterations in list(NULL, 0L, -1L, 1.5, TRUE, "1")) {
  stopifnot(!request("measure", iterations = iterations)$ok)
}
stopifnot(!handle(list(action = "unknown"))$ok,
          !handle(list(action = "capture", case = list()))$ok)
cap_case <- case
cap_case$options$max_cliques <- 1L
for (action in c("measure", "capture", "profile", "preprocess")) {
  answer <- request(action, cap_case, iterations = 1L)
  stopifnot(!answer$ok, identical(answer$error$kind, "cldreducer_solver_error"),
            startsWith(answer$error$message, "maximal clique enumeration exceeded max_cliques="))
}
unchanged(runtime, original_runtime)
unchanged(highs, original_highs)
cat("R driver checks passed.\n")
