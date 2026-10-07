# Spreadsheet style letter labels: A to Z, then AA to AZ, BA, and so on
# (docs/algorithm.md section 7).
make_letter_labels <- function(count) {
  if (length(count) != 1L || is.na(count) || count < 0 || count != round(count)) {
    stop("`count` must be a non-negative whole number.", call. = FALSE)
  }
  vapply(seq_len(count) - 1L, function(index) {
    label <- ""
    value <- index
    repeat {
      label <- paste0(LETTERS[value %% 26L + 1L], label)
      value <- value %/% 26L
      if (value == 0L) break
      value <- value - 1L
    }
    label
  }, character(1))
}
