"""Assignment-minimum compact letter display reduction.

Solves the assignment-minimum clique covering problem defined in Ennis, Fayle,
& Ennis (2012), "Assignment-Minimum Clique Coverings", ACM JEA 17, Art. 1.5
(https://doi.org/10.1145/2133803.2275596). The paper uses a backtracking
algorithm (FIND-AM); this module solves the same problem as a binary
mixed-integer program with HiGHS, then picks the canonical optimum of
docs/algorithm.md section 5 so that every implementation returns the same display.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from math import isfinite
from numbers import Integral, Real

import numpy as np
import pandas as pd
from highspy import kHighsInf

from .. import _solver
from ..cliques import maximal_cliques
from ..exceptions import SolverError
from ..labels import make_letter_labels
from ..result import CLDReductionResult
from ..validation import (
    count_assignments,
    normalize_means,
    reconstruct_adjacency_from_assignments,
    validate_adjacency,
)

# The clock behind the shared time budget. Tests replace it.
_now = time.monotonic

_INTEGRALITY_TOLERANCE = 1e-6
_INVALID_SOLUTION = "HiGHS returned an invalid solution"


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
    """Reduce a CLD by minimizing total letter assignments.

    Parameters
    ----------
    adjacency:
        Symmetric boolean matrix where `True` means two groups are not
        significantly different and may share a letter.
    groups:
        Group labels in matrix order.
    means:
        Optional group means used only to produce stable, mean-ordered letters.
    method:
        Method label stored in the result metadata.
    time_limit:
        Optional time budget in seconds, shared by all solves of this call.
    max_cliques:
        Optional cap on maximal cliques to enumerate before failing with a
        controlled `SolverError`. Pass `None` to disable the cap.
    """
    adjacency, groups = validate_adjacency(adjacency, groups)
    means = normalize_means(means, groups)
    time_limit, max_cliques = _validate_solver_controls(time_limit, max_cliques)

    cliques = maximal_cliques(adjacency, max_cliques=max_cliques)
    model = _build_model(adjacency, cliques)
    selected, minimum = _solve_canonical(model, time_limit)
    columns = _selected_columns(cliques, model, selected)
    tokens = _assign_letter_tokens(columns, len(groups), means, groups)
    assignments = {group: tokens[index] for index, group in enumerate(groups)}
    letters = {group: _format_letter_tokens(value) for group, value in assignments.items()}
    reconstructed = reconstruct_adjacency_from_assignments(assignments, groups)
    if not np.array_equal(reconstructed, adjacency):
        msg = "optimized letters did not preserve the input pairwise relationships"
        raise SolverError(msg)

    assignments_before = len(model.members)
    assignments_after = count_assignments(assignments)
    reduction_pct = (
        (assignments_before - assignments_after) / assignments_before * 100
        if assignments_before
        else 0.0
    )
    stats = {
        "assignments_before": assignments_before,
        "assignments_after": int(assignments_after),
        "reduction_pct": reduction_pct,
        "num_letters_before": len(cliques),
        "num_letters_after": len(columns),
        "num_groups": len(groups),
        "num_edges": len(model.edges),
        "solver_status": "Optimal",
        "objective": minimum,
    }

    return CLDReductionResult(
        letters=letters,
        assignments=assignments,
        stats=stats,
        method=method,
        groups=tuple(groups),
        relationship_preserved=True,
        adjacency=tuple(tuple(bool(value) for value in row) for row in adjacency),
    )


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


def _build_model(adjacency: np.ndarray, cliques: list[tuple[int, ...]]) -> _Model:
    """Build the model of docs/algorithm.md section 4."""
    num_groups = adjacency.shape[0]
    members = [(c, g) for c, clique in enumerate(cliques) for g in clique]
    x_index = {member: k for k, member in enumerate(members)}
    cliques_of: list[list[int]] = [[] for _ in range(num_groups)]
    for c, clique in enumerate(cliques):
        for g in clique:
            cliques_of[g].append(c)
    edges = [(i, j) for i in range(num_groups) for j in range(i + 1, num_groups) if adjacency[i, j]]

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
    cost[:num_x] = 1.0
    problem = _solver.Problem(
        num_cols=num_cols,
        num_x=num_x,
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


def _solve_canonical(model: _Model, time_limit: float | None) -> tuple[np.ndarray, int]:
    """Solve once for the minimum, then fix the memberships in (clique, group) order.

    This is the sequential fixing procedure of docs/algorithm.md section 5. Returns the
    selected x variables (a boolean array) and the minimum number of assignments.
    """
    problem = model.problem
    num_x = problem.num_x
    deadline = _now() + time_limit if time_limit is not None else None
    col_lower = np.zeros(problem.num_cols)
    col_upper = np.ones(problem.num_cols)

    outcome = _solve(model, col_lower, col_upper, None, deadline)
    selected = _check_solution(model, outcome, col_lower, col_upper, None)
    minimum = int(round(float(outcome.objective)))
    selected_x = selected

    for v in range(num_x):
        if selected_x[v]:
            col_lower[v] = 1.0
            continue
        trial_lower = col_lower.copy()
        trial_lower[v] = 1.0
        outcome = _solve(model, trial_lower, col_upper, minimum, deadline)
        if outcome.status == _solver.INFEASIBLE:
            col_upper[v] = 0.0
            continue
        selected_x = _check_solution(model, outcome, trial_lower, col_upper, minimum)
        col_lower = trial_lower
    return selected_x, minimum


def _solve(
    model: _Model,
    col_lower: np.ndarray,
    col_upper: np.ndarray,
    sum_limit: int | None,
    deadline: float | None,
) -> _solver.Outcome:
    remaining = None
    if deadline is not None:
        remaining = deadline - _now()
        if remaining <= 0:
            msg = "assignment-minimum MILP failed: Time limit reached"
            raise SolverError(msg)
    outcome = _solver.run(
        model.problem, col_lower, col_upper, sum_limit=sum_limit, time_limit=remaining
    )
    if outcome.status == _solver.INFEASIBLE and sum_limit is not None:
        return outcome
    if outcome.status != _solver.OPTIMAL:
        msg = f"assignment-minimum MILP failed: {outcome.text}"
        raise SolverError(msg)
    return outcome


def _check_solution(
    model: _Model,
    outcome: _solver.Outcome,
    col_lower: np.ndarray,
    col_upper: np.ndarray,
    expected_sum: int | None,
) -> np.ndarray:
    """Docs/algorithm.md section 6, checks 2 to 5. Returns the rounded x as booleans."""
    num_x = model.problem.num_x
    values = outcome.values
    if values is None or len(values) != model.problem.num_cols:
        raise SolverError(_INVALID_SOLUTION)
    x = np.asarray(values[:num_x], dtype=np.float64)
    # Each membership must be 0 or 1 within the tolerance; an integral 2 or -1 is invalid too.
    near_zero = np.abs(x) <= _INTEGRALITY_TOLERANCE
    near_one = np.abs(x - 1.0) <= _INTEGRALITY_TOLERANCE
    if not np.all(np.isfinite(x) & (near_zero | near_one)):
        raise SolverError(_INVALID_SOLUTION)
    rounded = x > 0.5
    if np.any(rounded & (col_upper[:num_x] < 0.5)) or np.any(~rounded & (col_lower[:num_x] > 0.5)):
        raise SolverError(_INVALID_SOLUTION)
    for columns in model.group_columns:
        if not any(rounded[k] for k in columns):
            raise SolverError(_INVALID_SOLUTION)
    for ends in model.edge_ends:
        if not any(rounded[a] and rounded[b] for a, b in ends):
            raise SolverError(_INVALID_SOLUTION)
    total = int(rounded.sum())
    wanted = expected_sum if expected_sum is not None else int(round(float(outcome.objective)))
    if total != wanted:
        raise SolverError(_INVALID_SOLUTION)
    return rounded


def _selected_columns(
    cliques: list[tuple[int, ...]], model: _Model, selected: np.ndarray
) -> list[list[int]]:
    """Members of each clique's letter, dropping empty columns (canonical clique order)."""
    columns: list[list[int]] = [[] for _ in cliques]
    for k, (c, g) in enumerate(model.members):
        if selected[k]:
            columns[c].append(g)
    return [column for column in columns if column]


def _assign_letter_tokens(
    columns: list[list[int]],
    num_groups: int,
    means: pd.Series | None,
    groups: list[str],
) -> list[tuple[str, ...]]:
    order = sorted(range(len(columns)), key=lambda c: _column_sort_key(columns[c], groups, means))
    labels = make_letter_labels(len(order))
    tokens: list[list[str]] = [[] for _ in range(num_groups)]
    for label, column in zip(labels, order, strict=True):
        for group_index in columns[column]:
            tokens[group_index].append(label)
    return [tuple(value) for value in tokens]


def _format_letter_tokens(tokens: tuple[str, ...]) -> str:
    if all(len(token) == 1 for token in tokens):
        return "".join(tokens)
    return " ".join(tokens)


def _column_sort_key(
    members: list[int],
    groups: list[str],
    means: pd.Series | None,
) -> tuple[float, int]:
    lowest = min(members)
    if means is not None:
        highest_mean = max(float(means[groups[index]]) for index in members)
        return (-highest_mean, lowest)
    return (float(lowest), lowest)
