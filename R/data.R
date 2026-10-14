#' Piepho (2004) wheat yield example
#'
#' All 190 pairwise comparisons of 20 wheat treatments (varieties) from the
#' CIMMYT multi-environment yield trial analyzed by Piepho (2004) and reproduced
#' in Table VIII of Ennis, Fayle, and Ennis (2012). The comparisons are
#' "not significantly different" for 172 pairs. The standard (maximal) display
#' has 4 letters and 56 letter assignments. The default CLD-C result has
#' the same counts. With `method = "assignment_minimum"`, [reduce_letters()]
#' returns the CLD-sigma result with 4 letters and 44 assignments.
#'
#' @format A data frame with 190 rows and 3 columns:
#' \describe{
#'   \item{group1}{Label of the first treatment, a character string from `"1"`
#'     to `"20"`.}
#'   \item{group2}{Label of the second treatment.}
#'   \item{significant}{Logical. `TRUE` when the two treatments differ
#'     significantly.}
#' }
#' @source Piepho, H.-P. (2004). An algorithm for a letter-based representation
#'   of all-pairwise comparisons. *Journal of Computational and Graphical
#'   Statistics*, 13(2), 456-466. \doi{10.1198/1061860043515}, as tabulated in
#'   Ennis, Fayle, and Ennis (2012), Table VIII. \doi{10.1145/2133803.2275596}
#' @seealso [reduce_letters()]
#' @examples
#' dim(piepho2004_wheat)
#' mean(!piepho2004_wheat$significant)
#' reduce_letters(piepho2004_wheat)$stats$assignments_after
#' reduce_letters(piepho2004_wheat,
#'                method = "assignment_minimum")$stats$assignments_after
"piepho2004_wheat"

#' Simple example: pairwise results of five groups
#'
#' The five-group example of Ennis, Fayle, and Ennis (2012) in which the
#' CLD-sigma method reduces the display `ABC` of one group to `AC`.
#' The default CLD-C result keeps `ABC`. Groups 1 to 3, 2 to 4,
#' and 3 to 5 do not differ significantly; all other pairs do.
#'
#' @format A data frame with 10 rows and 3 columns: `group1` and `group2`
#'   (character labels `"1"` to `"5"`) and `significant` (logical).
#' @source Ennis, J. M., Fayle, C. M., and Ennis, D. M. (2012). Assignment-minimum
#'   clique coverings. *ACM Journal of Experimental Algorithmics*, 17, Article
#'   1.5. \doi{10.1145/2133803.2275596}
#' @seealso [simple_abc_means], [reduce_letters()]
#' @examples
#' simple_abc_pairs
#' reduce_letters(simple_abc_pairs, simple_abc_means)$letters
#' reduce_letters(simple_abc_pairs, simple_abc_means,
#'                method = "assignment_minimum")$letters
"simple_abc_pairs"

#' Simple example: group means
#'
#' The group means that go with [simple_abc_pairs]. They fix the order of the
#' groups and of the letters.
#'
#' @format A data frame with 5 rows and 2 columns: `group` (character labels
#'   `"1"` to `"5"`) and `mean` (numeric).
#' @source Ennis, J. M., Fayle, C. M., and Ennis, D. M. (2012). Assignment-minimum
#'   clique coverings. *ACM Journal of Experimental Algorithmics*, 17, Article
#'   1.5. \doi{10.1145/2133803.2275596}
#' @seealso [simple_abc_pairs], [reduce_letters()]
#' @examples
#' simple_abc_means
"simple_abc_means"
