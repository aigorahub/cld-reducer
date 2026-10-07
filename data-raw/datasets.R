# Build the example data sets from the CSV files in conformance/data/, which are
# the single source of truth for all three languages.
#
# Run from the repository root: Rscript data-raw/datasets.R
# The CI job "generated-files" runs this script and checks that the saved data/
# files still hold the same objects (data-raw/check-datasets.R).

read_pairs <- function(file) {
  read.csv(file.path("conformance", "data", file), stringsAsFactors = FALSE,
           colClasses = c("character", "character", "logical"))
}

piepho2004_wheat <- read_pairs("piepho2004_wheat_pairs.csv")
simple_abc_pairs <- read_pairs("simple_abc_to_ac_pairs.csv")
simple_abc_means <- read.csv(file.path("conformance", "data", "simple_abc_to_ac_means.csv"),
                             stringsAsFactors = FALSE, colClasses = c("character", "numeric"))

dir.create("data", showWarnings = FALSE)
for (name in c("piepho2004_wheat", "simple_abc_pairs", "simple_abc_means")) {
  save(list = name, file = file.path("data", paste0(name, ".rda")),
       compress = "bzip2", version = 2)
}
