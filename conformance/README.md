# cld-reducer conformance suite

One set of fixtures binds the R, Python, and JavaScript implementations of cld-reducer. The expected results come from exact search in `generate.py`, never from a solver. `docs/algorithm.md` is the specification the implementations follow; this folder tests their observable results: the groups, the letter assignments, the display, and the integer statistics.

## Files

| Path | Contents |
|---|---|
| `data/*.csv` | The two example data sets (the Piepho 2004 wheat pairs, and the simple ABC pairs and means). `python/examples/` holds identical copies, and the R data sets are built from these files. |
| `inputs/*.json` | The graph catalog: `exhaustive-n1` to `exhaustive-n5`, `random-n06` to `random-n12`, and `structured`. Written by `generate.py`. |
| `manifest.json` | SHA-256 digest of every data file and input, case counts, and the excluded cases with reasons. |
| `generate.py` | Standard library Python. Builds the inputs, finds the expected results by exact search, and writes `inputs/`, `fixtures/`, and `manifest.json`. |
| `test_generate.py` | Hand-checked tests of the generator and the cross check against plain enumeration. |
| `fixtures/reduce.json` | Valid CLD-sigma calls and their expected results. |
| `fixtures/reduce_letter_minimum.json` | Valid CLD-C calls and their expected results. |
| `fixtures/reduce_weighted.json` | Weighted vertex reduction cases for both methods, including the C default. |
| `fixtures/errors.json` | Invalid calls and the expected error kind and message prefix. |
| `fixtures/labels.json` | Label counts and the expected labels. |
| `fixtures/checker.json` | Wrong wheat and CLD-C results that every runner's checker must reject. |
| `run_r.R` | Runs every fixture against the R package (added with the R package). |
| `../python/tests/test_conformance.py` | Runs every fixture against the Python package, with presolve on and off. |
| `../js/scripts/conformance.mjs` | Runs every fixture against the built JavaScript package, with presolve on and off. |

Commands, from the repository root:

```sh
python3 conformance/generate.py --check     # files are current; CSV copies match
python3 conformance/test_generate.py        # generator self-test and cross check
python3 conformance/generate.py --write     # after changing a recipe
```

On the development host (WSL, Python 3.14), `--check` takes about 22 seconds and `test_generate.py` about 41 seconds. After changing a recipe, run `--write` and commit the changed inputs, fixtures, and manifest together. `--check` reads text with line ends normalized, so it passes on Windows checkouts with CRLF.

## Case counts

| Fixture | Cases |
|---|---|
| `reduce.json` | 1422: 1099 exhaustive, 264 random, 24 structured, 35 hand-built |
| `reduce_letter_minimum.json` | 1442: the sigma input families, 16 further random graphs, 3 witnesses, 1 C alias |
| `reduce_weighted.json` | 30: 15 explicit sigma calls and 15 calls with the C default |
| `errors.json` | 65 |
| `labels.json` | 18 |
| `checker.json` | 5 wrong results: 2 wheat and 3 C results. The sixth result, the noncanonical wheat optimum, is in `reduce.json`. |

- **Exhaustive.** Every labeled graph with 1 to 5 groups: 1, 2, 8, 64, and 1024 graphs. Adjacency route with default group labels `"1"` to `"n"` and no means.
- **Random.** Seeded graphs with 6 to 12 groups (splitmix64; the seed and the edge probability are in each input). Forty candidates per size with edge probabilities from 0.25 to 0.85; 264 are kept (40, 40, 40, 40, 39, 36, and 29 for 6 to 12 groups). Labels are `T01`, `T02`, and so on. Even-numbered graphs use the pairs route (every fourth one with shuffled and flipped rows, so the group order comes from first appearance), odd-numbered ones the adjacency route (every fourth one with the means listed in another order than the groups). Two thirds have means.
- **Structured.** The usual shape of a real display: means 10 down in steps of 0.5, a pair is not significant when the means differ by at most 1 or 2, for 6, 8, 10, 12, 15, and 20 groups, with the groups in mean order and in a shuffled mean order. Pairs route.
- **Hand-built (`hand/`).** The simple ABC example (pairs with means, pairs without means, adjacency), the wheat example (190 pairs; 56 assignments before, 44 after, 4 letters after), the canonical clique order example (`hand/canonical-order-rename`, the D4 case: groups 0 to 4, non-significant pairs 01 02 03 04 14 24, where group 3 gets `C` and not `A`), a 28 group star (labels past `Z`), the complete and the empty graph, one group, one group from a table with zero rows, two groups, paths and cycles, `max_cliques` at the clique count, `null`, the default, and 3,000,000,000, labels with carriage returns, the empty-string label, the labels `"NaN"`, `"NA"`, `"null"`, and `"None"` (text, not missing values), the hyphenated method name, significance given in every accepted form, custom column names, extra columns, numeric labels, first-appearance group order, and means that fix the group order, tie, are negative or are large.
- **Weighted reduction.** Repeated vertices, interleaved classes, complete graphs, separate isolated classes, paths, cycles, and a witness where unit costs would give 23 expanded assignments instead of 19. The expected results come from exact search on the original graph.
- **Errors.** At least one case for every input rule of section 1, 2, and 6 of the specification, and for the order in which the checks run.

## Input and fixture format

Every fixture file has `schema_version` (1), `kind`, and `cases`, with one case per line.

**Graph inputs** (`inputs/*.json`) are `{"schema_version", "name", "source", "graphs"}`. A graph is `{"id", "n", "edges", "labels", "means", "route", ...}`: `edges` are the non-significant pairs as 0-based index pairs `[i, j]` with `i < j`; `labels` is a list or `null` (default labels); `means` is a list of `{"group", "mean"}` or `null`; `route` is `pairs` or `adjacency`. Random graphs also carry `seed` and `p`.

**Reduction cases** (`reduce.json`, `reduce_letter_minimum.json`, and `reduce_weighted.json`): `{"id", "call", "input", "options", "expected"}`.

- `call` is `pairs` or `adjacency`.
- `input` for `pairs` is `{"pairs": [row, ...], "means": ...}`. A row is an object with the keys `group1`, `group2`, `significant` (or the column names given in `options`); extra keys are ignored. The table has one column for every key that occurs in the rows. Group labels may be JSON strings or integers.
- `input` for `adjacency` is `{"adjacency": [[...]], "groups": ..., "means": ...}`: a matrix of 0 and 1 (and booleans), a list of labels or `null`, and means as above. Means are matched to groups by label.
- `means` is `null` or a list of `{"group", "mean"}` in the order that gives the group order (pairs route). Python passes a `pandas.DataFrame` with columns `group` and `mean`, R a data frame with those columns, and JavaScript the array.
- `options` holds only keys the call needs: `group1`, `group2`, `significant` (column names), `method`, `max_cliques` (an integer, or `null` for no cap; absent means the default 10000), `time_limit`.
- `expected`: `groups` (the group order), `assignments` (group to token list), `letters` (group to display), `stats` (`assignments_before`, `assignments_after`, `num_letters_before`, `num_letters_after`, `num_groups`, `num_edges`), `solver_status` (`"Optimal"`), `objective`, `reduction_pct` (`{"numerator": before - after, "denominator": before}`), `method`, and `relationship_preserved` (true). The normalized `method` is `assignment_minimum` or `letter_minimum`. The integer `objective` equals `assignments_after` for sigma or `num_letters_after` for C. JSON objects are unordered in some languages, so `groups` is the order.
- The wheat case also has `non_canonical`: a valid, minimal, but not canonical optimum in the same shape as `expected`.

**`errors.json`** cases: `{"id", "call", "input", "options", "expected": {"kind", "message_prefix"}}`. `kind` is `invalid_input` or `solver`. Inputs may hold `null`, strings, and numbers where the rule under test needs them.

**`labels.json`** cases: `{"id", "count", "labels"}`. The runner calls the implementation's label function: Python `cld_reducer.labels.make_letter_labels(count)`, R `make_letter_labels(count)` (internal, reached with `cldreducer:::`), JavaScript `makeLetterLabels(count)` from `dist/labels.js`.

**`checker.json`**: `{"case": "hand/wheat", "bad": [{"name", "result"}, ...], "letter_bad": [{"case", "name", "result"}, ...]}`. Each `result` has the shape of `expected`. Wheat negatives use the top-level `case`. Each C negative names its matching C case.

## Pass rule

A `reduce` case passes when the call returns without error and:

1. `groups` equals `expected.groups`, in order.
2. `assignments` and `letters` equal the expected values for every group.
3. The integer statistics and `objective` equal the expected values, and `solver_status` is `"Optimal"`.
4. `reduction_pct` equals `(before - after) / before * 100` computed in double precision from `expected.reduction_pct`. No rounding is applied.
5. `method` equals `expected.method` and `relationship_preserved` is true.

An `errors` case passes when the call fails with an error of the expected kind (Python `InvalidInputError` or `SolverError`; R conditions of class `cldreducer_invalid_input` or `cldreducer_solver_error`; the JavaScript classes `InvalidInputError` or `SolverError`) whose message starts with `message_prefix`. A `labels` case passes when the label list is equal.

**Checkers.** Each runner checks three wrong sigma results against the wheat `expected`: its `non_canonical` result and the `loses_relationship` and `not_minimal` results from `checker.json`. It also checks three wrong C results against their matching C cases. The checker must reject every wrong result and accept each expected result. The negative cases cover relationship loss, a noncanonical optimum, and a larger valid display for both methods.

## Exact search

`generate.py` has its own maximal clique code (Bron-Kerbosch with pivoting, then sorted), its own branch and bound for the minimum number of assignments, and its own version of the canonical procedure of section 5 of the specification, using the exact search instead of a solver. The input rules of sections 1, 2, and 6 are also written out in `generate.py`, and every `errors` case is first run through them, so a wrong expected prefix cannot reach a fixture.

`test_generate.py` checks the search against plain enumeration on every labeled graph with up to 6 groups (33,867 graphs, 251 million membership subsets for the 15 graphs in which 24 memberships are optional). For each graph, the enumeration finds the minimum and the lexicographically greatest optimal selection by trying every subset of the optional memberships, and the test requires the same minimum and the same selection from the search. One test pins the wheat result: 4 maximal cliques, 56 memberships, a minimum of 44, and 64 optimal coverings, one of which is the canonical one.

## Exclusions

`manifest.json` lists every excluded case with its reason.

- The sigma fixture excludes 16 random candidates because they have more than 70 membership variables (11 with 12 groups, 4 with 11 groups, 1 with 10 groups). The sigma exact search is too slow on them. The C fixture includes all 16 graphs. The exclusion rule depends only on the graph, so it is the same on every machine.
- Exhaustive graphs with 6 or more groups are not fixtures (32768 and 2097152 graphs); the cross check in `test_generate.py` covers all graphs with 6 groups.
- The adjacency rule "at least one group" cannot be reached from JSON (an empty list has no second dimension and gives the square matrix error), so it has no error fixture.

## CLD-C fixtures

`generate.py build()` emits `fixtures/reduce_letter_minimum.json` alongside the
byte-identical sigma `reduce.json`. All three runners also load `reduce_weighted.json`.
For frozen sigma records, they pass `assignment_minimum` when the method is absent.
In weighted records, an absent method tests the C default. C covers all valid
existing input families, including dense random
graphs excluded from the sigma reference, plus repository-contained witness graphs
and its alias. Every C expected result stores `letter_minimum`.

The C generator searches set covers over canonically sorted maximal cliques. Its
independent test enumerates nonempty vertex subsets, filters to maximal cliques,
then enumerates their covers. It compares cliques, minimum C, canonical decisions,
full columns, assignments and rendered output on all 33,867 labeled graphs with
one to six groups. K6 has one maximal clique and two subset states; no six-vertex
graph has more than nine maximal cliques. It never searches subsets of all
nonmaximal cliques. These are standard-library searches with no production imports.

`checker.json` retains the wheat negatives and adds C relationship-loss,
nonminimum-cover and minimum-but-noncanonical-cover records keyed to their matching
C fixture IDs. Each runner proves those expected records pass its same checker
before requiring rejection of the negatives. The manifest records C counts and
method-specific exclusions.
