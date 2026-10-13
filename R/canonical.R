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
  if (sum(problem$cost[problem$decision_columns] * selected) != wanted) invalid()
  selected
}

# Every feasible decision vector contains the essential decisions. If they
# cover the graph, positive decision costs make that vector the unique optimum.
# Zero auxiliary costs let coverage supply witnesses without changing its cost.
essential_cover_certificate <- function(model, decisions, required, strategy) {
  problem <- model$problem
  cost <- problem$cost
  if (!is.numeric(cost) || is.complex(cost) || !is.null(dim(cost)) ||
      length(cost) != problem$num_cols || any(!is.finite(cost))) return(NULL)
  decision_cost <- cost[decisions]
  if (any(decision_cost <= 0 | decision_cost != floor(decision_cost))) return(NULL)
  auxiliary <- rep(TRUE, problem$num_cols)
  auxiliary[decisions] <- FALSE
  if (any(cost[auxiliary] != 0)) return(NULL)
  selected <- decisions %in% required
  minimum <- sum(decision_cost[selected])
  # The reference engine stores its minimum as an R integer.
  if (!is.finite(minimum) || minimum > .Machine$integer.max) return(NULL)
  if (!strategy$coverage(model, selected)) return(NULL)
  list(selected = selected, minimum = as.integer(minimum))
}

# Use the certificate when possible. Otherwise solve once for the minimum,
# then fix memberships in (clique, group) order (docs/algorithm.md section 5).
# The private switch retains the reference path for differential checks.
solve_canonical <- function(model, time_limit, strategy, certificate = TRUE) {
  if (inherits(model, "cld_decision_plan")) return(solve_plan(model, time_limit, strategy, certificate))
  problem <- model$problem
  decisions <- problem$decision_columns
  if (anyDuplicated(decisions) || any(!is.finite(decisions) | decisions != floor(decisions) |
      decisions < 1L | decisions > problem$num_cols)) solver_error("HiGHS returned an invalid solution")
  deadline <- if (is.null(time_limit)) NULL else elapsed() + time_limit
  required <- strategy$essential_decisions(model)
  if (!is.numeric(required) || !is.null(dim(required)) ||
      any(!is.finite(required) | required != floor(required) | !required %in% decisions) ||
      anyDuplicated(required) || is.unsorted(required, strictly = TRUE)) {
    solver_error("HiGHS returned an invalid solution")
  }
  if (!is.null(deadline) && elapsed() >= deadline) {
    solver_error(strategy$failure_prefix, "Time limit reached")
  }
  if (certificate) {
    certified <- essential_cover_certificate(model, decisions, required, strategy)
    if (!is.null(deadline) && elapsed() >= deadline) {
      solver_error(strategy$failure_prefix, "Time limit reached")
    }
    if (!is.null(certified)) return(certified)
  }

  canonical_trials(model, strategy, required, deadline)
}

canonical_trials <- function(model, strategy, required, deadline) {
  problem <- model$problem
  col_lower <- rep(0, problem$num_cols)
  col_upper <- rep(1, problem$num_cols)
  col_lower[required] <- 1
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


remaining_time <- function(deadline, strategy) {
  if (is.null(deadline)) return(NULL)
  remaining <- deadline - elapsed()
  if (remaining <= 0) solver_error(strategy$failure_prefix, "Time limit reached")
  remaining
}

plan_certificate <- function(plan, required, strategy) {
  cost <- plan$cost
  if (!is.numeric(cost) || is.complex(cost) || !is.null(dim(cost)) ||
      any(!is.finite(cost) | cost <= 0 | cost != floor(cost))) return(NULL)
  selected <- seq_len(plan$decision_count) %in% required
  minimum <- sum(cost[selected])
  if (!is.finite(minimum) || minimum > .Machine$integer.max ||
      !strategy$coverage(plan, selected)) return(NULL)
  list(selected = selected, minimum = as.integer(minimum))
}

solve_plan <- function(plan, time_limit, strategy, certificate = TRUE) {
  invalid <- function() solver_error("HiGHS returned an invalid solution")
  count <- plan$decision_count
  if (length(count) != 1L || !is.finite(count) || count < 0 || count != floor(count) ||
      length(plan$cost) != count) invalid()
  deadline <- if (is.null(time_limit)) NULL else elapsed() + time_limit
  required <- strategy$essential_decisions(plan)
  if (!is.numeric(required) || is.complex(required) || !is.null(dim(required)) ||
      any(!is.finite(required) | required != floor(required) | required < 1 | required > count) ||
      anyDuplicated(required) || is.unsorted(required, strictly = TRUE)) invalid()
  remaining_time(deadline, strategy)
  if (certificate) {
    certified <- plan_certificate(plan, required, strategy)
    remaining_time(deadline, strategy)
    if (!is.null(certified)) return(certified)
  }
  remaining <- remaining_time(deadline, strategy)
  model <- strategy$compiler(plan)
  deadline <- if (is.null(remaining)) NULL else elapsed() + remaining
  problem <- model$problem
  decisions <- problem$decision_columns
  if (length(decisions) != count || anyDuplicated(decisions) || !is.numeric(decisions) ||
      any(!is.finite(decisions) | decisions != floor(decisions) | decisions < 1 |
          decisions > problem$num_cols) || length(problem$cost) != problem$num_cols) invalid()
  auxiliary <- rep(TRUE, problem$num_cols)
  auxiliary[decisions] <- FALSE
  if (anyNA(problem$cost) || !identical(as.numeric(problem$cost[decisions]), as.numeric(plan$cost)) ||
      any(problem$cost[auxiliary] != 0)) invalid()
  canonical_trials(model, strategy, decisions[required], deadline)
}
