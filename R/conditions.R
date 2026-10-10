# The two error kinds of docs/algorithm.md section 10, as classed conditions.

cld_condition <- function(message, kind) {
  structure(
    class = c(kind, "cldreducer_error", "error", "condition"),
    list(message = message, call = NULL)
  )
}

invalid_input <- function(...) {
  stop(cld_condition(paste0(...), "cldreducer_invalid_input"))
}

solver_error <- function(...) {
  stop(cld_condition(paste0(...), "cldreducer_solver_error"))
}
