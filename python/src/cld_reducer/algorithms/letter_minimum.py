"""Pure minimum-letter set cover over full maximal cliques."""

from dataclasses import dataclass

import numpy as np
from highspy import kHighsInf

from .. import _solver


@dataclass(frozen=True)
class Model:
    problem: _solver.Problem
    edges: list[tuple[int, int]]
    coverage_columns: list[list[int]]


def build_model(context):
    cliques = context.cliques
    rows = context.cliques_of + [
        [c for c in context.cliques_of[i] if j in cliques[c]] for i, j in context.edges
    ]
    starts = [0]
    indices = []
    for row in rows:
        indices.extend(row)
        starts.append(len(indices))
    n = len(cliques)
    return Model(
        _solver.Problem(
            num_cols=n,
            decision_columns=list(range(n)),
            cost=np.ones(n),
            start=np.asarray(starts, dtype=np.int32),
            index=np.asarray(indices, dtype=np.int32),
            value=np.ones(len(indices)),
            row_lower=np.ones(len(rows)),
            row_upper=np.full(len(rows), kHighsInf),
        ),
        context.edges,
        rows,
    )


def coverage(model, selected):
    return all(any(selected[k] for k in row) for row in model.coverage_columns)


def decode(cliques, model, selected):
    return [list(q) for q, on in zip(cliques, selected, strict=True) if on]
