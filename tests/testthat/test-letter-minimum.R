tied_c_graph <- function() {
  a <- diag(TRUE, 6)
  edges <- matrix(c(1,3,1,4,1,5,1,6,2,3,2,4,2,5,2,6,3,4,3,6,4,5), ncol=2, byrow=TRUE)
  a[edges] <- TRUE
  a | t(a)
}

test_that("C uses full columns and normalizes its alias", {
  out <- reduce_letters(simple_abc_pairs, simple_abc_means, method="letter-minimum")
  expect_identical(out$method, "letter_minimum")
  expect_equal(out$stats$objective, 3)
  expect_type(out$stats$objective, "double")
  expect_equal(out$stats$num_letters_after, 3)
  expect_equal(out$stats$assignments_after, 9)
  expect_equal(out$assignments[["3"]], c("A","B","C"))
})

test_that("C canonical trials accept optimal and skip invalid infeasible vectors", {
  real <- solve_lp
  statuses <- character()
  local_mocked_bindings(solve_lp = function(problem, lower, upper, sum_limit, time_limit) {
    if (is.null(sum_limit)) problem$cost[problem$decision_columns] <- 1 + seq(.001,0,length.out=length(problem$decision_columns))
    out <- real(problem, lower, upper, sum_limit, time_limit)
    if (!is.null(sum_limit)) statuses <<- c(statuses, out$status)
    if (out$status == "infeasible") out$values <- NaN
    out
  })
  out <- reduce_from_adjacency(tied_c_graph(), method="letter_minimum")
  expect_equal(out$stats$objective, 5)
  expect_true(all(c("optimal","infeasible") %in% statuses))
  expect_equal(unname(out$letters), c("ABC","DE","ABD","ACE","CE","BD"))
})

test_that("C rejects invalid initial vectors, objectives and statuses", {
  real <- solve_lp
  for (kind in c("none","length","zero","full","fractional","nan","two","objective","infinite","status")) {
    local_mocked_bindings(solve_lp = function(...) {
      out <- real(...)
      if (kind == "status") return(list(status="infeasible",text="status-text"))
      if (kind == "none") out$values <- NULL
      if (kind == "length") out$values <- rep(1,5)
      if (kind == "zero") out$values[] <- 0
      if (kind == "full") out$values[] <- 1
      if (kind == "fractional") out$values[] <- .5
      if (kind == "nan") out$values[] <- NaN
      if (kind == "two") out$values[] <- 2
      if (kind == "objective") out$objective <- 3
      if (kind == "infinite") out$objective <- Inf
      out
    })
    expect_error(reduce_from_adjacency(tied_c_graph(),method="letter_minimum"),
      if (kind == "status") "letter-minimum MILP failed: status-text" else "HiGHS returned an invalid solution")
  }
})

test_that("native noncontiguous decisions exclude auxiliary values from the cap", {
  problem <- list(num_cols=3L, decision_columns=c(3L,1L), cost=c(1,0,1),
    matrix=Matrix::sparseMatrix(i=c(1,1,2),j=c(1,3,2),x=1,dims=c(2,3)),
    row_lower=c(1,1),row_upper=c(Inf,Inf))
  out <- solve_lp(problem,rep(0,3),rep(1,3),1)
  expect_identical(out$status,"optimal")
  expect_equal(out$values[2],1)
  for (strategy in reduction_methods()) {
    strategy$coverage <- function(model,selected) any(selected)
    out <- solve_canonical(list(problem=problem),NULL,strategy)
    expect_equal(out$minimum,1)
    expect_equal(out$selected,c(TRUE,FALSE))
  }
})

test_that("C validates controls, correct-count edge coverage, trial statuses and fixings", {
  expect_error(reduce_from_adjacency(tied_c_graph(),method="letter_minimum",time_limit=0),"time_limit")
  expect_error(reduce_from_adjacency(tied_c_graph(),method="letter_minimum",max_cliques=0),"max_cliques")
  real <- solve_lp
  for (kind in c("edge","fixing","count","status")) {
    local_mocked_bindings(solve_lp = function(problem, lower, upper, sum_limit, time_limit) {
      if (is.null(sum_limit)) problem$cost[problem$decision_columns] <- 1 + seq(.001,0,length.out=6)
      out <- real(problem,lower,upper,sum_limit,time_limit)
      if (kind == "edge" && is.null(sum_limit)) {
        out$values <- c(1,1,1,1,1,0)
        out$objective <- 5
      }
      if (!is.null(sum_limit) && out$status == "optimal") {
        if (kind == "fixing") out$values[which(lower > .5)[1]] <- 0
        if (kind == "count") out$values[] <- 1
        if (kind == "status") return(list(status="failed",text="Memory limit reached"))
      }
      out
    })
    expect_error(reduce_from_adjacency(tied_c_graph(),method="letter_minimum"),
      if (kind == "status") "letter-minimum MILP failed: Memory limit" else "HiGHS returned an invalid solution")
  }
})

test_that("C uses one deadline before initial and trial solves", {
  real <- solve_lp
  for (phase in c("initial","trial")) {
    now <- 0
    local_mocked_bindings(elapsed = function() {
      value <- now
      if (phase == "initial") now <<- 10
      value
    }, solve_lp = function(problem,lower,upper,sum_limit,time_limit) {
      if (is.null(sum_limit)) problem$cost[problem$decision_columns] <- 1 + seq(.001,0,length.out=6)
      out <- real(problem,lower,upper,sum_limit,time_limit)
      now <<- now + 10
      out
    })
    expect_error(reduce_from_adjacency(tied_c_graph(),method="letter_minimum",time_limit=5),
      "letter-minimum MILP failed: Time limit reached")
  }
})

test_that("the adapter maps ambiguous status and retains its text", {
  local_mocked_bindings(highs_solve = function(...) list(status_message="Primal infeasible or unbounded"), .package="highs")
  problem <- list(num_cols=1L,decision_columns=1L,cost=1,matrix=Matrix::Matrix(1,sparse=TRUE),row_lower=1,row_upper=Inf)
  out <- solve_lp(problem,0,1)
  expect_identical(out$status,"infeasible")
  expect_identical(out$text,"Primal infeasible or unbounded")
  expect_error(reduce_from_adjacency(diag(TRUE,1),method="letter_minimum"),
    "letter-minimum MILP failed: Primal infeasible or unbounded")
})

test_that("sigma keeps its public objective type after sharing the integer optimum", {
  out <- reduce_letters(simple_abc_pairs, simple_abc_means, method = "assignment_minimum")
  expect_type(out$stats$objective,"double")
  expect_equal(out$stats$objective,8)
})
