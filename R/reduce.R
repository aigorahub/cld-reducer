#' Reduce a compact letter display
#'
#' `reduce_letters()` and `reduce_from_adjacency()` find a compact letter
#' display (CLD) minimizing assignments (CLD-sigma, the default) or distinct
#' letters (CLD-C), in which two groups share a
#' letter exactly when they are not significantly different. This is the
#' assignment-minimum clique covering problem of Ennis, Fayle, and Ennis
#' (2012). The programs are solved with 'HiGHS'. When several displays have the
#' same minimum objective, the function returns the canonical one
#' defined in the specification (`docs/algorithm.md` in the source repository),
#' so the result does not depend on the solver. The same method is available
#' in Python and JavaScript, and all three return the same display.
#'
#' @param pairs A data frame with one row for every pair of groups. The columns
#'   named by `group1` and `group2` hold the two group labels, and the column
#'   named by `significant` tells whether the pair differs significantly.
#'   Significance can be logical, the numbers 0 and 1, or text such as `"yes"`,
#'   `"no"`, `"ns"`, `"significant"`. Every unordered pair of groups needs
#'   exactly one row. Labels are converted to character.
#' @param means Optional group means, used for the order of the letters (the
#'   letter that holds the highest mean comes first). Either a named numeric
#'   vector, or a data frame with the columns `group` and `mean` (otherwise its
#'   first two columns). In `reduce_letters()`, the order of the means is also the
#'   order of the groups; without means, the groups are in order of first
#'   appearance in `group1`, then `group2`. Every mean must be finite.
#' @param group1,group2,significant Names of the columns of `pairs`.
#' @param method `"assignment_minimum"` (CLD-sigma, default) minimizes assignments;
#'   `"letter_minimum"` (CLD-C) minimizes full maximal-clique columns, with no
#'   assignment secondary objective. Hyphenated aliases are also accepted.
#'   Public result metadata uses the underscore spelling.
#' @param time_limit One time budget in seconds for all solves of the call, or
#'   `NULL` for no limit.
#' @param max_cliques The largest number of maximal cliques to enumerate before
#'   stopping with an error, or `NULL` for no limit.
#' @param adjacency A square logical or 0/1 matrix. `adjacency[i, j]` is `TRUE`
#'   when groups `i` and `j` are not significantly different and must share a
#'   letter. It must be symmetric with `TRUE` on the diagonal.
#' @param groups Group labels for the rows of `adjacency`. The default is
#'   `"1"`, `"2"`, and so on.
#'
#' @return An object of class `cld_reduction`, a list with
#'   * `letters`: a named character vector with the display of each group
#'     (the letters of a group are joined with no separator when every letter is
#'     one character, and with spaces after `Z`, when letters like `"AA"` appear);
#'   * `assignments`: a named list with the letters of each group as a character
#'     vector;
#'   * `stats`: a list with `assignments_before`, `assignments_after`,
#'     `reduction_pct` (not rounded), `num_letters_before`, `num_letters_after`,
#'     `num_groups`, `num_edges`, `solver_status`, and `objective`;
#'   * `method`, `groups`, `relationship_preserved`, and `adjacency` (a logical
#'     matrix).
#'
#'   `objective` equals `assignments_after` for CLD-sigma and `num_letters_after`
#'   for CLD-C. `assignments_after` and `reduction_pct` always measure assignments.
#'   Equal C optima select the lexicographically greatest binary clique vector
#'   in canonical order, then use the same stable mean/index letter formatting.
#'
#'   The `print()` method shows the display and the counts, and
#'   `as.data.frame()` gives a table with the columns `group`, `letters`, and
#'   `assignments`.
#'
#' @section Errors:
#' Malformed input stops with a condition of class `cldreducer_invalid_input`.
#' Solver problems, an invalid `time_limit` or `max_cliques`, and too many
#' cliques stop with a condition of class `cldreducer_solver_error`. Both also
#' have the class `cldreducer_error`.
#'
#' @references
#' Ennis, J. M., Fayle, C. M., and Ennis, D. M. (2012). Assignment-minimum
#' clique coverings. *ACM Journal of Experimental Algorithmics*, 17, Article
#' 1.5. \doi{10.1145/2133803.2275596}
#'
#' @examples
#' # Five groups; groups 1 to 3, 2 to 4, and 3 to 5 do not differ.
#' result <- reduce_letters(simple_abc_pairs, simple_abc_means)
#' result$letters
#' result$stats$assignments_after
#'
#' # The same example from the matrix of non-significant pairs
#' adjacency <- diag(TRUE, 5)
#' adjacency[cbind(c(1, 1, 2, 2, 3, 3, 4), c(2, 3, 3, 4, 4, 5, 5))] <- TRUE
#' adjacency <- adjacency | t(adjacency)
#' reduce_from_adjacency(adjacency, means = simple_abc_means)
#' @export
reduce_letters <- function(pairs, means = NULL, group1 = "group1", group2 = "group2",
                           significant = "significant", method = "assignment_minimum",
                           time_limit = NULL, max_cliques = 10000L) {
  graph <- pairs_to_graph(pairs, means, group1, group2, significant)
  reduce_graph(graph, method, time_limit, max_cliques)
}

#' @rdname reduce_letters
#' @export
reduce_from_adjacency <- function(adjacency, groups = NULL, means = NULL,
                                  method = "assignment_minimum", time_limit = NULL,
                                  max_cliques = 10000L) {
  graph <- adjacency_to_graph(adjacency, groups, means)
  reduce_graph(graph, method, time_limit, max_cliques)
}

reduce_graph <- function(graph, method, time_limit, max_cliques) {
  strategy <- check_method(method)
  controls <- check_controls(time_limit, max_cliques)
  groups <- graph$groups
  adjacency <- graph$adjacency
  size <- length(groups)

  cliques <- maximal_cliques(adjacency, controls$max_cliques)
  model <- strategy$builder(graph_context(graph, cliques))
  solution <- solve_canonical(model, controls$time_limit, strategy)

  columns <- strategy$decoder(cliques, model, solution$selected)
  render_result(graph, cliques, model, solution, columns, strategy)
}

reduction_methods <- function() list(
  list(name = "assignment_minimum", aliases = c("assignment_minimum", "assignment-minimum"),
       failure_prefix = "assignment-minimum MILP failed: ", builder = build_model,
       coverage = assignment_coverage, decoder = assignment_columns, counts_assignments = TRUE),
  list(name = "letter_minimum", aliases = c("letter_minimum", "letter-minimum"),
       failure_prefix = "letter-minimum MILP failed: ", builder = build_letter_model,
       coverage = letter_coverage, decoder = letter_columns, counts_assignments = FALSE)
)
