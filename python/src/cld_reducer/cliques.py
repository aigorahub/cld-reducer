"""Maximal clique enumeration in the canonical order of docs/algorithm.md section 3."""

from __future__ import annotations

import numpy as np

from .exceptions import SolverError


def maximal_cliques(adjacency: np.ndarray, *, max_cliques: int | None) -> list[tuple[int, ...]]:
    """Return all maximal cliques as ascending index tuples, sorted lexicographically.

    `adjacency[i, j]` true means groups `i` and `j` are connected. The enumeration is
    Bron-Kerbosch with pivoting, written without recursion so that large graphs cannot
    exhaust the call stack. Only the set of cliques and the sorted order are part of the
    specification. With `max_cliques` set, the search stops with a `SolverError` as soon
    as it has found more than that many cliques.
    """
    size = adjacency.shape[0]
    neighbors = [set(np.flatnonzero(adjacency[i]).tolist()) - {i} for i in range(size)]
    found: list[tuple[int, ...]] = []

    def pivot_candidates(p: set[int], x: set[int]) -> list[int]:
        pivot = max(p | x, key=lambda u: len(p & neighbors[u]))
        return sorted(p - neighbors[pivot])

    everyone = set(range(size))
    # Each frame is [clique so far, candidates p, excluded x, vertices to branch on, next index].
    frames = [[(), everyone, set(), pivot_candidates(everyone, set()), 0]]
    while frames:
        frame = frames[-1]
        r, p, x, branch, position = frame
        if position >= len(branch):
            frames.pop()
            continue
        frame[4] = position + 1
        v = branch[position]
        child_r = (*r, v)
        child_p = p & neighbors[v]
        child_x = x & neighbors[v]
        p.discard(v)
        x.add(v)
        if not child_p and not child_x:
            found.append(tuple(sorted(child_r)))
            if max_cliques is not None and len(found) > max_cliques:
                msg = (
                    "maximal clique enumeration exceeded max_cliques="
                    f"{max_cliques}; increase max_cliques or pass None to disable the cap"
                )
                raise SolverError(msg)
        elif child_p:
            frames.append([child_r, child_p, child_x, pivot_candidates(child_p, child_x), 0])
    return sorted(found)
