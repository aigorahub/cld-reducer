# Lemma 2.5: identical closed neighborhoods share one weighted vertex.
reduce_graph_vertices <- function(adjacency) {
  keys <- apply(adjacency, 1L, function(row) paste(as.integer(row), collapse = ""))
  membership <- match(keys, unique(keys))
  classes <- lapply(seq_len(max(membership)), function(k) which(membership == k))
  representatives <- vapply(classes, function(group) group[1L], integer(1))
  list(adjacency = adjacency[representatives, representatives, drop = FALSE],
       classes = classes, weights = lengths(classes))
}

expand_graph_columns <- function(columns, classes) {
  lapply(columns, function(column) sort(unlist(classes[column], use.names = FALSE)))
}
