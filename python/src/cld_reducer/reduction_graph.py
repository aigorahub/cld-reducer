"""Collapse identical closed neighborhoods and retain the original vertex map."""

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class ReductionGraph:
    adjacency: np.ndarray
    classes: list[list[int]]

    @property
    def weights(self) -> list[int]:
        return [len(group) for group in self.classes]

    def expand(self, columns) -> list[list[int]]:
        return [sorted(v for c in column for v in self.classes[c]) for column in columns]


def reduce_graph(adjacency: np.ndarray) -> ReductionGraph:
    """Lemma 2.5: use the diagonal so only adjacent true twins are merged."""
    by_row: dict[bytes, list[int]] = {}
    for vertex, row in enumerate(adjacency):
        by_row.setdefault(row.tobytes(), []).append(vertex)
    classes = list(by_row.values())
    representatives = [group[0] for group in classes]
    return ReductionGraph(adjacency[np.ix_(representatives, representatives)], classes)
