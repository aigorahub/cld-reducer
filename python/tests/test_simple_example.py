from __future__ import annotations

import pandas as pd

from cld_reducer import reduce_letters


def simple_pairs() -> pd.DataFrame:
    groups = ["1", "2", "3", "4", "5"]
    non_significant = {
        ("1", "2"),
        ("1", "3"),
        ("2", "3"),
        ("2", "4"),
        ("3", "4"),
        ("3", "5"),
        ("4", "5"),
    }
    rows = []
    for index, group1 in enumerate(groups):
        for group2 in groups[index + 1 :]:
            rows.append(
                {
                    "group1": group1,
                    "group2": group2,
                    "significant": tuple(sorted((group1, group2))) not in non_significant,
                }
            )
    return pd.DataFrame(rows)


def simple_means() -> pd.Series:
    return pd.Series({"1": 3.73, "2": 3.57, "3": 3.46, "4": 3.33, "5": 3.30})


def test_simple_abc_assignment_reduces_to_ac() -> None:
    result = reduce_letters(simple_pairs(), simple_means())

    assert result.letters == {
        "1": "A",
        "2": "AB",
        "3": "AC",
        "4": "BC",
        "5": "C",
    }
    assert result.stats["assignments_before"] == 9
    assert result.stats["assignments_after"] == 8
    assert result.relationship_preserved is True


def test_result_can_be_converted_to_frame() -> None:
    result = reduce_letters(simple_pairs(), simple_means())

    frame = result.to_frame()

    assert frame.loc[frame["group"] == "3", "letters"].item() == "AC"
    assert set(frame.columns) == {"group", "letters", "assignments"}
