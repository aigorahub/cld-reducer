# Browser page for the JavaScript solver

Status: implemented in PR #13, merged as `b12423098d288496d4364ceeb6e094ada984a613`. The pull request holds the verification record.

Workspace: `/Users/john/aigora/dev/cld-reducer-pre-model-certificate`.
Branch: `feat/browser-solver-page`.
Base: `0b6bd6d46f8a2cc6dfda9b44ceb782f87a211759` (`main`, development version 0.3.1).
Reference: the turfLP dashboard at `9e6e7e569c07c53f338b7da817cdb59880110959`.

## Goal

Add one static HTML page that runs the JavaScript package of this repository in a
browser. A user opens the file, gives pairwise significance decisions, and reads
the reduced compact letter display. The page needs no server and no network.

## Scope

A private package in `dashboard/`, with its own manifest and lock file.
`npm run build` writes `dashboard/dist/cld-reducer-dashboard.html` and the same
page as `dashboard/dist/site/index.html` for a static host. Deployment is not part
of this change.

The page bundles `js/src` with esbuild. It calls the public API only:
`loadSolver`, `reduceLetters`, and the error classes. It adds no solver code and
no algorithm change. The build inlines `highs.wasm` from `js/node_modules`,
compressed with gzip. The existing `loadSolver({ wasmBinary })` path loads it.
The displayed version comes from `js/package.json`.

The solve runs in a classic worker made from a Blob. Cancel terminates that
worker and starts a new one. Each run has an id, and the page ignores a reply
with another id. A change of the input or the method stops a run and removes
the shown result. The page has no solve on its own thread, because such a solve
cannot be cancelled.

### Input

- Pairwise decisions as CSV with the columns `group1`, `group2`, and
  `significant`, by paste or by file. These are the default column names of the
  package. The page gives the cells to `reduceLetters` as text. The package
  applies its own rules: accepted decision words, no self comparison, no
  duplicate pair, and one row for every unordered pair. A missing pair is an
  error. The page shows the package message.
- Optional means as CSV with the columns `group` and `mean`.
- Two built-in examples from `conformance/data`: the five-group example and the
  wheat example, with their source notes. The build reads the files, so the page
  holds the same data as the fixtures.
- The page states that it reads decisions and does not run significance tests.

### Methods and output

- CLD-C (`letter_minimum`) is the default. CLD-sigma (`assignment_minimum`) is
  the alternative. One action runs both methods for a comparison.
- The page states the objective of each method, and that neither method
  optimizes the other quantity as a second objective.
- Each result shows the distinct letters, the assignments, the objective value,
  the relationship check of the package, and the time in the browser.
- A table gives the letters of each group. A matrix gives the letters that each
  pair of groups shares, for up to 30 groups.
- The result downloads as CSV and as JSON.
- The page does not report whether the essential cover proof or HiGHS produced a
  result. The public API does not expose that. The page makes no speed claim.

### Safety

- Labels go into the page as text nodes only.
- The page checks each reply before it shows it: the method, the row count, the
  relationship flag, and the shared letters against the input matrix. A failed
  check shows an error and no result.
- A content security policy in the page blocks network connections.
- The built page holds the license of this repository, the license of the
  `highs` package, and the data source record from `js/NOTICE`.

## Out of scope

A server, accounts, storage, a time limit control, matrix input, a second
optimization objective, an indicator of the proof path, and any hosting or
release step.

## Repository changes

- `dashboard/`: sources, tests, build script, browser test, README.
- `.Rbuildignore` and `scripts/check_r_package.R`: keep `dashboard` out of the R
  archive. The Python and npm archives use explicit file lists under `python/`
  and `js/`, so they cannot include it.
- `.github/workflows/js.yaml`: a `dashboard` job that runs the type check, the
  unit tests, the build, and the browser test, and keeps the built page as a
  workflow artifact.
- `README.md`, `NEWS.md`, `docs/development-status.md`: short entries.

## Verification

- Unit tests (Vitest): CSV reading, exports, reply checks, and the worker
  protocol with the real WebAssembly solver.
- Browser test (Playwright with the installed Chrome) on the built file, opened
  with `file://`, with network requests blocked:
  solver start, both examples with both methods against the conformance
  fixtures, paste and file input, invalid input, a method change, cancellation
  of a busy worker and a new run, an altered reply, label rendering, both
  downloads, page response during a solve, and a narrow viewport.
- Simple (both methods) and wheat with CLD-C are essential cover results. Wheat
  with CLD-sigma calls HiGHS. A unit test counts the solver calls to keep this
  classification true.
- Existing gates: JavaScript type check, tests, conformance, package check, and
  the R archive content check.
