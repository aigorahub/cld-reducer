# The model of docs/algorithm.md section 4 and the canonical solve of section 5.

# Build the model for the cliques. The first `num_x` columns are the
# membership variables x[c, g], numbered in canonical (clique, group) order; the
# rest are the y variables (edge, clique).
build_model <- function(adjacency, cliques) {
  size <- nrow(adjacency)
  members <- do.call(rbind, lapply(seq_along(cliques), function(c) {
    cbind(clique = rep(c, length(cliques[[c]])), group = cliques[[c]])
  }))
  num_x <- nrow(members)
  x_index <- matrix(0L, nrow = length(cliques), ncol = size)
  x_index[members] <- seq_len(num_x)
  cliques_of <- lapply(seq_len(size), function(g) members[members[, "group"] == g, "clique"])

  edges <- which(adjacency & upper.tri(adjacency), arr.ind = TRUE)
  edges <- edges[order(edges[, 1L], edges[, 2L]), , drop = FALSE]
  num_edges <- nrow(edges)

  y_edge <- integer(0)
  y_clique <- integer(0)
  for (e in seq_len(num_edges)) {
    shared <- intersect(cliques_of[[edges[e, 1L]]], cliques_of[[edges[e, 2L]]])
    y_edge <- c(y_edge, rep(e, length(shared)))
    y_clique <- c(y_clique, sort(shared))
  }
  num_y <- length(y_edge)
  num_cols <- num_x + num_y

  rows <- integer(0)
  cols <- integer(0)
  vals <- numeric(0)
  lower <- numeric(0)
  upper <- numeric(0)
  add_row <- function(columns, values, lo, hi) {
    row <- length(lower) + 1L
    rows <<- c(rows, rep(row, length(columns)))
    cols <<- c(cols, columns)
    vals <<- c(vals, values)
    lower <<- c(lower, lo)
    upper <<- c(upper, hi)
  }
  # Every group has a letter.
  for (g in seq_len(size)) {
    columns <- x_index[cbind(cliques_of[[g]], g)]
    add_row(columns, rep(1, length(columns)), 1, Inf)
  }
  # Every non-significant edge is covered by a clique that holds both ends.
  for (e in seq_len(num_edges)) {
    columns <- num_x + which(y_edge == e)
    add_row(columns, rep(1, length(columns)), 1, Inf)
  }
  # A covering clique needs both ends: y <= x for each end.
  group_ends <- list(edges[, 1L], edges[, 2L])
  for (k in seq_len(num_y)) {
    for (end in 1:2) {
      g <- group_ends[[end]][y_edge[k]]
      add_row(c(num_x + k, x_index[y_clique[k], g]), c(1, -1), -Inf, 0)
    }
  }
  cost <- c(rep(1, num_x), rep(0, num_y))
  problem <- list(
    num_cols = num_cols, num_x = num_x, cost = cost,
    matrix = Matrix::sparseMatrix(i = rows, j = cols, x = vals,
                                  dims = c(length(lower), num_cols)),
    row_lower = lower, row_upper = upper
  )
  list(
    problem = problem,
    members = members,
    edges = edges,
    group_columns = lapply(seq_len(size), function(g) x_index[cbind(cliques_of[[g]], g)]),
    edge_ends = lapply(seq_len(num_edges), function(e) {
      k <- which(y_edge == e)
      cbind(x_index[cbind(y_clique[k], edges[e, 1L])], x_index[cbind(y_clique[k], edges[e, 2L])])
    })
  )
}

# One solve under the shared time budget. Returns the solver outcome; an
# infeasible outcome is returned only when `sum_limit` is set (a re-solve).
solve_step <- function(model, col_lower, col_upper, sum_limit, deadline) {
  remaining <- Inf
  if (!is.null(deadline)) {
    remaining <- deadline - elapsed()
    if (remaining <= 0) {
      solver_error("assignment-minimum MILP failed: Time limit reached")
    }
  }
  outcome <- solve_lp(model$problem, col_lower, col_upper, sum_limit, remaining)
  if (identical(outcome$status, "infeasible") && !is.null(sum_limit)) {
    return(outcome)
  }
  if (!identical(outcome$status, "optimal")) {
    solver_error("assignment-minimum MILP failed: ", outcome$text)
  }
  outcome
}

# Section 6, checks 2 to 5. Returns the rounded x as logicals.
check_solution <- function(model, outcome, col_lower, col_upper, expected_sum) {
  invalid <- function() solver_error("HiGHS returned an invalid solution")
  problem <- model$problem
  values <- outcome$values
  if (length(values) != problem$num_cols || anyNA(values)) invalid()
  x <- values[seq_len(problem$num_x)]
  # Each membership must be 0 or 1 within the tolerance; an integral 2 or -1 is invalid too.
  binary <- is.finite(x) & (abs(x) <= 1e-6 | abs(x - 1) <= 1e-6)
  if (!all(binary)) invalid()
  selected <- x > 0.5
  if (any(selected & col_upper[seq_len(problem$num_x)] < 0.5) ||
      any(!selected & col_lower[seq_len(problem$num_x)] > 0.5)) {
    invalid()
  }
  if (!all(vapply(model$group_columns, function(k) any(selected[k]), logical(1)))) invalid()
  if (!all(vapply(model$edge_ends, function(ends) {
    any(selected[ends[, 1L]] & selected[ends[, 2L]])
  }, logical(1)))) {
    invalid()
  }
  wanted <- if (is.null(expected_sum)) round(outcome$objective) else expected_sum
  if (sum(selected) != wanted) invalid()
  selected
}

# Solve once for the minimum, then fix the memberships in (clique, group) order
# (docs/algorithm.md section 5). Returns the selected x and the minimum.
solve_canonical <- function(model, time_limit) {
  problem <- model$problem
  deadline <- if (is.null(time_limit)) NULL else elapsed() + time_limit
  col_lower <- rep(0, problem$num_cols)
  col_upper <- rep(1, problem$num_cols)

  outcome <- solve_step(model, col_lower, col_upper, NULL, deadline)
  selected <- check_solution(model, outcome, col_lower, col_upper, NULL)
  minimum <- round(outcome$objective)

  for (v in seq_len(problem$num_x)) {
    if (selected[v]) {
      col_lower[v] <- 1
      next
    }
    trial <- col_lower
    trial[v] <- 1
    outcome <- solve_step(model, trial, col_upper, minimum, deadline)
    if (identical(outcome$status, "infeasible")) {
      col_upper[v] <- 0
      next
    }
    selected <- check_solution(model, outcome, trial, col_upper, minimum)
    col_lower <- trial
  }
  list(selected = selected, minimum = minimum)
}
