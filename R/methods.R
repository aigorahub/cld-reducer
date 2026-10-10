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
  # Match positions, not names: `[` cannot select the empty-string name.
  at_letters <- match(x$groups, names(x$letters))
  at_tokens <- match(x$groups, names(x$assignments))
  data.frame(
    group = x$groups,
    letters = unname(x$letters[at_letters]),
    assignments = vapply(at_tokens, function(i) paste(x$assignments[[i]], collapse = " "),
                         character(1)),
    row.names = row.names,
    stringsAsFactors = FALSE
  )
}
