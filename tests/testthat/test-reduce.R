test_that("the simple example reduces ABC to AC", {
  result <- reduce_letters(simple_abc_pairs, simple_abc_means)
  expect_s3_class(result, "cld_reduction")
  expect_equal(result$letters, simple_letters)
  expect_equal(result$assignments[["3"]], c("A", "C"))
  expect_equal(result$groups, as.character(1:5))
  expect_equal(result$stats$assignments_before, 9)
  expect_equal(result$stats$assignments_after, 8)
  expect_equal(result$stats$num_letters_before, 3)
  expect_equal(result$stats$num_letters_after, 3)
  expect_equal(result$stats$num_groups, 5)
  expect_equal(result$stats$num_edges, 7)
  expect_equal(result$stats$solver_status, "Optimal")
  expect_equal(result$stats$objective, 8)
  expect_identical(result$stats$reduction_pct, (9 - 8) / 9 * 100)
  expect_identical(result$method, "assignment_minimum")
  expect_true(result$relationship_preserved)
  expect_equal(result$adjacency, `dimnames<-`(simple_adjacency(), list(as.character(1:5), as.character(1:5))))
})

test_that("the pairs route and the adjacency route agree", {
  by_pairs <- reduce_letters(simple_abc_pairs, simple_abc_means)
  by_matrix <- reduce_from_adjacency(simple_adjacency(), means = simple_abc_means)
  expect_equal(by_pairs, by_matrix)
})

test_that("the wheat example reduces 56 assignments to 44 with the canonical display", {
  result <- reduce_letters(piepho2004_wheat)
  expect_equal(result$stats$assignments_before, 56)
  expect_equal(result$stats$assignments_after, 44)
  expect_equal(result$stats$num_letters_before, 4)
  expect_equal(result$stats$num_letters_after, 4)
  expect_equal(result$stats$num_edges, 172)
  # The 64 minimal displays are tied; this is the canonical one
  # (conformance fixture hand/wheat).
  expect_equal(unname(result$letters), c(
    "ABC", "BD", "AD", "BD", "AB", "BD", "AB", "ABC", "BD", "AB",
    "BD", "CD", "BD", "ABC", "ABC", "AB", "ABC", "B", "ABC", "C"
  ))
  expect_equal(result$stats$reduction_pct, 12 / 56 * 100)
})

test_that("the canonical clique order renames letters (D4 example)", {
  m <- adjacency_of(5, cbind(c(1, 1, 1, 1, 2, 3), c(2, 3, 4, 5, 5, 5)))
  result <- reduce_from_adjacency(m, as.character(0:4))
  expect_equal(unname(result$letters), c("ABC", "A", "B", "C", "AB"))
  expect_equal(result$stats$assignments_before, result$stats$assignments_after)
})

test_that("means decide the letter order", {
  path <- adjacency_of(3, cbind(c(1, 2), c(2, 3)))
  with_means <- reduce_from_adjacency(path, c("a", "b", "c"), c(a = 1, b = 2, c = 5))
  expect_equal(with_means$letters, c(a = "B", b = "AB", c = "A"))
  without <- reduce_from_adjacency(path, c("a", "b", "c"))
  expect_equal(without$letters, c(a = "A", b = "AB", c = "B"))
  ties <- reduce_from_adjacency(path, c("a", "b", "c"), c(a = 2, b = 2, c = 2))
  expect_equal(ties$letters, c(a = "A", b = "AB", c = "B"))
})

test_that("labels past Z are separated by spaces", {
  star <- adjacency_of(28, cbind(1, 2:28))
  result <- reduce_from_adjacency(star)
  tokens <- result$assignments[["1"]]
  expect_length(tokens, 27)
  expect_equal(tail(tokens, 2), c("Z", "AA"))
  expect_equal(strsplit(result$letters[["1"]], " ")[[1]], tokens)
  expect_equal(result$letters[["2"]], "A")
})

test_that("complete, empty, and single-group graphs", {
  full <- reduce_from_adjacency(matrix(TRUE, 5, 5))
  expect_equal(unname(full$letters), rep("A", 5))
  empty <- reduce_from_adjacency(diag(TRUE, 5))
  expect_equal(unname(empty$letters), c("A", "B", "C", "D", "E"))
  one <- reduce_from_adjacency(matrix(TRUE, 1, 1), "solo", c(solo = 2.5))
  expect_equal(one$letters, c(solo = "A"))
  expect_equal(one$stats$reduction_pct, 0)
})

test_that("a group name that looks like a special value works", {
  result <- reduce_from_adjacency(adjacency_of(3, cbind(1, 2)), c("NA", "10", "2"))
  expect_equal(result$groups, c("NA", "10", "2"))
  expect_equal(names(result$letters), c("NA", "10", "2"))
  expect_equal(unname(result$letters), c("A", "A", "B"))
})

test_that("print and as.data.frame show the display", {
  result <- reduce_letters(simple_abc_pairs, simple_abc_means)
  frame <- as.data.frame(result)
  expect_equal(names(frame), c("group", "letters", "assignments"))
  expect_equal(frame$group, as.character(1:5))
  expect_equal(frame$letters, c("A", "AB", "AC", "BC", "C"))
  expect_equal(frame$assignments, c("A", "A B", "A C", "B C", "C"))
  expect_equal(rownames(frame), as.character(1:5))
  out <- capture.output(print(result))
  expect_match(out[1], "Reduced compact letter display \\(assignment_minimum\\)")
  expect_true(any(grepl("Assignments: 9 -> 8 \\(11.1% fewer\\)", out)))
  capture.output(printed <- print(result))
  expect_identical(printed, result)
})
