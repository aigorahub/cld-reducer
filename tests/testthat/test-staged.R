# The staged methods against a search over displays made of cliques of any
# size. The search shares no rule with the model: it uses every clique, not
# only maximal ones, and branches on the first group or joined pair that the
# chosen cliques do not cover yet. A letter that covers nothing new only adds
# a letter and assignments, so skipping such letters loses no minimum.
exhaustive_minima <- function(n, edges) {
  joined <- adjacency_of(n, if (length(edges)) edges + 1L else NULL)
  members <- function(mask) which(bitwAnd(mask, bitwShiftL(1L, seq_len(n) - 1L)) != 0L)
  cliques <- Filter(function(mask) {
    g <- members(mask)
    all(joined[g, g])
  }, seq_len(2L^n - 1L))
  elements <- c(bitwShiftL(1L, seq_len(n) - 1L),
                unlist(lapply(seq_len(n), function(i) lapply(seq_len(n), function(j) {
                  if (i < j && joined[i, j]) bitwOr(bitwShiftL(1L, i - 1L), bitwShiftL(1L, j - 1L)) else NULL
                }))))
  letters_first <- c(Inf, Inf)
  assignments_first <- c(Inf, Inf)
  search <- function(chosen, letters, assignments) {
    no_letters <- letters > letters_first[1] || (letters == letters_first[1] && assignments >= letters_first[2])
    no_assignments <- assignments > assignments_first[1] ||
      (assignments == assignments_first[1] && letters >= assignments_first[2])
    if (no_letters && no_assignments) return(invisible())
    covered <- vapply(elements, function(e) any(bitwAnd(chosen, e) == e), logical(1))
    if (all(covered)) {
      if (!no_letters) letters_first <<- c(letters, assignments)
      if (!no_assignments) assignments_first <<- c(assignments, letters)
      return(invisible())
    }
    open <- elements[!covered][1L]
    for (q in cliques) {
      if (bitwAnd(q, open) == open && !q %in% chosen) search(c(chosen, q), letters + 1, assignments + length(members(q)))
    }
  }
  search(integer(0), 0, 0)
  list(letters_first = letters_first, assignments_first = assignments_first)
}

# Every labeled graph on 3, 4 and 5 groups (1,096 graphs), as in the
# exhaustive conformance inputs, which the built package does not contain.
every_graph <- function(n) {
  slots <- which(upper.tri(diag(n)), arr.ind = TRUE)
  slots <- slots[order(slots[, 1L], slots[, 2L]), , drop = FALSE]
  lapply(seq_len(2L^nrow(slots)) - 1L, function(subset) {
    on <- bitwAnd(subset, bitwShiftL(1L, seq_len(nrow(slots)) - 1L)) != 0L
    list(n = n, edges = if (any(on)) slots[on, , drop = FALSE] - 1L else NULL)
  })
}

test_that("each order keeps its first minimum and reaches the search minimum of the other count", {
  graphs <- c(every_graph(3L), every_graph(4L), every_graph(5L))
  checked <- 0L
  for (graph in graphs) {
    adjacency <- adjacency_of(graph$n, if (length(graph$edges)) graph$edges + 1L else NULL)
    if (sum(lengths(maximal_cliques(adjacency, NULL))) > 14L) next
    want <- exhaustive_minima(graph$n, graph$edges)
    c_then_sigma <- reduce_from_adjacency(adjacency, method = "letter_then_assignment")
    sigma_then_c <- reduce_from_adjacency(adjacency, method = "assignment_then_letter")
    expect_equal(c(c_then_sigma$stats$num_letters_after, c_then_sigma$stats$assignments_after), want$letters_first)
    expect_equal(c(sigma_then_c$stats$assignments_after, sigma_then_c$stats$num_letters_after), want$assignments_first)
    expect_true(c_then_sigma$relationship_preserved && sigma_then_c$relationship_preserved)
    checked <- checked + 1L
  }
  expect_gt(checked, 1000L)
})

test_that("separates the two orders on the graph of Table II of the 2012 paper", {
  # No letter-minimum display of this graph is assignment-minimum.
  members <- rbind(c(1,1,1,0,0,0,0), c(1,1,0,1,0,1,0), c(1,1,0,1,0,1,0), c(0,0,1,0,1,0,1),
                   c(1,0,0,1,0,0,0), c(0,0,0,1,1,0,0), c(0,1,1,0,0,1,1), c(0,0,0,1,1,1,1))
  adjacency <- members %*% t(members) > 0
  c_only <- reduce_from_adjacency(adjacency, method = "letter_minimum")
  sigma_only <- reduce_from_adjacency(adjacency, method = "assignment_minimum")
  c_then_sigma <- reduce_from_adjacency(adjacency, method = "letter_then_assignment")
  sigma_then_c <- reduce_from_adjacency(adjacency, method = "assignment_then_letter")
  expect_equal(c_then_sigma$stats$num_letters_after, c_only$stats$num_letters_after)
  expect_equal(sigma_then_c$stats$assignments_after, sigma_only$stats$assignments_after)
  expect_gt(c_then_sigma$stats$assignments_after, sigma_only$stats$assignments_after)
  expect_gt(sigma_then_c$stats$num_letters_after, c_only$stats$num_letters_after)
  expect_lte(c_then_sigma$stats$assignments_after, c_only$stats$assignments_after)
  expect_lte(sigma_then_c$stats$num_letters_after, sigma_only$stats$num_letters_after)
})

test_that("names the method, accepts the hyphen aliases and reports the second objective", {
  c_then_sigma <- reduce_letters(simple_abc_pairs, simple_abc_means, method = "letter-then-assignment")
  sigma_then_c <- reduce_letters(simple_abc_pairs, simple_abc_means, method = "assignment-then-letter")
  expect_identical(c_then_sigma$method, "letter_then_assignment")
  expect_identical(sigma_then_c$method, "assignment_then_letter")
  # CLD-C alone keeps ABC for group 3 (9 assignments); the second stage reaches 8.
  expect_equal(c(c_then_sigma$stats$num_letters_after, c_then_sigma$stats$assignments_after, c_then_sigma$stats$objective), c(3, 8, 8))
  expect_equal(c(sigma_then_c$stats$assignments_after, sigma_then_c$stats$num_letters_after, sigma_then_c$stats$objective), c(8, 3, 3))
  expect_equal(unname(c_then_sigma$letters), c("A", "AB", "AC", "BC", "C"))
})

test_that("names the second stage in a solver error and keeps one time budget", {
  real <- solve_lp
  calls <- 0L
  local_mocked_bindings(solve_lp = function(...) {
    calls <<- calls + 1L
    real(...)
  })
  # The multipartite graph reaches HiGHS in the first stage; count its solves,
  # then fail the first solve after them.
  reduce_from_adjacency(multipartite222_adjacency(), method = "letter_minimum")
  first_stage <- calls
  calls <- 0L
  local_mocked_bindings(solve_lp = function(...) {
    calls <<- calls + 1L
    if (calls > first_stage) return(list(status = "failed", text = "solver-text"))
    real(...)
  })
  expect_error(reduce_from_adjacency(multipartite222_adjacency(), method = "letter_then_assignment"),
               "staged solve failed: ", class = "cldreducer_solver_error")
})
