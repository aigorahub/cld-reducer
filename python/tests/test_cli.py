from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from cld_reducer import InvalidInputError
from cld_reducer.cli import main


def test_cli_writes_reduced_letters(tmp_path: Path) -> None:
    pairs = tmp_path / "pairs.csv"
    means = tmp_path / "means.csv"
    output = tmp_path / "reduced.csv"

    pairs.write_text(
        "\n".join(
            [
                "group1,group2,significant",
                "1,2,false",
                "1,3,false",
                "1,4,true",
                "1,5,true",
                "2,3,false",
                "2,4,false",
                "2,5,true",
                "3,4,false",
                "3,5,false",
                "4,5,false",
            ]
        )
        + "\n",
        encoding="utf8",
    )
    means.write_text(
        "\n".join(
            [
                "group,mean",
                "1,3.73",
                "2,3.57",
                "3,3.46",
                "4,3.33",
                "5,3.30",
            ]
        )
        + "\n",
        encoding="utf8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "cld_reducer.cli",
            str(pairs),
            "--means",
            str(means),
            "--time-limit",
            "30",
            "--out",
            str(output),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert completed.stderr == ""
    reduced = pd.read_csv(output)
    row = reduced.loc[reduced["group"].astype(str) == "3"].iloc[0]
    assert row["letters"] == "AC"
    assert row["stat_assignments_before"] == 9
    assert row["stat_assignments_after"] == 8


@pytest.mark.parametrize("labels", [("001", "002"), ("NA", "NaN"), ("", "b")])
@pytest.mark.parametrize("custom", [False, True])
@pytest.mark.parametrize("mean_columns", [("group", "mean"), ("treatment", "group")])
def test_cli_preserves_labels(tmp_path, labels, custom, mean_columns):
    group1, group2, significant = (
        ("left", "right", "different") if custom else ("group1", "group2", "significant")
    )
    pairs, means, output = (tmp_path / name for name in ("pairs.csv", "means.csv", "out.csv"))
    pd.DataFrame({group1: [labels[0]], group2: [labels[1]], significant: [False]}).to_csv(
        pairs, index=False
    )
    pd.DataFrame({mean_columns[0]: labels, mean_columns[1]: [2.0, 1.0]}).to_csv(means, index=False)
    assert (
        main(
            [
                str(pairs),
                "--means",
                str(means),
                "--out",
                str(output),
                "--group1",
                group1,
                "--group2",
                group2,
                "--significant",
                significant,
            ]
        )
        == 0
    )
    frame = pd.read_csv(output, dtype=str, keep_default_na=False)
    assert frame["group"].tolist() == list(labels)
    assert frame["letters"].tolist() == ["A", "A"]


@pytest.mark.parametrize("mean", ["", "NaN", "inf", "not-a-number"])
def test_cli_rejects_invalid_means(tmp_path, mean):
    pairs, means, output = (tmp_path / name for name in ("pairs.csv", "means.csv", "out.csv"))
    pairs.write_text("group1,group2,significant\na,b,false\n")
    means.write_text(f"group,mean\na,{mean}\nb,1\n")
    with pytest.raises(InvalidInputError, match="means must be finite numbers"):
        main([str(pairs), "--means", str(means), "--out", str(output)])


def test_cli_rejects_missing_significance(tmp_path):
    pairs = tmp_path / "pairs.csv"
    pairs.write_text("group1,group2,significant\na,b,\n")
    with pytest.raises(InvalidInputError, match="cannot coerce significance"):
        main([str(pairs), "--out", str(tmp_path / "out.csv")])
