# Driver checks. Run: Rscript benchmarks/test_r_driver.R --repo /absolute/repo
args <- commandArgs(trailingOnly = TRUE)
stopifnot(length(args) == 2L, identical(args[[1L]], "--repo"))
repo <- normalizePath(args[[2L]], mustWork = TRUE)
source(file.path(repo, "benchmarks", "r_driver.R"))
driver <- bench_driver(repo)
handle <- driver$handle
version <- handle(list(action = "version"))
stopifnot(version$ok, identical(version$settings$presolve, "off"),
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
