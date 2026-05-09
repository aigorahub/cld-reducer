from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from cld_reducer import reduce_from_adjacency, reduce_letters
from cld_reducer.exceptions import InvalidInputError
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


def test_extended_letter_labels() -> None:
    labels = make_letter_labels(29)

    assert labels[:3] == ["A", "B", "C"]
    assert labels[25:] == ["Z", "AA", "AB", "AC"]
