plan_for <- function(adjacency, strategy) {
  graph <- list(adjacency = adjacency, groups = as.character(seq_len(nrow(adjacency))), means = NULL)
  strategy$planner(graph_context(graph, maximal_cliques(adjacency, 10000L),
                                 assignments = strategy$counts_assignments))
}

test_that("certified public calls do not compile a BIP", {
  local_mocked_bindings(
    compile_assignment_plan = function(...) stop("compiler called"),
    compile_letter_plan = function(...) stop("compiler called"),
    build_model = function(...) stop("builder called"),
    build_letter_model = function(...) stop("builder called"),
    solve_lp = function(...) stop("solver called")
  )
  for (graph in list(diag(TRUE, 4), matrix(TRUE, 5, 5), simple_adjacency())) for (strategy in reduction_methods()) {
    expect_true(reduce_from_adjacency(graph, method = strategy$name)$relationship_preserved)
  }
})

test_that("fallback scans and compiles once with or without some essentials", {
  parts <- rep(1:3, each = 2L)
  graph <- outer(parts, parts, `!=`)
  diag(graph) <- TRUE
  with_isolate <- diag(TRUE, 7)
  with_isolate[1:6, 1:6] <- graph
  for (adjacency in list(graph, with_isolate)) for (strategy in reduction_methods()) {
    plan <- plan_for(adjacency, strategy)
    reference <- solve_canonical(strategy$builder(plan$context), NULL, strategy, certificate = FALSE)
    scans <- builds <- 0L
    original_scan <- strategy$essential_decisions
    original_compile <- strategy$compiler
    strategy$essential_decisions <- function(data) {
      scans <<- scans + 1L
      original_scan(data)
    }
    strategy$compiler <- function(data) {
      builds <<- builds + 1L
      original_compile(data)
    }
    expect_identical(solve_canonical(plan, NULL, strategy), reference)
    expect_identical(scans, 1L)
    expect_identical(builds, 1L)
  }
})

test_that("fallback excludes compilation time without resetting the remaining budget", {
  parts <- rep(1:3, each = 2L)
  graph <- outer(parts, parts, `!=`)
  diag(graph) <- TRUE
  now <- 0
  local_mocked_bindings(elapsed = function() now,
    solve_lp = function(problem, lower, upper, sum_limit, time_limit) {
      expect_equal(time_limit, 7)
      stop("budget verified")
    })
  for (strategy in reduction_methods()) {
    now <- 0
    plan <- plan_for(graph, strategy)
    scan <- strategy$essential_decisions
    coverage <- strategy$coverage
    compiler <- strategy$compiler
    strategy$essential_decisions <- function(data) { now <<- now + 2; scan(data) }
    strategy$coverage <- function(data, selected) { now <<- now + 1; coverage(data, selected) }
    strategy$compiler <- function(data) { now <<- now + 100; compiler(data) }
    expect_error(solve_canonical(plan, 10, strategy), "budget verified")
  }
})

test_that("expiry during scan or proof prevents compilation", {
  now <- 0
  local_mocked_bindings(elapsed = function() now)
  for (phase in c("scan", "certificate")) for (strategy in reduction_methods()) {
    now <- 0
    plan <- plan_for(simple_adjacency(), strategy)
    scan <- strategy$essential_decisions
    coverage <- strategy$coverage
    strategy$essential_decisions <- function(data) {
      if (phase == "scan") now <<- 5
      scan(data)
    }
    strategy$coverage <- function(data, selected) { now <<- 5; coverage(data, selected) }
    strategy$compiler <- function(...) stop("compiler called")
    expect_error(solve_canonical(plan, 5, strategy), "Time limit reached")
  }
})

test_that("plan costs and indices retain proof safeguards", {
  strategy <- reduction_methods()[[2L]]
  plan <- plan_for(simple_adjacency(), strategy)
  for (required in list(NULL, TRUE, -1, 999, 0.5, c(2, 1), c(1, 1))) {
    custom <- strategy
    custom$essential_decisions <- function(...) required
    expect_error(solve_canonical(plan, NULL, custom), "invalid solution")
  }
  for (cost in c(0, -1, 0.5, NA_real_, Inf)) {
    bad <- plan
    bad$cost[1L] <- cost
    expect_null(plan_certificate(bad, strategy$essential_decisions(bad), strategy))
  }
  plan$cost[] <- .Machine$integer.max
  expect_null(plan_certificate(plan, strategy$essential_decisions(plan), strategy))
})

test_that("plan essentials map to native columns without changing canonical order", {
  strategy <- reduction_methods()[[2L]]
  plan <- plan_for(simple_adjacency(), strategy)
  plan$cost <- c(3, 7, 11)
  strategy$essential_decisions <- function(...) c(1L, 2L)
  strategy$coverage <- function(model, selected) selected[1L] && selected[2L]
  strategy$compiler <- function(...) list(problem = list(num_cols = 5L,
    decision_columns = c(5L, 1L, 3L), cost = c(7, 0, 11, 0, 3),
    matrix = Matrix::sparseMatrix(i = 1:3, j = c(1L, 5L, 2L), x = 1, dims = c(3L, 5L)),
    row_lower = rep(1, 3), row_upper = rep(Inf, 3)))
  original_solve <- solve_lp
  calls <- 0L
  local_mocked_bindings(solve_lp = function(problem, lower, upper, sum_limit, time_limit) {
    if (calls == 0L) expect_equal(lower, c(1, 0, 0, 0, 1))
    calls <<- calls + 1L
    original_solve(problem, lower, upper, sum_limit, time_limit)
  })
  expect_identical(solve_canonical(plan, NULL, strategy, certificate = FALSE),
                   list(selected = c(TRUE, TRUE, FALSE), minimum = 10L))
  expect_gt(calls, 0L)
})

test_that("invalid compiled models fail before the solver", {
  calls <- 0L
  local_mocked_bindings(solve_lp = function(...) {
    calls <<- calls + 1L
    stop("invalid model reached solver")
  })
  for (defect in c("count", "duplicate", "range", "decision_cost", "auxiliary_cost", "cost_length")) {
    strategy <- reduction_methods()[[1L]]
    plan <- plan_for(simple_adjacency(), strategy)
    model <- strategy$compiler(plan)
    problem <- model$problem
    if (defect == "count") problem$decision_columns <- problem$decision_columns[-1L]
    else if (defect == "duplicate") problem$decision_columns[2L] <- problem$decision_columns[1L]
    else if (defect == "range") problem$decision_columns[1L] <- problem$num_cols + 1L
    else if (defect == "decision_cost") problem$cost[1L] <- problem$cost[1L] + 1
    else if (defect == "auxiliary_cost") problem$cost[plan$decision_count + 1L] <- 1
    else problem$cost <- problem$cost[-length(problem$cost)]
    model$problem <- problem
    strategy$compiler <- function(...) model
    expect_error(solve_canonical(plan, NULL, strategy, certificate = FALSE),
                 "HiGHS returned an invalid solution", info = defect)
  }
  expect_identical(calls, 0L)
})
