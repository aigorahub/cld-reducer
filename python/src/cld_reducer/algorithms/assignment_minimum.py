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


def _build_model(context) -> _Model:
    """Build the model of docs/algorithm.md section 4."""
    adjacency, cliques = context.adjacency, context.cliques
    num_groups = adjacency.shape[0]
    members = [(c, g) for c, clique in enumerate(cliques) for g in clique]
    x_index = {member: k for k, member in enumerate(members)}
    cliques_of = context.cliques_of
    edges = context.edges

    num_x = len(members)
    y_pairs: list[tuple[int, int]] = []  # (edge, clique)
    for e, (i, j) in enumerate(edges):
        shared = sorted(set(cliques_of[i]) & set(cliques_of[j]))
        y_pairs.extend((e, c) for c in shared)

    rows: list[list[tuple[int, float]]] = []
    row_lower: list[float] = []
    row_upper: list[float] = []
    # Every group is in at least one clique.
    for g in range(num_groups):
        rows.append([(x_index[(c, g)], 1.0) for c in cliques_of[g]])
        row_lower.append(1.0)
        row_upper.append(kHighsInf)
    # Every non-significant edge is covered by at least one clique that holds both ends.
    by_edge: dict[int, list[int]] = {}
    for k, (e, _) in enumerate(y_pairs):
        by_edge.setdefault(e, []).append(num_x + k)
    for e in range(len(edges)):
        rows.append([(col, 1.0) for col in by_edge[e]])
        row_lower.append(1.0)
        row_upper.append(kHighsInf)
    # A covering clique needs both ends: y <= x for each end.
    for k, (e, c) in enumerate(y_pairs):
        i, j = edges[e]
        for g in (i, j):
            rows.append([(num_x + k, 1.0), (x_index[(c, g)], -1.0)])
            row_lower.append(-kHighsInf)
            row_upper.append(0.0)

    start = [0]
    index: list[int] = []
    value: list[float] = []
    for row in rows:
        for col, coefficient in row:
            index.append(col)
            value.append(coefficient)
        start.append(len(index))
    num_cols = num_x + len(y_pairs)
    cost = np.zeros(num_cols)
    cost[:num_x] = [context.weights[g] for _, g in members]
    problem = _solver.Problem(
        num_cols=num_cols,
        decision_columns=list(range(num_x)),
        cost=cost,
        start=np.asarray(start, dtype=np.int32),
        index=np.asarray(index, dtype=np.int32),
        value=np.asarray(value, dtype=np.float64),
        row_lower=np.asarray(row_lower, dtype=np.float64),
        row_upper=np.asarray(row_upper, dtype=np.float64),
    )
    edge_ends: list[list[tuple[int, int]]] = [[] for _ in edges]
    for e, c in y_pairs:
        edge_ends[e].append((x_index[(c, edges[e][0])], x_index[(c, edges[e][1])]))
    return _Model(
        problem=problem,
        members=members,
        edges=edges,
        group_columns=[[x_index[(c, g)] for c in cliques_of[g]] for g in range(num_groups)],
        edge_ends=edge_ends,
    )


def _coverage(model: _Model, selected: np.ndarray) -> bool:
    return all(any(selected[k] for k in columns) for columns in model.group_columns) and all(
        any(selected[a] and selected[b] for a, b in ends) for ends in model.edge_ends
    )


def _selected_columns(
    cliques: list[tuple[int, ...]], model: _Model, selected: np.ndarray
) -> list[list[int]]:
    """Members of each clique's letter, dropping empty columns (canonical clique order)."""
    columns: list[list[int]] = [[] for _ in cliques]
    for k, (c, g) in enumerate(model.members):
        if selected[k]:
            columns[c].append(g)
    return [column for column in columns if column]
