# cld-reducer for Python

Reduce compact letter displays (CLDs) while preserving the pairwise statistical relationships they encode. This is the Python package of the [cld-reducer repository](https://github.com/aigorahub/cld-reducer), which also holds an R package and a JavaScript package. All three solve the assignment-minimum clique covering of Ennis, Fayle, and Ennis (2012), <https://doi.org/10.1145/2133803.2275596>, as a mixed-integer program with [HiGHS](https://highs.dev), and they return the same display for the same input. The rules they follow are in `docs/algorithm.md` in the repository.

The solver is HiGHS through `highspy`. The dependencies are `highspy`, NumPy, and pandas.

## Installation

The package is not on PyPI yet. Install it from the repository:

```sh
pip install "git+https://github.com/aigorahub/cld-reducer.git#subdirectory=python"
```

The `#subdirectory=python` part is needed because the Python package lives in `python/`. Python 3.10 or later. The module is `cld_reducer` and the command line tool is `cld-reduce`.

For development, work from this folder:

```sh
cd python
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
ruff check . && ruff format --check . && pytest
```

## Usage

```python
import pandas as pd

from cld_reducer import reduce_letters

pairs = pd.read_csv("examples/simple_abc_to_ac_pairs.csv")
means = pd.read_csv("examples/simple_abc_to_ac_means.csv")

result = reduce_letters(pairs, means)
print(result.letters)
# {'1': 'A', '2': 'AB', '3': 'AC', '4': 'BC', '5': 'C'}
print(result.to_frame())
#   group letters assignments
# 0     1       A           A
# 1     2      AB         A B
# 2     3      AC         A C
# 3     4      BC         B C
# 4     5       C           C
print(result.stats)
# {'assignments_before': 9, 'assignments_after': 8, 'reduction_pct': 11.11111111111111, 'num_letters_before': 3, 'num_letters_after': 3, 'num_groups': 5, 'num_edges': 7, 'solver_status': 'Optimal', 'objective': 8}
```

Run it from this folder. `reduce_letters` takes complete pairwise results: one row for each pair of groups, with a boolean column that tells whether the pair differs significantly. Missing pairs are rejected. `means` is optional and orders the groups and the letters. If you already have the non-significance matrix, use `reduce_from_adjacency`; there, `True` means two groups are not significantly different and must share a letter.

The result, a `CLDReductionResult`, has:

- `letters`: the display of each group, for example `"AC"` (tokens are joined with spaces after `Z`, as in `"Z AA"`)
- `assignments`: the letters of each group as a tuple, the safe machine-readable form
- `stats`: the counts before and after the reduction and the solver status; `reduction_pct` is not rounded
- `relationship_preserved`: always `True` for a returned result
- `to_frame()`: a tidy `pandas.DataFrame`

The public names are `reduce_letters`, `reduce_from_adjacency`, `CLDReductionResult`, `CLDReducerError`, `InvalidInputError`, and `SolverError`.

When several displays have the same, smallest number of assignments, the package returns the canonical one defined in `docs/algorithm.md`, so R, Python, and JavaScript agree. `time_limit` is one time budget in seconds for all solves of a call, and `max_cliques` (10,000 by default; `None` removes it) bounds the number of maximal cliques.

## Command line

```sh
cld-reduce examples/simple_abc_to_ac_pairs.csv \
  --means examples/simple_abc_to_ac_means.csv \
  --time-limit 30 \
  --out reduced.csv
```

The pairs file has the columns `group1`, `group2`, and `significant`; the optional means file has `group` and `mean`. The output CSV has the reduced letters and the summary statistics. Other flags: `--group1`, `--group2`, `--significant`, `--max-cliques`, `--no-max-cliques`, and `--method`.

## Examples

Run these from this folder:

```sh
python examples/simple_abc_to_ac.py
python examples/piepho2004_wheat.py
```

The CSV files in `examples/` are identical copies of the files in `conformance/data/` at the repository root.

## Changes in 0.2.0

The 0.2.0 release moved the package to `python/` and the solver to `highspy`, which can change the display for inputs with several minimal displays and can rename letters. See the root `NEWS.md` for the full list.

## License

MIT. See `LICENSE`.
