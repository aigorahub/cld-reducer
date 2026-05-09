# cld-reducer

`cld-reducer` is a small Python package for reducing Compact Letter Displays
(CLDs) while preserving the pairwise statistical relationships encoded by the
display.

It implements the **assignment-minimum clique covering** problem introduced by
Ennis, Fayle, and Ennis (2012) — the problem of finding a CLD that uses the
fewest possible individual letter-to-group assignments. The 2012 paper solves
this problem with a backtracking algorithm (FIND-AM); this package solves the
same problem with a binary mixed-integer program via SciPy's HiGHS backend, and
is the implementation behind the CLD letter-reduction work presented at
Sensometrics 2026.

## Why reduce CLDs?

Compact Letter Displays are useful because two products that share at least one
letter are not significantly different, while products with no shared letters
are significantly different.

For large sensory studies, standard maximal-clique CLD algorithms often assign
more letters than are needed to preserve those relationships. A sample labeled
`ABC`, for example, may only need `AC` if the removed `B` does not change any
pairwise significance relationship.

`cld-reducer` minimizes the total number of group-letter assignments and then
checks that the reduced display reconstructs exactly the same relationship
matrix as the input.

## Install

Until the package is published to PyPI, install it directly from GitHub:

```bash
python -m pip install git+https://github.com/aigorahub/cld-reducer.git
```

For local development:

```bash
git clone https://github.com/aigorahub/cld-reducer.git
cd cld-reducer
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

## Python API

Use `reduce_letters` with complete pairwise post-hoc results. Each row
identifies two groups and whether that comparison is statistically significant.
Missing unordered pairs are rejected so an accidental omission is not silently
treated as a significant difference.

```python
import pandas as pd

from cld_reducer import reduce_letters

pairs = pd.DataFrame(
    [
        {"group1": "1", "group2": "2", "significant": False},
        {"group1": "1", "group2": "3", "significant": False},
        {"group1": "1", "group2": "4", "significant": True},
        {"group1": "1", "group2": "5", "significant": True},
        {"group1": "2", "group2": "3", "significant": False},
        {"group1": "2", "group2": "4", "significant": False},
        {"group1": "2", "group2": "5", "significant": True},
        {"group1": "3", "group2": "4", "significant": False},
        {"group1": "3", "group2": "5", "significant": False},
        {"group1": "4", "group2": "5", "significant": False},
    ]
)
means = pd.Series({"1": 3.73, "2": 3.57, "3": 3.46, "4": 3.33, "5": 3.30})

result = reduce_letters(pairs, means)

print(result.letters)
print(result.stats)
print(result.to_frame())
```

The worked example reduces Sample 3 from `ABC` to `AC`:

```python
{"1": "A", "2": "AB", "3": "AC", "4": "BC", "5": "C"}
```

The returned `CLDReductionResult` includes:

- `letters`: display-ready CLD strings by group
- `assignments`: unambiguous letter-token tuples by group
- `stats`: counts before/after reduction and solver metadata
- `relationship_preserved`: `True` when the reduced display exactly preserves
  the input pairwise relationships
- `to_frame()`: a tidy `pandas.DataFrame`

If you already have a non-significance adjacency matrix, use
`reduce_from_adjacency`. In that matrix, `True` means two groups are not
significantly different and must share at least one letter. The adjacency input
must contain booleans or explicit `0`/`1` values; missing values and strings are
rejected.

When labels extend beyond `Z`, `letters` uses spaces to avoid ambiguous strings
such as `XYZAA`. The `assignments` tuple is always the safest machine-readable
representation.

## Example datasets

Two examples ship with the package:

- [`examples/simple_abc_to_ac.py`](examples/simple_abc_to_ac.py) — the 5-group
  toy example used in the Python API section above.
- [`examples/piepho2004_wheat.py`](examples/piepho2004_wheat.py) — the
  20-treatment CIMMYT wheat yield trial from Piepho (2004), reproduced in
  Table 7 of Ennis, Fayle, & Ennis (2012). Reduces 56 letter assignments to
  44 (21.4% reduction) using 4 letters, matching the result in the paper.

## CLI

Input pairwise CSV:

```csv
group1,group2,significant
1,2,false
1,3,false
1,4,true
```

Optional means CSV:

```csv
group,mean
1,3.73
2,3.57
3,3.46
```

Run:

```bash
cld-reduce examples/simple_abc_to_ac_pairs.csv \
  --means examples/simple_abc_to_ac_means.csv \
  --time-limit 30 \
  --out reduced.csv
```

The output CSV contains the reduced letters plus summary statistics.

## Method

The current method is `assignment_minimum`. It solves the assignment-minimum
clique covering problem defined in Ennis, Fayle, & Ennis (2012). The paper
shows that searching among clique-minimum coverings is *not* sufficient — there
are graphs whose unique assignment-minimum covering uses more cliques than the
clique-minimum covering — so a dedicated algorithm is needed.

1. Build the non-significance graph from pairwise post-hoc results.
2. Generate the maximal cover, the starting point used by the 2012 paper
   (every assignment-minimum covering is a subcovering of the maximal cover).
3. Solve a binary mixed-integer program that selects group-letter assignments
   with the smallest total assignment count. This replaces the `FIND-AM`
   backtracking algorithm of the 2012 paper with a MILP formulation solved by
   HiGHS, which lets us reuse a mature, presolve-equipped solver instead of a
   custom search.
4. Reconstruct the pairwise relationship matrix from the reduced assignments.
5. Return the result only if every original relationship is preserved.

Additional CLD algorithms can be added later under `cld_reducer.algorithms`
without changing the public package name.

Exact assignment minimization can become expensive for dense or highly
structured graphs. The API and CLI expose `time_limit` and `max_cliques`
controls; by default, maximal clique enumeration stops with a clear solver
error after 10,000 cliques.

## Development Checks

```bash
ruff format --check .
ruff check .
pytest
python -m build
python examples/simple_abc_to_ac.py
```

## Citation

If you use this package, please cite the foundational paper that introduced
the assignment-minimum clique covering problem:

> Ennis, J. M., Fayle, C. M., & Ennis, D. M. (2012). Assignment-Minimum Clique
> Coverings. *ACM Journal of Experimental Algorithmics*, 17, Article 1.5.
> https://doi.org/10.1145/2133803.2275596

You may additionally reference the talks that present this implementation:

> Ennis, J. M. (2019). Computational Advances in the Production of Compact
> Letter Displays. *Conference on Statistical Practice (CSP 2019)*, American
> Statistical Association, New Orleans, LA, February 14–16.

> Ennis, J., Graham, C., Castro, L., Lampert, R., Jordan, R., & Rios de Souza,
> V. (2026). Too many letters? Cutting through the sensory clutter with letter
> reduction algorithms. *Sensometrics 2026*, Valencia, Spain.

See `CITATION.cff` for machine-readable citation metadata.
