# Maximal cliques in the canonical order of docs/algorithm.md section 3.

# All maximal cliques of the graph, each as ascending group indices, sorted
# lexicographically (a list of integer vectors). Bron-Kerbosch with pivoting.
# With `max_cliques` set, stops with a solver error as soon as more cliques are
# found.
maximal_cliques <- function(adjacency, max_cliques) {
  size <- nrow(adjacency)
  neighbors <- lapply(seq_len(size), function(i) setdiff(which(adjacency[i, ]), i))
  found <- list()
  count <- 0L

  expand <- function(r, p, x) {
    if (length(p) == 0L && length(x) == 0L) {
      count <<- count + 1L
      if (!is.null(max_cliques) && count > max_cliques) {
        solver_error(
          "maximal clique enumeration exceeded max_cliques=",
          format(max_cliques, scientific = FALSE, trim = TRUE),
          "; increase max_cliques or pass NULL to disable the cap"
        )
      }
      found[[count]] <<- sort(r)
      return(invisible())
    }
    candidates <- c(p, x)
    pivot <- candidates[which.max(vapply(
      candidates, function(u) sum(p %in% neighbors[[u]]), numeric(1)
    ))]
    for (v in setdiff(p, neighbors[[pivot]])) {
      expand(c(r, v), intersect(p, neighbors[[v]]), intersect(x, neighbors[[v]]))
      p <- setdiff(p, v)
      x <- c(x, v)
    }
    invisible()
  }
  expand(integer(0), seq_len(size), integer(0))

  width <- max(lengths(found))
  padded <- t(vapply(found, function(clique) {
    c(clique, rep(0L, width - length(clique)))
  }, integer(width)))
  if (width == 1L) padded <- matrix(padded, ncol = 1L)
  found[do.call(order, lapply(seq_len(width), function(k) padded[, k]))]
}
