test_that("the example data sets have the documented shape", {
  expect_s3_class(piepho2004_wheat, "data.frame")
  expect_equal(dim(piepho2004_wheat), c(190, 3))
  expect_equal(names(piepho2004_wheat), c("group1", "group2", "significant"))
  expect_type(piepho2004_wheat$group1, "character")
  expect_type(piepho2004_wheat$significant, "logical")
  expect_false(anyNA(piepho2004_wheat))
  expect_equal(sort(unique(c(piepho2004_wheat$group1, piepho2004_wheat$group2))),
               sort(as.character(1:20)))
  expect_equal(sum(!piepho2004_wheat$significant), 172)

  expect_equal(dim(simple_abc_pairs), c(10, 3))
  expect_equal(sum(!simple_abc_pairs$significant), 7)
  expect_equal(simple_abc_means, data.frame(
    group = as.character(1:5), mean = c(3.73, 3.57, 3.46, 3.33, 3.30),
    stringsAsFactors = FALSE
  ))
})

test_that("each pair of groups occurs once in the wheat data", {
  key <- ifelse(as.integer(piepho2004_wheat$group1) < as.integer(piepho2004_wheat$group2),
                paste(piepho2004_wheat$group1, piepho2004_wheat$group2),
                paste(piepho2004_wheat$group2, piepho2004_wheat$group1))
  expect_false(anyDuplicated(key) > 0)
  expect_false(any(piepho2004_wheat$group1 == piepho2004_wheat$group2))
})

test_that("the pairs and means of the simple example agree with each other", {
  result <- reduce_letters(simple_abc_pairs, simple_abc_means)
  expect_equal(result$stats$assignments_after, 8)
})
