# cld-reducer algorithm specification

This document is the normative specification for every cld-reducer implementation: the R package at the repository root, the Python package in `python/`, and the JavaScript package in `js/`. The conformance generator in `conformance/` follows it too, and its fixtures are the observable form of this document. Where an implementation and this document disagree, this document wins until it is changed through the fix protocol of the plan.

The problem is the assignment-minimum clique covering of Ennis, Fayle, and Ennis (2012), <https://doi.org/10.1145/2133803.2275596>. The input is the non-significance graph of a set of groups. The output is a compact letter display (CLD) with the fewest letter-to-group assignments in which two groups share a letter exactly when they are not significantly different.

## Conventions

- Groups have 0-based indices `0 … n-1` in this document, in the group order of section 1 or 2. Public group labels are strings.
- The non-significance graph has one vertex per group and an edge `{i, j}`, `i < j`, when groups `i` and `j` are not significantly different (adjacency true). A clique is a set of vertices that are pairwise adjacent. A maximal clique is a clique that no other vertex can join. A vertex with no edges is a maximal clique of size 1.
- "Edge" always means a non-significant pair `i < j`. "Significant pair" is a pair with no edge.
- "Solver error" and "invalid input error" are the two error kinds of section 10.
- Numbers called "whole" are finite numbers with no fractional part.
- Text in `code` that ends in a colon and a space, for example `` `assignment-minimum MILP failed: ` ``, is a message prefix. Anything after the prefix is language specific.

## 1. Pairwise input

Used by `reduce_letters` (R and Python) and `reduceLetters` (TypeScript). The input is a table with one row per compared pair.

**Columns.** Three columns identify the group of each side and the significance. The default names are `group1`, `group2`, `significant`, and the caller can pass other names. A missing column is an invalid input error with the prefix `post_hoc_results missing required columns: ` followed by the sorted list of missing names. Extra columns are ignored.

**Labels.** Group labels are converted to strings with the language's string conversion (Python `str`, R `as.character`, JavaScript `String`). Two labels that give the same string are the same group. Fixtures use string labels only.

**Significance.** Each value converts to a boolean "significant". Accepted values:

- Booleans.
- The numbers 0 and 1. Python accepts `int` and NumPy integers (not floats, as in 0.1.0). R and JavaScript accept any number equal to 0 or 1.
- Strings, after trimming and lower casing: `true`, `t`, `yes`, `y`, `1`, `significant` mean significant; `false`, `f`, `no`, `n`, `0`, `not significant`, `ns` mean not significant.

Anything else (including a missing value) is an invalid input error with the prefix `cannot coerce significance value to bool: `.

**Checks, in this order**, each an invalid input error:

1. Required columns (above).
2. Every significance value converts (above), row by row.
3. No self comparison (`group1` equals `group2` after conversion): `post_hoc_results must not contain self-comparisons`.
4. No duplicate unordered pair: prefix `post_hoc_results contains duplicate unordered pairs: `.
5. Group order and means (below), including the unique and non-empty group checks.
6. Unknown groups: when the group order comes from the means, every label in the table must be in it. Prefix `post_hoc_results contains groups not present in means/groups: `.
7. Missing pairs: every unordered pair of groups must have a row. Prefix `post_hoc_results missing unordered pairwise comparisons: `.

A table with no rows and no means has no groups and fails check 5.

**Group order.** When means are given, the group order is the order of the means. Otherwise it is the order of first appearance in the `group1` column read top to bottom, followed by the labels of the `group2` column read top to bottom that did not appear yet. The group order decides the canonical order of section 3 and the tie-break of section 5. Labels must be unique after conversion and there must be at least one group: prefixes `group labels must be unique after string conversion` and `at least one group is required`.

**Means.** Means are optional. They set the group order (below) and the order of the letters (section 7), and nothing else. When given, every group needs a mean, every mean must be a finite number, and the order of the means is the group order. Accepted forms:

| Language | Forms |
|---|---|
| R | named numeric vector (names give the order), or a data frame with columns `group` and `mean` (else its first two columns) |
| Python | mapping, `pandas.Series`, or `pandas.DataFrame` with columns `group` and `mean` (else its first two columns) |
| JavaScript | `Map<string, number>`, or an array of `{ group, mean }`. A plain object is rejected, because integer-like keys reorder and the order decides ties |

Invalid input errors for means: `means must be a mapping, pandas Series, pandas DataFrame, or None` (Python wording; R and JavaScript use their own words after the same meaning), `means DataFrame must have at least two columns or columns named group and mean`, `means are missing values for groups: `, and the new check `means must be finite numbers`. The finite check runs after the missing check, on the means of all groups.

From the validated table, the adjacency matrix has `adjacency[i][j]` true when the pair `{i, j}` is not significant, and `adjacency[i][i]` true. Section 2 then applies.

## 2. Adjacency input

Used by `reduce_from_adjacency` and `reduceFromAdjacency`. The input is a square matrix. `adjacency[i][j]` true means groups `i` and `j` are not significantly different and must share at least one letter.

**Values.** Booleans, or numbers equal to 0 or 1 (Python also accepts the floats 0.0 and 1.0 here, as in 0.1.0). Anything else, including strings, is an invalid input error.

**Checks, in this order**, each an invalid input error with this message or prefix:

1. No missing value (R `NA`, Python `None` or NaN, JavaScript `null`, `undefined`, or `NaN`): `adjacency must not contain missing values`.
2. Every value is a boolean or an explicit 0/1: `adjacency must contain only booleans or explicit 0/1 values`.
3. The matrix is two dimensional and square: `adjacency must be a square matrix`. An empty list (`[]`) has no second dimension and fails here. A matrix with zero rows and zero columns that is two dimensional (an R `matrix(logical(0), 0, 0)`) fails the next check.
4. At least one group: `adjacency must contain at least one group`.
5. Symmetric: `adjacency must be symmetric`.
6. Diagonal true: `adjacency diagonal must be True`. (R and JavaScript may say `TRUE` or `true`; the prefix `adjacency diagonal must be ` is stable.)
7. Groups: when given, they are converted and checked as in section 1 (unique, at least one), then their count must equal the matrix size: `number of groups must match adjacency dimensions`.

**Default groups** are `"1"` to `"n"` (strings, 1-based).

**Means** follow section 1 and are matched to the groups by label. For adjacency input, the group order is the `groups` argument (or the default), not the means order. Missing means for a group are an invalid input error as in section 1.

**Method.** `method` is `assignment_minimum` (the hyphenated spelling `assignment-minimum` is accepted and stored as `assignment_minimum`). Any other value is an invalid input error with the prefix `unsupported CLD reduction method: ` followed by the quoted value. This check comes after the checks above and before the `time_limit` and `max_cliques` checks of section 6. For pairwise input the call reaches this point after section 1 completes.

## 3. Maximal cliques

The cover starts from the set of all maximal cliques of the non-significance graph, the "maximal covering".

**Canonical order.** Write each clique as its group indices in ascending order. Sort the cliques lexicographically by those lists (compare the first indices, then the second, and so on; a list that is a prefix of another comes first, which cannot happen between two maximal cliques). The result is the canonical clique order, `c = 0 … k-1`. Everything after this section uses it: variable order, the tie-break, and the letter sort.

**Enumeration.** The method is free (Bron-Kerbosch with pivoting is typical). Only the set of cliques and the sorted order are normative.

**Cap.** When `max_cliques` is a number and the graph has more than `max_cliques` maximal cliques, raise a solver error with the prefix `maximal clique enumeration exceeded max_cliques=` followed by the cap and `; increase max_cliques or pass None to disable the cap` (R `NULL`, JavaScript `null`, in place of `None`). An implementation may stop counting as soon as the cap is exceeded. `max_cliques` of `None`, `NULL`, or `null` removes the cap. The cap applies to the count, so a graph with exactly `max_cliques` cliques passes.

**Counts.** `assignments_before` is the sum of the clique sizes. `num_letters_before` is `k`.

## 4. Model

Let `E` be the edges. Variables, all binary:

- `x[c, g]` for each clique `c` and each member `g` of it. This is the membership "group `g` has the letter of clique `c`". The number of `x` variables is `assignments_before`.
- `y[e, c]` for each edge `e = {i, j}` and each clique `c` that holds both `i` and `j`. This means "clique `c` covers edge `e`".

Objective: minimize the sum of all `x`.

Constraints:

1. Each group has a membership: for every group `g`, `sum over c of x[c, g] >= 1`.
2. Each edge is covered: for every edge `e`, `sum over c of y[e, c] >= 1`.
3. Coverage needs both ends: `y[e, c] <= x[c, i]` and `y[e, c] <= x[c, j]`, for every `y[e, c]`.

Significant pairs have no constraint, and they need none: a membership `x[c, g]` is only ever made inside a clique of the non-significance graph, so two groups that share a letter are always adjacent. Conversely, constraint 2 forces every edge to share a letter, so the display preserves all relationships (checked again in section 8).

Variable order for the tie-break of section 5 is the `x` variables sorted by `(c, g)`: clique in canonical order, then group index ascending. The `y` variables have no order requirement; implementations may place them anywhere.

## 5. Canonical solve

Many graphs have several optimal coverings (the Piepho 2004 wheat example has 64). To make every implementation return the same one, the result is pinned:

> Among all optimal solutions (those with the minimum sum of `x`), return the one whose membership vector, read over the `x` variables in `(c, g)` order, is lexicographically greatest, with 1 greater than 0.

Equivalently: visiting the `x` variables in order, each is 1 whenever some optimal covering that agrees with all earlier choices has it at 1. The result does not depend on which optimum a solver returns.

**Procedure** (the sequential fixing procedure). The `y` variables are never fixed; the `x` fixings are bound changes (lower bound 1 or upper bound 0), not new rows.

1. Solve the model once. Let `z` be the rounded objective value and `S` the rounded `x` of the solution. This is the minimum.
2. Visit the `x` variables in `(c, g)` order. For variable `v`:
   1. If `S[v]` is 1, fix `v` to 1 (lower bound 1) and continue.
   2. If `S[v]` is 0, solve again with every earlier fixing, `v` fixed to 1, and the added limit `sum(x) <= z`. If the model is feasible, replace `S` with the new solution and fix `v` to 1. If it is infeasible, fix `v` to 0 (upper bound 0).
   3. Any other status in the re-solve is a solver error (section 6).
3. After the last variable, `S` is the answer. Every `x` is fixed, and `sum(x)` equals `z`.

The bound `sum(x) <= z` can be a column cost bound, an objective cutoff, or a row; the model for the re-solve may stay an optimization (minimize the sum of `x`) as long as the result is a feasible solution with `sum(x) = z`. All solves share the time budget and the checks of section 6.

The cost is one solve plus at most one extra solve per variable that is 0 in the current solution when visited. For the wheat example that is between 12 and 56 small solves.

## 6. Solver settings and checks

**Settings.** HiGHS is the solver in all three languages.

| Setting | R (`highs` 1.14) | Python (`highspy` >= 1.15.1) | JavaScript (`highs` >= 1.15.3) |
|---|---|---|---|
| presolve | off | on | on |
| `mip_rel_gap`, `mip_abs_gap` | 0 | 0 | 0 |
| `primal_feasibility_tolerance`, `mip_feasibility_tolerance` | 1e-9 | 1e-9 | 1e-9 |
| threads | 1 (the `highs_control()` default) | 1 | not set: the WebAssembly build is single threaded |
| solver log | off | off | off |
| `time_limit` | remaining budget, or none | same | same |

R keeps presolve off because the CRAN `highs` package bundles HiGHS 1.14, where presolve gave a wrong optimum on a small matrix in the sibling project turfLP. Python and JavaScript use HiGHS 1.15 and presolve on. Each of those two test suites also runs the whole conformance suite with presolve off, through an internal setting that is not part of the public API.

**Controls.** Both checks are solver errors, run after the method check of section 2 and before the cliques of section 3, `time_limit` first:

- `time_limit` is absent or a finite number greater than 0 (seconds; a boolean or a string is not a number): otherwise `time_limit must be positive when provided`.
- `max_cliques` is absent or a whole number of 1 or more (a boolean is not a number): otherwise the message starts with `max_cliques must be a positive integer or ` and ends with `None` (Python), `NULL` (R), or `null` (JavaScript).

**One budget.** `time_limit` is one budget for all solves in a call, measured from just before the first solve with a monotonic clock (R `proc.time()[["elapsed"]]`, Python `time.monotonic()`, JavaScript `performance.now() / 1000`). Each solve gets the time left as its HiGHS time limit. When no time is left before a solve starts, or HiGHS stops on the time limit, the call raises a solver error with the prefix `assignment-minimum MILP failed: ` and the text `Time limit reached`. The clique enumeration is not part of the budget.

**Checks after each solve.**

1. The model status must be optimal. For the re-solves of section 5, infeasible is also allowed and means "cannot set this variable to 1". With presolve on, HiGHS can report "unbounded or infeasible" for an infeasible model; no model here is unbounded, so that status counts as infeasible in the re-solves only. Any other status is a solver error with the prefix `assignment-minimum MILP failed: ` followed by the HiGHS status text. In the first solve, infeasible is also an error with that prefix.
2. Every `x` must be within 1e-6 of 0 or 1. Then `x` is rounded.
3. The rounded `x` must agree with the fixings made so far (fixed to 1 are 1, fixed to 0 are 0).
4. The rounded `x` must give every group a membership and cover every edge (some clique has both ends set to 1).
5. `sum(x)` must equal the rounded objective value on the first solve, and `z` on every later solve.

When check 2 to 5 fails, raise a solver error with the prefix `HiGHS returned an invalid solution`. The status text in check 1 is the text HiGHS uses for its model status (for example `Time limit reached`, `Infeasible`).

## 7. Letters

From the final `x`:

1. **Columns.** One column per clique; the members are the groups with `x[c, g] = 1`. Drop columns with no member. The columns keep the canonical clique order.
2. **Order.** Sort the columns with a stable sort over the canonical order. The key is:
   - with means: `(-m, i)`, where `m` is the highest mean among the column's selected members and `i` is the lowest index among them (ascending: higher highest mean first, then lower lowest index);
   - without means: `(i, i)`, where `i` is the lowest index among the selected members.
   Columns with equal keys stay in canonical clique order.
3. **Labels.** The sorted columns get the labels `A` to `Z`, then `AA`, `AB`, … `AZ`, `BA`, … (spreadsheet style: 26 one letter labels, then 676 two letter labels, then three letters).
4. **Tokens.** The tokens of a group are the labels of the columns it belongs to, in column order (label order, not text order: `AA` comes after `Z`). A group always has at least one token (constraint 1).
5. **Display.** The display of a group joins its tokens with no separator when every token has one character, otherwise with single spaces. `assignments` carries the tokens and is the safe machine form.

`num_letters_after` is the number of columns kept.

## 8. Check

Rebuild the relationships from the tokens: groups `i` and `j` share a letter when their token sets intersect, and every group shares with itself. The rebuilt matrix must equal the input adjacency. If it does not, raise a solver error with the message `optimized letters did not preserve the input pairwise relationships`. A returned result always has `relationship_preserved` true.

## 9. Result and statistics

| Field | Value |
|---|---|
| `letters` | group label to display string (section 7) |
| `assignments` | group label to tokens (section 7) |
| `groups` | group labels in group order |
| `method` | `"assignment_minimum"` |
| `relationship_preserved` | true |
| `adjacency` | the input matrix as booleans |
| `stats` | the table below |

Statistics (R and Python snake case, JavaScript camel case):

| R and Python | JavaScript | Value |
|---|---|---|
| `assignments_before` | `assignmentsBefore` | sum of the clique sizes (section 3) |
| `assignments_after` | `assignmentsAfter` | total number of tokens over all groups |
| `reduction_pct` | `reductionPct` | `(before - after) / before * 100` as an unrounded double; 0 when `before` is 0 |
| `num_letters_before` | `numLettersBefore` | number of maximal cliques |
| `num_letters_after` | `numLettersAfter` | number of columns kept |
| `num_groups` | `numGroups` | number of groups |
| `num_edges` | `numEdges` | number of edges `i < j` with adjacency true |
| `solver_status` | `solverStatus` | the text `Optimal` |
| `objective` | `objective` | the minimum `z`, a whole number equal to `assignments_after` |

`reduction_pct` is not rounded in any language: the IEEE operations give the same double everywhere, and rounding functions differ at ties. R's `print()` method and the example scripts round it to one decimal for display only.

## 10. Errors

There are two kinds in every language.

| Kind | Python | R condition classes | JavaScript |
|---|---|---|---|
| invalid input | `InvalidInputError` (subclass of `CLDReducerError` and `ValueError`) | `cldreducer_invalid_input`, `cldreducer_error`, `error`, `condition` | `InvalidInputError` (subclass of `CldReducerError`) |
| solver | `SolverError` (subclass of `CLDReducerError` and `RuntimeError`) | `cldreducer_solver_error`, `cldreducer_error`, `error`, `condition` | `SolverError` (subclass of `CldReducerError`) |

The message starts with the stable prefix of this document. Language specific parts (the formatting of lists and values) follow the prefix. The conformance error fixtures match kind and prefix only.

Invalid input error prefixes and messages, in one list:

- `post_hoc_results missing required columns: `
- `cannot coerce significance value to bool: `
- `post_hoc_results must not contain self-comparisons`
- `post_hoc_results contains duplicate unordered pairs: `
- `post_hoc_results contains groups not present in means/groups: `
- `post_hoc_results missing unordered pairwise comparisons: `
- `group labels must be unique after string conversion`
- `at least one group is required`
- `means must be a mapping, pandas Series, pandas DataFrame, or None` (meaning, not exact words, in R and JavaScript)
- `means DataFrame must have at least two columns or columns named group and mean` (meaning, not exact words, in R and JavaScript)
- `means are missing values for groups: `
- `means must be finite numbers`
- `adjacency must not contain missing values`
- `adjacency must contain only booleans or explicit 0/1 values`
- `adjacency must be a square matrix`
- `adjacency must contain at least one group`
- `adjacency must be symmetric`
- `adjacency diagonal must be `
- `number of groups must match adjacency dimensions`
- `unsupported CLD reduction method: `

Solver error prefixes and messages:

- `time_limit must be positive when provided`
- `max_cliques must be a positive integer or ` followed by `None`, `NULL`, or `null`
- `maximal clique enumeration exceeded max_cliques=`
- `assignment-minimum MILP failed: ` followed by the HiGHS status text
- `HiGHS returned an invalid solution`
- `optimized letters did not preserve the input pairwise relationships`

## 11. Public API

### Python

```python
from cld_reducer import (
    reduce_letters, reduce_from_adjacency,
    CLDReductionResult, CLDReducerError, InvalidInputError, SolverError,
)

def reduce_letters(post_hoc_results, means=None, *, method="assignment_minimum",
                   group1="group1", group2="group2", significant="significant",
                   time_limit=None, max_cliques=10_000) -> CLDReductionResult: ...

def reduce_from_adjacency(adjacency, groups=None, means=None, *,
                          method="assignment_minimum", time_limit=None,
                          max_cliques=10_000) -> CLDReductionResult: ...

@dataclass(frozen=True)
class CLDReductionResult:
    letters: dict[str, str]
    assignments: dict[str, tuple[str, ...]]
    stats: dict[str, Any]
    method: str
    groups: tuple[str, ...]
    relationship_preserved: bool
    adjacency: tuple[tuple[bool, ...], ...]
    def to_frame(self) -> pandas.DataFrame: ...   # columns group, letters, assignments
```

- `post_hoc_results` is a `pandas.DataFrame` or a sequence of mappings. `adjacency` is anything NumPy converts to a matrix. `max_cliques=None` removes the cap.
- `to_frame()` joins the tokens of a group with single spaces in `assignments`.
- The command line tool `cld-reduce` takes `pairs`, `--means`, `--out`, `--group1`, `--group2`, `--significant`, `--time-limit`, `--max-cliques`, `--no-max-cliques`, and `--method`, and writes the `to_frame()` columns plus one `stat_<name>` column per scalar statistic.

### R

```r
reduce_letters(pairs, means = NULL, group1 = "group1", group2 = "group2",
               significant = "significant", method = "assignment_minimum",
               time_limit = NULL, max_cliques = 10000L)
reduce_from_adjacency(adjacency, groups = NULL, means = NULL,
                      method = "assignment_minimum", time_limit = NULL,
                      max_cliques = 10000L)
```

- `pairs` is a data frame. `adjacency` is a logical or 0/1 numeric matrix. `max_cliques = NULL` removes the cap.
- The result has class `cld_reduction`, a list with `letters` (named character vector), `assignments` (named list of character vectors), `stats` (list), `method`, `groups`, `relationship_preserved`, and `adjacency` (logical matrix with group names). Methods: `print()` (rounds `reduction_pct` to one decimal for display) and `as.data.frame()` (columns `group`, `letters`, `assignments`, like Python `to_frame()`).
- Errors are R conditions with the classes of section 10.
- Data sets: `piepho2004_wheat` (190 rows), `simple_abc_pairs` (10 rows), and `simple_abc_means` (5 rows, columns `group` and `mean`).

### TypeScript

```ts
import {
  reduceLetters, reduceFromAdjacency, loadSolver,
  CldReducerError, InvalidInputError, SolverError,
  type CldReduction, type ReduceOptions,
} from "cld-reducer";

interface ReduceOptions {
  means?: Map<string, number> | ReadonlyArray<{ group: string; mean: number }>;
  method?: "assignment_minimum" | "assignment-minimum";
  timeLimit?: number;               // seconds, one budget for all solves
  maxCliques?: number | null;       // default 10000; null removes the cap
  group1?: string; group2?: string; significant?: string;   // pairs only
  groups?: readonly string[];       // adjacency only
}

interface CldReduction {
  letters: Record<string, string>;
  assignments: Record<string, string[]>;
  groups: string[];
  rows: { group: string; letters: string; assignments: string }[];  // tokens joined by spaces
  stats: {
    assignmentsBefore: number; assignmentsAfter: number; reductionPct: number;
    numLettersBefore: number; numLettersAfter: number; numGroups: number;
    numEdges: number; solverStatus: string; objective: number;
  };
  method: string;
  relationshipPreserved: boolean;
  adjacency: boolean[][];
}

function reduceLetters(pairs: ReadonlyArray<Record<string, unknown>>,
                       options?: ReduceOptions): Promise<CldReduction>;
function reduceFromAdjacency(adjacency: ReadonlyArray<ReadonlyArray<boolean | number>>,
                             options?: ReduceOptions): Promise<CldReduction>;
function loadSolver(options?: { locateFile?: (file: string) => string;
                                wasmBinary?: ArrayBuffer | Uint8Array;
                                wasmModule?: WebAssembly.Module }): Promise<void>;
```

- `letters` and `assignments` are plain objects keyed by group label; the order of groups is in `groups` and `rows`, because JavaScript puts integer-like keys first.
- The first call loads the WebAssembly solver; later calls reuse it. Concurrent first calls share one load, and a failed load is not cached. With `wasmBinary` or `wasmModule`, the solver loads from those bytes or that module and does not read or fetch `highs.wasm`. `loadSolver` is optional.
- The solve is synchronous inside the returned promise and blocks the JavaScript thread until it finishes; use a worker for large inputs.
- Errors are thrown as the three classes of section 10.

### Differences between the languages

- Only the spelling of names, result shape, and means forms differ (tables above); the results for the same input are the same groups, assignments, letters, and integer statistics.
- Presolve is off in R and on in Python and JavaScript (section 6).
- `time_limit` and `timeLimit` are seconds. Only JavaScript is asynchronous.
- Python accepts integer 0 and 1 for significance and also the floats 0.0 and 1.0 in adjacency; R and JavaScript accept any number equal to 0 or 1 in both.

## 12. Worked examples

**Simple ABC.** Five groups `"1"` to `"5"` with means 3.73, 3.57, 3.46, 3.33, 3.30. The non-significant pairs, by label, are `12 13 23 24 34 35 45`. By index (label minus 1), the maximal cliques in canonical order are `{0,1,2}`, `{1,2,3}`, `{2,3,4}`, so `assignments_before` is 9. Only the membership of group `"3"` (index 2) in the middle clique is optional, because the pair `24` needs only groups `"2"` and `"4"` there. The optimum is unique, `assignments_after` is 8, and the display is `{"1": "A", "2": "AB", "3": "AC", "4": "BC", "5": "C"}`. Group `"3"` drops the letter `B`.

**Canonical clique order renames letters.** Groups 0 to 4, no means, non-significant pairs `01 02 03 04 14 24`. The maximal cliques are `{0,1,4}`, `{0,2,4}`, `{0,3}`. Every membership is forced, so the optimum is unique with `assignments_before = assignments_after = 8`. Without means, the three columns all have the lowest member 0, so the stable sort keeps the canonical order and the letters are `A`, `B`, `C` for these cliques: group 0 gets `ABC`, group 1 `A`, group 2 `B`, group 3 `C`, group 4 `AB`. NetworkX 3.7 enumerates the cliques as `{0,3}`, `{0,1,4}`, `{0,2,4}`, and the 0.1.0 Python package gave group 3 the letter `A`. The canonical order changes that name. This is accepted as part of the canonical tie-break and listed in `NEWS.md`.

**Wheat.** The Piepho (2004) wheat example (20 treatments, 190 pairs) has 4 maximal cliques, 56 assignments in the maximal covering, a minimum of 44, and 64 optimal coverings. The canonical procedure picks one of the 64; its display is a conformance fixture.

## 13. Conformance

`conformance/` holds the inputs, a standard library Python generator that finds the expected results by exact search (never by a solver), and the fixtures. A result passes when the group order, assignments, letters, integer statistics, `solver_status`, and `objective` are equal to the fixture, `reduction_pct` equals `(before - after) / before * 100` computed from the fixture integers, and each error case matches kind and message prefix. Each runner (`python/tests/test_conformance.py`, `js/scripts/conformance.mjs`, `conformance/run_r.R`) runs the cases and first proves that its checker rejects a display that loses a relationship, a valid but non canonical optimum, and a non minimal display.
