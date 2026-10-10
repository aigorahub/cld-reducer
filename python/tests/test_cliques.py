from __future__ import annotations

import inspect
import itertools
import sys

import numpy as np
import pytest

from cld_reducer.cliques import maximal_cliques
from cld_reducer.exceptions import SolverError


def adjacency_of(size: int, edges: list[tuple[int, int]]) -> np.ndarray:
    matrix = np.eye(size, dtype=bool)
    for i, j in edges:
        matrix[i, j] = matrix[j, i] = True
    return matrix


def brute_force(matrix: np.ndarray) -> list[tuple[int, ...]]:
    size = matrix.shape[0]
    cliques = [
        subset
        for r in range(1, size + 1)
        for subset in itertools.combinations(range(size), r)
        if all(matrix[a, b] for a, b in itertools.combinations(subset, 2))
    ]
    return sorted(c for c in cliques if not any(set(c) < set(d) for d in cliques))


def test_canonical_order_of_the_renaming_example() -> None:
    matrix = adjacency_of(5, [(0, 1), (0, 2), (0, 3), (0, 4), (1, 4), (2, 4)])

    assert maximal_cliques(matrix, max_cliques=None) == [(0, 1, 4), (0, 2, 4), (0, 3)]


def test_isolated_groups_are_singleton_cliques() -> None:
    assert maximal_cliques(adjacency_of(3, [(0, 1)]), max_cliques=None) == [(0, 1), (2,)]


def test_complete_and_empty_graphs() -> None:
    assert maximal_cliques(np.ones((4, 4), dtype=bool), max_cliques=None) == [(0, 1, 2, 3)]
    assert maximal_cliques(np.eye(3, dtype=bool), max_cliques=None) == [(0,), (1,), (2,)]


@pytest.mark.parametrize("size", [4, 5])
def test_every_graph_matches_brute_force(size: int) -> None:
    pairs = list(itertools.combinations(range(size), 2))
    for mask in range(1 << len(pairs)):
        edges = [pair for k, pair in enumerate(pairs) if mask >> k & 1]
        matrix = adjacency_of(size, edges)
        assert maximal_cliques(matrix, max_cliques=None) == brute_force(matrix)


def test_random_graphs_match_brute_force() -> None:
    rng = np.random.default_rng(7)
    for _ in range(40):
        upper = np.triu(rng.random((9, 9)) < 0.55, k=1)
        matrix = upper | upper.T | np.eye(9, dtype=bool)
        assert maximal_cliques(matrix, max_cliques=None) == brute_force(matrix)


def test_cap_counts_cliques_and_allows_exactly_the_cap() -> None:
    matrix = np.eye(3, dtype=bool)

    assert len(maximal_cliques(matrix, max_cliques=3)) == 3
    with pytest.raises(SolverError, match="exceeded max_cliques=2"):
        maximal_cliques(matrix, max_cliques=2)


def test_enumeration_does_not_recurse() -> None:
    matrix = np.ones((250, 250), dtype=bool)
    old = sys.getrecursionlimit()
    # A recursive search would need about 250 frames; allow only 60 more than this test uses.
    sys.setrecursionlimit(len(inspect.stack()) + 60)
    try:
        cliques = maximal_cliques(matrix, max_cliques=None)
    finally:
        sys.setrecursionlimit(old)

    assert cliques == [tuple(range(250))]
