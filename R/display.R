render_result <- function(graph, cliques, model, solution, columns, strategy) {
  groups <- graph$groups
  adjacency <- graph$adjacency
  size <- length(groups)
  keys <- t(vapply(columns, function(members) {
    lowest <- min(members)
    if (is.null(graph$means)) c(lowest, lowest) else c(-max(graph$means[members]), lowest)
  }, numeric(2)))
  order_of <- order(keys[, 1L], keys[, 2L])   # stable: ties keep the clique order
  labels <- make_letter_labels(length(columns))
  tokens <- rep(list(character(0)), size)
  for (k in seq_along(order_of)) {
    for (g in columns[[order_of[k]]]) tokens[[g]] <- c(tokens[[g]], labels[k])
  }
  names(tokens) <- groups
  display <- vapply(tokens, function(t) {
    if (all(nchar(t) == 1L)) paste(t, collapse = "") else paste(t, collapse = " ")
  }, character(1))

  # Section 8: the letters must give back the input relationships.
  shared <- outer(seq_len(size), seq_len(size), Vectorize(function(i, j) {
    length(intersect(tokens[[i]], tokens[[j]])) > 0L
  }))
  if (!identical(shared, adjacency)) {
    solver_error("optimized letters did not preserve the input pairwise relationships")
  }

  before <- sum(lengths(cliques))
  after <- sum(lengths(tokens))
  if (solution$minimum != if (strategy$counts_assignments) after else length(columns)) {
    solver_error("HiGHS returned an invalid solution")
  }
  dimnames(adjacency) <- list(groups, groups)
  structure(
    list(
      letters = display,
      assignments = tokens,
      stats = list(
        assignments_before = before,
        assignments_after = after,
        reduction_pct = if (before > 0) (before - after) / before * 100 else 0,
        num_letters_before = length(cliques),
        num_letters_after = length(columns),
        num_groups = size,
        num_edges = nrow(model$edges),
        solver_status = "Optimal",
        objective = as.numeric(solution$minimum)
      ),
      method = strategy$name,
      groups = groups,
      relationship_preserved = TRUE,
      adjacency = adjacency
    ),
    class = "cld_reduction"
  )
}
