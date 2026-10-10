brute_force_cliques <- function(m) {
  n <- nrow(m)
  found <- list()
  for (mask in seq_len(2^n - 1)) {
    s <- which(bitwAnd(mask, 2^(seq_len(n) - 1)) > 0)
    if (all(m[s, s])) found[[length(found) + 1L]] <- s
  }
  maximal <- Filter(function(s) {
    !any(vapply(found, function(t) length(t) > length(s) && all(s %in% t), logical(1)))
  }, found)
  width <- max(lengths(maximal))
  padded <- do.call(rbind, lapply(maximal, function(s) c(s, rep(0L, width - length(s)))))
  maximal[do.call(order, lapply(seq_len(width), function(k) padded[, k]))]
}

test_that("cliques come in the canonical order (the renaming example)", {
  m <- adjacency_of(5, cbind(c(1, 1, 1, 1, 2, 3), c(2, 3, 4, 5, 5, 5)))
  expect_equal(maximal_cliques(m, NULL), list(c(1L, 2L, 5L), c(1L, 3L, 5L), c(1L, 4L)))
})

test_that("an isolated group is a clique of its own", {
  expect_equal(maximal_cliques(adjacency_of(3, cbind(1, 2)), NULL), list(c(1L, 2L), 3L))
})

test_that("complete and empty graphs", {
  expect_equal(maximal_cliques(matrix(TRUE, 4, 4), NULL), list(1:4))
  expect_equal(maximal_cliques(diag(TRUE, 3), NULL), list(1L, 2L, 3L))
})

test_that("cliques match brute force on every graph with 4 groups and on random graphs", {
  pairs <- which(upper.tri(diag(4)), arr.ind = TRUE)
  for (mask in 0:(2^6 - 1)) {
    keep <- bitwAnd(mask, 2^(seq_len(6) - 1)) > 0
    m <- adjacency_of(4, if (any(keep)) pairs[keep, , drop = FALSE] else NULL)
    expect_equal(maximal_cliques(m, NULL), brute_force_cliques(m))
  }
  set.seed(7)
  for (i in 1:10) {
    upper <- upper.tri(diag(7)) & matrix(runif(49) < 0.55, 7)
    m <- upper | t(upper) | diag(TRUE, 7)
    expect_equal(maximal_cliques(m, NULL), brute_force_cliques(m))
  }
})

test_that("the cap counts cliques and allows exactly the cap", {
  expect_length(maximal_cliques(diag(TRUE, 3), 3), 3)
  expect_error(maximal_cliques(diag(TRUE, 3), 2), "exceeded max_cliques=2",
               class = "cldreducer_solver_error")
})
