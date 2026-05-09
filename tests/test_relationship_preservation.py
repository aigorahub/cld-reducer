from __future__ import annotations

import numpy as np

from cld_reducer import reduce_from_adjacency
from cld_reducer.validation import reconstruct_adjacency_from_assignments


def test_all_significant_groups_get_distinct_letters() -> None:
    adjacency = np.eye(4, dtype=bool)

    result = reduce_from_adjacency(adjacency, groups=["A", "B", "C", "D"])

    assert result.stats["assignments_after"] == 4
    assert len(set(result.letters.values())) == 4
    assert result.relationship_preserved is True


def test_all_non_significant_groups_share_one_letter() -> None:
    adjacency = np.ones((4, 4), dtype=bool)

    result = reduce_from_adjacency(adjacency, groups=["A", "B", "C", "D"])

    assert result.letters == {"A": "A", "B": "A", "C": "A", "D": "A"}
    assert result.stats["assignments_after"] == 4
    assert result.stats["num_letters_after"] == 1
    assert result.relationship_preserved is True


def test_random_symmetric_graphs_preserve_relationships() -> None:
    rng = np.random.default_rng(20260509)

    for case_index in range(8):
        upper = rng.random((6, 6)) < 0.45
        adjacency = np.triu(upper, k=1)
        adjacency = adjacency | adjacency.T | np.eye(6, dtype=bool)
        groups = [f"G{case_index}_{index}" for index in range(6)]

        result = reduce_from_adjacency(adjacency, groups=groups)
        reconstructed = reconstruct_adjacency_from_assignments(result.assignments, groups)

        assert result.relationship_preserved is True
        assert np.array_equal(reconstructed, adjacency)
        assert result.stats["assignments_after"] <= result.stats["assignments_before"]
