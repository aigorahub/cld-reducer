# Run the shared conformance fixtures against the R package, and check that each
# R data set equals its CSV file in conformance/data/.
#
# Run from the repository root: Rscript conformance/run_r.R
# Needs jsonlite and pkgload. Exits with status 1 on any failure.
# See conformance/README.md for the file formats and the pass rule.

pkgload::load_all(".", quiet = TRUE)
ns <- asNamespace("cldreducer")

read_fixture <- function(kind) {
  jsonlite::fromJSON(file.path("conformance", "fixtures", paste0(kind, ".json")),
                     simplifyVector = FALSE)
}

failures <- character(0)
fail <- function(id, ...) failures <<- c(failures, paste0(id, ": ", ...))

# A JSON array of scalars as an atomic vector; null becomes NA.
column <- function(values) unlist(lapply(values, function(v) if (is.null(v)) NA else v))

# Fixture rows as a data frame with one column for every key that occurs. An R data
# frame always has column names, so zero rows become typed empty columns with the
# names the call uses (docs/algorithm.md section 1, zero rows).
rows_to_frame <- function(rows, columns) {
  if (length(rows) == 0L) {
    frame <- list(character(0), character(0), logical(0))
    names(frame) <- columns
    return(as.data.frame(frame, stringsAsFactors = FALSE))
  }
  keys <- unique(unlist(lapply(rows, names)))
  frame <- lapply(keys, function(key) column(lapply(rows, function(r) r[[key]])))
  names(frame) <- keys
  as.data.frame(frame, stringsAsFactors = FALSE)
}

# One element of a named list by position: `[[` cannot select the empty-string name.
pick <- function(x, name) x[[match(name, names(x))]]

means_of <- function(means) {
  if (is.null(means)) NULL else data.frame(
    group = column(lapply(means, function(m) m[["group"]])),
    mean = column(lapply(means, function(m) m[["mean"]])),
    stringsAsFactors = FALSE
  )
}

matrix_of <- function(rows) {
  if (length(rows) == 0L) {
    return(list())
  }
  do.call(rbind, lapply(rows, column))
}

call_case <- function(case) {
  options <- list()
  for (key in c("group1", "group2", "significant", "method")) {
    if (key %in% names(case$options)) options[[key]] <- case$options[[key]]
  }
  # A key with the value null (no cap) must stay in the list.
  for (key in c("max_cliques", "time_limit")) {
    if (key %in% names(case$options)) options[key] <- list(case$options[[key]])
  }
  means <- means_of(case$input$means)
  if (identical(case$call, "pairs")) {
    columns <- vapply(c("group1", "group2", "significant"), function(key) {
      if (is.null(options[[key]])) key else options[[key]]
    }, character(1))
    do.call(reduce_letters, c(list(pairs = rows_to_frame(case$input$pairs, columns),
                                   means = means), options))
  } else {
    groups <- case$input$groups
    if (!is.null(groups)) groups <- as.character(column(groups))[seq_along(groups)]
    do.call(reduce_from_adjacency, c(list(adjacency = matrix_of(case$input$adjacency),
                                          groups = groups, means = means), options))
  }
}

percent <- function(p) p$numerator / p$denominator * 100

actual_of <- function(r) {
  list(groups = r$groups, assignments = r$assignments, letters = r$letters,
       stats = r$stats[c("assignments_before", "assignments_after", "num_letters_before",
                         "num_letters_after", "num_groups", "num_edges")],
       solver_status = r$stats$solver_status, objective = r$stats$objective,
       reduction_pct = r$stats$reduction_pct, method = r$method,
       relationship_preserved = r$relationship_preserved)
}

# The pass rule of conformance/README.md for one reduce case. Returns the names
# of the parts that differ.
mismatches <- function(actual, expected) {
  bad <- character(0)
  groups <- as.character(unlist(expected$groups))
  if (!identical(actual$groups, groups)) bad <- c(bad, "groups")
  tokens <- function(x) lapply(groups, function(g) as.character(unlist(pick(x, g))))
  if (!identical(unname(lapply(groups, function(g) pick(actual$assignments, g))),
                 tokens(expected$assignments))) {
    bad <- c(bad, "assignments")
  }
  if (!identical(unname(vapply(groups, function(g) pick(actual$letters, g), character(1))),
                 unname(vapply(groups, function(g) pick(expected$letters, g), character(1))))) {
    bad <- c(bad, "letters")
  }
  stat_names <- names(expected$stats)
  if (!isTRUE(all(unlist(actual$stats[stat_names]) == unlist(expected$stats[stat_names])))) {
    bad <- c(bad, "stats")
  }
  if (!identical(actual$solver_status, expected$solver_status)) bad <- c(bad, "solver_status")
  if (!isTRUE(actual$objective == expected$objective)) bad <- c(bad, "objective")
  if (!isTRUE(actual$reduction_pct == percent(expected$reduction_pct))) {
    bad <- c(bad, "reduction_pct")
  }
  if (!identical(actual$method, expected$method)) bad <- c(bad, "method")
  if (!identical(actual$relationship_preserved, TRUE)) bad <- c(bad, "relationship_preserved")
  bad
}

# A fixture result in the shape of actual_of(), so that mismatches() can judge it.
as_actual <- function(result) {
  groups <- as.character(unlist(result$groups))
  list(
    groups = groups,
    assignments = stats::setNames(lapply(groups, function(g) {
      as.character(unlist(pick(result$assignments, g)))
    }), groups),
    letters = stats::setNames(vapply(groups, function(g) pick(result$letters, g), character(1)),
                              groups),
    stats = lapply(result$stats, identity),
    solver_status = result$solver_status, objective = result$objective,
    reduction_pct = percent(result$reduction_pct), method = result$method,
    relationship_preserved = result$relationship_preserved
  )
}

reduce_cases <- read_fixture("reduce")$cases

# The checker must accept the expected wheat result and reject the three wrong ones.
local({
  wheat <- reduce_cases[[which(vapply(reduce_cases, function(c) c$id, "") == "hand/wheat")]]
  if (length(mismatches(as_actual(wheat$expected), wheat$expected)) != 0L) {
    stop("the conformance checker rejects the expected wheat result")
  }
  wrong <- c(list(wheat$non_canonical), lapply(read_fixture("checker")$bad, `[[`, "result"))
  rejected <- vapply(wrong, function(bad) length(mismatches(as_actual(bad), wheat$expected)) > 0L,
                     logical(1))
  if (length(wrong) != 3L || !all(rejected)) stop("the conformance checker accepts a wrong result")
})

counts <- c(reduce = 0L, errors = 0L, labels = 0L, data = 0L)

for (case in reduce_cases) {
  result <- tryCatch(call_case(case), error = function(e) e)
  if (inherits(result, "condition")) {
    fail(case$id, "raised an error: ", conditionMessage(result))
  } else {
    bad <- mismatches(actual_of(result), case$expected)
    if (length(bad) > 0L) fail(case$id, "differs in ", paste(bad, collapse = ", "))
  }
  counts[["reduce"]] <- counts[["reduce"]] + 1L
}

error_classes <- c(invalid_input = "cldreducer_invalid_input", solver = "cldreducer_solver_error")
for (case in read_fixture("errors")$cases) {
  result <- tryCatch({ call_case(case); NULL }, error = function(e) e)
  want <- case$expected
  if (is.null(result)) {
    fail(case$id, "no error")
  } else if (!inherits(result, error_classes[[want$kind]])) {
    fail(case$id, "wrong condition: ", paste(class(result), collapse = "/"), ": ",
         conditionMessage(result))
  } else if (!startsWith(conditionMessage(result), want$message_prefix)) {
    fail(case$id, "message is '", conditionMessage(result), "'")
  }
  counts[["errors"]] <- counts[["errors"]] + 1L
}

for (case in read_fixture("labels")$cases) {
  if (!identical(ns$make_letter_labels(case$count), as.character(unlist(case$labels)))) {
    fail(case$id, "labels differ")
  }
  counts[["labels"]] <- counts[["labels"]] + 1L
}

# Each R data set equals its CSV in conformance/data/ (the data sets are built
# from these files by data-raw/datasets.R).
read_csv_data <- function(file, classes) {
  read.csv(file.path("conformance", "data", file), stringsAsFactors = FALSE, colClasses = classes)
}
data_sets <- list(
  piepho2004_wheat = read_csv_data("piepho2004_wheat_pairs.csv", c("character", "character", "logical")),
  simple_abc_pairs = read_csv_data("simple_abc_to_ac_pairs.csv", c("character", "character", "logical")),
  simple_abc_means = read_csv_data("simple_abc_to_ac_means.csv", c("character", "numeric"))
)
for (name in names(data_sets)) {
  if (!identical(get(name, envir = ns), data_sets[[name]]) &&
      !identical(get(name), data_sets[[name]])) {
    fail(paste0("data set ", name), "differs from its CSV file")
  }
  counts[["data"]] <- counts[["data"]] + 1L
}

cat(sprintf("%s: %d checked\n", names(counts), counts), sep = "")
if (length(failures) > 0L) {
  cat(sprintf("%d failures\n", length(failures)))
  cat(head(failures, 50L), sep = "\n")
  quit(status = 1L)
}
cat(sprintf("all %d conformance cases pass (%d reduce, %d errors, %d labels), and %d data sets equal their CSV files\n",
            counts[["reduce"]] + counts[["errors"]] + counts[["labels"]],
            counts[["reduce"]], counts[["errors"]], counts[["labels"]], counts[["data"]]))
