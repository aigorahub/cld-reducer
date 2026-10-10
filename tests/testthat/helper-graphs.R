# Graph helpers for the tests. They build every input from literal values.

# A symmetric logical matrix with TRUE on the diagonal and TRUE for each (i, j)
# row of `edges`.
adjacency_of <- function(size, edges = NULL) {
  m <- diag(TRUE, size)
  if (!is.null(edges)) {
    edges <- matrix(edges, ncol = 2L)
    m[edges] <- TRUE
    m[edges[, 2:1, drop = FALSE]] <- TRUE
  }
  m
}

# Pairwise rows for `labels`, with the pairs in `not_significant` (a two column
# matrix of positions) marked as not significant.
pairs_of <- function(labels, not_significant = NULL) {
  index <- which(upper.tri(diag(length(labels))), arr.ind = TRUE)
  index <- index[order(index[, 1L], index[, 2L]), , drop = FALSE]
  key <- function(m) paste(m[, 1L], m[, 2L])
  same <- if (is.null(not_significant)) logical(nrow(index)) else
    key(index) %in% key(matrix(not_significant, ncol = 2L))
  data.frame(group1 = labels[index[, 1L]], group2 = labels[index[, 2L]],
             significant = !same, stringsAsFactors = FALSE)
}

# The simple ABC example (groups 1 to 5): 1-2, 1-3, 2-3, 2-4, 3-4, 3-5, 4-5.
simple_edges <- cbind(c(1, 1, 2, 2, 3, 3, 4), c(2, 3, 3, 4, 4, 5, 5))
simple_letters <- c("1" = "A", "2" = "AB", "3" = "AC", "4" = "BC", "5" = "C")

simple_adjacency <- function() adjacency_of(5, simple_edges)
simple_means <- function() c("1" = 3.73, "2" = 3.57, "3" = 3.46, "4" = 3.33, "5" = 3.3)
