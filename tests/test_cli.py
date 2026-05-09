from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pandas as pd


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
