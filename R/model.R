# The model of docs/algorithm.md section 4 and the canonical solve of section 5.

# Build the model for the cliques. The first `num_x` columns are the
# membership variables x[c, g], numbered in canonical (clique, group) order; the
# rest are the y variables (edge, clique).
build_model <- function(context) {
  adjacency <- context$adjacency
  cliques <- context$cliques
  size <- nrow(adjacency)
  members <- do.call(rbind, lapply(seq_along(cliques), function(c) {
    cbind(clique = rep(c, length(cliques[[c]])), group = cliques[[c]])
  }))
  num_x <- nrow(members)
  x_index <- matrix(0L, nrow = length(cliques), ncol = size)
  x_index[members] <- seq_len(num_x)
  cliques_of <- context$cliques_of

  edges <- context$edges
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
  cost <- c(context$weights[members[, "group"]], rep(0, num_y))
  problem <- list(
    num_cols = num_cols, decision_columns = seq_len(num_x), cost = cost,
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

assignment_coverage <- function(model, selected) {
  all(vapply(model$group_columns, function(k) any(selected[k]), logical(1))) &&
    all(vapply(model$edge_ends, function(ends) {
      any(selected[ends[, 1L]] & selected[ends[, 2L]])
    }, logical(1)))
}
assignment_columns <- function(cliques, model, selected) {
  columns <- lapply(seq_along(cliques), function(c) {
    model$members[model$members[, "clique"] == c & selected, "group"]
  })
  columns[lengths(columns) > 0L]
}

graph_context <- function(graph, cliques, weights = rep(1L, length(graph$groups))) {
  edges <- which(graph$adjacency & upper.tri(graph$adjacency), arr.ind = TRUE)
  edges <- edges[order(edges[, 1L], edges[, 2L]), , drop = FALSE]
  c(graph, list(cliques = cliques, edges = edges, weights = weights,
    cliques_of = lapply(seq_along(graph$groups), function(g) {
      which(vapply(cliques, function(q) g %in% q, logical(1)))
    })))
}

build_letter_model <- function(context) {
  n <- length(context$cliques)
  edge_columns <- lapply(seq_len(nrow(context$edges)), function(e) {
    intersect(context$cliques_of[[context$edges[e, 1L]]],
              context$cliques_of[[context$edges[e, 2L]]])
  })
  columns <- c(context$cliques_of, edge_columns)
  list(problem = list(num_cols = n, decision_columns = seq_len(n), cost = rep(1, n),
    matrix = Matrix::sparseMatrix(i = rep(seq_along(columns), lengths(columns)),
      j = unlist(columns), x = 1, dims = c(length(columns), n)),
    row_lower = rep(1, length(columns)), row_upper = rep(Inf, length(columns))),
    edges = context$edges, coverage_columns = columns)
}
letter_coverage <- function(model, selected) {
  all(vapply(model$coverage_columns, function(cs) any(selected[cs]), logical(1)))
}
letter_columns <- function(cliques, model, selected) cliques[selected]
