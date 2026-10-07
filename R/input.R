# Input checks. They follow docs/algorithm.md sections 1, 2, and 6 in the same order,
# with the stable message prefixes of section 10.

true_words <- c("true", "t", "yes", "y", "1", "significant")
false_words <- c("false", "f", "no", "n", "0", "not significant", "ns")

format_list <- function(x) {
  paste0("[", paste0("'", x, "'", collapse = ", "), "]")
}

# Group labels are strings (docs/algorithm.md section 1).
label_text <- function(x) {
  if (is.factor(x)) x <- as.character(x)
  as.character(x)
}

# A missing label (NA) is invalid input, wherever labels are given.
check_labels_present <- function(labels) {
  if (anyNA(labels)) {
    invalid_input("group labels must not be missing")
  }
  invisible(labels)
}

coerce_significance <- function(x) {
  if (is.factor(x)) x <- as.character(x)
  out <- rep(NA, length(x))
  if (is.logical(x)) {
    out <- x
  } else if (is.numeric(x)) {
    out[!is.na(x) & x == 1] <- TRUE
    out[!is.na(x) & x == 0] <- FALSE
  } else if (is.character(x)) {
    # Trim spaces, tabs, carriage returns, and line feeds only (section 1).
    words <- tolower(trimws(x, whitespace = "[ \t\r\n]"))
    out[words %in% true_words] <- TRUE
    out[words %in% false_words] <- FALSE
  }
  bad <- which(is.na(out))
  if (length(bad) > 0L) {
    invalid_input(
      "cannot coerce significance value to bool: ",
      if (is.character(x)) paste0("'", x[bad[1L]], "'") else format(x[bad[1L]])
    )
  }
  as.logical(out)
}

check_groups <- function(groups) {
  labels <- check_labels_present(label_text(groups))
  if (anyDuplicated(labels) > 0L) {
    invalid_input("group labels must be unique after string conversion")
  }
  if (length(labels) == 0L) {
    invalid_input("at least one group is required")
  }
  labels
}

# Means as a list(group, mean), from a named vector or a data frame.
parse_means <- function(means) {
  if (is.null(means)) {
    return(NULL)
  }
  if (is.data.frame(means)) {
    if (all(c("group", "mean") %in% names(means))) {
      return(list(group = label_text(means[["group"]]), mean = means[["mean"]]))
    }
    if (ncol(means) >= 2L) {
      return(list(group = label_text(means[[1L]]), mean = means[[2L]]))
    }
    invalid_input(
      "means data frame must have at least two columns or columns named group and mean"
    )
  }
  if (is.atomic(means) && !is.null(names(means))) {
    return(list(group = names(means), mean = unname(means)))
  }
  invalid_input(
    "means must be a named numeric vector or a data frame with group and mean columns"
  )
}

# The means of `groups`, in that order, or NULL when no means are given.
match_means <- function(table, groups) {
  if (is.null(table)) {
    return(NULL)
  }
  check_labels_present(table$group)
  repeated <- unique(table$group[duplicated(table$group)])
  if (length(repeated) > 0L) {
    invalid_input("means contain duplicate groups: ", format_list(repeated))
  }
  index <- match(groups, table$group)
  if (anyNA(index)) {
    invalid_input("means are missing values for groups: ", format_list(groups[is.na(index)]))
  }
  values <- table$mean[index]
  if (!is.numeric(values) || !all(is.finite(values))) {
    invalid_input("means must be finite numbers")
  }
  as.numeric(values)
}

# Section 1: pairwise rows (and optional means) to a graph.
pairs_to_graph <- function(pairs, means, group1, group2, significant) {
  if (!is.data.frame(pairs)) {
    invalid_input("pairs must be a data frame")
  }
  missing_columns <- sort(setdiff(unique(c(group1, group2, significant)), names(pairs)))
  if (length(missing_columns) > 0L) {
    invalid_input("post_hoc_results missing required columns: ", format_list(missing_columns))
  }
  first <- label_text(pairs[[group1]])
  second <- label_text(pairs[[group2]])
  check_labels_present(c(first, second))
  not_significant <- !coerce_significance(pairs[[significant]])
  if (any(first == second)) {
    invalid_input("post_hoc_results must not contain self-comparisons")
  }
  # Pair keys use the positions of exact labels, not joined text: no delimiter can make two
  # pairs share a key, and no locale collation decides the order.
  universe <- unique(c(first, second))
  key <- function(a, b) {
    i <- match(a, universe)
    j <- match(b, universe)
    ifelse(is.na(i) | is.na(j), NA_character_, paste(pmin(i, j), pmax(i, j)))
  }
  shown <- function(a, b) paste(pmin(a, b), pmax(a, b), sep = "|")
  keys <- key(first, second)
  if (anyDuplicated(keys) > 0L) {
    twice <- duplicated(keys)
    invalid_input(
      "post_hoc_results contains duplicate unordered pairs: ",
      format_list(unique(shown(first[twice], second[twice])))
    )
  }

  table <- parse_means(means)
  groups <- if (is.null(table)) check_groups(unique(c(first, second))) else check_groups(table$group)
  mean_values <- match_means(table, groups)
  unknown <- setdiff(c(first, second), groups)
  if (length(unknown) > 0L) {
    invalid_input(
      "post_hoc_results contains groups not present in means/groups: ",
      format_list(sort(unknown))
    )
  }
  size <- length(groups)
  if (size > 1L) {
    pair_index <- which(upper.tri(diag(size)), arr.ind = TRUE)
    a <- groups[pair_index[, 1L]]
    b <- groups[pair_index[, 2L]]
    expected <- key(a, b)
    absent <- is.na(expected) | !expected %in% keys
    if (any(absent)) {
      invalid_input(
        "post_hoc_results missing unordered pairwise comparisons: ",
        format_list(sort(shown(a[absent], b[absent])))
      )
    }
  }
  adjacency <- diag(TRUE, size)
  i <- match(first[not_significant], groups)
  j <- match(second[not_significant], groups)
  adjacency[cbind(i, j)] <- TRUE
  adjacency[cbind(j, i)] <- TRUE
  list(groups = groups, adjacency = adjacency, means = mean_values)
}

# Section 2: a matrix (and optional groups and means) to a graph.
adjacency_to_graph <- function(adjacency, groups, means) {
  if (is.data.frame(adjacency)) {
    adjacency <- as.matrix(adjacency)
  }
  if (is.matrix(adjacency)) {
    if (anyNA(adjacency)) {
      invalid_input("adjacency must not contain missing values")
    }
    explicit <- is.logical(adjacency) ||
      (is.numeric(adjacency) && all(adjacency %in% c(0, 1)))
    if (!explicit) {
      invalid_input("adjacency must contain only booleans or explicit 0/1 values")
    }
  }
  if (!is.matrix(adjacency) || nrow(adjacency) != ncol(adjacency)) {
    invalid_input("adjacency must be a square matrix")
  }
  size <- nrow(adjacency)
  if (size == 0L) {
    invalid_input("adjacency must contain at least one group")
  }
  cell <- matrix(as.logical(adjacency), size, size)
  if (!all(cell == t(cell))) {
    invalid_input("adjacency must be symmetric")
  }
  if (!all(diag(cell))) {
    invalid_input("adjacency diagonal must be TRUE")
  }
  if (is.null(groups)) {
    labels <- as.character(seq_len(size))
  } else {
    labels <- check_groups(groups)
    if (length(labels) != size) {
      invalid_input("number of groups must match adjacency dimensions")
    }
  }
  list(groups = labels, adjacency = cell, means = match_means(parse_means(means), labels))
}

check_method <- function(method) {
  if (!is.character(method) || length(method) != 1L || is.na(method) ||
      !method %in% c("assignment_minimum", "assignment-minimum")) {
    invalid_input(
      "unsupported CLD reduction method: '",
      paste(format(method), collapse = ", "), "'"
    )
  }
  invisible("assignment_minimum")
}

check_controls <- function(time_limit, max_cliques) {
  if (!is.null(time_limit) &&
      (!is.numeric(time_limit) || length(time_limit) != 1L || !is.finite(time_limit) ||
       time_limit <= 0)) {
    solver_error("time_limit must be positive when provided")
  }
  # A finite whole number of any size; it stays a double, so a cap of 2^31 or more is not
  # narrowed to an integer.
  if (!is.null(max_cliques) &&
      (!is.numeric(max_cliques) || length(max_cliques) != 1L || !is.finite(max_cliques) ||
       max_cliques < 1 || max_cliques != round(max_cliques))) {
    solver_error("max_cliques must be a positive integer or NULL")
  }
  list(
    time_limit = if (is.null(time_limit)) NULL else as.numeric(time_limit),
    max_cliques = if (is.null(max_cliques)) NULL else as.numeric(max_cliques)
  )
}
