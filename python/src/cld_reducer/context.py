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
    members: list[tuple[int, int]] | None = None
    group_columns: list[list[int]] | None = None


def graph_context(adjacency, groups, means, cliques, weights=None, assignments=False):
    n = len(groups)
    cliques_of = [[] for _ in range(n)]
    members = [] if assignments else None
    group_columns = [[] for _ in range(n)] if assignments else None
    for c, clique in enumerate(cliques):
        for g in clique:
            cliques_of[g].append(c)
            if assignments:
                group_columns[g].append(len(members))
                members.append((c, g))
    return Context(
        adjacency,
        groups,
        means,
        cliques,
        [(i, j) for i in range(n) for j in range(i + 1, n) if adjacency[i, j]],
        cliques_of,
        [1] * n if weights is None else weights,
        members,
        group_columns,
    )


def shared_positions(left, right):
    """Yield matching positions in two sorted clique incidence lists."""
    i = j = 0
    while i < len(left) and j < len(right):
        if left[i] == right[j]:
            yield i, j
            i += 1
            j += 1
        elif left[i] < right[j]:
            i += 1
        else:
            j += 1


@dataclass(frozen=True)
class DecisionPlan:
    """Coverage data in semantic decision order, without solver arrays."""

    context: Context
    cost: list[int]
    members: list[tuple[int, int]]
    group_columns: list[list[int]]
    edge_ends: list[list[tuple[int, int]]]
    coverage_columns: list[list[int]]

    @property
    def decision_count(self):
        return len(self.members) if self.members else len(self.context.cliques)
