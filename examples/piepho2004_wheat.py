"""Run the Piepho (2004) CIMMYT wheat yield experiment example.

Source: 20-treatment multi-environment wheat yield trial reported by Piepho
(2004), reproduced in Table 7 of Ennis, Fayle, & Ennis (2012),
"Assignment-Minimum Clique Coverings", ACM JEA 17, Art. 1.5
(https://doi.org/10.1145/2133803.2275596). The maximal covering has 4 cliques
and 56 letter assignments; the assignment-minimum reduction has 4 cliques and
44 letter assignments, matching the result reported in the paper.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from cld_reducer import reduce_letters


def main() -> None:
    example_dir = Path(__file__).resolve().parent
    pairs = pd.read_csv(example_dir / "piepho2004_wheat_pairs.csv")
    result = reduce_letters(pairs)

    print(result.to_frame().to_string(index=False))
    print()
    print(f"Groups:             {result.stats['num_groups']}")
    print(f"Non-sig edges:      {result.stats['num_edges']}")
    print(
        f"Letters:            {result.stats['num_letters_before']} "
        f"-> {result.stats['num_letters_after']}"
    )
    print(f"Assignments before: {result.stats['assignments_before']}")
    print(f"Assignments after:  {result.stats['assignments_after']}")
    print(f"Reduction:          {result.stats['reduction_pct']}%")
    print(f"Preserved:          {result.relationship_preserved}")


if __name__ == "__main__":
    main()
