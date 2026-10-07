# Plan: R and JavaScript packages for cld-reducer, structured like turfLP

Plan version: 2 (2026-10-07), after Astra plan review round 1 (six findings, all fixed; see the
execution log). Driver: cld-driver (Claude Code, claude-opus-5-5, xhigh).
Branch: `feat/r-js-packages`. Worktree: `C:\Claude\cld-reducer-r-js-packages`.
Base: `origin/main` at `eb95fe9ad5e983a1f2e6e02668c3419647b9571e`.

## Mission

Restructure `aigorahub/cld-reducer` like `aigorahub/turfLP`: an R package at the repository
root, a JavaScript/TypeScript package in `js/`, the existing Python package in `python/`, one
normative specification, and one shared conformance suite. All three languages solve the
assignment-minimum CLD reduction with HiGHS and return the same reduced letter display for the
same input. The run ends at a green, reviewed, draft PR that is ready for a CRAN submission of
the R package and an npm publish of the JavaScript package. Nothing is merged, tagged, released,
submitted, or published by this run.

## Source request

John Ennis, #core-team Slack, 2026-10-07 11:15 ET:

> take the repo cld-reducer and structure it like turfLP so that it covers R and JavaScript.
> That might mean switching the solver to the one turfLP uses. The goal is to get it submitted to
> CRAN and npm for R and javascript. The turfLP repo is an almost perfect example of a repo that
> is set up for supporting R, python, and JavaScript for a linear programming problems and it
> uses HIGHs as the solver for all three, I believe, so make sure the agent works in cld-reducer
> (which is the one it will change) and turfLP, which it will use as a template. Before you
> start, plan very carefully with robust review then do it as an elves run.

Team rule from John (2026-10-02): no pushes to `main`. Work on a feature branch in a registered
Elves worktree.

## Evidence gathered on 2026-10-07

Each fact below was checked today in the repositories or registries. It is not from memory.

- **turfLP solver, R.** `DESCRIPTION` imports `highs (>= 1.14.0)` and `Matrix`.
  `R/turf.R` `solve_lp()` calls `highs::highs_solve()` with `highs::highs_control(presolve =
  "off", mip_rel_gap = 0, mip_abs_gap = 0, primal_feasibility_tolerance = 1e-9,
  mip_feasibility_tolerance = 1e-9, time_limit = ...)`. The comment says HiGHS 1.14 presolve gave
  a wrong optimum on a 7 by 4 matrix. CRAN `highs` is version 1.14.0-2 (GPL >= 2, Depends R >=
  4.0.0). Its `highs_control()` defaults to `threads = 1L`.
- **turfLP solver, Python.** `python/pyproject.toml` depends on `highspy>=1.15.1,<1.16`.
  `python/src/turflp/_solver.py` uses `highspy.Highs` with presolve "on", gaps 0, feasibility
  tolerances 1e-9, `threads = 1`. PyPI `highspy` latest is 1.15.1 (requires Python >= 3.9).
- **turfLP solver, JavaScript.** `js/package.json` depends on `highs >=1.15.3 <1.16.0` (HiGHS
  compiled to WebAssembly, `lovasoa/highs-js`, MIT). npm `highs` latest is 1.15.3.
  `js/src/solver.ts` uses the same options without threads (the WASM build is single thread) and
  has a loader workaround for `wasmBinary`/`wasmModule`.
- **turfLP conformance.** Expected values come from exact enumeration in a standard-library
  Python generator, never from a solver. turfLP compares objective values only, because its
  three languages can return different tied optima.
- **cld-reducer today.** Python only. `scipy.optimize.milp` (scipy's bundled HiGHS) solves the
  MILP. `networkx.find_cliques` enumerates maximal cliques. Dependencies: networkx, numpy,
  pandas, scipy. Version 0.1.0, not on PyPI. 25 tests. One workflow (`ci.yml`).
- **Ties are real.** A standard-library count (driver scratch script) shows that the Piepho
  (2004) wheat example has 4 maximal cliques, 56 assignments in the maximal covering, a minimum of
  44, and **64 different assignment-minimum coverings**. The simple ABC example has one optimum.
  Without a fixed tie-break rule, R, Python, and JavaScript can print different wheat displays.
- **Names.** npm: `cld-reducer`, `cldreducer`, `cld_reducer`, and `@aigorahub/cld-reducer` all
  return 404 (free). PyPI: `cld-reducer` returns 404 (free). CRAN: no package named
  `cldreducer` in any letter case (checked against the CRAN `PACKAGES` index).
- **Issues and PRs.** Both repositories: no open issues, no open PRs. cld-reducer history: PR #1
  (input hardening) and PR #2 (2012 citation, wheat example), both merged. turfLP history: PRs
  #1, #2, #6 to #10 merged, #4 and #5 (Dependabot) closed, issue #3 closed by PR #6. Lessons
  taken: HiGHS 1.14 presolve risk (PR #1); check every solver result (issue #3); npm trusted
  publishing needs a first manual publish (PR #9); keep CRAN examples short (PR #10).
- **Branch rules on cld-reducer `main`.** PRs required, 0 approvals, conversation resolution
  required, admins enforced, no required status checks.
- **Local machine.** Windows 11, Node 24.18.0, npm 11.16.0, Python 3.13.14 (no scipy, highspy,
  or uv installed), no R. WSL Ubuntu runs, with python3 and git only.

## Decisions

The driver made these decisions. Items marked **Mason confirms** change public names or
results, so Mason confirms them when he approves the plan.

- **D1. R package name `cldreducer`** (Mason confirms). R names cannot contain `-` or `_`.
  Lower case avoids a case conflict check on CRAN. CRAN names are permanent.
- **D2. npm package name `cld-reducer`** (Mason confirms). Same as the PyPI name and the
  repository. Unscoped, like `turflp`.
- **D3. One version, 0.2.0, for all three packages.** turfLP publishes npm and PyPI from one
  GitHub release with tag `v<version>`, and each publish workflow checks the tag against its
  package version. One version keeps one tag valid. Python moves from 0.1.0 to 0.2.0 because its
  solver, dependencies, and tie results change.
- **D4. Canonical tie-break** (Mason confirms). Among all assignment-minimum coverings, return
  the one whose membership vector, read in canonical order, is lexicographically greatest: in
  that order, keep each membership whenever an optimal covering that agrees with all earlier
  choices keeps it. The spec in B1 pins the order.
  This changes Python output in two ways. (1) Inputs with several optima can get a different
  optimal covering. (2) Inputs with one optimal covering can get **different letter names**:
  the canonical clique order (sorted group indices) replaces the NetworkX enumeration order,
  and that order breaks ties in the letter sort key. Example (Astra, review round 1): groups
  0 to 4, no means, non-significant pairs 01, 02, 03, 04, 14, 24. Every membership is forced,
  so the optimum is unique, but NetworkX 3.7 orders the cliques {0,3}, {0,1,4}, {0,2,4} and
  the canonical order is {0,1,4}, {0,2,4}, {0,3}; group 3 changes from `A` to `C`. The simple ABC
  result does not change. turfLP did not need this rule, because it compares objective values
  only.
- **D5. Python moves to `highspy` directly** and drops `scipy` and `networkx`. Same HiGHS
  family and options as JavaScript, explicit control of presolve, threads, and tolerances, and
  the same clique code in all three languages. New Python dependencies: `highspy>=1.15.1,<1.16`,
  `numpy>=1.24`, `pandas>=2.0`.
- **D6. `stats["reduction_pct"]` becomes the unrounded value** `(before - after) / before * 100`
  in all three languages. These IEEE operations give the same double in Python, R, and
  JavaScript. Language rounding functions differ at ties, so rounding moves to print methods.
- **D7. Presolve.** Python and JavaScript use presolve "on" and their conformance runs repeat
  with presolve "off". R uses presolve "off", like turfLP, because the CRAN `highs` package
  bundles HiGHS 1.14.
- **D8. Node.js `>=22`.** Node 20 reached end of life in April 2026. CI tests Node 22 and 24.
  (turfLP still says `>=20`.)
- **D9. Python keeps `requires-python >=3.10`.** CI tests 3.10 and 3.13, like turfLP.
- **D10. Canonical data in `conformance/data/`.** The two example data sets move there (with
  history). Python examples keep identical copies (same git blob), and `generate.py --check`
  fails when a copy differs. R data sets are built from them.
- **D11. Out of turfLP's layout on purpose:** no browser dashboard and no Next.js example. They
  are not needed for CRAN or npm. No `export_r.R`: every conformance input comes from the
  Python generator, so no input needs R.

## Target layout

| Path after the change | turfLP counterpart | Contents |
|---|---|---|
| `DESCRIPTION`, `NAMESPACE`, `R/`, `man/`, `tests/testthat/`, `data/`, `data-raw/`, `inst/` | same | R package `cldreducer` at the root |
| `LICENSE` (2 lines), `LICENSE.md` (full MIT text) | same | `MIT + file LICENSE` |
| `NEWS.md`, `cran-comments.md`, `.Rbuildignore`, `cldreducer.Rproj` | same | R release files |
| `python/` (`pyproject.toml`, `uv.lock`, `README.md`, `LICENSE`, `src/cld_reducer/`, `tests/`, `examples/`) | `python/` | Existing Python package, moved with `git mv` |
| `js/` (`package.json`, `package-lock.json`, `tsconfig*.json`, `vitest.config.ts`, `src/`, `test/`, `scripts/conformance.mjs`, `README.md`, `LICENSE`) | `js/` | npm package `cld-reducer` |
| `conformance/` (`README.md`, `data/`, `inputs/`, `manifest.json`, `generate.py`, `test_generate.py`, `fixtures/`, `run_r.R`) | `conformance/` | Shared suite |
| `docs/algorithm.md` | same | Normative specification |
| `.github/workflows/{R-CMD-check,conformance-r,python,js,publish-npm,publish-python}.yaml` | same names | CI and publishing |
| `README.md`, `CITATION.cff` | `README.md` | Root overview, citation metadata |

The R package stays at the root, as in turfLP, so `remotes::install_github("aigorahub/cld-reducer")`
and the r-lib actions work without a subdirectory.

The Python package keeps its distribution name `cld-reducer`, import name `cld_reducer`, public
API (`reduce_letters`, `reduce_from_adjacency`, `CLDReductionResult`, `CLDReducerError`,
`InvalidInputError`, `SolverError`), CLI `cld-reduce` with all current flags, and all 25 current
tests. The tests move to `python/tests/` and run from `python/`. Example scripts move to
`python/examples/` and read their CSV copies there. One user-facing change: installing from a git
URL needs `#subdirectory=python`. NEWS.md and the README say so.

## Specification content (written in B1 as `docs/algorithm.md`)

The spec is normative. Every implementation and the generator follow it. It must pin at least:

1. **Pairwise input.** Columns `group1`, `group2`, `significant` (names configurable). Labels
   become strings. Significance accepts booleans, the numbers 0 and 1 (Python: `int` or NumPy
   integer, as today; R and JavaScript: a number equal to 0 or 1), and the trimmed, case
   insensitive strings `true t yes y 1 significant` and `false f no n 0 not significant ns`.
   Self comparisons, duplicate unordered pairs, missing pairs, and unknown groups are errors.
   Group order is the means order when means are given; otherwise it is the order of first
   appearance in the `group1` column followed by the `group2` column (current Python rule).
   Means must be finite numbers for every group (new check in all three).
2. **Adjacency input.** Square, symmetric, diagonal true, values boolean or 0/1, no missing
   values. Default groups are `"1"` to `"n"`.
3. **Maximal cliques.** The set of all maximal cliques of the non-significance graph. Canonical
   order: each clique as its ascending group indices, cliques sorted lexicographically. If the
   count exceeds `max_cliques`, raise the solver error (current text). The enumeration method is
   free; the order after sorting is not.
4. **Model.** Binary `x[g,c]` for each membership of the maximal covering, binary `y[e,c]` for
   each non-significant edge and each clique that holds both ends. Minimize the sum of `x`. Each
   group has at least one `x`; each edge has at least one `y`; `y[e,c] <= x[i,c]` and
   `y[e,c] <= x[j,c]`.
5. **Canonical solve.** Solve once for the minimum `z`. Then visit the `x` variables in
   (clique, group) order. If the current solution has the variable at 1, fix it to 1. If it has
   it at 0, solve again with the fixings so far, this variable fixed to 1, and `sum(x) <= z`: if
   feasible, take the new solution and fix the variable to 1; if infeasible, fix it to 0. Any
   other solver status is an error. The result is the lexicographically greatest optimal
   membership vector. It does not depend on which optimum a solver returns first.
6. **Solver settings and checks.** Gaps 0, feasibility tolerances 1e-9, logging off, one
   thread. `time_limit` is one budget for all solves in a call; each solve gets the time left.
   Presolve per D7. After each solve: status must be optimal (or infeasible where step 5 allows
   it), every `x` within 1e-6 of 0 or 1, and the rounded solution must respect the fixings,
   cover every group and every edge, and have `sum(x)` equal to the rounded objective on the
   first solve and equal to `z` on every later solve. Otherwise raise
   "HiGHS returned an invalid solution" (solver error). A non optimal, non infeasible status
   raises "assignment-minimum MILP failed: " followed by the HiGHS status text (current prefix).
7. **Letters.** Drop empty columns. Sort columns stably over the canonical clique order by
   (minus the highest member mean, lowest member index) with means, or (lowest member index)
   without. Labels A to Z, then AA, AB, and so on. A group's display joins its tokens with no
   separator when every token is one character, otherwise with single spaces.
8. **Check.** Rebuild the relationships from the letters. Any difference raises the current
   solver error text.
9. **Result and stats.** `letters`, `assignments`, `groups`, `method` ("assignment_minimum"),
   `relationship_preserved`, `adjacency`, and stats `assignments_before`, `assignments_after`,
   `reduction_pct` (D6), `num_letters_before`, `num_letters_after`, `num_groups`, `num_edges`,
   `solver_status` ("Optimal"), `objective` (equal to `assignments_after`).
10. **Errors.** Two kinds in every language: invalid input and solver. The stable message
    prefixes are the current Python texts. Language specific parts (list and value formatting)
    come after the prefix.
11. **Public API** for R, Python, and TypeScript (below), and the differences between them.

## R package design

- **Exports:** `reduce_letters(pairs, means = NULL, group1 = "group1", group2 = "group2",
  significant = "significant", method = "assignment_minimum", time_limit = NULL,
  max_cliques = 10000L)` and `reduce_from_adjacency(adjacency, groups = NULL, means = NULL,
  method = "assignment_minimum", time_limit = NULL, max_cliques = 10000L)`. `max_cliques = NULL`
  removes the cap. Means: named numeric vector (names give the order) or a data frame with
  `group` and `mean` columns (else the first two columns).
- **Return value:** class `cld_reduction` (a list with `letters` named character vector,
  `assignments` named list, `stats` list, `method`, `groups`, `relationship_preserved`,
  `adjacency` logical matrix). S3 methods `print()` (rounds `reduction_pct` to one decimal for
  display) and `as.data.frame()` (columns `group`, `letters`, `assignments`, like Python
  `to_frame()`).
- **Conditions:** classes `cldreducer_invalid_input` and `cldreducer_solver_error`, both with
  `cldreducer_error`, `error`, `condition`.
- **Dependencies:** Depends `R (>= 4.0.0)` (the floor of `highs`). Imports `highs (>= 1.14.0)`,
  `Matrix`. Suggests `testthat (>= 3.0.0)`. No compiled code.
- **Data:** `piepho2004_wheat` (190 rows), `simple_abc_pairs` (10 rows), `simple_abc_means`
  (5 rows), built by `data-raw/datasets.R` from `conformance/data/`, saved as `data/*.rda`,
  `LazyData: true`, each documented with its source (Piepho 2004, Ennis, Fayle, and Ennis 2012
  Table 7). The CSV files are not in the R package, so the proof that each data set equals its
  CSV runs in `conformance/run_r.R` and in the generated-files CI job, not in testthat.
- **Docs:** roxygen2 with markdown, like turfLP (`Config/roxygen2/version` pinned). A package
  help page, one page per function and data set, runnable examples. `inst/CITATION` with the
  package manual entry and the 2012 article (doi:10.1145/2133803.2275596). `inst/WORDLIST` for
  the spelling check.
- **DESCRIPTION text:** Title in title case, no "R" or "package" in it. Description cites
  Ennis, Fayle, and Ennis (2012) <doi:10.1145/2133803.2275596> and Piepho (2004) with a DOI that
  B5 verifies by resolving it. Software names in single quotes ('HiGHS'). URL and BugReports.
- **Authors@R:** John Ennis (aut, cre, email from H2), Carl Graham, Luciana Castro, Rachel
  Lampert, Ryan Jordan, Vanessa Rios de Souza (aut), Aigora (cph, fnd). Mason confirms (H3).
- **Tests:** testthat edition 3, using only what the installed package contains (its functions,
  its data sets, and literal expected values in the test files). No test reads `conformance/`,
  a CSV, or any path outside the package. Coverage: input checks and messages, clique order,
  the simple ABC display, the wheat result (56 before, 44 after, 4 letters, and the canonical
  display as a literal copied from the wheat fixture, with a comment naming the fixture id),
  the D4 renaming example, labels beyond Z, solver failure paths (through a replaceable solve
  hook, like turfLP), and the shape of the data sets. `conformance/run_r.R` holds every check
  that needs repository files. All tests together under 60 s on CI.
- **Examples:** each under 2 s on CI (R CMD check `--timings`). The wheat example is small.
- **CRAN files:** `cran-comments.md` (new submission, test environments, results per
  environment), `NEWS.md` (0.2.0 entry), `.Rbuildignore` covering `^python$`, `^js$`,
  `^conformance$`, `^docs$`, `^data-raw$`, `^\.github$`, `^README\.md$`, `^LICENSE\.md$`,
  `^cran-comments\.md$`, `^CITATION\.cff$`, `^.*\.Rproj$`, `^\.Rproj\.user$`, `^\.git$`,
  `^\.elves$`, `^\.elves-session\.json$`, and nothing the package needs.

## JavaScript package design

- **Name and format:** `cld-reducer` 0.2.0, ESM, TypeScript declarations, `exports` "." with
  `types` and `import`, `files` = `dist`, `LICENSE`, `README.md`, `sideEffects: false`,
  `engines.node >=22`. Dependency `highs >=1.15.3 <1.16.0`. Dev dependencies TypeScript,
  Vitest, `@types/node`. `prepack` builds.
- **API:** `reduceLetters(pairs, options?)` and `reduceFromAdjacency(adjacency, options?)`, both
  `Promise<CldReduction>`. Options: `means` (a `Map<string, number>` or an array of
  `{ group, mean }`; a plain object is rejected with `InvalidInputError`, because JavaScript
  orders integer-like object keys first and group order decides ties), `group1`, `group2`,
  `significant`, `method`, `timeLimit` (seconds), `maxCliques` (`null` removes the cap), and
  `groups` for adjacency input. `loadSolver(options?)` with `locateFile`, `wasmBinary`,
  `wasmModule`, copied from turfLP's loader pattern including its `instantiateWasm` workaround.
  Error classes `CldReducerError`, `InvalidInputError`, `SolverError`.
- **Result:** `{ letters: Record<string, string>, assignments: Record<string, string[]>,
  groups: string[], rows: { group, letters, assignments }[]` (in `rows`, `assignments` is the
  tokens joined by spaces, like Python `to_frame()`), `stats: { assignmentsBefore,
  assignmentsAfter, reductionPct, numLettersBefore, numLettersAfter, numGroups, numEdges,
  solverStatus, objective }, method, relationshipPreserved, adjacency: boolean[][] }`. `groups`
  and `rows` carry the order.
- **Build and tests:** `tsc` build to `dist/`, `vitest` unit tests (inputs, cliques, labels,
  solver settings read back from HiGHS, failure paths through a hook, loading with
  `wasmBinary` and `wasmModule`, every model disposed), `scripts/conformance.mjs` against the
  built package with presolve on and off.
- **Package contents:** `npm pack --dry-run --json` lists only `package.json`, `README.md`,
  `LICENSE`, and `dist/**`. A clean install of the packed tarball in a temporary folder runs the
  README example.
- **README:** install, usage, API, blocking solve (use a worker for large inputs), browser
  loading with `locateFile` or `wasmBinary`, differences from R and Python.
- **Publish workflow:** `publish-npm.yaml` like turfLP: on release published or manual
  dispatch, environment `npm`, `id-token: write`, Node 24, latest npm, tag equals
  `v<version>`, `npm ci`, `npm publish --access public`. No token in the repository.

## Python package changes

- B1 moves files only. B3 changes the solver per D4 to D6 and the spec.
- `python/pyproject.toml`: version 0.2.0, new dependencies (D5), `license-files`, sdist
  includes, `[project.urls]` Source to `tree/main/python`, ruff and pytest settings kept.
  `python/uv.lock` created with `uv lock`, like turfLP.
- New modules stay small: cliques, model and solve, labels. Public names do not change.
- New tests: `test_conformance.py` (all fixtures, presolve on and off), `test_solver.py`
  (settings read back, failure paths, time budget across solves), `test_cliques.py`.

## Conformance suite design

- `conformance/generate.py`: standard library only, no import of any package code. It builds
  the inputs (hand cases, every labeled graph with 1 to 5 groups, seeded random graphs with 6 to
  12 groups from a seeded generator such as splitmix64, structured cases like sorted means with
  a significance threshold, the two example data sets), writes `inputs/*.json`,
  `manifest.json` (SHA-256 of each input, origin, counts, exclusions with reasons), and
  `fixtures/*.json`. `--check` regenerates in memory and fails on any difference. `--write`
  writes.
- Expected values come from exact search, not from a solver: its own maximal clique code, a
  depth first search for the minimum, and a second search that returns the lexicographically
  greatest optimal vector by the spec order.
- `conformance/test_generate.py`: hand-checked tests, and a cross check of the search against
  plain enumeration of all optional memberships on every graph with up to 6 groups. One test
  pins the 64 optimal wheat coverings and the canonical one.
- Fixture kinds: `reduce.json` (graph input, call route `pairs` or `adjacency`, options, and
  expected groups, assignments, letters, integer stats, `solver_status`, `objective`, and the
  `reduction_pct` numerator and denominator), `errors.json` (input, expected kind and message
  prefix), `labels.json` (count to labels, including after Z).
- **Pass rule:** exact equality of group order, assignments, letters, integer stats,
  `solver_status`, `objective`; `reduction_pct` equals `(before - after) / before * 100` from the
  fixture integers; errors match kind and message prefix. Each runner first proves its checker
  rejects a display that loses a relationship, a valid but non canonical wheat optimum, and a
  non minimal display. The wheat fixture carries one non canonical optimum, and the generator
  writes the other two bad results, for this self check.
- Runners: `python/tests/test_conformance.py`, `js/scripts/conformance.mjs`,
  `conformance/run_r.R`. CI runs all three on every push.

## CI workflows

| Workflow | Jobs | Trigger |
|---|---|---|
| `python.yaml` (replaces `ci.yml`) | test: ubuntu, macos, windows x Python 3.10, 3.13 with `uv sync --locked --extra dev` (the `dev` extra holds pytest, ruff, and build; plain `uv sync` installs no extras), then `uv run --locked ruff check .`, `uv run --locked ruff format --check .`, `uv run --locked pytest`, and both example scripts; minimum: `uv venv --python 3.10`, `uv pip install -e ".[dev]" "highspy==1.15.1" "numpy==1.24.*" "pandas==2.0.*"`, `uv run --no-sync pytest`; package: `uv build`, wheel into a clean venv without the `dev` extra, CLI on the ABC example | push, pull_request |
| `js.yaml` | test: ubuntu, macos, windows x Node 22, 24: `npm ci`, typecheck, build, test, `test:conformance`; pack: tarball contents check and clean install smoke test | push, pull_request |
| `R-CMD-check.yaml` | R-CMD-check: macOS release, Windows release, Ubuntu devel, release, oldrel-1; as-cran: Ubuntu release, `--as-cran` with the PDF manual (TinyTeX), `error-on: "warning"`, `check-dir` under `runner.temp` (B5-A7); generated-files: see "Generated-files job" below | push to main, pull_request |
| `conformance-r.yaml` | `generate.py --check`, `test_generate.py` (from B2), `Rscript conformance/run_r.R` (from B5) | push, pull_request |
| `publish-npm.yaml` | as in the JavaScript design | release published, manual |
| `publish-python.yaml` | turfLP's workflow adapted to `python/` (PyPI trusted publishing, environment `pypi`) | release published, manual |

**Generated-files job** (in `R-CMD-check.yaml`, Ubuntu, R release). It generates, publishes,
then checks, in this order:

1. Install dependencies, with roxygen2 pinned to the version recorded in DESCRIPTION
   (`Config/roxygen2/version`), so a newer roxygen2 alone cannot cause drift.
2. Save the committed data sets: copy `data/*.rda` from `HEAD` to a temporary folder (a missing
   file is recorded as missing).
3. Run `Rscript data-raw/datasets.R` (writes `data/*.rda` from `conformance/data/*.csv`), then
   `Rscript -e 'roxygen2::roxygenise()'` (writes `man/` and `NAMESPACE`).
4. Upload `man/`, `NAMESPACE`, and `data/` as the artifact `generated-files` with
   `if: always()`, so the artifact exists even when a later step fails.
5. Documentation drift: fail when `git status --porcelain -- man NAMESPACE` prints anything.
   This catches changed and deleted tracked files and new untracked files (for example the
   help page of a new export), which `git diff --exit-code` misses.
6. Data drift: `Rscript data-raw/check-datasets.R <saved folder>` loads each regenerated data set
   and the saved committed copy and fails when a committed copy is missing or when
   `identical()` is false. Content is compared, not bytes, because `.rda` bytes can change
   between R versions.

In Option B the first R push has no `man/` or `data/*.rda`, so this job fails at step 5 or 6
and leaves the `generated-files` artifact; the worker downloads it with `gh run download`,
commits the files, and the next run passes.

Action versions follow turfLP (`actions/checkout@v6`, `actions/setup-node@v7`,
`actions/setup-python@v7`, `astral-sh/setup-uv@v10.2.0`, `r-lib/actions/*@v2`,
`actions/upload-artifact@v7`, `pypa/gh-action-pypi-publish@v1.14.2`). Every workflow sets
`permissions: read-all`; only the publish jobs add `id-token: write`.

## How the R checks run

R is not installed on this machine. Two options. Mason picks one (H11). **If Mason does not
choose, Option B applies.**

- **Option A: local R plus CI.** Mason approves a local install for the worker: the current R
  release (4.6.x) for the execution host and CRAN binary packages `highs`, `testthat`,
  `roxygen2` (the pinned version), `jsonlite`, `pkgload`, `rcmdcheck`. On Windows no Rtools is
  needed, because all are binaries. The worker runs roxygen, `data-raw/datasets.R`, testthat,
  `conformance/run_r.R`, and `R CMD build`, then copies the tarball into an empty temporary
  folder outside the checkout and runs `R CMD check --as-cran --no-manual` there. CI remains
  the gate. (Route dependent: the host is Windows for routes (b) and (c), Linux for route (a).)
- **Option B (default): CI only.** No local R install. The worker pushes R changes and reads CI
  logs (`gh run list --branch feat/r-js-packages`, `gh run view <id> --log-failed`). The
  generated-files job produces `man/`, `NAMESPACE`, and `data/*.rda`; the worker downloads
  them with `gh run download` and commits them. Slower: each R fix costs one CI round (about 5
  to 10 minutes).

In both options the PDF manual check runs only in the CI as-cran job, and R conformance runs
in `conformance-r.yaml`. Before the CRAN submission, a human runs win-builder (R-devel and
R-release); the results go to the maintainer email (H4). The run does not do this.

## Scope

### In scope

- Move the Python package to `python/` with history, switch it to `highspy` with the canonical
  tie-break, and keep its API, CLI, examples, and tests working.
- New R package `cldreducer` at the root, ready for `R CMD check --as-cran`.
- New npm package `cld-reducer` in `js/`, ready for `npm publish`.
- `docs/algorithm.md`, `conformance/`, the six workflows, root and per-language READMEs,
  `NEWS.md`, `CITATION.cff`, `inst/CITATION`, `cran-comments.md`, version 0.2.0 everywhere.

### Out of scope

- Any change in `C:\Claude\turfLP` or `aigorahub/turfLP` (read only template).
- Merge, tag, GitHub release, CRAN or win-builder submission, npm or PyPI publish, npm or PyPI
  trusted publisher setup, GitHub environment creation, repository description changes.
- New algorithms (only `assignment_minimum`), a browser dashboard, a Next.js example, vignettes,
  a pkgdown site, Python `datasets` module.
- Changes to the published citation facts (authors, DOIs, talk details), other than the version
  and release date fields.

## Batches

Commit subjects use `[feat/r-js-packages · Batch N/6 · Contract|Implement|Validate|Review|Close]
<concrete outcome>`. Each batch has exactly one `Close` commit with a Confidence trailer in the
format of the Elves skill. No AI attribution lines in commits or PR text.

### Batch 1 [B1]: Layout move and specification

**Coordinator-to-implementer handoff:**

- **Intent / why:** Give the repository turfLP's shape before any new code, and write the spec
  that all three languages and the generator follow.
- **Non-obvious rationale:** Move with `git mv` so `git log --follow` keeps history. Keep the
  Python solver code unchanged in this batch, so the move alone is proven by the 25 current
  tests. The spec must pin every rule in "Specification content", because R and JavaScript are
  written from it, not from Python code.
- **Build On targets:** turfLP `docs/algorithm.md` (structure and tone), turfLP `.gitignore`,
  current `src/cld_reducer/*` (current rules and error texts), current `ci.yml`.
- **Owned surfaces:** `python/**` (moved files), `conformance/data/*.csv`, `docs/algorithm.md`,
  `LICENSE`, `LICENSE.md`, `.gitignore`, `.github/workflows/python.yaml` (renamed from `ci.yml`).
- **Forbidden surfaces:** turfLP, `.git` internals, run docs owned by the driver
  (`docs/elves/*`, `docs/plans/**`, `.elves-session.json`), other worktrees, `main`.
- **Acceptance evidence:** the commands named in the criteria, with output in the progress
  ledger and the Close commit body.
- **Failure modes / pitfalls:** hatch paths are relative to `python/`; pytest must run from
  `python/`; the CLI test calls `python -m cld_reducer.cli` and needs the editable install. On
  this Windows machine (routes (b) and (c); route dependent), `core.autocrlf=true`, so working tree text files are CRLF while git stores LF:
  compare copies by git blob id, not by working tree bytes, and check that `git diff --stat -M`
  shows renames, not rewrites.
- **HEAD / paths / output:** start at the staging commit on `feat/r-js-packages`; plan
  `docs/plans/r-js-packages/plan.md`; report per Elves worker packet.

**Tasks:**

- [ ] `git mv` `pyproject.toml`, `src/`, `tests/`, `examples/*.py` into `python/`; `git mv`
  the three example CSV files into `conformance/data/`; copy them byte for byte into
  `python/examples/`.
- [ ] `git mv LICENSE LICENSE.md`; new `LICENSE` with `YEAR: 2026` and
  `COPYRIGHT HOLDER: Aigora`; `python/LICENSE` copy of the full text.
- [ ] Short `python/README.md`; fix paths in `python/pyproject.toml`.
- [ ] Rename `ci.yml` to `python.yaml` and set `working-directory: python`.
- [ ] Merge turfLP's `.gitignore` entries for R and JavaScript into `.gitignore`.
- [ ] Write `docs/algorithm.md`.

**Acceptance criteria:**

- [ ] B1-A1: `git log --follow --oneline python/src/cld_reducer/api.py` lists commit `f877505`, and `git log --follow --oneline conformance/data/piepho2004_wheat_pairs.csv` lists commit `ce9c54e`.
- [ ] B1-A2: In `python/`, after `pip install -e ".[dev]"`, `ruff check .`, `ruff format --check .`, and `pytest` pass, with the same 25 tests as `main` passing and no test file changed.
- [ ] B1-A3: `python python/examples/simple_abc_to_ac.py` prints group 3 with letters `AC`, and `python python/examples/piepho2004_wheat.py` prints 56 assignments before and 44 after.
- [ ] B1-A4: `docs/algorithm.md` covers all 11 items of the plan section "Specification content", including the canonical tie-break order and procedure, the stable error message prefixes, and the API of all three languages.
- [ ] B1-A5: The repository root has no `pyproject.toml`, `src/`, `tests/`, or `examples/`, and `git ls-files -s` shows the same blob id for each of the three CSV files in `python/examples/` and in `conformance/data/`.

**Docs likely touched:** `python/README.md`, `docs/algorithm.md`.
**Risk:** `low`: a move plus a document.
**Caution:** the CLI test and the examples resolve paths from their own files; run them from
the repository root and from `python/`.
**Affected surfaces:** repository layout, Python packaging paths, CI path.
**Constitution impacts:** none.
**Review focus:** completeness and precision of `docs/algorithm.md`; history preserved.
**Focused tests:** all current Python tests.
**Depends on:** none.

### Batch 2 [B2]: Conformance generator and fixtures

**Coordinator-to-implementer handoff:**

- **Intent / why:** Fix the expected answer for every case before any language implements it.
- **Non-obvious rationale:** The generator must not import package code or call a solver; it is
  the independent referee. Exact search is feasible: the wheat example has 18 optional
  memberships after the forced ones. Keep random graphs at 12 groups or fewer so `--check` stays
  fast (target: under 2 minutes on the execution host; record the time).
- **Build On targets:** turfLP `conformance/generate.py` (argparse modes, manifest, SHA-256,
  splitmix64), `conformance/test_generate.py`, `conformance/README.md`.
- **Owned surfaces:** `conformance/**` except `run_r.R`; `.github/workflows/conformance-r.yaml`
  (generator steps only; B5 adds the R steps).
- **Forbidden surfaces:** as B1, plus `python/src/**`, `js/**`, `R/**`.
- **Acceptance evidence:** commands and counts below.
- **Failure modes / pitfalls:** fix dict order and `json.dumps` settings (sorted keys or a fixed
  order, `\n` line ends) so output is the same on Windows and Linux. Working tree files are CRLF
  on this Windows machine (`core.autocrlf=true`; route dependent): read text in universal newline mode, hash and compare
  LF-normalized text, and write with `newline="\n"`.
- **HEAD / paths / output:** after B1 Close.

**Tasks:**

- [ ] `generate.py` with `--write` and `--check`; inputs, manifest, fixtures; `--check` also
  compares the CSV copies in `python/examples/` with `conformance/data/` after line ending
  normalization.
- [ ] `test_generate.py` with hand cases and the enumeration cross check.
- [ ] `conformance/README.md`: files, input format, fixture format, pass rule, exclusions,
  commands.
- [ ] `conformance-r.yaml` with the two generator steps (Python 3.12 on Ubuntu).

**Acceptance criteria:**

- [ ] B2-A1: `python conformance/generate.py --check` exits 0 on Windows, and the same command exits 0 in the `conformance-r.yaml` job on Ubuntu on the PR head that closes B2.
- [ ] B2-A2: `python conformance/test_generate.py` exits 0, and its cross check compares the exact search with plain enumeration on every graph with up to 6 groups.
- [ ] B2-A3: The fixtures contain every labeled graph with 1 to 5 groups, at least 200 seeded random graphs with 6 to 12 groups, the wheat and simple ABC examples, the D4 letter renaming example, a 28 group star (labels after Z), the complete and the empty graph, `max_cliques` cases, and error cases for every input rule of the spec; `conformance/README.md` states the case counts.
- [ ] B2-A4: The wheat fixture expects 56 assignments before, 44 after, 4 letters after, and the canonical display; the simple ABC fixture expects `{"1": "A", "2": "AB", "3": "AC", "4": "BC", "5": "C"}`.
- [ ] B2-A5: `generate.py` and `test_generate.py` import only the Python standard library (checked by a grep of their import lines).

**Docs likely touched:** `conformance/README.md`.
**Risk:** `standard`: the generator is the referee; a bug here passes into all three languages.
**Caution:** the spec order is (clique, group) for the tie-break; do not reuse Python's current
(group, clique) variable order.
**Affected surfaces:** `conformance/`.
**Constitution impacts:** none.
**Review focus:** generator independence and correctness of the canonical search.
**Focused tests:** `test_generate.py`.
**Depends on:** B1.

### Batch 3 [B3]: Python on highspy with the canonical tie-break

**Coordinator-to-implementer handoff:**

- **Intent / why:** Make the Python package follow the spec on the same HiGHS family as
  JavaScript, and pass every fixture.
- **Non-obvious rationale:** The canonical pass removes solver dependence from results, so the
  three languages agree even on tied inputs. Fix variables through column bounds, not new rows.
  Keep `SolverError` for invalid `time_limit` and `max_cliques` (current tests expect it).
- **Build On targets:** turfLP `python/src/turflp/_solver.py` (options, read back, status
  handling), current `algorithms/assignment_minimum.py` and `validation.py`.
- **Owned surfaces:** `python/**`, `.github/workflows/python.yaml`.
- **Forbidden surfaces:** as B1. Fixture JSON is never edited by hand. A suspected generator or
  spec defect follows the fix protocol in "Notes".
- **Acceptance evidence:** below.
- **Failure modes / pitfalls:** `highspy` returns `(status, value)` from `getOptionValue` on
  1.15; `kHighsInf` for infinite bounds; integrality uses `HighsVarType.kInteger` with bounds
  0 and 1; the pandas `means` order must be kept exactly.
- **HEAD / paths / output:** after B2 Close.

**Tasks:**

- [ ] Clique enumeration, canonical order, model, canonical solve, checks, labels, stats per
  spec; remove `scipy` and `networkx`.
- [ ] Example scripts print `reduction_pct` with one decimal (the stat is now unrounded).
- [ ] `test_conformance.py`, `test_solver.py`, `test_cliques.py`.
- [ ] `python.yaml`: uv test matrix, minimum versions job, package job; `uv.lock`.

**Acceptance criteria:**

- [ ] B3-A1: In `python/`, `pytest` passes, including every conformance fixture with presolve on and with presolve off.
- [ ] B3-A2: The 25 tests from `main` pass with no change to their files.
- [ ] B3-A3: `python/pyproject.toml` depends on exactly `highspy>=1.15.1,<1.16`, `numpy>=1.24`, and `pandas>=2.0`, and `grep -rE "scipy|networkx" python/src` finds nothing.
- [ ] B3-A4: A test reads the HiGHS options back after a solve and finds presolve as set, both gaps 0, both feasibility tolerances 1e-9, and threads 1.
- [ ] B3-A5: Tests prove the failure paths: a time budget shared across solves raises the time limit error, a non optimal status raises `SolverError`, and a scripted invalid solution raises the "HiGHS returned an invalid solution" error.
- [ ] B3-A6: The `python.yaml` jobs test, minimum, and package pass in CI on the PR head that closes B3.

**Docs likely touched:** `python/README.md`, `docs/algorithm.md` (only if a spec gap is found;
record it in the Close commit).
**Risk:** `high`: public behavior changes for tied inputs and the dependency set changes.
**Caution:** never edit a fixture to make a test pass; a disagreement follows the fix protocol
in "Notes".
**Affected surfaces:** `python/src/cld_reducer/**`, `python/tests/**`, packaging, CI.
**Constitution impacts:** Python public API and CLI must not change.
**Review focus:** canonical solve correctness, solution checks, time budget, API parity.
**Focused tests:** conformance, solver, cliques, all current tests.
**Depends on:** B2.

### Batch 4 [B4]: JavaScript package

**Coordinator-to-implementer handoff:**

- **Intent / why:** Publishable npm package `cld-reducer` that passes every fixture.
- **Non-obvious rationale:** A second implementation finds spec gaps cheaply before the slow R
  loop. Copy turfLP's solver loader, including the `instantiateWasm` workaround and the failed
  load race; it was reviewed in three rounds there.
- **Build On targets:** turfLP `js/src/solver.ts`, `js/src/input.ts`, `js/test/*.test.ts`,
  `js/scripts/conformance.mjs`, `js/package.json`, `js/tsconfig*.json`, `js/vitest.config.ts`.
- **Owned surfaces:** `js/**`, `.github/workflows/js.yaml`.
- **Forbidden surfaces:** as B3.
- **Acceptance evidence:** below.
- **Failure modes / pitfalls:** `highs` types read as CommonJS under NodeNext; sparse array holes
  read as missing; object key order (reason for the `means` rule); every HiGHS model must be
  disposed; Windows paths in tests use `fileURLToPath`.
- **HEAD / paths / output:** after B3 Close.

**Tasks:**

- [ ] Package files, source, tests, conformance script, README, LICENSE, lock file.
- [ ] `js.yaml` with the test matrix and the pack job.

**Acceptance criteria:**

- [ ] B4-A1: In `js/`, `npm ci`, `npm run typecheck`, `npm run build`, `npm test`, and `npm run test:conformance` pass, and the conformance script runs every fixture with presolve on and with presolve off.
- [ ] B4-A2: `npm pack --dry-run --json` lists only `package.json`, `README.md`, `LICENSE`, and files under `dist/`, and `dist/index.d.ts` declares `reduceLetters`, `reduceFromAdjacency`, `loadSolver`, and the three error classes.
- [ ] B4-A3: The packed tarball installs in an empty temporary folder, and a Node script there imports `cld-reducer` and prints the simple ABC display `{"1":"A","2":"AB","3":"AC","4":"BC","5":"C"}`.
- [ ] B4-A4: Tests prove the solver settings read back from HiGHS, the failure paths of B3-A5, loading from `wasmBinary` and from `wasmModule` without reading `highs.wasm` from disk, disposal of every model, and rejection of a plain object for `means`.
- [ ] B4-A5: The `js.yaml` jobs pass in CI on the PR head that closes B4.

**Docs likely touched:** `js/README.md`.
**Risk:** `standard`: new package, known solver pattern.
**Caution:** do not publish; `npm publish --dry-run` is allowed only without credentials.
**Affected surfaces:** `js/`, CI.
**Constitution impacts:** none.
**Review focus:** API parity with the spec, error classes, package contents, loader.
**Focused tests:** conformance script, solver and load tests.
**Depends on:** B2 (B3 for any spec fixes found there).

### Batch 5 [B5]: R package

**Coordinator-to-implementer handoff:**

- **Intent / why:** CRAN-ready R package `cldreducer` at the root that passes every fixture.
- **Non-obvious rationale:** Presolve off in R (D7). `highs_control()` already defaults to one
  thread. Use a replaceable solve hook for failure path tests, like turfLP's `solve_lp`. Keep
  examples small for CRAN timing.
- **Build On targets:** turfLP `DESCRIPTION`, `R/turf.R` `solve_lp()`, `R/data.R`,
  `R/turfLP-package.R`, `tests/testthat/`, `.Rbuildignore`, `inst/CITATION`, `inst/WORDLIST`,
  `cran-comments.md`, `NEWS.md`, `.github/workflows/R-CMD-check.yaml`,
  `conformance-r.yaml`, `conformance/run_r.R`, `data-raw/`.
- **Owned surfaces:** `DESCRIPTION`, `NAMESPACE`, `R/**`, `man/**`, `tests/**`, `data/**`,
  `data-raw/**`, `inst/**`, `.Rbuildignore`, `cldreducer.Rproj`, `NEWS.md`,
  `cran-comments.md`, `conformance/run_r.R`, `.github/workflows/R-CMD-check.yaml`,
  `.github/workflows/conformance-r.yaml`, `.github/.gitignore`.
- **Forbidden surfaces:** as B3.
- **Acceptance evidence:** below; CI run URLs in the Close commit body.
- **Failure modes / pitfalls:** without local R (Option B), generated files come from the CI
  artifact; `CITATION.cff` at the root needs `.Rbuildignore`; non ASCII characters in R code
  fail the check; examples over 5 s get a CRAN NOTE; tests must not write outside `tempdir()`;
  tests must not read repository files, because CRAN checks the tarball alone (a relative path
  such as `../../../conformance` can reach the checkout from the default `check/` folder in CI,
  so B5-A7 moves the check folder outside it);
  the generated-files job must install the roxygen2 version recorded in DESCRIPTION, or version
  churn alone fails the diff.
- **HEAD / paths / output:** after B4 Close.

**Tasks:**

- [ ] Package metadata, R code, roxygen docs, data, tests, CITATION, WORDLIST, NEWS,
  cran-comments, `.Rbuildignore`.
- [ ] `conformance/run_r.R`, `R-CMD-check.yaml`, `conformance-r.yaml`.

**Acceptance criteria:**

- [ ] B5-A1: The CI as-cran job (`R CMD check --as-cran` with the PDF manual) ends with 0 errors and 0 warnings, and every NOTE it reports is listed and explained in `cran-comments.md`.
- [ ] B5-A2: The five R-CMD-check matrix jobs (macOS release, Windows release, Ubuntu devel, release, oldrel-1) end with 0 errors and 0 warnings, and any NOTE is listed and explained in `cran-comments.md`.
- [ ] B5-A3: `conformance-r.yaml` passes, and `run_r.R` reports every fixture in `reduce.json`, `errors.json`, and `labels.json` as checked and passed.
- [ ] B5-A4: The generated-files job follows the six steps of the plan section "Generated-files job" and passes on the PR head that closes B5. Its failure path is shown once: either a failing run that still produced a downloadable `generated-files` artifact (the Option B bootstrap run), or, under Option A, a local run of the same commands on a tree with one deleted help page, one stale help page, one new undocumented export, and no `data/` folder, which exits non-zero for each case.
- [ ] B5-A5: The check timings show every example under 2 s, and the testthat run takes under 60 s on Ubuntu release.
- [ ] B5-A6: `R CMD build` output contains no file from `python/`, `js/`, `conformance/`, `docs/`, `data-raw/`, `.github/`, or the run docs (checked with `tar tzf` on the built tarball).
- [ ] B5-A7: The as-cran job checks the built tarball in a check directory under `runner.temp`, outside the checkout, so the tests cannot reach repository files; `grep -rnE "\.\./|read\.csv|readLines|jsonlite|file\.path" tests/` finds nothing (a comment may still name a fixture id); and `run_r.R` compares each R data set with its CSV in `conformance/data/`.

**Docs likely touched:** `man/`, `NEWS.md`, `cran-comments.md`.
**Risk:** `high`: CRAN rules, and a CI-gated loop under Option B (the default).
**Caution:** do not run win-builder or submit to CRAN; those are human steps.
**Affected surfaces:** R package files at the root, R workflows.
**Constitution impacts:** none.
**Review focus:** CRAN policy (DESCRIPTION text, examples, tests, timings, files in the
tarball), spec parity, data documentation.
**Focused tests:** testthat, `run_r.R`.
**Depends on:** B2 (B3 and B4 for spec fixes).

### Batch 6 [B6]: Documentation, citation, versions, and publish workflows

**Coordinator-to-implementer handoff:**

- **Intent / why:** Make the repository read and release like turfLP.
- **Non-obvious rationale:** One version (D3). README commands must be run, not assumed.
  Publish workflows are added but never triggered.
- **Build On targets:** turfLP `README.md`, `python/README.md`, `js/README.md`,
  `publish-npm.yaml`, `publish-python.yaml`, current `README.md` and `CITATION.cff`.
- **Owned surfaces:** `README.md`, `python/README.md`, `js/README.md`, `CITATION.cff`,
  `NEWS.md`, `.github/workflows/publish-npm.yaml`, `.github/workflows/publish-python.yaml`,
  version fields in `DESCRIPTION`, `python/pyproject.toml`, `python/src/cld_reducer/__init__.py`,
  `js/package.json`, `js/package-lock.json`.
- **Forbidden surfaces:** as B3; citation facts other than version and date.
- **Acceptance evidence:** below.
- **Failure modes / pitfalls:** badge URLs must name the new workflow files; `CITATION.cff`
  must still validate after the edit; `date-released` is the B6 date, and the release step
  (H8) changes it if the release date differs.
- **HEAD / paths / output:** after B5 Close.

**Tasks:**

- [ ] Root README (overview, R install and usage, Python and JavaScript sections, method,
  citation), per-language READMEs, NEWS.md 0.2.0 (all user-visible changes of D3 to D6 and the
  git URL change), `CITATION.cff` version and date, publish workflows.

**Acceptance criteria:**

- [ ] B6-A1: `DESCRIPTION`, `python/pyproject.toml`, `python/src/cld_reducer/__init__.py`, `js/package.json`, and `CITATION.cff` all state version 0.2.0.
- [ ] B6-A2: Every code example in `README.md`, `python/README.md`, and `js/README.md` was run on the final code (R examples in CI or local R), and its printed output in the README matches the run.
- [ ] B6-A3: `cffconvert --validate` passes on `CITATION.cff`.
- [ ] B6-A4: `publish-npm.yaml` and `publish-python.yaml` check that the release tag equals `v` plus the package version and use trusted publishing with no stored token; no workflow publishes on push or pull_request.
- [ ] B6-A5: `NEWS.md` 0.2.0 lists the R and JavaScript packages, the Python layout move and git URL change, the move to `highspy`, the canonical tie-break, the canonical clique order that can rename letters for inputs with one optimal covering (with the D4 example), the unrounded `reduction_pct`, the `solver_status` text "Optimal", `time_limit` as one budget for all solves, and the new finite means check.

**Docs likely touched:** all READMEs, NEWS.md, CITATION.cff.
**Risk:** `low`.
**Caution:** do not set up publishers or environments; list them as human items.
**Affected surfaces:** docs and release files.
**Constitution impacts:** none.
**Review focus:** accuracy of every command and claim; no overstated status (nothing is on
CRAN, npm, or PyPI yet).
**Focused tests:** README commands.
**Depends on:** B3, B4, B5.

## Master Acceptance

- [ ] M-A1: At the final head, the Python, JavaScript, and R runners each pass every fixture in `conformance/fixtures/`, so the three languages return the same groups, assignments, letters, and integer stats for every case.
- [ ] M-A2: At the final head, every job of `R-CMD-check.yaml`, `conformance-r.yaml`, `python.yaml`, and `js.yaml` succeeds on the PR, and the as-cran job shows 0 errors and 0 warnings.
- [ ] M-A3: The npm package is ready to publish: B4-A2 and B4-A3 hold at the final head, `publish-npm.yaml` is in place, and nothing was published.
- [ ] M-A4: Existing Python users keep the import name `cld_reducer`, the public names and exceptions, the CLI `cld-reduce` with its flags, and all 25 tests from `main`; the git URL change and the behavior changes are in NEWS.md.
- [ ] M-A5: The PR body lists every human open item of this plan (H1 to H13), and nothing was merged, tagged, released, submitted to CRAN, or published to npm or PyPI.
- [ ] M-A6: Astra and a fresh Opus 5.5 review report no open finding at the exact final head, and a `Local tests passed on <head SHA>` PR comment lists the local commands and results.

## Definition of green

All of these hold at one exact PR head:

1. GitHub Actions on the PR head: every job in `R-CMD-check.yaml` (5 matrix, as-cran,
   generated-files), `conformance-r.yaml`, `python.yaml` (6 matrix, minimum, package), and
   `js.yaml` (6 matrix, pack) succeeds. No job is skipped or cancelled.
2. The as-cran log shows `0 errors | 0 warnings`; each NOTE is in `cran-comments.md`.
3. Local record on the execution host (route dependent: Windows for routes (b) and (c), WSL
   Linux for route (a)), posted as the PR comment `Local tests passed on <SHA>`:
   `python conformance/generate.py --check`, `python conformance/test_generate.py`; in
   `python/`: `ruff check .`, `ruff format --check .`, `pytest`, both example scripts; in `js/`:
   `npm ci`, `npm run typecheck`, `npm run build`, `npm test`, `npm run test:conformance`,
   `npm pack --dry-run`; and, with Option A, `R CMD check --as-cran --no-manual` and
   `Rscript conformance/run_r.R`.
4. `elves_landing_check.py --session .elves-session.json --repo-root .` passes on the evidence
   commit.
5. Astra and the fresh Opus 5.5 reviewer both report no open finding at that head.
6. The PR is still a draft and is not merged.

## Risks

| Risk | Effect | Response |
|---|---|---|
| Canonical pass needs extra solves | Slower on large graphs: one extra solve each time the visited membership is 0 in the current solution (wheat: between 12 and 56 small solves) | Fix by bounds, share the time budget, measure wheat and a 30 group random graph in tests and README |
| HiGHS 1.14 (R) and 1.15 (Python, JS) differ | Different first optima or a presolve defect | Canonical pass; R presolve off; Python and JS conformance with presolve on and off |
| Generator defect | Wrong expected values in all three languages | Cross check against plain enumeration (B2-A2); hand-checked cases; Astra review of B2 |
| No local R | Slow R loop | Option A, or Option B with the generated-files artifact |
| CRAN rejection points | Resubmission | turfLP lessons: short examples, explained NOTEs, PDF manual check, `.Rbuildignore`, spelling WORDLIST |
| Python behavior change on tied inputs and on letter names | Different wheat display than 0.1.0; renamed letters for some uniquely optimal inputs (D4 example) | Mason confirms D4 (H10); NEWS.md entry names both changes; the D4 example is a fixture; 0.1.0 was never on PyPI |
| npm name taken before first publish | Rename needed | Name free today; H6 asks for an early first publish after approval |
| Group label strings differ by language for numeric labels | Different group keys | Spec says labels are strings; fixtures use string labels; README notes it |
| `highs` (GPL) imported by an MIT package | License questions | Same as turfLP, which passed the CRAN pretests |
| Elves supervisor not usable on native Windows | Execution cannot launch as routed | Section "Execution routes": LB1 and routes (a), (b), (c) |

## Human open items

These need a person. The run does not do them.

- **H1.** Confirm names: R `cldreducer` (permanent on CRAN), npm `cld-reducer`.
- **H2.** CRAN maintainer name and email for `cre` in DESCRIPTION (proposal: John Ennis,
  `john.m.ennis@aigora.com`, as in turfLP). The maintainer must answer the CRAN confirmation
  email.
- **H3.** Confirm the author list and roles (six authors from `pyproject.toml` as `aut`,
  Aigora as `cph` and `fnd`).
- **H4.** Run win-builder (R-devel and R-release) before submission and add the results to
  `cran-comments.md`.
- **H5.** Submit to CRAN through the web form after Mason approves, and answer reviewer mail.
- **H6.** npm: an npm account or organization with publish rights and 2FA; first publish of
  `cld-reducer` by hand (`npm publish --access public` in `js/` at the release tag), because npm
  trusted publishing needs an existing package; then add the trusted publisher (repository
  `aigorahub/cld-reducer`, workflow `publish-npm.yaml`, environment `npm`).
- **H7.** PyPI (not requested by John): a pending trusted publisher for `cld-reducer`
  (workflow `publish-python.yaml`, environment `pypi`), or a decision to delete that workflow.
- **H8.** GitHub: create environments `npm` and `pypi`; after merge, tag `v0.2.0` and publish a
  release; update the repository description ("Python tools ...") and topics.
- **H9.** Merge approval for the PR.
- **H10.** Confirm D4 (canonical tie-break and canonical clique order), including both Python
  output changes: a different covering for inputs with several optima, and renamed letters for
  some inputs with one optimum. Confirm the Python changes D5 and D6.
- **H11.** Choose Option A (local R install) or Option B (CI only) for the R loop. Without a
  choice, Option B applies.
- **H13.** Choose the execution route (a), (b), or (c) of the section "Execution routes". Route
  (c) needs Mason's explicit acceptance of experimental prewalk and of the items it gives up.
- **H12.** Confirm that the wheat significance data (Piepho 2004, as reproduced in Ennis,
  Fayle, and Ennis 2012, Table 7) may ship in the CRAN package with that citation.

## Execution routes

### Launch blocker LB1 (corrected after review round 1)

The routed launch, `cobbler_agents.py native-worker launch --host claude --prewalk required`,
cannot run on this native Windows host. Facts from Elves 2.39.0 as installed:

- Every `cobbler_agents.py` command exits at import with `ModuleNotFoundError: No module named
  'fcntl'` (`cobbler_runtime/worktree_fingerprint.py`).
- `cobbler_runtime/storage.py` needs more than `fcntl`: lines 61 to 96 load an atomic
  no-replace rename only on Linux (`renameat2`) and macOS (`renameatx_np`) and fail closed
  elsewhere, and line 289 onward opens directory descriptors and uses `dir_fd`, which Windows
  Python does not support. `acceptance_contract.py sync-session --write` fails here for the
  same reason (`PermissionError` on the directory open). A locking-only patch still fails.
- `references/agent-teams.md` states: "Native Windows Python is not a qualified Elves execution
  host." Elves supports Windows only through WSL2.
- No cached prewalk qualification exists on Windows or in WSL. WSL Ubuntu has `python3` and
  `git` only.
- Read-only helpers work on Windows: `acceptance_contract.py validate`,
  `elves_landing_check.py`, and the pure validators in `cobbler_runtime/prewalk.py`.

The choice of route changes run contracts, paths, and evidence. "Route-dependent content" below
lists every place. Mason chooses the route (H13).

### Route (a): Linux host in WSL, qualified prewalk

The only route that runs the Elves supervisor and its required-mode qualification as designed.

- Setup in WSL: Claude Code CLI and login, `gh` and auth, Node.js 24, Python 3 with `venv`,
  `uv`, Elves 2.39.0 (`python3 scripts/sync_installed_skills.py --apply --target claude` from an
  `aigorahub/elves` checkout), and R under Option A.
- Repository transfer: clone `aigorahub/cld-reducer` in the WSL file system, create the
  registered worktree with `preflight_worktree.py --create-worktree feat/r-js-packages --base
  origin/main` (same tripwire `eb95fe9`), then bring the unpushed staging commits across with
  `git bundle create` on Windows and `git fetch <bundle>` plus a fast-forward in WSL. The
  Windows worktree is then retired (not deleted until Mason agrees).
- Rebuild what is Windows-specific: `worktree_path` and every path in the run docs and packet;
  regenerate the ignored worker packet in the WSL worktree; rerun `sync-session` and
  `validate` there.
- Driver: the driver must run where the supervisor runs. Either Lantern seats a WSL driver with
  these run docs, or this session drives through `wsl.exe` commands. Lantern decides.
- Then: `native-worker launch --prewalk required --guide-model claude-opus-5-5 --guide-effort
  xhigh --execution-model claude-sonnet-5-5 --execution-effort high`. Qualification failure
  stops the run.
- Risks (Astra): the commit transfer, the ignored packet, the worktree registration, and every
  Windows path and Windows-only evidence item must be redone; a mistake there breaks the
  tripwire or the landing check.
- Proof needed before launch: registration, required prewalk qualification, durable state
  writes, worker launch and resume, and acceptance reconciliation, all on the WSL host, with the
  recorded paths and the final evidence requirements changed to that host.

### Route (b): port Elves storage to native Windows

Not a patch. It needs a separately designed and tested Windows storage port in
`aigorahub/elves`: locking (for example `LockFileEx` through `msvcrt` or `ctypes`), an atomic
no-replace rename (for example `MoveFileExW` without `MOVEFILE_REPLACE_EXISTING`), and a
replacement for the descriptor-relative (`dir_fd`) traversal and its no-follow guarantees, with
Windows CI, a security review, a release, a reinstall, and then required-mode qualification. It
is a separate project outside this run and would delay it by days. Not recommended for this run.
No Elves issue exists for it yet; filing one is Lantern's or Mason's decision.

### Route (c): manual experimental prewalk in a Herdr tab, driver-supervised batches

Proposed by Lantern. The worker is an interactive Claude Code session in a separate Herdr tab of
this workspace, in the registered Windows worktree. The driver (this session) is the
supervisor, does not park, gates each batch, and owns all run memory.

**Steps (after `EXECUTE APPROVED` and Mason's acceptance of experimental prewalk):**

1. Push the staging commits to `origin feat/r-js-packages` and open the draft PR. Create the
   rollback ref `refs/elves/rollback/cld-reducer-r-js-packages-2026-10-07/b0`.
2. Choose a session UUID `S`. Write `{"schema_version": 1, "run_id":
   "cld-reducer-r-js-packages-2026-10-07", "session_id": "S"}` to
   `.elves/runtime/prewalk/cld_reducer_r_js_package-d60c05050bd9310e/session.json` (the path
   that `prewalk.prewalk_paths()` returns for this run).
3. Write the guide message `.elves/runtime/guide-message.md`: the text of the installed
   `prewalk.guide_prompt(run_id, paths, todo_limit=10)` (exact TODO and checkpoint shapes),
   then the full worker packet. This is the one packet message.
4. `herdr tab create --workspace "$HERDR_WORKSPACE_ID" --cwd C:\Claude\cld-reducer-r-js-packages
   --label cld-worker --no-focus`; read the root pane `P` from the JSON.
5. `herdr agent start cld-worker --kind claude --pane P -- --session-id S --model
   claude-opus-5-5 --effort xhigh --permission-mode auto`.
6. Guide turn: `herdr agent prompt cld-worker "@.elves/runtime/guide-message.md" --wait`, then
   `herdr agent wait cld-worker --timeout <ms>` in a loop as the watchdog if the prompt wait ends
   first.
   The guide orients, writes the B1 TODO (at most 10 items) and the first meaningful B1 edit
   (no commit with `Close`), writes `checkpoint.json` (`first_meaningful_edit`), and ends its
   turn.
7. Transition checks by the driver, model-free, before any resume: `herdr agent get
   cld-worker` shows state `idle` or `done` and session `S`;
   `prewalk.load_and_validate_transition_artifacts()` and `prewalk.validate_meaningful_edit()`
   from the installed Elves pass (if either cannot run on Windows, the driver does the same
   checks by hand: valid TODO and checkpoint shapes, a real product edit among the declared
   changed paths, no change to driver-owned run docs or forbidden paths, no `Close` commit since
   the staging head, branch and origin unchanged, `git ls-remote origin` shows `main`
   unchanged). Any failure stops the run before resume.
8. End the guide process: `herdr agent prompt cld-worker "/exit"`, then `herdr pane
   process-info --pane P` must show the shell in the foreground.
9. Resume the same session on the execution route: `herdr agent start cld-worker --kind claude
   --pane P -- --resume S --model claude-sonnet-5-5 --effort high --permission-mode auto`.
10. Handoff evidence: `herdr agent get cld-worker` shows session `S` again; `herdr pane
    process-info --pane P` shows the argv with `--resume S --model claude-sonnet-5-5 --effort
    high`. After the first execution reply, the transcript
    `~/.claude/projects/C--Claude-cld-reducer-r-js-packages/S.jsonl` must show one `sessionId`
    (`S`), `cwd` equal to the worktree, and assistant messages with `model` claude-opus-5-5
    before the transition and claude-sonnet-5-5 after it. (Claude Code transcripts record the
    served model on each assistant message; this was checked on the driver's own transcript.
    Effort is not recorded anywhere, so the execution effort stays unobserved.)
11. Transition message: `herdr agent prompt cld-worker "Continue." --wait`. The worker finishes
    B1, pushes its `Close` commit, writes `.elves/runtime/worker-report-B1.md`, replies with that
    path, and waits.
12. Batch loop: see "Batch completion and session evidence". The driver prompts the next batch
    only when `herdr agent get` shows `idle` or `done`. The prompt names the batch and points to
    its handoff block in the plan and to packet sections 4 to 8; it never resends the packet.

**Rule check against the installed Elves 2.39.0, with corrections to Lantern's proposal:**

- Packet once, only `Continue.` at the transition, exact resume with a route override, `auto`
  permission mode and never `bypassPermissions` (prewalk.md): kept.
- Correction: the session id is assigned by the driver with `--session-id` and written to
  `session.json` before the guide turn, as the Elves Claude transport does with a
  caller-generated UUID; the guide prompt requires reading it from that file.
- Correction: the guide message uses the installed `guide_prompt()` text so the TODO and
  checkpoint shapes are exact, and both artifacts are validated before the resume.
- Correction: later batch prompts are new worker turns, so the handoff standard ("before every
  worker turn, a stand-alone packet") applies; each batch prompt points to that batch's
  handoff block in the plan, which has all eight parts. This is not a packet replay.
- "Do not type messages into a working, blocked, unknown, or parked pane" (agent-teams.md):
  prompts go only to `idle` or `done`. On `blocked`, the driver reads the pane and does not
  answer the approval dialog (workspace rule); it reports to Lantern. On `unknown`, it waits and
  reads.
- After the first edit, cold fallback is forbidden (prewalk.md): if the worker process dies,
  the driver resumes session `S` on the execution route and sends `Continue.`; transient
  provider errors wait 5, 10, then 20 minutes. If `S` cannot be resumed, the run stops and the
  driver reports; it never starts a fresh session with a copied packet.
- Compaction (prewalk.md, P4): an interactive session that runs six batches will likely
  compact. After a compaction the driver records `prewalk_fallback:
  prewalk_dequalified_by_compaction`, and later batches rely on the run docs and packet files,
  not on retained guide context.
- No rule forbids the route outright, but agent-teams.md says native Windows is not a qualified
  Elves execution host, so the route runs outside Elves' qualified support. Mason's acceptance
  covers that.

**What route (c) gives up compared with a qualified cobbler prewalk:**

1. No live qualification canary: retained guide context and instruction fidelity after the
   resume are unproven (experimental, not `retained_safe`).
2. No machine-enforced transition kernel: the driver runs the validators or the same checks by
   hand.
3. No version-3 private native-worker state, no single redacted follow log, no stream identity
   check, no salvage tail, no continuity watchdog, no futile re-drive guard: the driver uses
   `herdr agent wait` with timeouts, `herdr agent read`, the transcript JSONL, and the execution
   log.
4. No sandbox and no narrowed Git roots: the worker runs with Mason's full git and `gh`
   authority (scopes `repo`, `workflow`) and could push other refs, edit or merge PRs, or create
   tags. Prevention is by instruction and the `auto` permission classifier only. Detection:
   after every batch the driver checks `git ls-remote origin` (`main` unchanged, no new ref other
   than `feat/r-js-packages`), `gh pr view` (still draft, not merged), and `gh release list` and
   tags (none new). `main` protection (PR required, admins enforced) blocks a direct push to
   `main`, but not a PR merge.
5. The transition is done by the driver, not by the supervisor.
6. Native Windows is not a qualified Elves host; Elves writers (`sync-session --write`,
   `cobbler_agents.py`) are unavailable, so the driver writes the session JSON itself and runs
   only the read-only Elves checks.
7. The route-change proof is the transcript `model` field and the argv. For Claude Code, Elves
   itself records the route change as `unobserved`, so this point is not weaker.

What it keeps: one exact session across the route change (checkable), one packet, only
`Continue.` at the transition, the registered worktree, driver-owned run memory, per-batch
acceptance checks by the driver, and the final independent reviews.

**Recommendation.** Route (c) if Mason accepts the seven items above; it can start on this
machine without new installs beyond the Python venv and `npm ci`. Route (a) if Mason wants
qualified prewalk; it costs the WSL setup and transfer first. Route (b) is not for this run.

### Batch completion and session evidence

Only the driver writes `.elves-session.json`, the survival guide, the execution log, and the
plan. The worker never edits them.

- **Route (c):** after the worker pushes the B<N> `Close` commit and writes
  `.elves/runtime/worker-report-B<N>.md`, it is idle. The driver checks every `B<N>-A#` itself
  (reruns or inspects the named commands; reads the CI result for the Close commit), writes
  `met` and `evidence` for each row and `status: complete` for the batch, updates the
  execution log and survival guide, runs `acceptance_contract.py validate`, commits only those
  run-doc paths as `[feat/r-js-packages · Batch N/6 · Review] Record B<N> acceptance evidence`,
  pushes, creates the rollback ref `b<N>`, and only then prompts B<N+1>. A failed row gets a gap
  prompt for the same batch first. This is the B1 to B2 path.
- **Routes (a) and (b), parked full-run:** the worker closes each internal batch with its
  `Close` commit body and `.elves/runtime/worker-report-B<N>.md` as interim evidence. Session
  rows stay `met: false` until the driver's one terminal (or safety) reconciliation, where the
  driver verifies each row and writes it. This is the Elves trusted full-run rule; the
  survival guide's "Acceptance Checks" says so.

### Route-dependent content

| Item | Route (c) | Route (a) | Route (b) |
|---|---|---|---|
| Worktree and `worktree_path` | `C:\Claude\cld-reducer-r-js-packages` | new WSL path, re-registered | Windows path |
| Driver monitor mode and delegation | interactive, per batch (`Delegation scope: batch`) | parked, `full_run` | parked, `full_run` |
| Batch completion evidence | driver writes session rows per batch | worker reports; driver reconciles at terminal | same as (a) |
| Prewalk mode and evidence | experimental, manual; transcript and argv | required, qualified canary | required, qualified canary |
| Worker launch | Herdr steps 4 to 11 | `cobbler_agents.py native-worker launch` | same as (a) |
| Local record host ("Definition of green" item 3) | Windows | WSL Linux | Windows |
| Local tools (Python venv, `npm ci`, R under Option A) | Windows | WSL Linux | Windows |
| CRLF pitfalls (B1, B2, packet) | apply (`core.autocrlf=true`) | apply only if WSL git sets `core.autocrlf` | apply |
| Worker packet paths and report path | Windows paths | rewritten for WSL | Windows paths |
| Elves Report path | Windows temp folder | `/tmp` | Windows temp folder |
| Session-file writes | driver writes JSON directly | `sync-session --write` works | after the port |

Every other part of the plan (spec, packages, conformance, CI, acceptance criteria) is the same
on every route.

### Run control summary

- **Models:** guide claude-opus-5-5 at xhigh; execution claude-sonnet-5-5 at high, on every
  route. Plan and final reviewer: Codex gpt-6-astra at high in tab `cld-review` (seated by
  Lantern). Second final reviewer: a fresh Opus 5.5 session that is not the driver or the
  worker. No silent model change; a route change needs Mason.
- **Git:** the worker commits and pushes only `feat/r-js-packages`. PR actions, run memory,
  final review, and landing stay with the driver.
- **PR:** none in Phase 1. After `EXECUTE APPROVED`, the driver pushes the staging commits and
  opens the draft PR before the worker starts.
- **Stop point:** a landable draft PR that meets "Definition of green". No merge, tag, release,
  CRAN submission, or publish.

## Non-Negotiables

- Never edit, commit, or push in `C:\Claude\turfLP` or `aigorahub/turfLP`.
- Never push to `main`, never merge, tag, release, submit to CRAN or win-builder, or publish to
  npm or PyPI. Only `feat/r-js-packages` is pushed.
- Never weaken, skip, or delete a test or a fixture to get green. Fixtures change only through
  the fix protocol in "Notes".
- Keep the Python import name, public API, exceptions, and CLI flags.
- No AI attribution in commits, PR text, or files.
- The user owns whether Elves may merge. Default is user-merges; opt-ins are merge-on-green or
  the reviewed-PR landing command (`\land-pr` or `/land-pr`), both after final readiness.
  This run has no opt-in.

## Test Strategy

- **Primary gates:** conformance (`generate.py --check`, `test_generate.py`, the three
  runners), Python `pytest`, JavaScript `npm test` and `npm run test:conformance`, R
  `R CMD check --as-cran`.
- **Secondary gates:** ruff, TypeScript typecheck, package build and clean install smoke tests,
  roxygen diff, README commands.
- **Mid-run proof:** impact path for the batch plus its CI workflow. Full local record and all
  CI at terminal readiness.
- **Known flaky tests:** none known.

## Notes

- **Fix protocol for the spec and the generator.** When an implementation disagrees with a
  fixture, first prove which side is wrong with a hand-checked case and plain enumeration. If
  the generator or `docs/algorithm.md` is wrong or unclear, fix it in a separate commit labeled
  with the owning batch (`Batch 1/6 · Review` for the spec, `Batch 2/6 · Review` for the
  generator), add the case to `conformance/test_generate.py`, regenerate with
  `generate.py --write`, and name the change in the next Close commit body. Then all
  implementations that already passed must pass again. Fixture JSON is never edited by hand.
- Local tools needed in execution, on the execution host (route dependent), installed only
  after approval: a Python virtual
  environment under `python/.venv` with the package, `pytest`, `ruff`, `uv`, `cffconvert`;
  `npm ci` in `js/`; R per H11.
- turfLP paths in this plan are references to read, never to change.
- Every date in run docs is ET unless it says otherwise.
