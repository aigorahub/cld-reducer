"""Pure minimum-letter set cover over full maximal cliques."""

from dataclasses import dataclass

import numpy as np
from highspy import kHighsInf

from .. import _solver
from ..context import DecisionPlan, shared_positions


@dataclass(frozen=True)
class Model:
    problem: _solver.Problem
    edges: list[tuple[int, int]]
    coverage_columns: list[list[int]]


def build_plan(context):
    rows = context.cliques_of + [
        [
            context.cliques_of[i][a]
            for a, _ in shared_positions(context.cliques_of[i], context.cliques_of[j])
        ]
        for i, j in context.edges
    ]
    return DecisionPlan(context, [1] * len(context.cliques), [], [], [], rows)


def build_model(context):
    return compile_plan(build_plan(context))


def compile_plan(plan):
    rows = plan.coverage_columns
    starts = [0]
    indices = []
    for row in rows:
        indices.extend(row)
        starts.append(len(indices))
    n = plan.decision_count
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
        plan.context.edges,
        rows,
    )


def coverage(model, selected):
    return all(any(selected[k] for k in row) for row in model.coverage_columns)


def essential_decisions(model):
    """A clique is required exactly when it uniquely covers a vertex or edge."""
    return sorted({row[0] for row in model.coverage_columns if len(row) == 1})


def decode(cliques, model, selected):
    return [list(q) for q, on in zip(cliques, selected, strict=True) if on]
