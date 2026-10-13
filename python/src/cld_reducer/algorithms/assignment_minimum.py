"""Assignment-minimum compact letter display reduction.

Solves the assignment-minimum clique covering problem defined in Ennis, Fayle,
& Ennis (2012), "Assignment-Minimum Clique Coverings", ACM JEA 17, Art. 1.5
(https://doi.org/10.1145/2133803.2275596). The paper uses a backtracking
algorithm (FIND-AM); this module solves the same problem as a binary
mixed-integer program with HiGHS, then picks the canonical optimum of
docs/algorithm.md section 5 so that every implementation returns the same display.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from numbers import Integral, Real

import numpy as np
import pandas as pd
from highspy import kHighsInf

from .. import _solver
from ..context import DecisionPlan, shared_positions
from ..exceptions import SolverError
from ..result import CLDReductionResult
from ..validation import (
    normalize_means,
    validate_adjacency,
)


@dataclass(frozen=True)
class _Model:
    problem: _solver.Problem
    members: list[tuple[int, int]]  # (clique, group) of each x variable, in canonical order
    edges: list[tuple[int, int]]
    group_columns: list[list[int]]  # x variables of each group
    edge_ends: list[list[tuple[int, int]]]  # per edge: the two x variables of each covering clique


def reduce_assignment_minimum(
    adjacency: np.ndarray,
    groups: list[str],
    means: pd.Series | None = None,
    *,
    method: str = "assignment_minimum",
    time_limit: float | None = None,
    max_cliques: int | None = 10_000,
) -> CLDReductionResult:
    """Run sigma; method remains an unchanged metadata label for compatibility."""
    from dataclasses import replace

    from ..reduction import METHODS, reduce_validated

    adjacency, groups = validate_adjacency(adjacency, groups)
    means = normalize_means(means, groups)
    result = reduce_validated(adjacency, groups, means, METHODS[0], time_limit, max_cliques)
    return replace(result, method=method)


def _validate_solver_controls(
    time_limit: float | None, max_cliques: int | None
) -> tuple[float | None, int | None]:
    if time_limit is not None and (
        isinstance(time_limit, bool)
        or not isinstance(time_limit, Real)
        or not isfinite(float(time_limit))
        or time_limit <= 0
    ):
        msg = "time_limit must be positive when provided"
        raise SolverError(msg)
    if max_cliques is not None and (
        isinstance(max_cliques, bool) or not isinstance(max_cliques, Integral) or max_cliques < 1
    ):
        msg = "max_cliques must be a positive integer or None"
        raise SolverError(msg)
    return (
        float(time_limit) if time_limit is not None else None,
        int(max_cliques) if max_cliques is not None else None,
    )


def build_plan(context):
    members, group_columns = context.members, context.group_columns
    if members is None:
        members = []
        group_columns = [[] for _ in context.groups]
        for c, clique in enumerate(context.cliques):
            for g in clique:
                group_columns[g].append(len(members))
                members.append((c, g))
    edge_ends = [
        [
            (group_columns[i][a], group_columns[j][b])
            for a, b in shared_positions(context.cliques_of[i], context.cliques_of[j])
        ]
        for i, j in context.edges
    ]
    return DecisionPlan(
        context, [context.weights[g] for _, g in members], members, group_columns, edge_ends, []
    )


def _build_model(context) -> _Model:
    """Legacy compiled-model entry point."""
    return compile_plan(build_plan(context))


def compile_plan(plan) -> _Model:
    """Compile the same BIP from coverage data, only when required."""
    num_x = len(plan.members)
    num_y = sum(map(len, plan.edge_ends))
    rows = [[(k, 1.0) for k in columns] for columns in plan.group_columns]
    row_lower = [1.0] * len(rows)
    row_upper = [kHighsInf] * len(rows)
    witness = num_x
    for ends in plan.edge_ends:
        rows.append([(witness + k, 1.0) for k in range(len(ends))])
        row_lower.append(1.0)
        row_upper.append(kHighsInf)
        witness += len(ends)
    witness = num_x
    for ends in plan.edge_ends:
        for pair in ends:
            for k in pair:
                rows.append([(witness, 1.0), (k, -1.0)])
                row_lower.append(-kHighsInf)
                row_upper.append(0.0)
            witness += 1
    start = [0]
    index = []
    value = []
    for row in rows:
        for col, coefficient in row:
            index.append(col)
            value.append(coefficient)
        start.append(len(index))
    cost = np.zeros(num_x + num_y)
    cost[:num_x] = plan.cost
    problem = _solver.Problem(
        num_cols=num_x + num_y,
        decision_columns=list(range(num_x)),
        cost=cost,
        start=np.asarray(start, dtype=np.int32),
        index=np.asarray(index, dtype=np.int32),
        value=np.asarray(value, dtype=np.float64),
        row_lower=np.asarray(row_lower, dtype=np.float64),
        row_upper=np.asarray(row_upper, dtype=np.float64),
    )
    return _Model(problem, plan.members, plan.context.edges, plan.group_columns, plan.edge_ends)


def _coverage(model: _Model, selected: np.ndarray) -> bool:
    return all(any(selected[k] for k in columns) for columns in model.group_columns) and all(
        any(selected[a] and selected[b] for a, b in ends) for ends in model.edge_ends
    )


def _essential_decisions(model: _Model) -> list[int]:
    """Exact single-deletion test on the full cover, using coverage alternatives."""
    required = {columns[0] for columns in model.group_columns if len(columns) == 1}
    for ends in model.edge_ends:
        if len(ends) == 1:
            required.update(ends[0])
    return sorted(required)


def _selected_columns(
    cliques: list[tuple[int, ...]], model: _Model, selected: np.ndarray
) -> list[list[int]]:
    """Members of each clique's letter, dropping empty columns (canonical clique order)."""
    columns: list[list[int]] = [[] for _ in cliques]
    for k, (c, g) in enumerate(model.members):
        if selected[k]:
            columns[c].append(g)
    return [column for column in columns if column]
