elapsed <- function() proc.time()[["elapsed"]]

# One solve under the shared time budget. Returns the solver outcome; an
# infeasible outcome is returned only when `sum_limit` is set (a re-solve).
solve_step <- function(model, col_lower, col_upper, sum_limit, deadline, strategy) {
  remaining <- Inf
  if (!is.null(deadline)) {
    remaining <- deadline - elapsed()
    if (remaining <= 0) {
      solver_error(strategy$failure_prefix, "Time limit reached")
    }
  }
  outcome <- solve_lp(model$problem, col_lower, col_upper, sum_limit, remaining)
  if (identical(outcome$status, "infeasible") && !is.null(sum_limit)) {
    return(outcome)
  }
  if (!identical(outcome$status, "optimal")) {
    solver_error(strategy$failure_prefix, outcome$text)
  }
  outcome
}

# Section 6: validate ordered decisions; auxiliary variables do not define the output.
check_solution <- function(model, outcome, col_lower, col_upper, expected_sum, strategy) {
  invalid <- function() solver_error("HiGHS returned an invalid solution")
  problem <- model$problem
  values <- outcome$values
  if (length(values) != problem$num_cols || anyNA(values)) invalid()
  x <- values[problem$decision_columns]
  # Each membership must be 0 or 1 within the tolerance; an integral 2 or -1 is invalid too.
  binary <- is.finite(x) & (abs(x) <= 1e-6 | abs(x - 1) <= 1e-6)
  if (!all(binary)) invalid()
  selected <- x > 0.5
  if (any(selected & col_upper[problem$decision_columns] < 0.5) ||
      any(!selected & col_lower[problem$decision_columns] > 0.5)) {
    invalid()
  }
  if (!strategy$coverage(model, selected)) invalid()
  if (is.null(expected_sum) && (length(outcome$objective) != 1L ||
      !is.finite(outcome$objective))) invalid()
  wanted <- if (is.null(expected_sum)) round(outcome$objective) else expected_sum
  if (sum(selected) != wanted) invalid()
  selected
}

# Solve once for the minimum, then fix the memberships in (clique, group) order
# (docs/algorithm.md section 5). Returns the selected x and the minimum.
solve_canonical <- function(model, time_limit, strategy) {
  problem <- model$problem
  decisions <- problem$decision_columns
  if (anyDuplicated(decisions) || any(!is.finite(decisions) | decisions != floor(decisions) |
      decisions < 1L | decisions > problem$num_cols)) solver_error("HiGHS returned an invalid solution")
  deadline <- if (is.null(time_limit)) NULL else elapsed() + time_limit
  col_lower <- rep(0, problem$num_cols)
  col_upper <- rep(1, problem$num_cols)

  outcome <- solve_step(model, col_lower, col_upper, NULL, deadline, strategy)
  selected <- check_solution(model, outcome, col_lower, col_upper, NULL, strategy)
  minimum <- as.integer(round(outcome$objective))

  for (k in seq_along(problem$decision_columns)) {
    v <- problem$decision_columns[k]
    if (selected[k]) {
      col_lower[v] <- 1
      next
    }
    trial <- col_lower
    trial[v] <- 1
    outcome <- solve_step(model, trial, col_upper, minimum, deadline, strategy)
    if (identical(outcome$status, "infeasible")) {
      col_upper[v] <- 0
      next
    }
    selected <- check_solution(model, outcome, trial, col_upper, minimum, strategy)
    col_lower <- trial
  }
  list(selected = selected, minimum = minimum)
}
