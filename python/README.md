# cld-reducer for Python

Reduce compact letter displays (CLDs) while preserving the pairwise statistical relationships they encode. This is the Python package of the [cld-reducer repository](https://github.com/aigorahub/cld-reducer), which also holds an R package and a JavaScript package. The algorithm is the assignment-minimum clique covering of Ennis, Fayle, and Ennis (2012), <https://doi.org/10.1145/2133803.2275596>, written as a mixed-integer program for HiGHS. The rules every language follows are in `docs/algorithm.md`.

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
```

The public names are `reduce_letters`, `reduce_from_adjacency`, `CLDReductionResult`, `CLDReducerError`, `InvalidInputError`, and `SolverError`. The root README describes the inputs, the result, and the command line options.

## Examples

Run these from this folder:

```sh
python examples/simple_abc_to_ac.py
python examples/piepho2004_wheat.py
```

The CSV files in `examples/` are identical copies of the files in `conformance/data/` at the repository root.

## License

MIT. See `LICENSE`.
