"""Input rules and solution checks of docs/algorithm.md sections 1, 2, and 6 that the final
review (round 1) asked to pin: binary memberships, missing labels, duplicate mean labels,
ASCII-only trimming, zero rows, and label-exact pairs."""

from __future__ import annotations

import dataclasses

import numpy as np
import pandas as pd
import pytest

from cld_reducer import (
    InvalidInputError,
    SolverError,
    _solver,
    reduce_from_adjacency,
    reduce_letters,
)

SINGLETON = np.array([[True]])
PATH3 = np.array([[1, 1, 0], [1, 1, 1], [0, 1, 1]], dtype=bool)


def all_pairs(labels: list[str], nonsignificant: set[tuple[int, int]]) -> list[dict[str, object]]:
    return [
        {"group1": labels[i], "group2": labels[j], "significant": (i, j) not in nonsignificant}
        for i in range(len(labels))
        for j in range(i + 1, len(labels))
    ]


@pytest.mark.parametrize("value", [2.0, -1.0, np.inf], ids=["two", "minus-one", "infinite"])
def test_membership_outside_zero_and_one_is_invalid(monkeypatch: pytest.MonkeyPatch, value) -> None:
    real = _solver.run

    def wrapper(*args, **kwargs):
        outcome = real(*args, **kwargs)
        values = outcome.values.copy()
        values[0] = value
        return dataclasses.replace(outcome, values=values)

    monkeypatch.setattr(_solver, "run", wrapper)
    with pytest.raises(SolverError, match="HiGHS returned an invalid solution"):
        reduce_from_adjacency(SINGLETON)


def test_empty_adjacency_matrix_is_rejected() -> None:
    with pytest.raises(InvalidInputError, match="adjacency must contain at least one group"):
        reduce_from_adjacency(np.zeros((0, 0), dtype=bool))


@pytest.mark.parametrize(
    "means",
    [
        pd.DataFrame({"group": ["a", "b", "c", "a"], "mean": [1.0, 2.0, 3.0, 9.0]}),
        {"a": 1.0, "b": 2.0, "c": 3.0, 1: 4.0, "1": 5.0},
    ],
    ids=["repeated-label", "same-after-string-conversion"],
)
def test_duplicate_mean_labels_are_rejected_for_adjacency_input(means) -> None:
    with pytest.raises(InvalidInputError, match="means contain duplicate groups: "):
        reduce_from_adjacency(PATH3, ["a", "b", "c"], means)


@pytest.mark.parametrize("label", [None, float("nan"), pd.NA], ids=["none", "nan", "pandas-na"])
def test_missing_group_labels_are_rejected(label) -> None:
    rows = all_pairs(["a", "b", "c"], {(0, 1), (1, 2)})
    rows[1]["group2"] = label
    with pytest.raises(InvalidInputError, match="group labels must not be missing"):
        reduce_letters(rows)
    with pytest.raises(InvalidInputError, match="group labels must not be missing"):
        reduce_from_adjacency(np.eye(2, dtype=bool), ["a", label])


def test_missing_label_comes_before_significance() -> None:
    rows = all_pairs(["a", "b", "c"], set())
    rows[0]["significant"] = "maybe"
    rows[1]["group1"] = None
    with pytest.raises(InvalidInputError, match="group labels must not be missing"):
        reduce_letters(rows)


def test_zero_rows() -> None:
    assert reduce_letters([], {"a": 1.0}).letters == {"a": "A"}
    with pytest.raises(InvalidInputError, match="at least one group is required"):
        reduce_letters([])
    # A data frame has column names, and they are still required.
    with pytest.raises(InvalidInputError, match="post_hoc_results missing required columns"):
        reduce_letters(pd.DataFrame())


def test_significance_trimming_is_ascii_only() -> None:
    def rows(value: str) -> list[dict[str, object]]:
        return [{"group1": "a", "group2": "b", "significant": value}]

    assert reduce_letters(rows(" ns\t\r\n")).letters == {"a": "A", "b": "A"}
    with pytest.raises(InvalidInputError, match="cannot coerce significance value to bool: "):
        reduce_letters(rows("ns "))


@pytest.mark.parametrize("separator", ["\r", "\0", "|"])
def test_pairs_are_identified_by_exact_labels(separator: str) -> None:
    labels = ["a", f"b{separator}c", f"a{separator}b", "c"]
    rows = all_pairs(labels, {(0, 1), (1, 2), (2, 3)})
    result = reduce_letters(rows)
    assert list(result.letters) == ["a", f"b{separator}c", f"a{separator}b", "c"]
    with pytest.raises(InvalidInputError, match="missing unordered pairwise comparisons"):
        reduce_letters(rows[1:])


def test_empty_string_label() -> None:
    result = reduce_from_adjacency(np.eye(2, dtype=bool), ["", "b"])
    assert result.letters == {"": "A", "b": "B"}
    assert result.to_frame()["letters"].tolist() == ["A", "B"]
