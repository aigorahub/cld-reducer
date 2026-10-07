# HiGHS through the highs package, with the settings of docs/algorithm.md section 6.

# The clock behind the shared time budget, in seconds. Tests replace it.
elapsed <- function() {
  proc.time()[["elapsed"]]
}

# Solve the model with the given column bounds. `sum_limit` adds the row
# `sum(x) <= sum_limit`; `time_limit` is the HiGHS time limit in seconds.
# Returns list(status, text, values, objective), where status is "optimal",
# "infeasible", "time_limit", or "failed". Tests replace this function.
solve_lp <- function(problem, col_lower, col_upper, sum_limit = NULL, time_limit = Inf) {
  a <- problem$matrix
  lhs <- problem$row_lower
  rhs <- problem$row_upper
  if (!is.null(sum_limit)) {
    a <- rbind(a, Matrix::sparseMatrix(
      i = rep(1L, problem$num_x), j = seq_len(problem$num_x), x = 1,
      dims = c(1L, problem$num_cols)
    ))
    lhs <- c(lhs, -Inf)
    rhs <- c(rhs, sum_limit)
  }
  res <- highs::highs_solve(
    L = problem$cost,
    lower = col_lower,
    upper = col_upper,
    A = a,
    lhs = lhs,
    rhs = rhs,
    types = rep("I", problem$num_cols),
    maximum = FALSE,
    # HiGHS 1.14, bundled with the highs package, gave a wrong optimum with
    # presolve on in a small test case of the sibling project turfLP, so
    # presolve is off. highs_control() uses one thread by default.
    control = highs::highs_control(
      time_limit = time_limit,
      presolve = "off",
      mip_rel_gap = 0,
      mip_abs_gap = 0,
      primal_feasibility_tolerance = 1e-9,
      mip_feasibility_tolerance = 1e-9
    )
  )
  text <- res$status_message
  # No model here is unbounded, so "unbounded or infeasible" means infeasible.
  status <- switch(text,
    "Optimal" = "optimal",
    "Infeasible" = ,
    "Primal infeasible or unbounded" = "infeasible",
    "Time limit reached" = "time_limit",
    "failed"
  )
  if (status == "optimal") {
    return(list(status = status, text = text, values = res$primal_solution,
                objective = res$objective_value))
  }
  list(status = status, text = text)
}
