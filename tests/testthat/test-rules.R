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
    expect_error(reduce_from_adjacency(matrix(TRUE, 1L, 1L), method = "assignment_minimum"),
                 "HiGHS returned an invalid solution", class = "cldreducer_solver_error")
  }
})

test_that("the table and the printout keep an empty-string label", {
  result <- reduce_from_adjacency(diag(TRUE, 2L), c("", "b"), method = "assignment_minimum")
  table <- as.data.frame(result)
  expect_identical(table$group, c("", "b"))
  expect_identical(table$letters, c("A", "B"))
  expect_identical(table$assignments, c("A", "B"))
  expect_false(anyNA(table$letters))
  printed <- capture.output(print(result))
  expect_false(any(grepl("NA", printed, fixed = TRUE)))
})

test_that("max_cliques takes any finite whole number and rejects Inf", {
  expect_silent(result <- reduce_from_adjacency(diag(TRUE, 3L), max_cliques = 3e9, method = "assignment_minimum"))
  expect_equal(result$stats$num_letters_after, 3)
  expect_silent(reduce_from_adjacency(diag(TRUE, 1L), max_cliques = 2^31, method = "assignment_minimum"))
  expect_error(reduce_from_adjacency(diag(TRUE, 2L), max_cliques = Inf, method = "assignment_minimum"),
               "max_cliques must be a positive integer or NULL",
               class = "cldreducer_solver_error")
  expect_error(reduce_from_adjacency(diag(TRUE, 3L), max_cliques = 2, method = "assignment_minimum"),
               "maximal clique enumeration exceeded max_cliques=2;",
               class = "cldreducer_solver_error")
})

test_that("missing labels are invalid input", {
  pairs <- data.frame(group1 = c("a", "a", "b"), group2 = c("b", NA, NA), significant = FALSE)
  expect_error(reduce_letters(pairs, method = "assignment_minimum"), "group labels must not be missing",
               class = "cldreducer_invalid_input")
  pairs <- data.frame(group1 = c("a", NA, "b"), group2 = c("b", "c", "c"),
                      significant = c("maybe", "no", "no"))
  expect_error(reduce_letters(pairs, method = "assignment_minimum"), "group labels must not be missing",
               class = "cldreducer_invalid_input")
  expect_error(reduce_from_adjacency(diag(TRUE, 2L), c("a", NA), method = "assignment_minimum"),
               "group labels must not be missing", class = "cldreducer_invalid_input")
  expect_error(reduce_from_adjacency(diag(TRUE, 2L), c("a", "b"),
                                     data.frame(group = c("a", NA), mean = c(1, 2)), method = "assignment_minimum"),
               "group labels must not be missing", class = "cldreducer_invalid_input")
})

test_that("a numeric NaN label is missing, and the text NaN is a label", {
  missing <- "group labels must not be missing"
  expect_error(reduce_from_adjacency(diag(TRUE, 2L), c(1, NaN), method = "assignment_minimum"), missing,
               class = "cldreducer_invalid_input")
  pairs <- data.frame(group1 = c(1, 1, 2), group2 = c(2, NaN, 3), significant = TRUE)
  expect_error(reduce_letters(pairs, method = "assignment_minimum"), missing, class = "cldreducer_invalid_input")
  pairs$significant <- "maybe"
  expect_error(reduce_letters(pairs, method = "assignment_minimum"), missing, class = "cldreducer_invalid_input")
  expect_error(reduce_from_adjacency(diag(TRUE, 2L), c("1", "2"),
                                     data.frame(group = c(1, NaN), mean = c(1, 2)), method = "assignment_minimum"),
               missing, class = "cldreducer_invalid_input")
  expect_error(reduce_letters(all_pairs(c("1", "2")), data.frame(group = c(1, NaN), mean = 1:2), method = "assignment_minimum"),
               missing, class = "cldreducer_invalid_input")
  expect_error(reduce_from_adjacency(diag(TRUE, 2L), c("a", "b"), stats::setNames(1:2, c("a", NA)), method = "assignment_minimum"),
               missing, class = "cldreducer_invalid_input")
  expect_error(reduce_from_adjacency(diag(TRUE, 2L), factor(c("a", NA)), method = "assignment_minimum"), missing,
               class = "cldreducer_invalid_input")

  text <- c("NaN", "NA", "null")
  result <- reduce_from_adjacency(diag(TRUE, 3L), text, stats::setNames(c(3, 2, 1), text), method = "assignment_minimum")
  expect_identical(result$groups, text)
  expect_identical(unname(result$letters), c("A", "B", "C"))
  result <- reduce_letters(all_pairs(text, "1 2"), data.frame(group = text, mean = c(3, 2, 1)), method = "assignment_minimum")
  expect_identical(result$groups, text)
  expect_identical(unname(result$letters), c("A", "A", "B"))
})

test_that("a factor with an explicit NA level has a missing label", {
  missing <- "group labels must not be missing"
  with_na_level <- list(addNA(factor(c("a", NA))), factor(c("a", NA), exclude = NULL))
  for (groups in with_na_level) {
    expect_false(anyNA(groups))
    expect_error(reduce_from_adjacency(diag(TRUE, 2L), groups, method = "assignment_minimum"), missing,
                 class = "cldreducer_invalid_input")
    expect_error(reduce_from_adjacency(diag(TRUE, 2L), c("a", "b"),
                                       data.frame(group = groups, mean = 1:2), method = "assignment_minimum"),
                 missing, class = "cldreducer_invalid_input")
    expect_error(reduce_letters(all_pairs(c("a", "b")), data.frame(group = groups, mean = 1:2), method = "assignment_minimum"),
                 missing, class = "cldreducer_invalid_input")
  }
  pairs <- data.frame(group1 = factor(c("a", "a", "b")),
                      group2 = factor(c("b", NA, NA), exclude = NULL), significant = FALSE)
  expect_error(reduce_letters(pairs, method = "assignment_minimum"), missing, class = "cldreducer_invalid_input")
  pairs$significant <- "maybe"
  expect_error(reduce_letters(pairs, method = "assignment_minimum"), missing, class = "cldreducer_invalid_input")
  pairs <- data.frame(group1 = addNA(factor(c("a", NA, "b"))), group2 = c("b", "c", "c"),
                      significant = FALSE)
  expect_error(reduce_letters(pairs, method = "assignment_minimum"), missing, class = "cldreducer_invalid_input")

  text <- factor(c("NaN", "NA"))
  result <- reduce_from_adjacency(diag(TRUE, 2L), text, method = "assignment_minimum")
  expect_identical(result$groups, c("NaN", "NA"))
})

test_that("duplicate mean labels are invalid input for adjacency input", {
  path3 <- matrix(c(TRUE, TRUE, FALSE, TRUE, TRUE, TRUE, FALSE, TRUE, TRUE), 3L)
  expect_error(
    reduce_from_adjacency(path3, c("a", "b", "c"), c(a = 1, b = 2, c = 3, a = 9), method = "assignment_minimum"),
    "means contain duplicate groups: ", class = "cldreducer_invalid_input"
  )
})

test_that("significance trimming removes only spaces, tabs, and line breaks", {
  ok <- reduce_letters(data.frame(group1 = "a", group2 = "b", significant = " ns\t\r\n"), method = "assignment_minimum")
  expect_identical(unname(ok$letters), c("A", "A"))
  expect_error(reduce_letters(data.frame(group1 = "a", group2 = "b", significant = "ns\u00a0"), method = "assignment_minimum"),
               "cannot coerce significance value to bool: ", class = "cldreducer_invalid_input")
})

test_that("a data frame with zero rows has no comparisons", {
  empty <- data.frame(group1 = character(0), group2 = character(0), significant = logical(0))
  result <- reduce_letters(empty, c(a = 1), method = "assignment_minimum")
  expect_identical(unname(result$letters), "A")
  expect_identical(result$groups, "a")
  expect_error(reduce_letters(empty, method = "assignment_minimum"), "at least one group is required",
               class = "cldreducer_invalid_input")
})

test_that("pairs are identified by exact labels", {
  for (sep in c("\r", "|", " ")) {
    labels <- c("a", paste0("b", sep, "c"), paste0("a", sep, "b"), "c")
    pairs <- all_pairs(labels, c("1 2", "2 3", "3 4"))
    expect_identical(reduce_letters(pairs, method = "assignment_minimum")$groups, labels)
    expect_error(reduce_letters(pairs[-1L, ], method = "assignment_minimum"),
                 "post_hoc_results missing unordered pairwise comparisons: ",
                 class = "cldreducer_invalid_input")
  }
})
