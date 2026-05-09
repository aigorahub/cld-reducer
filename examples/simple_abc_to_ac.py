"""Run the simple CLD reduction example where ABC becomes AC."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from cld_reducer import reduce_letters


def main() -> None:
    example_dir = Path(__file__).resolve().parent
    pairs = pd.read_csv(example_dir / "simple_abc_to_ac_pairs.csv")
    means = pd.read_csv(example_dir / "simple_abc_to_ac_means.csv")
    result = reduce_letters(pairs, means)

    print(result.to_frame().to_string(index=False))
    print()
    print(f"Assignments before: {result.stats['assignments_before']}")
    print(f"Assignments after:  {result.stats['assignments_after']}")
    print(f"Reduction:          {result.stats['reduction_pct']}%")
    print(f"Preserved:          {result.relationship_preserved}")


if __name__ == "__main__":
    main()
