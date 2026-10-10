expect_invalid <- function(expr, pattern) {
  expect_error(expr, pattern, class = "cldreducer_invalid_input")
}
expect_solver <- function(expr, pattern) {
  expect_error(expr, pattern, class = "cldreducer_solver_error")
}

triple <- data.frame(
  group1 = c("a", "a", "b"), group2 = c("b", "c", "c"),
  significant = c(FALSE, TRUE, FALSE), stringsAsFactors = FALSE
)

test_that("errors have the documented classes", {
  err <- tryCatch(reduce_letters(triple[0, ]), error = identity)
  expect_s3_class(err, "cldreducer_invalid_input")
  expect_s3_class(err, "cldreducer_error")
  expect_s3_class(err, "error")
  err <- tryCatch(reduce_from_adjacency(diag(TRUE, 2), time_limit = 0), error = identity)
  expect_s3_class(err, "cldreducer_solver_error")
  expect_s3_class(err, "cldreducer_error")
})

test_that("significance accepts logical, 0 and 1, and the documented words", {
  expect_equal(coerce_significance(c(TRUE, FALSE)), c(TRUE, FALSE))
  expect_equal(coerce_significance(c(1, 0, 1L)), c(TRUE, FALSE, TRUE))
  expect_equal(
    coerce_significance(c("true", "T", " Yes ", "y", "1", "significant", "SIGNIFICANT")),
    rep(TRUE, 7)
  )
  expect_equal(
    coerce_significance(c("false", "F", "No", "n", "0", " not significant ", "NS")),
    rep(FALSE, 7)
  )
  expect_equal(coerce_significance(factor(c("yes", "no"))), c(TRUE, FALSE))
  for (bad in list("maybe", "", NA, 2, 0.5, NA_character_, list(1))) {
    expect_invalid(coerce_significance(bad), "cannot coerce significance value to bool: ")
  }
})

test_that("every significance form works in a call", {
  labels <- c("w", "x", "y", "z")
  rows <- pairs_of(labels)
  rows$significant <- c("yes", " NS ", "1", "0", "not significant", "TRUE")
  result <- reduce_letters(rows)
  expect_equal(result$groups, labels)
  expect_equal(result$stats$num_edges, 3)
})

test_that("pairwise input is checked in the documented order", {
  no_sig <- triple[c("group1", "group2")]
  expect_invalid(reduce_letters(no_sig), "post_hoc_results missing required columns: \\['significant'\\]")
  expect_invalid(reduce_letters(triple, group1 = "g1"), "missing required columns: \\['g1'\\]")
  expect_invalid(reduce_letters(as.list(triple)), "pairs must be a data frame")
  bad <- triple
  bad$group2[1] <- "a"
  expect_invalid(reduce_letters(bad), "must not contain self-comparisons")
  bad$significant[1] <- NA
  expect_invalid(reduce_letters(bad), "cannot coerce significance value to bool")
  dup <- rbind(triple, data.frame(group1 = "b", group2 = "a", significant = FALSE))
  expect_invalid(reduce_letters(dup), "duplicate unordered pairs: \\['a\\|b'\\]")
  expect_invalid(reduce_letters(triple[1:2, ]), "missing unordered pairwise comparisons: \\['b\\|c'\\]")
  few <- data.frame(group = c("a", "b"), mean = c(1, 2))
  expect_invalid(reduce_letters(triple, few), "groups not present in means/groups: \\['c'\\]")
  expect_invalid(reduce_letters(triple[1:2, ], few, method = "greedy"), "groups not present")
  expect_invalid(reduce_letters(triple[1:2, ], method = "greedy"), "missing unordered pairwise")
})

test_that("group order comes from the means or from first appearance", {
  rows <- data.frame(group1 = c("b", "c", "c"), group2 = c("a", "a", "b"),
                     significant = c(FALSE, TRUE, FALSE), stringsAsFactors = FALSE)
  expect_equal(reduce_letters(rows)$groups, c("b", "c", "a"))
  means <- c(c = 1, b = 2, a = 3)
  expect_equal(reduce_letters(rows, means)$groups, c("c", "b", "a"))
  as_frame <- data.frame(group = c("a", "c", "b"), mean = c(3, 1, 2))
  expect_equal(reduce_letters(rows, as_frame)$groups, c("a", "c", "b"))
  two_columns <- data.frame(name = c("a", "c", "b"), value = c(3, 1, 2))
  expect_equal(reduce_letters(rows, two_columns)$groups, c("a", "c", "b"))
})

test_that("labels are converted to strings", {
  rows <- data.frame(group1 = c(10, 10, 2), group2 = c(2, 3, 3),
                     significant = c(FALSE, TRUE, FALSE))
  expect_equal(reduce_letters(rows)$groups, c("10", "2", "3"))
  expect_equal(reduce_letters(data.frame(group1 = factor("x"), group2 = factor("y"),
                                         significant = TRUE))$groups, c("x", "y"))
})

test_that("custom column names and extra columns work", {
  rows <- data.frame(u = triple$group1, v = triple$group2, s = c(0, 1, 0), note = "x")
  result <- reduce_letters(rows, group1 = "u", group2 = "v", significant = "s")
  expect_equal(result$groups, c("a", "b", "c"))
})

test_that("means must be named numeric vectors or data frames of finite numbers", {
  expect_invalid(reduce_letters(triple, 1:3), "means must be a named numeric vector")
  expect_invalid(reduce_letters(triple, list(a = 1)), "means must be a named numeric vector")
  expect_invalid(reduce_letters(triple, data.frame(g = c("a", "b", "c"))), "at least two columns")
  expect_invalid(reduce_from_adjacency(diag(TRUE, 2), c("a", "b"), c(a = 1)),
                 "means are missing values for groups: \\['b'\\]")
  for (bad in list(c(a = 1, b = NA, c = 3), c(a = 1, b = Inf, c = 3), c(a = "1", b = "2", c = "3"),
                   c(a = TRUE, b = FALSE, c = TRUE))) {
    expect_invalid(reduce_letters(triple, bad), "means must be finite numbers")
  }
  expect_invalid(reduce_letters(triple, data.frame(group = c("a", "a", "b", "c"), mean = 1:4)),
                 "unique after string conversion")
})

test_that("means are matched to the groups of a matrix by label", {
  result <- reduce_from_adjacency(simple_adjacency(), means = rev(simple_means()))
  expect_equal(result$groups, as.character(1:5))
  expect_equal(result$letters, simple_letters)
})

test_that("adjacency input is checked in the documented order", {
  two <- function(m, ...) reduce_from_adjacency(m, c("a", "b"), ...)
  expect_invalid(two(matrix(c(1, NA, NA, 1), 2)), "adjacency must not contain missing values")
  expect_invalid(two(matrix(c("T", "F", "F", "T"), 2)), "only booleans or explicit 0/1 values")
  expect_invalid(two(matrix(c(1, 2, 2, 1), 2)), "only booleans or explicit 0/1 values")
  expect_invalid(two(matrix(c(1, 0.5, 0.5, 1), 2)), "only booleans or explicit 0/1 values")
  expect_invalid(two(matrix(c(1, NA, 3, 1), 2)), "must not contain missing values")
  expect_invalid(two(matrix(c(1, 0, 0, 1, 0, 1), 2)), "adjacency must be a square matrix")
  expect_invalid(two(list()), "adjacency must be a square matrix")
  expect_invalid(two(1:4), "adjacency must be a square matrix")
  expect_invalid(reduce_from_adjacency(matrix(logical(0), 0, 0)), "at least one group")
  expect_invalid(two(matrix(c(1, 0, 1, 1), 2)), "adjacency must be symmetric")
  expect_invalid(two(matrix(c(1, 0, 0, 0), 2)), "adjacency diagonal must be TRUE")
  expect_invalid(reduce_from_adjacency(diag(TRUE, 2), "a"), "number of groups must match")
  expect_invalid(reduce_from_adjacency(diag(TRUE, 2), c("a", "a")), "unique after string conversion")
  expect_invalid(reduce_from_adjacency(diag(TRUE, 2), c(1, "1")), "unique after string conversion")
  expect_invalid(reduce_from_adjacency(diag(TRUE, 1), character(0)), "at least one group is required")
})

test_that("adjacency input accepts logical and 0/1 matrices and data frames", {
  expect_equal(reduce_from_adjacency(diag(2))$letters, c("1" = "A", "2" = "B"))
  expect_equal(reduce_from_adjacency(as.data.frame(diag(2)))$groups, c("1", "2"))
  expect_equal(reduce_from_adjacency(diag(TRUE, 3), c("x", "y", "z"))$groups, c("x", "y", "z"))
})

test_that("method and solver controls are checked in the documented order", {
  m <- diag(TRUE, 2)
  expect_invalid(reduce_from_adjacency(m, method = "greedy", time_limit = 0), "unsupported CLD reduction method: ")
  expect_invalid(reduce_from_adjacency(m, method = NA_character_), "unsupported CLD reduction method")
  expect_solver(reduce_from_adjacency(m, time_limit = 0, max_cliques = 0), "time_limit must be positive when provided")
  for (bad in list(0, -1, "30", TRUE, NA_real_, Inf, c(1, 2))) {
    expect_solver(reduce_from_adjacency(m, time_limit = bad), "time_limit must be positive when provided")
  }
  for (bad in list(0, -3, 1.5, "10", TRUE, NA_real_, c(1, 2))) {
    expect_solver(reduce_from_adjacency(m, max_cliques = bad), "max_cliques must be a positive integer or NULL")
  }
  expect_equal(reduce_from_adjacency(diag(TRUE, 1), method = "assignment-minimum")$method, "assignment_minimum")
})

test_that("the clique cap applies to the count and NULL removes it", {
  m <- diag(TRUE, 3)
  expect_equal(reduce_from_adjacency(m, max_cliques = 3)$stats$num_letters_before, 3)
  expect_solver(reduce_from_adjacency(m, max_cliques = 2), "exceeded max_cliques=2")
  expect_equal(reduce_from_adjacency(m, max_cliques = NULL)$stats$num_letters_before, 3)
})
