# cldreducer 0.3.0

- Add pure CLD-C with `method="letter_minimum"` and alias `letter-minimum` in R,
  Python, JavaScript, and the Python CLI. It minimizes full maximal-clique letter
  columns with a fixed canonical tie rule; it has no assignment secondary objective.
- CLD-sigma remains the default (`assignment_minimum`, alias `assignment-minimum`).
  Both methods use one reduction framework per language and normalize public method
  metadata. The installed Python assignment-minimum helper retains metadata-only
  method behavior and always runs sigma.
- For C, objective counts letters. Assignments and reduction percentage retain their
  assignment meanings. Existing default displays and shared sigma fixtures are unchanged.
- Add independent C reference searches, a 33,867-graph census, cross-language fixtures,
  solver failures, and installed-package checks.

# cldreducer 0.2.0

First release of the R package. The repository now holds three packages that follow one specification (`docs/algorithm.md`) and pass one conformance suite (`conformance/`): the R package `cldreducer` at the repository root, the Python package `cld-reducer` in `python/`, and the JavaScript package `cld-reducer` in `js/`. All three solve the problem with HiGHS and return the same display for the same input.

## R package

- `reduce_letters()` reduces a compact letter display from pairwise comparisons, and `reduce_from_adjacency()` does the same from a matrix of non-significant pairs. Both return a `cld_reduction` object with `print()` and `as.data.frame()` methods.
- The example data sets are `piepho2004_wheat`, `simple_abc_pairs`, and `simple_abc_means`.
- R turns HiGHS presolve off, because the highs package bundles HiGHS 1.14.

## JavaScript package

- New npm package `cld-reducer` in `js/`, built on HiGHS compiled to WebAssembly: `reduceLetters()`, `reduceFromAdjacency()`, `loadSolver()`, and the error classes `CldReducerError`, `InvalidInputError`, and `SolverError`. Group means must be a `Map` or an array of `{ group, mean }`; a plain object is rejected.

## Python package

- Preserve exact CSV labels, including leading zeros, NA-like text, and empty strings.
- Preserve mixed numeric labels in lists of pair rows and means mappings.
- Use one means-column rule for group order and values.
- Report uneven adjacency rows as `InvalidInputError` with the square-matrix message.

- The package moved to `python/`. The import name `cld_reducer`, the public names, the exceptions, and the `cld-reduce` command with its flags are unchanged. Installing from a git URL now needs `#subdirectory=python`:
  `pip install "git+https://github.com/aigorahub/cld-reducer.git#subdirectory=python"`.
- The solver is HiGHS through `highspy`. The dependencies are `highspy`, `numpy`, and `pandas`; `scipy` and `networkx` are gone.
- **Canonical tie-break.** Many inputs have several displays with the same, smallest number of assignments (the Piepho 2004 wheat example has 64). The package now returns one fixed display: among all minimal displays, the one whose membership vector is lexicographically greatest in the order of the specification. The result no longer depends on which optimum the solver finds first, so R, Python, and JavaScript agree. For inputs with several minimal displays this can differ from version 0.1.0.
- **Canonical clique order.** Maximal cliques are now ordered by their sorted group indices, where 0.1.0 used the order of NetworkX. This order breaks ties between letters, so the letters can be renamed even for inputs that have only one minimal display. Example: five groups numbered 0 to 4, no means, and non-significant pairs 01, 02, 03, 04, 14, 24 have one minimal display; group 3 had `A` in 0.1.0 and has `C` now.
- `stats["reduction_pct"]` is not rounded any more; print it with the format you need. The example scripts print one decimal.
- `stats["solver_status"]` is the text `Optimal`, and `stats["objective"]` is a whole number.
- `time_limit` is one time budget for all solves of a call. Each solve gets the time that is left.
- Group means must be finite numbers; a missing, infinite, or non-numeric mean is an `InvalidInputError`.
- A missing group label (`None`, `NaN`, `pd.NA`, or `pd.NaT`) is an `InvalidInputError`, in the comparisons, the groups, and the means.
- Means with a repeated group label are an `InvalidInputError` for `reduce_from_adjacency()` too.
- Significance text is trimmed of spaces, tabs, carriage returns, and line feeds only. Other white space, such as a no-break space, makes the value invalid.
- An empty list of comparisons is a table with zero rows, so the groups come from the means.
- A solver value that is not within 1e-6 of 0 or 1 is a `SolverError`, also when the value is a whole number.

## Release preparation

- Check installed Python wheels, wheels rebuilt from source distributions, and npm TypeScript consumers outside the checkout.
- Require manual tag-based publication with dry runs, version checks, artifact hashes, and separate npm/PyPI jobs.
- Record data reuse conditions and Python publication history as open release requirements.
