# cld-reducer

`cld-reducer` is a small Python package for reducing Compact Letter Displays
(CLDs) while preserving the pairwise statistical relationships encoded by the
display.

The first implementation formulates CLD reduction as an
assignment-minimum clique-covering problem and solves it with SciPy's HiGHS
mixed-integer programming backend. It is intended as a reference implementation
for the CLD letter-reduction work presented at Sensometrics 2026.

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

The current method is `assignment_minimum`.

1. Build the non-significance graph from pairwise post-hoc results.
2. Generate maximal cliques, equivalent to a conventional CLD starting point.
3. Solve a binary mixed-integer program that selects group-letter assignments
   with the smallest total assignment count.
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

If you use this package, please cite the repository and the associated
Sensometrics 2026 work:

> Ennis, J., Graham, C., Castro, L., Lampert, R., Jordan, R., & Rios de
> Souza, V. (2026). Too many letters? Cutting through the sensory clutter with
> letter reduction algorithms. Sensometrics 2026.

See `CITATION.cff` for machine-readable citation metadata.
