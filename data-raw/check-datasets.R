# Compare the data sets that data-raw/datasets.R just wrote to data/ with the
# copies that were committed (saved by the CI job before the script ran).
# Content is compared with identical(), not bytes, because .rda bytes can
# change between R versions.
#
# Usage: Rscript data-raw/check-datasets.R <folder with the saved data/*.rda files>
# Exits with status 1 when a committed copy is missing or differs.

args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 1L) stop("usage: Rscript data-raw/check-datasets.R <saved folder>")
saved <- args[1L]

names <- c("piepho2004_wheat", "simple_abc_pairs", "simple_abc_means")
load_one <- function(file, name) {
  env <- new.env()
  load(file, envir = env)
  get(name, envir = env)
}

problems <- character(0)
for (name in names) {
  fresh <- file.path("data", paste0(name, ".rda"))
  old <- file.path(saved, paste0(name, ".rda"))
  if (!file.exists(fresh)) {
    problems <- c(problems, paste0(name, ": data-raw/datasets.R did not write ", fresh))
  } else if (!file.exists(old)) {
    problems <- c(problems, paste0(name, ": the committed data/", name, ".rda is missing"))
  } else if (!identical(load_one(fresh, name), load_one(old, name))) {
    problems <- c(problems, paste0(name, ": the committed data/", name, ".rda differs"))
  }
}
if (length(problems) > 0L) {
  cat(problems, sep = "\n")
  quit(status = 1)
}
cat("data sets are current:", paste(names, collapse = ", "), "\n")
