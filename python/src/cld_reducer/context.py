"""Graph data shared by model builders."""

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Context:
    adjacency: np.ndarray
    groups: list[str]
    means: object
    cliques: list[tuple[int, ...]]
    edges: list[tuple[int, int]]
    cliques_of: list[list[int]]
    weights: list[int]


def graph_context(adjacency, groups, means, cliques, weights=None):
    n = len(groups)
    return Context(
        adjacency,
        groups,
        means,
        cliques,
        [(i, j) for i in range(n) for j in range(i + 1, n) if adjacency[i, j]],
        [[c for c, q in enumerate(cliques) if g in q] for g in range(n)],
        [1] * n if weights is None else weights,
    )
