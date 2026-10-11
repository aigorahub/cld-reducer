"""Weighted true twins, false twins, and the public default."""

import numpy as np

from cld_reducer import _solver, reduce_from_adjacency
from cld_reducer.canonical import _solve_canonical
from cld_reducer.reduction import METHODS
from cld_reducer.reduction_graph import reduce_graph


def test_only_closed_neighborhood_twins_are_merged():
    graph = np.array([[1, 1, 0, 0], [1, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]], bool)
    reduced = reduce_graph(graph)
    assert reduced.classes == [[0, 1], [2], [3]]
    assert reduced.weights == [2, 1, 1]
    assert np.array_equal(reduced.adjacency, np.eye(3, dtype=bool))
    assert reduced.expand([[0, 2]]) == [[0, 1, 3]]


def test_default_is_c_and_sigma_counts_original_vertices(presolve):
    graph = np.ones((5, 5), dtype=bool)
    default = reduce_from_adjacency(graph)
    assert default == reduce_from_adjacency(graph, method="letter_minimum")
    assert default.method == "letter_minimum"
    assert default.stats["objective"] == 1
    sigma = reduce_from_adjacency(graph, method="assignment_minimum")
    assert sigma.stats["objective"] == sigma.stats["assignments_after"] == 5
    assert sigma.stats["num_edges"] == 10


def test_cost_cap_uses_weights_during_canonical_trials(presolve):
    from types import SimpleNamespace

    problem = _solver.Problem(
        num_cols=3,
        decision_columns=[0, 1, 2],
        cost=np.array([5.0, 1.0, 1.0]),
        start=np.array([0, 2, 4], dtype=np.int32),
        index=np.array([0, 1, 0, 2], dtype=np.int32),
        value=np.ones(4),
        row_lower=np.ones(2),
        row_upper=np.full(2, np.inf),
    )
    from dataclasses import replace

    strategy = replace(METHODS[0], coverage=lambda _, x: (x[0] or x[1]) and (x[0] or x[2]))
    selected, minimum = _solve_canonical(SimpleNamespace(problem=problem), None, strategy)
    assert minimum == 2
    assert selected.tolist() == [False, True, True]
