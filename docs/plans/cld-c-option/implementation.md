# CLD-C implementation

Base: `315d634e7a56a8dc5315fd6c2b91acd970316465` on `plan/cld-c-option`.
Approved plan SHA-256: `f4ac34435200fdce3da0c2885c4eb5c5e00362d7418b9421455810c81edb16bc`.

## Delivered behavior

Each language has one input pipeline, graph context, binary model boundary,
canonical solver, solver adapter, display renderer and result checks. A two-entry
registry selects each mathematical builder, coverage check and column decoder.
CLD-sigma remains the default. CLD-C selects full maximal cliques and minimizes
only their count. Both aliases normalize public result metadata.

Explicit ordered decision indices define objective support, caps and tie fixing;
sigma auxiliaries are excluded. Initial objectives must be finite before rounding.
Later feasible decision counts use the stored integer optimum. One deadline spans
all solves; infeasible trials skip numeric checks, while infeasible initial solves
fail. Adapters retain ambiguous status text while mapping to infeasible.

The historical Python helper still always runs sigma, validates its result, and
then stores the caller's supplied metadata unchanged. Public signatures and result
shapes are preserved. R keeps presolve off. Assignment statistics retain their
meaning under both methods.

Independent standard-library C searches compare all 33,867 labeled graphs with
one to six groups, filtering vertex subsets to maximal cliques before searching
covers. The generator manages 1,442 C records and matching checker negatives.
The three planning witnesses are embedded in the repository generator and fixtures;
no runtime or test depends on external planning files. Their sigma and C results
are independently generated and checked by all three existing runners.

The existing sigma fixture is byte-identical, SHA-256
`1e06d3fbdabc5c501fb14d1929028430da72640bb3aa1bffcc5b6067f3f59b37`.
Package versions are 0.3.0; the lock format, historical release-test tags and fake
registry versions are unchanged. Candidate citation release date is omitted.
The v0.2.0 tag and frozen CRAN submission files were not modified.

## Local validation

- Sigma refactor before adding C: Python 3,023 tests, JavaScript 88 tests, R 310
  assertions passed, preserving the existing fixtures and failures.
- Full Python suite after C: 5,938 tests passed on Python 3.13 and on Python
  3.10 with minimum dependencies (NumPy 1.24.4, pandas 2.0.3, highspy 1.15.1),
  including presolve on/off;
  ruff lint/format and all five release tests passed.
- JavaScript: typecheck/build passed, 108 unit tests passed on Node 22.23.3,
  24.21.0 and 26.3.0; all 2,864 reduction
  fixtures passed with presolve on and off, plus errors and labels.
- R: 348 assertions passed; all 2,864 reduction fixtures, 65 errors, 18 label
  cases and three dataset comparisons passed.
- Generator `--check` and all 26 independent reference tests passed, including
  sigma and C exhaustive censuses and the witness comparisons.
- Python wheel and source distribution built and passed Twine checks. Separate
  clean installs of the wheel and a wheel rebuilt from the source distribution
  passed API, both C CLI spellings, exact labels, sigma helper compatibility,
  simple and wheat examples.
- Clean npm tarball install passed WASM execution for both methods and compiled
  the installed TypeScript consumer, including unrestricted `method?: string`.
- R 4.6.1 archive contents and `R CMD check --as-cran --timings` passed with
  PDF and HTML manuals: zero errors, zero warnings, one new-submission NOTE.
  The installed TinyTeX directory must be included in PATH for the PDF check.

## Remaining required evidence

Mandatory seated Grok and Agy implementation reviews and the remote CI matrix are
pending. The implementation environment lacks `HERDR_ENV=1`; the Herdr skill
forbids inspecting or controlling seated agents from outside a managed pane.
Reviews must use the exact feature head, the absolute worktree and approved plan,
with Agy in plan mode and `/boost` before every review, and must wait for children.
Plan reviews do not establish implementation correctness. No merge or publication
is authorized by this implementation.
