"""Assignment-minimum compact letter display reduction."""

from __future__ import annotations

from dataclasses import dataclass
from math import inf, isfinite
from numbers import Integral, Real

import networkx as nx
import numpy as np
import pandas as pd
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import lil_matrix

from ..exceptions import SolverError
from ..labels import make_letter_labels
from ..result import CLDReductionResult
from ..validation import (
    count_assignments,
    normalize_means,
    reconstruct_adjacency_from_assignments,
    validate_adjacency,
)


@dataclass(frozen=True)
class _ModelVariables:
    x: dict[tuple[int, int], int]
    y: dict[tuple[int, int], int]
    count: int


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
        Optional solver time limit in seconds.
    max_cliques:
        Optional cap on maximal cliques to enumerate before failing with a
        controlled `SolverError`. Pass `None` to disable the cap.
    """
    adjacency, groups = validate_adjacency(adjacency, groups)
    means = normalize_means(means, groups)
    time_limit, max_cliques = _validate_solver_controls(time_limit, max_cliques)

    cliques = _maximal_cliques(adjacency, max_cliques=max_cliques)
    maximal_matrix = _membership_matrix(len(groups), cliques)
    assignments_before = int(maximal_matrix.sum())

    selected_matrix, solver_info = _solve_assignment_minimum(
        adjacency, maximal_matrix, time_limit=time_limit
    )
    selected_matrix = _drop_empty_columns(selected_matrix)
    assignments = _assign_letter_tokens(selected_matrix, groups, means)
    letters = {group: _format_letter_tokens(tokens) for group, tokens in assignments.items()}
    reconstructed = reconstruct_adjacency_from_assignments(assignments, groups)
    relationship_preserved = bool(np.array_equal(reconstructed, adjacency))
    if not relationship_preserved:
        msg = "optimized letters did not preserve the input pairwise relationships"
        raise SolverError(msg)

    assignments_after = count_assignments(assignments)
    reduction_pct = (
        (assignments_before - assignments_after) / assignments_before * 100
        if assignments_before
        else 0.0
    )
    stats = {
        "assignments_before": assignments_before,
        "assignments_after": int(assignments_after),
        "reduction_pct": round(reduction_pct, 1),
        "num_letters_before": int(maximal_matrix.shape[1]),
        "num_letters_after": int(selected_matrix.shape[1]),
        "num_groups": len(groups),
        "num_edges": int(np.triu(adjacency, k=1).sum()),
        **solver_info,
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


def _maximal_cliques(adjacency: np.ndarray, *, max_cliques: int | None) -> list[set[int]]:
    graph = nx.Graph()
    graph.add_nodes_from(range(adjacency.shape[0]))
    edge_indices = np.argwhere(np.triu(adjacency, k=1))
    graph.add_edges_from((int(i), int(j)) for i, j in edge_indices)
    cliques = []
    for clique in nx.find_cliques(graph):
        cliques.append(set(clique))
        if max_cliques is not None and len(cliques) > max_cliques:
            msg = (
                "maximal clique enumeration exceeded max_cliques="
                f"{max_cliques}; increase max_cliques or pass None to disable the cap"
            )
            raise SolverError(msg)
    return cliques


def _membership_matrix(num_groups: int, cliques: list[set[int]]) -> np.ndarray:
    matrix = np.zeros((num_groups, len(cliques)), dtype=bool)
    for clique_index, clique in enumerate(cliques):
        for group_index in clique:
            matrix[group_index, clique_index] = True
    return matrix


def _solve_assignment_minimum(
    adjacency: np.ndarray, maximal_matrix: np.ndarray, *, time_limit: float | None
) -> tuple[np.ndarray, dict[str, str | float]]:
    n_groups, n_cliques = maximal_matrix.shape
    edges = [(int(i), int(j)) for i, j in np.argwhere(np.triu(adjacency, k=1))]
    variables = _build_variables(maximal_matrix, edges)

    objective = np.zeros(variables.count)
    for variable_index in variables.x.values():
        objective[variable_index] = 1.0

    rows: list[dict[int, float]] = []
    lower_bounds: list[float] = []
    upper_bounds: list[float] = []

    # Every group must receive at least one letter.
    for group_index in range(n_groups):
        row: dict[int, float] = {}
        for clique_index in range(n_cliques):
            variable = variables.x.get((group_index, clique_index))
            if variable is not None:
                row[variable] = 1.0
        rows.append(row)
        lower_bounds.append(1.0)
        upper_bounds.append(inf)

    # Every non-significant edge must be covered by at least one shared letter.
    for edge_index, _edge in enumerate(edges):
        row = {}
        for key, variable in variables.y.items():
            if key[0] == edge_index:
                row[variable] = 1.0
        rows.append(row)
        lower_bounds.append(1.0)
        upper_bounds.append(inf)

    # A selected edge-cover variable requires both endpoint letter assignments.
    for (edge_index, clique_index), y_variable in variables.y.items():
        group_i, group_j = edges[edge_index]
        for group_index in (group_i, group_j):
            x_variable = variables.x[(group_index, clique_index)]
            rows.append({y_variable: 1.0, x_variable: -1.0})
            lower_bounds.append(-inf)
            upper_bounds.append(0.0)

    constraints = LinearConstraint(
        _sparse_rows(rows, variables.count),
        np.asarray(lower_bounds),
        np.asarray(upper_bounds),
    )
    result = milp(
        c=objective,
        integrality=np.ones(variables.count),
        bounds=Bounds(lb=np.zeros(variables.count), ub=np.ones(variables.count)),
        constraints=constraints,
        options={"time_limit": time_limit} if time_limit is not None else None,
    )
    if not result.success or result.x is None:
        msg = f"assignment-minimum MILP failed: {result.message}"
        raise SolverError(msg)

    selected = np.zeros_like(maximal_matrix, dtype=bool)
    for (group_index, clique_index), variable_index in variables.x.items():
        selected[group_index, clique_index] = result.x[variable_index] > 0.5

    return selected, {"solver_status": str(result.message), "objective": float(result.fun)}


def _build_variables(maximal_matrix: np.ndarray, edges: list[tuple[int, int]]) -> _ModelVariables:
    variable_index = 0
    x: dict[tuple[int, int], int] = {}
    for group_index in range(maximal_matrix.shape[0]):
        for clique_index in range(maximal_matrix.shape[1]):
            if maximal_matrix[group_index, clique_index]:
                x[(group_index, clique_index)] = variable_index
                variable_index += 1

    y: dict[tuple[int, int], int] = {}
    for edge_index, (group_i, group_j) in enumerate(edges):
        common_cliques = np.where(maximal_matrix[group_i] & maximal_matrix[group_j])[0]
        for clique_index in common_cliques:
            y[(edge_index, int(clique_index))] = variable_index
            variable_index += 1
    return _ModelVariables(x=x, y=y, count=variable_index)


def _sparse_rows(rows: list[dict[int, float]], num_columns: int):
    matrix = lil_matrix((len(rows), num_columns), dtype=float)
    for row_index, row in enumerate(rows):
        for column_index, value in row.items():
            matrix[row_index, column_index] = value
    return matrix.tocsc()


def _drop_empty_columns(matrix: np.ndarray) -> np.ndarray:
    keep = matrix.any(axis=0)
    return matrix[:, keep]


def _assign_letter_tokens(
    selected_matrix: np.ndarray,
    groups: list[str],
    means: pd.Series | None,
) -> dict[str, tuple[str, ...]]:
    column_order = sorted(
        range(selected_matrix.shape[1]),
        key=lambda column: _column_sort_key(selected_matrix[:, column], groups, means),
    )
    labels = make_letter_labels(len(column_order))
    column_to_label = {column: labels[index] for index, column in enumerate(column_order)}

    assignments: dict[str, tuple[str, ...]] = {}
    for group_index, group in enumerate(groups):
        group_columns = [column for column in column_order if selected_matrix[group_index, column]]
        assignments[group] = tuple(column_to_label[column] for column in group_columns)
    return assignments


def _format_letter_tokens(tokens: tuple[str, ...]) -> str:
    if all(len(token) == 1 for token in tokens):
        return "".join(tokens)
    return " ".join(tokens)


def _column_sort_key(
    column: np.ndarray,
    groups: list[str],
    means: pd.Series | None,
) -> tuple[float, int]:
    member_indices = np.where(column)[0]
    if means is not None:
        highest_mean = max(float(means[groups[index]]) for index in member_indices)
        return (-highest_mean, int(member_indices.min()))
    return (float(member_indices.min()), int(member_indices.min()))
