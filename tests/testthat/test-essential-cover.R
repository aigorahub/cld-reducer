# Keep the reference switch private while comparing the full public result and
# the exact ordered decision vector returned by the engine.
certificate_result <- function(adjacency, method, certificate = TRUE, ...) {
  canonical <- solve_canonical
  adapter <- solve_lp
  solution <- NULL
  calls <- 0L
  local_mocked_bindings(
    solve_canonical = function(model, time_limit, strategy) {
      solution <<- canonical(model, time_limit, strategy, certificate = certificate)
      solution
    },
    solve_lp = function(...) {
      calls <<- calls + 1L
      adapter(...)
    }
  )
  result <- reduce_from_adjacency(adjacency, method = method, ...)
  list(result = result, solution = solution, calls = calls)
}

certificate_graphs <- function() {
  path <- adjacency_of(3, cbind(1:2, 2:3))
  twins <- c(1L, 2L, 1L, 3L, 2L, 2L)
  list(singleton = diag(TRUE, 1), isolates = diag(TRUE, 3),
       complete = matrix(TRUE, 5, 5), abc = simple_adjacency(),
       weighted_twins = path[twins, twins])
}

test_that("certified calls match the complete reference output and ordered vector", {
  for (adjacency in certificate_graphs()) {
    groups <- as.character(seq_len(nrow(adjacency)))
    groups[1L] <- ""
    means <- stats::setNames(rep(c(2, 1), length.out = length(groups)), groups)
    for (strategy in reduction_methods()) {
      actual <- certificate_result(adjacency, strategy$name, groups = groups, means = means)
      reference <- certificate_result(adjacency, strategy$name, certificate = FALSE,
                                      groups = groups, means = means)
      expect_identical(actual$result, reference$result)
      expect_identical(as.data.frame(actual$result), as.data.frame(reference$result))
      expect_identical(actual$solution, reference$solution)
      expect_identical(actual$calls, 0L)
      expect_gt(reference$calls, 0L)
    }
  }
})

test_that("certified public calls do not reach the adapter", {
  local_mocked_bindings(solve_lp = function(...) stop("certificate reached solver"))
  for (adjacency in certificate_graphs()) {
    for (strategy in reduction_methods()) {
      result <- reduce_from_adjacency(adjacency, method = strategy$name)
      expect_true(result$relationship_preserved)
      expect_identical(result$stats$solver_status, "Optimal")
    }
  }
  result <- reduce_from_adjacency(certificate_graphs()$weighted_twins,
                                  method = "assignment_minimum")
  expect_equal(result$stats$objective, 9)
})

test_that("empty and incomplete essential covers keep the reference solver path", {
  incomplete <- diag(TRUE, 7)
  incomplete[1:6, 1:6] <- multipartite222_adjacency()
  for (adjacency in list(multipartite222_adjacency(), incomplete)) {
    graph <- adjacency_to_graph(adjacency, NULL, NULL)
    context <- graph_context(graph, maximal_cliques(adjacency, NULL))
    for (strategy in reduction_methods()) {
      model <- strategy$builder(context)
      required <- strategy$essential_decisions(model)
      expect_length(required, if (nrow(adjacency) == 6L) 0L else 1L)
      expect_false(strategy$coverage(model, model$problem$decision_columns %in% required))
      expect_null(essential_cover_certificate(model, model$problem$decision_columns,
                                             required, strategy))
      actual <- certificate_result(adjacency, strategy$name)
      reference <- certificate_result(adjacency, strategy$name, certificate = FALSE)
      expect_gt(actual$calls, 0L)
      expect_identical(actual$result, reference$result)
      expect_identical(actual$solution, reference$solution)
      expect_identical(actual$calls, reference$calls)
    }
  }
})

test_that("the certificate keeps noncontiguous decision order and weighted costs", {
  problem <- list(
    num_cols = 4L, decision_columns = c(4L, 1L), cost = c(2, 0, 0, 3),
    matrix = Matrix::sparseMatrix(i = 1:2, j = c(4L, 2L), x = 1, dims = c(2, 4)),
    row_lower = c(1, 1), row_upper = c(Inf, Inf)
  )
  model <- list(problem = problem)
  for (strategy in reduction_methods()) {
    strategy$essential_decisions <- function(model) 4L
    strategy$coverage <- function(model, selected) selected[1L]
    actual <- solve_canonical(model, NULL, strategy)
    reference <- solve_canonical(model, NULL, strategy, certificate = FALSE)
    expect_identical(actual, reference)
    expect_identical(actual, list(selected = c(TRUE, FALSE), minimum = 3L))
  }
})

test_that("invalid cost assumptions never certify or bypass the adapter", {
  model <- list(problem = list(num_cols = 4L, decision_columns = c(4L, 1L),
                               cost = c(2, 0, 0, 3)))
  invalid_costs <- list(
    c(0, 0, 0, 3), c(-1, 0, 0, 3), c(1.5, 0, 0, 3),
    c(NA, 0, 0, 3), c(NaN, 0, 0, 3), c(Inf, 0, 0, 3),
    c(2, 0, 0, 0), c(2, 0, 0, -1), c(2, 0, 0, 1.5), c(2, 0, 0, Inf),
    c(2, 1, 0, 3), c(2, -1, 0, 3), c(2, 0, Inf, 3),
    c(2, 0, 0, 2^31), c(2, 0, 0), NULL,
    c(TRUE, FALSE, FALSE, TRUE), c("2", "0", "0", "3"),
    c(2, 0, 0, 3 + 1i), matrix(c(2, 0, 0, 3), nrow = 1L)
  )
  local_mocked_bindings(solve_lp = function(...) stop("reference adapter reached"))
  for (strategy in reduction_methods()) {
    strategy$essential_decisions <- function(model) 4L
    strategy$coverage <- function(...) stop("invalid costs reached coverage")
    for (cost in invalid_costs) {
      model$problem$cost <- cost
      expect_null(essential_cover_certificate(model, c(4L, 1L), 4L, strategy))
      expect_error(solve_canonical(model, NULL, strategy), "reference adapter reached",
                   fixed = TRUE)
    }
  }
})

test_that("valid integer costs in either numeric representation certify without a clock", {
  local_mocked_bindings(elapsed = function() stop("helper read clock"),
                        solve_lp = function(...) stop("helper called solver"))
  for (cost in list(c(2, 0, 0, 3), c(2L, 0L, 0L, 3L))) {
    model <- list(problem = list(num_cols = 4L, cost = cost))
    strategy <- reduction_methods()[[1L]]
    strategy$coverage <- function(model, selected) all(selected)
    expect_identical(essential_cover_certificate(model, c(4L, 1L), c(1L, 4L), strategy),
                     list(selected = c(TRUE, TRUE), minimum = 5L))
  }
})

test_that("the engine checks the deadline after scan validation before certification", {
  now <- 0
  local_mocked_bindings(elapsed = function() now,
    essential_cover_certificate = function(...) stop("expired scan reached certificate"),
    solve_lp = function(...) stop("expired scan reached solver"))
  model <- list(problem = list(num_cols = 1L, decision_columns = 1L, cost = 1))
  for (strategy in reduction_methods()) {
    strategy$essential_decisions <- function(model) { now <<- now + 5; 1L }
    expect_error(solve_canonical(model, 5, strategy),
                 paste0(strategy$failure_prefix, "Time limit reached"),
                 fixed = TRUE, class = "cldreducer_solver_error")
  }
})

test_that("the engine checks the deadline after successful and failed certificates", {
  helper <- essential_cover_certificate
  now <- 0
  local_mocked_bindings(elapsed = function() now,
    essential_cover_certificate = function(...) {
      result <- helper(...)
      now <<- now + 5
      result
    }, solve_lp = function(...) stop("expired certificate reached solver"))
  model <- list(problem = list(num_cols = 1L, decision_columns = 1L, cost = 1))
  for (strategy in reduction_methods()) {
    strategy$essential_decisions <- function(model) 1L
    for (covered in c(TRUE, FALSE)) {
      strategy$coverage <- function(model, selected) covered
      expect_error(solve_canonical(model, 5, strategy),
                   paste0(strategy$failure_prefix, "Time limit reached"),
                   fixed = TRUE, class = "cldreducer_solver_error")
    }
  }
})

test_that("the reference switch omits the certificate but keeps the scan deadline", {
  now <- 0
  local_mocked_bindings(elapsed = function() now,
    essential_cover_certificate = function(...) stop("disabled certificate reached"),
    solve_lp = function(...) list(status = "optimal", values = 1, objective = 1))
  strategy <- reduction_methods()[[1L]]
  strategy$essential_decisions <- function(model) 1L
  strategy$coverage <- function(model, selected) all(selected)
  model <- list(problem = list(num_cols = 1L, decision_columns = 1L, cost = 1))
  expect_identical(solve_canonical(model, NULL, strategy, certificate = FALSE),
                   list(selected = TRUE, minimum = 1L))
  strategy$essential_decisions <- function(model) { now <<- now + 5; 1L }
  expect_error(solve_canonical(model, 5, strategy, certificate = FALSE),
               "assignment-minimum MILP failed: Time limit reached",
               fixed = TRUE, class = "cldreducer_solver_error")
})
