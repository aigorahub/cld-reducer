"""Result objects returned by CLD reduction."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class CLDReductionResult:
    """Optimized compact letter display and reduction metadata."""

    letters: dict[str, str]
    assignments: dict[str, tuple[str, ...]]
    stats: dict[str, Any]
    method: str
    groups: tuple[str, ...]
    relationship_preserved: bool
    adjacency: tuple[tuple[bool, ...], ...] = field(repr=False)

    def to_frame(self) -> pd.DataFrame:
        """Return the reduced letters and selected metadata as a DataFrame."""
        rows = []
        for group in self.groups:
            rows.append(
                {
                    "group": group,
                    "letters": self.letters[group],
                    "assignments": " ".join(self.assignments[group]),
                }
            )
        return pd.DataFrame(rows)
