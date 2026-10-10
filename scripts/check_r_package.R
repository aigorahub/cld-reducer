# Check the built source archive, not the checkout.
check_r_package <- function(tarball) {
  files <- utils::untar(tarball, list = TRUE)
  relative <- sub("^[^/]+/", "", files)
  forbidden <- c("python", "js", "conformance", "docs", "scripts", "data-raw",
                 ".git", ".github", ".elves", ".Rproj.user")
  stopifnot(!any(sub("/.*", "", relative) %in% forbidden))
  stopifnot(all(c("DESCRIPTION", "NAMESPACE", "LICENSE", "inst/COPYRIGHTS") %in% relative))
  stopifnot(all(paste0("data/", c("piepho2004_wheat", "simple_abc_pairs",
                                 "simple_abc_means"), ".rda") %in% relative))
  stopifnot(!any(grepl("(\\.pyc$|\\.tgz$|\\.whl$|\\.Rcheck/)", relative)))
  message("R source archive contents verified: ", tarball)
  invisible(tarball)
}
if (sys.nframe() == 0L) check_r_package(commandArgs(trailingOnly = TRUE)[1L])
