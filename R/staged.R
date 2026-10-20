# Staged (lexicographic) reductions: one minimum first, then the other count
# among the displays that keep that minimum. A second call of the other
# method would not keep the first minimum, so the second stage is its own
# model: the CLD-sigma model with one binary column u(c) for each maximal
# clique, the rows x(c, g) <= u(c), and a bound row on the first count. One
# column per maximal clique loses no lexicographic optimum, because two
# letters inside one maximal clique merge into their union with fewer letters
# and no more assignments. docs/algorithm.md section 15 states the model.

staged_methods <- function() list(
  list(name = "letter_then_assignment", aliases = c("letter_then_assignment", "letter-then-assignment"),
       first = "letter_minimum", letters_first = TRUE),
  list(name = "assignment_then_letter", aliases = c("assignment_then_letter", "assignment-then-letter"),
       first = "assignment_minimum", letters_first = FALSE)
)

staged_method <- function(method) {
  for (staged in staged_methods()) {
    if (is.character(method) && length(method) == 1L && !is.na(method) &&
        method %in% staged$aliases) return(staged)
  }
  NULL
}

staged_prefix <- "staged solve failed: "

reduce_staged <- function(graph, staged, time_limit, max_cliques) {
  controls <- check_controls(time_limit, max_cliques)
  deadline <- if (is.null(controls$time_limit)) NULL else elapsed() + controls$time_limit
  first <- reduce_graph(graph, staged$first, controls$time_limit, controls$max_cliques)
  tryCatch(second_stage(graph, staged, first, deadline, controls$max_cliques),
    cldreducer_solver_error = function(e) {
      # Every solver error of the second stage names it.
      if (startsWith(conditionMessage(e), staged_prefix)) stop(e)
      solver_error(staged_prefix, conditionMessage(e))
    })
}

second_stage <- function(graph, staged, first, deadline, max_cliques) {
  invalid <- function() solver_error(staged_prefix, "HiGHS returned an invalid solution")
  letters_first <- staged$letters_first
  bound <- if (letters_first) first$stats$num_letters_after else first$stats$assignments_after
  assignment <- Filter(function(m) m$name == "assignment_minimum", reduction_methods())[[1L]]

  reduced <- reduce_graph_vertices(graph$adjacency)
  small <- list(adjacency = reduced$adjacency,
                groups = graph$groups[vapply(reduced$classes, function(g) g[1L], integer(1))],
                means = NULL)
  cliques <- maximal_cliques(reduced$adjacency, max_cliques)
  context <- graph_context(small, cliques, reduced$weights, TRUE)
  plan <- build_assignment_plan(context)
  base <- compile_assignment_plan(plan)$problem

  first_u <- base$num_cols
  num_cols <- first_u + length(cliques)
  members <- plan$members
  k <- nrow(members)
  widened <- cbind(base$matrix, Matrix::sparseMatrix(i = integer(0), j = integer(0), x = numeric(0),
                                                     dims = c(nrow(base$matrix), length(cliques))))
  links <- Matrix::sparseMatrix(i = c(seq_len(k), seq_len(k)), j = c(seq_len(k), first_u + members[, "clique"]),
                                x = c(rep(1, k), rep(-1, k)), dims = c(k, num_cols))
  limit <- if (letters_first) {
    Matrix::sparseMatrix(i = rep(1L, length(cliques)), j = first_u + seq_along(cliques), x = 1, dims = c(1L, num_cols))
  } else {
    Matrix::sparseMatrix(i = rep(1L, k), j = seq_len(k), x = reduced$weights[members[, "group"]], dims = c(1L, num_cols))
  }
  problem <- list(
    num_cols = num_cols,
    decision_columns = if (letters_first) seq_len(k) else first_u + seq_along(cliques),
    cost = if (letters_first) c(base$cost, rep(0, length(cliques))) else c(rep(0, first_u), rep(1, length(cliques))),
    matrix = rbind(widened, links, limit),
    row_lower = c(base$row_lower, rep(-Inf, k), -Inf),
    row_upper = c(base$row_upper, rep(0, k), bound)
  )
  model <- c(unclass(plan), list(problem = problem))
  remaining <- function() if (is.null(deadline)) NULL else remaining_time(deadline, list(failure_prefix = staged_prefix))

  if (letters_first) {
    used <- function(selected) length(unique(members[selected, "clique"]))
    strategy <- utils::modifyList(assignment, list(
      name = staged$name, failure_prefix = staged_prefix,
      coverage = function(m, selected) assignment_coverage(m, selected) && used(selected) <= bound))
    # The decisions are the memberships, with positive weights, so the
    # essential cover proof of the package applies unchanged.
    solution <- solve_canonical(model, remaining(), strategy)
    columns <- assignment_columns(cliques, plan, solution$selected)
  } else {
    # A vertex or an edge that one clique alone covers forces that clique.
    cover <- c(context$cliques_of, lapply(seq_len(nrow(context$edges)), function(e) {
      intersect(context$cliques_of[[context$edges[e, 1L]]], context$cliques_of[[context$edges[e, 2L]]])
    }))
    forced <- sort(unique(first_u + unlist(cover[lengths(cover) == 1L], use.names = FALSE)))
    strategy <- utils::modifyList(assignment, list(
      name = staged$name, failure_prefix = staged_prefix, counts_assignments = FALSE,
      coverage = function(m, selected) all(vapply(cover, function(row) any(selected[row]), logical(1))),
      essential_decisions = function(m) as.integer(forced)))
    # A cover by the chosen cliques does not prove that memberships within
    # the bound exist, so the certificate is off; the third solve checks it.
    chosen <- solve_canonical(model, remaining(), strategy, certificate = FALSE)$selected
    subset <- cliques[chosen]
    sub_plan <- assignment$planner(graph_context(small, subset, reduced$weights, TRUE))
    inner <- solve_canonical(sub_plan, remaining(), utils::modifyList(assignment, list(failure_prefix = staged_prefix)))
    if (inner$minimum != bound) invalid()
    columns <- assignment$decoder(subset, sub_plan, inner$selected)
    if (length(columns) != length(subset)) invalid()
    solution <- list(selected = chosen, minimum = length(subset))
  }

  result <- render_result(graph, expand_graph_columns(cliques, reduced$classes), model, solution,
                          expand_graph_columns(columns, reduced$classes), strategy)
  # The first stage is optimal, so the second stage keeps its value exactly.
  kept <- if (letters_first) result$stats$num_letters_after else result$stats$assignments_after
  if (kept != bound) invalid()
  result
}
