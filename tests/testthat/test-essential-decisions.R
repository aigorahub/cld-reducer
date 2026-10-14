test_that("essential bounds reach the first and later solver calls", {
  real <- solve_lp
  for (strategy in reduction_methods()) {
    calls <- list()
    local_mocked_bindings(solve_lp = function(problem, col_lower, col_upper, sum_limit = NULL, time_limit = Inf) {
      calls[[length(calls) + 1L]] <<- list(lower=col_lower,upper=col_upper,cap=sum_limit)
      real(problem,col_lower,col_upper,sum_limit,time_limit)
    })
    result <- reduce_from_adjacency(simple_adjacency(),method=strategy$name)
    required <- if(strategy$counts_assignments) c(1,2,3,4,6,7,8,9) else 1:3
    lower <- if(strategy$counts_assignments) c(1,1,1,1,0,1,1,1,1,rep(0,9)) else rep(1,3)
    expect_equal(calls[[1]]$lower,lower)
    expect_true(all(calls[[1]]$upper == 1))
    expect_null(calls[[1]]$cap)
    expect_true(all(vapply(calls,function(call) all(call$lower[required] == 1),logical(1))))
    expect_equal(result$stats$objective,if(strategy$counts_assignments) 8 else 3)
  }
})

test_that("a first result must obey essential bounds even when coverage and cost are valid", {
  model <- list(problem=list(num_cols=2L,decision_columns=1:2,cost=c(1,1)))
  local_mocked_bindings(solve_lp=function(...) list(status="optimal",text="Optimal",values=c(0,1),objective=1))
  for(strategy in reduction_methods()) {
    strategy$coverage <- function(model,x) any(x)
    strategy$essential_decisions <- function(model) 1L
    expect_error(solve_canonical(model,NULL,strategy),"HiGHS returned an invalid solution",
                 class="cldreducer_solver_error")
  }
})

test_that("malformed scan indices fail before the adapter", {
  local_mocked_bindings(solve_lp=function(...) stop("invalid scan reached adapter"))
  model <- list(problem=list(num_cols=3L,decision_columns=c(3L,1L)))
  for(required in list(NULL,2L,0L,4L,1.5,TRUE,NA_real_,c(3L,1L),c(1L,1L),list(1L),matrix(1L))) {
    strategy <- reduction_methods()[[1]]
    strategy$essential_decisions <- function(model) required
    expect_error(solve_canonical(model,NULL,strategy),"HiGHS returned an invalid solution",
                 class="cldreducer_solver_error")
  }
})

test_that("scan time is part of the existing solver deadline", {
  now <- 0
  local_mocked_bindings(elapsed=function() now,solve_lp=function(...) stop("expired scan reached adapter"))
  context <- graph_context(adjacency_to_graph(simple_adjacency(),NULL,NULL),
                           list(1:3,2:4,3:5))
  for(strategy in reduction_methods()) {
    scan <- strategy$essential_decisions
    strategy$essential_decisions <- function(model) {now <<- now+10;scan(model)}
    expect_error(solve_canonical(strategy$builder(context),5,strategy),"MILP failed: Time limit reached",
                 class="cldreducer_solver_error")
  }
})

test_that("the exact scans handle isolates and a cover with no essential decisions", {
  graph <- adjacency_to_graph(diag(TRUE,3),NULL,NULL)
  context <- graph_context(graph,list(1L,2L,3L))
  for(strategy in reduction_methods()) {
    expect_identical(strategy$essential_decisions(strategy$builder(context)),1:3)
  }
  graph <- adjacency_to_graph(outer(0:5,0:5,function(u,v) u == v | u %/% 2 != v %/% 2),NULL,NULL)
  context <- graph_context(graph,maximal_cliques(graph$adjacency,NULL))
  for(strategy in reduction_methods()) {
    expect_identical(strategy$essential_decisions(strategy$builder(context)),integer(0))
  }
})
