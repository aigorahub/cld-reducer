test_that("only identical closed neighborhoods are merged", {
  graph <- diag(TRUE, 4)
  graph[1:2,1:2] <- TRUE
  reduced <- reduce_graph_vertices(graph)
  expect_equal(reduced$classes, list(1:2,3L,4L))
  expect_equal(reduced$weights,c(2,1,1))
  expect_equal(reduced$adjacency,diag(TRUE,3))
  expect_equal(expand_graph_columns(list(c(1L,3L)),reduced$classes),list(c(1L,2L,4L)))
})

test_that("C is the default and sigma counts original vertices", {
  graph <- matrix(TRUE,5,5)
  result <- reduce_from_adjacency(graph)
  expect_equal(result,reduce_from_adjacency(graph,method="letter_minimum"))
  expect_equal(result$method,"letter_minimum")
  expect_equal(result$stats$objective,1)
  sigma <- reduce_from_adjacency(graph,method="assignment_minimum")
  expect_equal(sigma$stats$objective,5)
  expect_equal(sigma$stats$assignments_after,5)
  expect_equal(sigma$stats$num_edges,10)
})

test_that("the canonical cost cap uses weights", {
  problem <- list(num_cols=3L,decision_columns=1:3,cost=c(5,1,1),
    matrix=Matrix::Matrix(matrix(c(1,1,0,1,0,1),nrow=2,byrow=TRUE),sparse=TRUE),
    row_lower=c(1,1),row_upper=c(Inf,Inf))
  strategy <- reduction_methods()[[1]]
  strategy$coverage <- function(model,x) (x[1] || x[2]) && (x[1] || x[3])
  result <- solve_canonical(list(problem=problem),NULL,strategy)
  expect_equal(result$minimum,2)
  expect_equal(result$selected,c(FALSE,TRUE,TRUE))
})
