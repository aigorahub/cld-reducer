from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from cld_reducer import reduce_from_adjacency, reduce_letters
from cld_reducer.exceptions import InvalidInputError, SolverError
from cld_reducer.labels import make_letter_labels


def test_asymmetric_adjacency_is_rejected() -> None:
    adjacency = np.array(
        [
            [True, True],
            [False, True],
        ]
    )

    with pytest.raises(InvalidInputError, match="symmetric"):
        reduce_from_adjacency(adjacency, groups=["A", "B"])


def test_missing_adjacency_values_are_rejected() -> None:
    adjacency = np.array(
        [
            [True, np.nan],
            [np.nan, True],
        ]
    )

    with pytest.raises(InvalidInputError, match="must not contain missing values"):
        reduce_from_adjacency(adjacency, groups=["A", "B"])


def test_string_adjacency_values_are_rejected() -> None:
    adjacency = np.array(
        [
            ["True", "False"],
            ["False", "True"],
        ]
    )

    with pytest.raises(InvalidInputError, match="only booleans or explicit 0/1 values"):
        reduce_from_adjacency(adjacency, groups=["A", "B"])


def test_non_binary_adjacency_values_are_rejected() -> None:
    adjacency = np.array(
        [
            [1, 2],
            [2, 1],
        ]
    )

    with pytest.raises(InvalidInputError, match="only booleans or explicit 0/1 values"):
        reduce_from_adjacency(adjacency, groups=["A", "B"])


def test_missing_pairwise_columns_are_rejected() -> None:
    pairs = pd.DataFrame({"group1": ["A"], "group2": ["B"]})

    with pytest.raises(InvalidInputError, match="missing required columns"):
        reduce_letters(pairs)


def test_duplicate_pairwise_rows_are_rejected() -> None:
    pairs = pd.DataFrame(
        [
            {"group1": "A", "group2": "B", "significant": False},
            {"group1": "B", "group2": "A", "significant": False},
        ]
    )

    with pytest.raises(InvalidInputError, match="duplicate unordered pairs"):
        reduce_letters(pairs)


def test_missing_pairwise_rows_are_rejected() -> None:
    pairs = pd.DataFrame(
        [
            {"group1": "A", "group2": "B", "significant": False},
            {"group1": "A", "group2": "C", "significant": True},
        ]
    )

    with pytest.raises(InvalidInputError, match="missing unordered pairwise comparisons"):
        reduce_letters(pairs, means={"A": 3.0, "B": 2.0, "C": 1.0})


def test_complete_pairwise_rows_accept_mean_order() -> None:
    pairs = pd.DataFrame(
        [
            {"group1": "A", "group2": "B", "significant": False},
            {"group1": "A", "group2": "C", "significant": True},
            {"group1": "B", "group2": "C", "significant": False},
        ]
    )

    result = reduce_letters(pairs, means={"B": 2.0, "A": 3.0, "C": 1.0})

    assert result.relationship_preserved is True


def test_max_cliques_cap_fails_with_solver_error() -> None:
    adjacency = np.eye(3, dtype=bool)

    with pytest.raises(SolverError, match="max_cliques"):
        reduce_from_adjacency(adjacency, groups=["A", "B", "C"], max_cliques=2)


@pytest.mark.parametrize("time_limit", [0, -1, float("nan"), "30"])
def test_invalid_time_limit_is_rejected(time_limit: object) -> None:
    adjacency = np.eye(2, dtype=bool)

    with pytest.raises(SolverError, match="time_limit"):
        reduce_from_adjacency(adjacency, groups=["A", "B"], time_limit=time_limit)


@pytest.mark.parametrize("max_cliques", [0, -1, 1.5, True])
def test_invalid_max_cliques_is_rejected(max_cliques: object) -> None:
    adjacency = np.eye(2, dtype=bool)

    with pytest.raises(SolverError, match="max_cliques"):
        reduce_from_adjacency(adjacency, groups=["A", "B"], max_cliques=max_cliques)


def test_extended_letter_labels() -> None:
    labels = make_letter_labels(29)

    assert labels[:3] == ["A", "B", "C"]
    assert labels[25:] == ["Z", "AA", "AB", "AC"]
