# Input rules and solution checks of docs/algorithm.md sections 1, 2, and 6 that the final
# review (round 1) asked to pin.

all_pairs <- function(labels, nonsignificant = character(0)) {
  index <- which(upper.tri(diag(length(labels))), arr.ind = TRUE)
  index <- index[order(index[, 1L], index[, 2L]), , drop = FALSE]
  data.frame(
    group1 = labels[index[, 1L]],
    group2 = labels[index[, 2L]],
    significant = !paste(index[, 1L], index[, 2L]) %in% nonsignificant,
    stringsAsFactors = FALSE
  )
}

test_that("a membership outside 0 and 1 is an invalid solution", {
  real <- solve_lp
  for (value in c(2, -1, Inf)) {
    local_mocked_bindings(solve_lp = function(...) {
      out <- real(...)
      if (!is.null(out$values)) out$values[1L] <- value
      out
    })
    expect_error(reduce_from_adjacency(matrix(TRUE, 1L, 1L)),
                 "HiGHS returned an invalid solution", class = "cldreducer_solver_error")
  }
})

test_that("the table and the printout keep an empty-string label", {
  result <- reduce_from_adjacency(diag(TRUE, 2L), c("", "b"))
  table <- as.data.frame(result)
  expect_identical(table$group, c("", "b"))
  expect_identical(table$letters, c("A", "B"))
  expect_identical(table$assignments, c("A", "B"))
  expect_false(anyNA(table$letters))
  printed <- capture.output(print(result))
  expect_false(any(grepl("NA", printed, fixed = TRUE)))
})

test_that("max_cliques takes any finite whole number and rejects Inf", {
  expect_silent(result <- reduce_from_adjacency(diag(TRUE, 3L), max_cliques = 3e9))
  expect_equal(result$stats$num_letters_after, 3)
  expect_silent(reduce_from_adjacency(diag(TRUE, 1L), max_cliques = 2^31))
  expect_error(reduce_from_adjacency(diag(TRUE, 2L), max_cliques = Inf),
               "max_cliques must be a positive integer or NULL",
               class = "cldreducer_solver_error")
  expect_error(reduce_from_adjacency(diag(TRUE, 3L), max_cliques = 2),
               "maximal clique enumeration exceeded max_cliques=2;",
               class = "cldreducer_solver_error")
})

test_that("missing labels are invalid input", {
  pairs <- data.frame(group1 = c("a", "a", "b"), group2 = c("b", NA, NA), significant = FALSE)
  expect_error(reduce_letters(pairs), "group labels must not be missing",
               class = "cldreducer_invalid_input")
  pairs <- data.frame(group1 = c("a", NA, "b"), group2 = c("b", "c", "c"),
                      significant = c("maybe", "no", "no"))
  expect_error(reduce_letters(pairs), "group labels must not be missing",
               class = "cldreducer_invalid_input")
  expect_error(reduce_from_adjacency(diag(TRUE, 2L), c("a", NA)),
               "group labels must not be missing", class = "cldreducer_invalid_input")
  expect_error(reduce_from_adjacency(diag(TRUE, 2L), c("a", "b"),
                                     data.frame(group = c("a", NA), mean = c(1, 2))),
               "group labels must not be missing", class = "cldreducer_invalid_input")
})

test_that("duplicate mean labels are invalid input for adjacency input", {
  path3 <- matrix(c(TRUE, TRUE, FALSE, TRUE, TRUE, TRUE, FALSE, TRUE, TRUE), 3L)
  expect_error(
    reduce_from_adjacency(path3, c("a", "b", "c"), c(a = 1, b = 2, c = 3, a = 9)),
    "means contain duplicate groups: ", class = "cldreducer_invalid_input"
  )
})

test_that("significance trimming removes only spaces, tabs, and line breaks", {
  ok <- reduce_letters(data.frame(group1 = "a", group2 = "b", significant = " ns\t\r\n"))
  expect_identical(unname(ok$letters), c("A", "A"))
  expect_error(reduce_letters(data.frame(group1 = "a", group2 = "b", significant = "ns\u00a0")),
               "cannot coerce significance value to bool: ", class = "cldreducer_invalid_input")
})

test_that("a data frame with zero rows has no comparisons", {
  empty <- data.frame(group1 = character(0), group2 = character(0), significant = logical(0))
  result <- reduce_letters(empty, c(a = 1))
  expect_identical(unname(result$letters), "A")
  expect_identical(result$groups, "a")
  expect_error(reduce_letters(empty), "at least one group is required",
               class = "cldreducer_invalid_input")
})

test_that("pairs are identified by exact labels", {
  for (sep in c("\r", "|", " ")) {
    labels <- c("a", paste0("b", sep, "c"), paste0("a", sep, "b"), "c")
    pairs <- all_pairs(labels, c("1 2", "2 3", "3 4"))
    expect_identical(reduce_letters(pairs)$groups, labels)
    expect_error(reduce_letters(pairs[-1L, ]),
                 "post_hoc_results missing unordered pairwise comparisons: ",
                 class = "cldreducer_invalid_input")
  }
})
