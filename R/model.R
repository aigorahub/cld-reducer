# Coverage plans use semantic decisions. Solver arrays exist only after compilation.

shared_positions <- function(left, right) {
  result <- matrix(0L, nrow = min(length(left), length(right)), ncol = 2L)
  i <- j <- 1L
  used <- 0L
  while (i <= length(left) && j <= length(right)) {
    if (left[i] == right[j]) {
      used <- used + 1L
      result[used, ] <- c(i, j)
      i <- i + 1L
      j <- j + 1L
    } else if (left[i] < right[j]) i <- i + 1L else j <- j + 1L
  }
  result[seq_len(used), , drop = FALSE]
}

build_assignment_plan <- function(context) {
  members <- context$members
  group_columns <- context$group_columns
  if (is.null(members)) {
    members <- do.call(rbind, lapply(seq_along(context$cliques), function(c) {
      cbind(clique = rep(c, length(context$cliques[[c]])), group = context$cliques[[c]])
    }))
    group_columns <- lapply(context$cliques_of, function(cs) integer(length(cs)))
    positions <- integer(length(group_columns))
    for (k in seq_len(nrow(members))) {
      g <- members[k, "group"]
      positions[g] <- positions[g] + 1L
      group_columns[[g]][positions[g]] <- k
    }
  }
  edge_ends <- lapply(seq_len(nrow(context$edges)), function(e) {
    i <- context$edges[e, 1L]
    j <- context$edges[e, 2L]
    matched <- shared_positions(context$cliques_of[[i]], context$cliques_of[[j]])
    cbind(group_columns[[i]][matched[, 1L]], group_columns[[j]][matched[, 2L]])
  })
  structure(list(context = context, decision_count = nrow(members),
    cost = context$weights[members[, "group"]], members = members,
    edges = context$edges, group_columns = group_columns, edge_ends = edge_ends),
    class = "cld_decision_plan")
}

build_model <- function(context) compile_assignment_plan(build_assignment_plan(context))

compile_assignment_plan <- function(plan) {
  num_x <- plan$decision_count
  num_y <- sum(vapply(plan$edge_ends, nrow, integer(1)))
  num_cols <- num_x + num_y
  num_rows <- length(plan$group_columns) + length(plan$edge_ends) + 2L * num_y
  nonzeros <- sum(lengths(plan$group_columns)) + 5L * num_y
  rows <- cols <- integer(nonzeros)
  vals <- numeric(nonzeros)
  lower <- upper <- numeric(num_rows)
  row <- cursor <- 0L
  add_row <- function(columns, values, lo, hi) {
    row <<- row + 1L
    if (length(columns)) {
      take <- cursor + seq_along(columns)
      rows[take] <<- row
      cols[take] <<- columns
      vals[take] <<- values
      cursor <<- cursor + length(columns)
    }
    lower[row] <<- lo
    upper[row] <<- hi
  }
  for (columns in plan$group_columns) add_row(columns, rep(1, length(columns)), 1, Inf)
  witness <- num_x
  for (ends in plan$edge_ends) {
    add_row(witness + seq_len(nrow(ends)), rep(1, nrow(ends)), 1, Inf)
    witness <- witness + nrow(ends)
  }
  witness <- num_x
  for (ends in plan$edge_ends) for (k in seq_len(nrow(ends))) {
    witness <- witness + 1L
    for (end in 1:2) add_row(c(witness, ends[k, end]), c(1, -1), -Inf, 0)
  }
  problem <- list(num_cols = num_cols, decision_columns = seq_len(num_x),
    cost = c(plan$cost, rep(0, num_y)),
    matrix = Matrix::sparseMatrix(i = rows, j = cols, x = vals, dims = c(num_rows, num_cols)),
    row_lower = lower, row_upper = upper)
  c(unclass(plan), list(problem = problem))
}

assignment_coverage <- function(model, selected) {
  all(vapply(model$group_columns, function(k) any(selected[k]), logical(1))) &&
    all(vapply(model$edge_ends, function(ends) {
      any(selected[ends[, 1L]] & selected[ends[, 2L]])
    }, logical(1)))
}
assignment_essential_decisions <- function(model) {
  vertices <- unlist(model$group_columns[lengths(model$group_columns) == 1L],
                     use.names = FALSE)
  edges <- unlist(lapply(model$edge_ends, function(ends) {
    if (nrow(ends) == 1L) ends[1L, ] else integer(0)
  }), use.names = FALSE)
  sort(unique(c(integer(0), vertices, edges)))
}
assignment_columns <- function(cliques, model, selected) {
  columns <- lapply(seq_along(cliques), function(c) {
    model$members[model$members[, "clique"] == c & selected, "group"]
  })
  columns[lengths(columns) > 0L]
}

graph_context <- function(graph, cliques, weights = rep(1L, length(graph$groups)), assignments = FALSE) {
  edges <- which(graph$adjacency & upper.tri(graph$adjacency), arr.ind = TRUE)
  edges <- edges[order(edges[, 1L], edges[, 2L]), , drop = FALSE]
  counts <- tabulate(unlist(cliques, use.names = FALSE), nbins = length(graph$groups))
  cliques_of <- lapply(counts, integer)
  positions <- integer(length(counts))
  members <- if (assignments) matrix(0L, nrow = sum(counts), ncol = 2L,
                                    dimnames = list(NULL, c("clique", "group"))) else NULL
  group_columns <- if (assignments) lapply(counts, integer) else NULL
  k <- 0L
  for (c in seq_along(cliques)) for (g in cliques[[c]]) {
    positions[g] <- positions[g] + 1L
    cliques_of[[g]][positions[g]] <- c
    if (assignments) {
      k <- k + 1L
      group_columns[[g]][positions[g]] <- k
      members[k, ] <- c(c, g)
    }
  }
  c(graph, list(cliques = cliques, edges = edges, weights = weights, cliques_of = cliques_of,
                members = members, group_columns = group_columns))
}


build_letter_plan <- function(context) {
  columns <- c(context$cliques_of, lapply(seq_len(nrow(context$edges)), function(e) {
    left <- context$cliques_of[[context$edges[e, 1L]]]
    right <- context$cliques_of[[context$edges[e, 2L]]]
    left[shared_positions(left, right)[, 1L]]
  }))
  n <- length(context$cliques)
  structure(list(context = context, decision_count = n, cost = rep(1, n),
    edges = context$edges, coverage_columns = columns), class = "cld_decision_plan")
}
build_letter_model <- function(context) compile_letter_plan(build_letter_plan(context))
compile_letter_plan <- function(plan) {
  columns <- plan$coverage_columns
  n <- plan$decision_count
  c(unclass(plan), list(problem = list(num_cols = n, decision_columns = seq_len(n), cost = plan$cost,
    matrix = Matrix::sparseMatrix(i = rep(seq_along(columns), lengths(columns)),
      j = unlist(columns), x = 1, dims = c(length(columns), n)),
    row_lower = rep(1, length(columns)), row_upper = rep(Inf, length(columns)))))
}
letter_coverage <- function(model, selected) {
  all(vapply(model$coverage_columns, function(cs) any(selected[cs]), logical(1)))
}
letter_essential_decisions <- function(model) {
  required <- unlist(model$coverage_columns[lengths(model$coverage_columns) == 1L],
                     use.names = FALSE)
  sort(unique(c(integer(0), required)))
}
letter_columns <- function(cliques, model, selected) cliques[selected]
