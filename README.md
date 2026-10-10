# cld-reducer

<!-- badges: start -->
[![R-CMD-check](https://github.com/aigorahub/cld-reducer/actions/workflows/R-CMD-check.yaml/badge.svg)](https://github.com/aigorahub/cld-reducer/actions/workflows/R-CMD-check.yaml)
[![python](https://github.com/aigorahub/cld-reducer/actions/workflows/python.yaml/badge.svg)](https://github.com/aigorahub/cld-reducer/actions/workflows/python.yaml)
[![js](https://github.com/aigorahub/cld-reducer/actions/workflows/js.yaml/badge.svg)](https://github.com/aigorahub/cld-reducer/actions/workflows/js.yaml)
[![conformance](https://github.com/aigorahub/cld-reducer/actions/workflows/conformance-r.yaml/badge.svg)](https://github.com/aigorahub/cld-reducer/actions/workflows/conformance-r.yaml)
<!-- badges: end -->

cld-reducer reduces compact letter displays (CLDs) while preserving the pairwise statistical relationships they encode. It comes as an R package (`cldreducer`, at the root of this repository), a Python package (`cld-reducer`, in [`python/`](python/)), and a JavaScript and TypeScript package (`cld-reducer`, in [`js/`](js/)). All three solve the problem with the HiGHS solver, follow one specification, and return the same display for the same input.

It implements the **assignment-minimum clique covering** problem introduced by Ennis, Fayle, and Ennis (2012): finding a CLD that uses the fewest possible individual letter-to-group assignments. The 2012 paper solves this problem with a backtracking algorithm (FIND-AM); this repository solves the same problem as a binary mixed-integer program with HiGHS. It is the implementation behind the CLD letter-reduction work presented at Sensometrics 2026.

See [submission status](docs/submission-status.md) for registry availability and [release instructions](docs/releasing.md) for the release process. The commands below install from the repository.

## Why reduce CLDs?

Compact Letter Displays are useful because two products that share at least one letter are not significantly different, while products with no shared letters are significantly different.

For large sensory studies, standard maximal-clique CLD algorithms often assign more letters than are needed to preserve those relationships. A sample labeled `ABC`, for example, may only need `AC` if the removed `B` does not change any pairwise significance relationship.

cld-reducer minimizes the total number of group-letter assignments and then checks that the reduced display reconstructs exactly the same relationship matrix as the input.

## Installation

```r
# install.packages("remotes")
remotes::install_github("aigorahub/cld-reducer")   # R
```

```sh
pip install "git+https://github.com/aigorahub/cld-reducer.git#subdirectory=python"   # Python 3.10 or later
```

The `#subdirectory=python` part is needed because the Python package lives in `python/`. The JavaScript package is built from `js/`; see [js/README.md](js/README.md). For registry releases, the commands are `install.packages("cldreducer")`, `pip install cld-reducer`, and `npm install cld-reducer`.

## Usage in R

Give `reduce_letters()` the complete pairwise results: one row for each pair of groups, with a logical column that tells whether the pair differs significantly. Missing pairs are rejected, so an accidental omission is not treated as a significant difference.

```r
library(cldreducer)

result <- reduce_letters(simple_abc_pairs, simple_abc_means)
result
#> Reduced compact letter display (assignment_minimum)
#>  group letters assignments
#>      1       A           A
#>      2      AB         A B
#>      3      AC         A C
#>      4      BC         B C
#>      5       C           C
#> Assignments: 9 -> 8 (11.1% fewer). Letters: 3 -> 3. Relationships preserved: TRUE.

result$letters
#>    1    2    3    4    5 
#>  "A" "AB" "AC" "BC"  "C"
```

The worked example reduces group 3 from `ABC` to `AC`. The `means` argument is optional; the means order the groups and the letters. If you already have the matrix of non-significant pairs, use `reduce_from_adjacency()`.

The package also contains the wheat yield example of Piepho (2004), as tabulated in Table 7 of Ennis, Fayle, and Ennis (2012): 20 treatments and 190 comparisons.

```r
wheat <- reduce_letters(piepho2004_wheat)
wheat$stats[c("assignments_before", "assignments_after", "num_letters_after")]
#> $assignments_before
#> [1] 56
#> 
#> $assignments_after
#> [1] 44
#> 
#> $num_letters_after
#> [1] 4
```

The 56 assignments of the maximal display reduce to 44 (21.4% fewer) with the same 4 letters, as in the paper.

## Usage in Python

```python
import pandas as pd

from cld_reducer import reduce_letters

# One row for each pair. True means the groups differ significantly.
pairs = pd.DataFrame(
    [
        ("1", "2", False),
        ("1", "3", False),
        ("1", "4", True),
        ("1", "5", True),
        ("2", "3", False),
        ("2", "4", False),
        ("2", "5", True),
        ("3", "4", False),
        ("3", "5", False),
        ("4", "5", False),
    ],
    columns=["group1", "group2", "significant"],
)
means = pd.DataFrame(
    {"group": ["1", "2", "3", "4", "5"], "mean": [3.73, 3.57, 3.46, 3.33, 3.30]}
)

result = reduce_letters(pairs, means)
print(result.letters)
# {'1': 'A', '2': 'AB', '3': 'AC', '4': 'BC', '5': 'C'}
```

This example works after package installation and needs no external files. The package also has a command line tool, `cld-reduce`. See [python/README.md](python/README.md).

## Usage in JavaScript

```js
import { reduceFromAdjacency } from "cld-reducer";

const result = await reduceFromAdjacency(
  [[1, 1, 0], [1, 1, 1], [0, 1, 1]],
  { groups: ["low", "mid", "high"] },
);
console.log(result.letters);
// { low: 'A', mid: 'AB', high: 'B' }
```

See [js/README.md](js/README.md) for the pairwise input, the options, and loading the WebAssembly solver in a browser.

## Method

The method is `assignment_minimum`.

1. Build the non-significance graph from the pairwise results.
2. Find all maximal cliques. Every assignment-minimum covering is a subcovering of the maximal covering, which is the starting point used by the 2012 paper.
3. Solve a binary mixed-integer program that selects group-letter assignments with the smallest total assignment count.
4. Among the displays with that smallest count, pick the canonical one: the display whose membership vector is lexicographically greatest in a fixed order. The wheat example has 64 displays with 44 assignments, and without a fixed rule different solvers would print different ones. The canonical rule makes the result independent of the solver and the language.
5. Rebuild the pairwise relationship matrix from the letters and return the result only if every original relationship is preserved.

Exact assignment minimization can become expensive for dense or highly structured graphs. All three packages offer a time limit and a cap on the number of maximal cliques (10,000 by default); the call stops with a clear error beyond the cap.

[docs/algorithm.md](docs/algorithm.md) is the normative specification: input rules, error messages, the canonical order, the solver settings, and the API of all three languages. The shared conformance suite in [conformance/](conformance/) has 1,422 reduce cases (plus 65 error cases and 18 label cases) with expected displays that come from an exact search in a standard-library Python script, not from a solver. R, Python, and JavaScript run all of them in CI. The Python and JavaScript runs repeat with HiGHS presolve off.

## Repository layout

| Path | Contents |
|---|---|
| `DESCRIPTION`, `R/`, `man/`, `tests/`, `data/` | R package `cldreducer` |
| `python/` | Python package `cld-reducer` (import name `cld_reducer`) |
| `js/` | npm package `cld-reducer` |
| `docs/algorithm.md` | Specification |
| `conformance/` | Fixtures, the generator, and the R runner |

## Citation

If you use this software, please cite the foundational paper that introduced the assignment-minimum clique covering problem:

> Ennis, J. M., Fayle, C. M., & Ennis, D. M. (2012). Assignment-Minimum Clique Coverings. *ACM Journal of Experimental Algorithmics*, 17, Article 1.5. https://doi.org/10.1145/2133803.2275596

You may additionally reference the talks that present this implementation:

> Ennis, J. M. (2019). Computational Advances in the Production of Compact Letter Displays. *Conference on Statistical Practice (CSP 2019)*, American Statistical Association, New Orleans, LA, February 14-16.

> Ennis, J., Graham, C., Castro, L., Lampert, R., Jordan, R., & Rios de Souza, V. (2026). Too many letters? Cutting through the sensory clutter with letter reduction algorithms. *Sensometrics 2026*, Valencia, Spain.

The wheat example is from Piepho, H.-P. (2004). An algorithm for a letter-based representation of all-pairwise comparisons. *Journal of Computational and Graphical Statistics*, 13(2), 456-466. https://doi.org/10.1198/1061860043515

See `CITATION.cff` for machine-readable citation metadata.

## License

MIT. See `LICENSE.md`.
