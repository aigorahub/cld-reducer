# Failure paths of docs/algorithm.md section 6, through the replaceable solver call.

simple <- function(...) reduce_from_adjacency(simple_adjacency(), ...)

test_that("a first solve that is not optimal is a solver error", {
  for (status in c("failed", "time_limit", "infeasible")) {
    local_mocked_bindings(solve_lp = function(...) list(status = status, text = "Some status"))
    expect_error(simple(), "assignment-minimum MILP failed: Some status",
                 class = "cldreducer_solver_error")
  }
})

test_that("a later solve that is not optimal or infeasible is a solver error", {
  real <- solve_lp
  calls <- 0L
  local_mocked_bindings(solve_lp = function(...) {
    calls <<- calls + 1L
    if (calls == 1L) real(...) else list(status = "failed", text = "Memory limit reached")
  })
  expect_error(simple(), "assignment-minimum MILP failed: Memory limit reached",
               class = "cldreducer_solver_error")
})

test_that("scripted invalid solutions are rejected", {
  real <- solve_lp
  corrupt <- function(change) {
    function(...) {
      out <- real(...)
      if (!is.null(out$values)) out$values <- change(out$values)
      out
    }
  }
  changes <- list(
    all_zero = function(v) rep(0, length(v)),
    fractional = function(v) replace(v, 1, 0.5),
    missing = function(v) replace(v, 1, NA),
    short = function(v) v[-1],
    sum_differs = function(v) replace(v, 1:9, 1)
  )
  for (change in changes) {
    local_mocked_bindings(solve_lp = corrupt(change))
    expect_error(simple(), "HiGHS returned an invalid solution", class = "cldreducer_solver_error")
  }
})

test_that("a solution that leaves an edge uncovered is rejected", {
  real <- solve_lp
  local_mocked_bindings(solve_lp = function(problem, col_lower, col_upper, sum_limit = NULL, ...) {
    out <- real(problem, col_lower, col_upper, sum_limit, ...)
    if (is.null(sum_limit)) {
      x <- out$values
      x[which(x[seq_len(problem$num_x)] > 0.5)[1]] <- 0
      out$values <- x
    }
    out
  })
  expect_error(simple(), "HiGHS returned an invalid solution", class = "cldreducer_solver_error")
})

# The first solve of the wheat example may already return the canonical optimum, which
# would leave no feasible re-solve to test. A tiny extra cost on the early memberships
# makes the first solve return a different minimal display, so the canonical procedure
# has to move to the canonical one with feasible re-solves.
first_solve_off_canonical <- function(real) {
  force(real)   # fix the real solver before a test replaces solve_lp
  function(problem, col_lower, col_upper, sum_limit = NULL, time_limit = Inf) {
    if (is.null(sum_limit)) {
      k <- seq_len(problem$num_x)
      problem$cost[k] <- 1 + 1e-3 * (problem$num_x - k) / problem$num_x
    }
    real(problem, col_lower, col_upper, sum_limit, time_limit)
  }
}

test_that("the canonical procedure reaches the canonical display from another optimum", {
  real <- solve_lp
  feasible_resolves <- 0L
  perturbed <- first_solve_off_canonical(real)
  local_mocked_bindings(solve_lp = function(problem, col_lower, col_upper, sum_limit = NULL, ...) {
    out <- perturbed(problem, col_lower, col_upper, sum_limit, ...)
    if (!is.null(sum_limit) && identical(out$status, "optimal")) {
      feasible_resolves <<- feasible_resolves + 1L
    }
    out
  })
  result <- reduce_letters(piepho2004_wheat)
  expect_gt(feasible_resolves, 0L)
  expect_equal(result$stats$assignments_after, 44)
  expect_equal(unname(result$letters)[1:4], c("ABC", "BD", "AD", "BD"))
})

test_that("later solutions are checked too", {
  perturbed <- first_solve_off_canonical(solve_lp)
  later <- 0L
  local_mocked_bindings(solve_lp = function(problem, col_lower, col_upper, sum_limit = NULL, ...) {
    out <- perturbed(problem, col_lower, col_upper, sum_limit, ...)
    if (!is.null(sum_limit) && identical(out$status, "optimal")) {
      later <<- later + 1L
      out$values <- rep(0, length(out$values))
    }
    out
  })
  expect_error(reduce_letters(piepho2004_wheat), "HiGHS returned an invalid solution",
               class = "cldreducer_solver_error")
  expect_equal(later, 1L)
})

test_that("a solution that violates a fixing is rejected", {
  perturbed <- first_solve_off_canonical(solve_lp)
  local_mocked_bindings(solve_lp = function(problem, col_lower, col_upper, sum_limit = NULL, ...) {
    out <- perturbed(problem, col_lower, col_upper, sum_limit, ...)
    if (!is.null(sum_limit) && identical(out$status, "optimal")) {
      out$values[which(col_lower[seq_len(problem$num_x)] > 0.5)[1]] <- 0
    }
    out
  })
  expect_error(reduce_letters(piepho2004_wheat), "HiGHS returned an invalid solution",
               class = "cldreducer_solver_error")
})

test_that("the time budget is shared across solves", {
  now <- 0
  real <- solve_lp
  limits <- numeric(0)
  local_mocked_bindings(
    elapsed = function() now,
    solve_lp = function(problem, col_lower, col_upper, sum_limit = NULL, time_limit = Inf) {
      limits <<- c(limits, time_limit)
      out <- real(problem, col_lower, col_upper, sum_limit, time_limit)
      now <<- now + 10   # every solve "takes" 10 seconds
      out
    }
  )
  expect_error(simple(time_limit = 5), "assignment-minimum MILP failed: Time limit reached",
               class = "cldreducer_solver_error")
  # The first solve got the whole budget; the second would get -5 seconds, so it never ran.
  expect_equal(limits, 5)
})

test_that("without a time limit no deadline applies", {
  real <- solve_lp
  limits <- numeric(0)
  local_mocked_bindings(solve_lp = function(problem, col_lower, col_upper, sum_limit = NULL, time_limit = Inf) {
    limits <<- c(limits, time_limit)
    real(problem, col_lower, col_upper, sum_limit, time_limit)
  })
  simple()
  expect_gt(length(limits), 1)
  expect_true(all(is.infinite(limits)))
})

test_that("the solver call reports statuses from HiGHS", {
  model <- build_model(simple_adjacency(), maximal_cliques(simple_adjacency(), NULL))
  p <- model$problem
  free <- solve_lp(p, rep(0, p$num_cols), rep(1, p$num_cols))
  expect_equal(free$status, "optimal")
  expect_equal(round(free$objective), 8)
  tight <- solve_lp(p, rep(0, p$num_cols), rep(1, p$num_cols), sum_limit = 7)
  expect_equal(tight$status, "infeasible")
})
