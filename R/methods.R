#' @export
print.cld_reduction <- function(x, ...) {
  cat("Reduced compact letter display (", x$method, ")\n", sep = "")
  print(as.data.frame(x), row.names = FALSE)
  s <- x$stats
  cat(sprintf(
    "Assignments: %d -> %d (%.1f%% fewer). Letters: %d -> %d. Relationships preserved: %s.\n",
    s$assignments_before, s$assignments_after, s$reduction_pct,
    s$num_letters_before, s$num_letters_after, x$relationship_preserved
  ))
  invisible(x)
}

#' @export
as.data.frame.cld_reduction <- function(x, row.names = NULL, optional = FALSE, ...) {
  data.frame(
    group = x$groups,
    letters = unname(x$letters[x$groups]),
    assignments = unname(vapply(x$assignments[x$groups], paste, character(1), collapse = " ")),
    row.names = row.names,
    stringsAsFactors = FALSE
  )
}
