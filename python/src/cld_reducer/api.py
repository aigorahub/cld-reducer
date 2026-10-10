"""Public API for CLD reduction."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import pandas as pd

from .reduction import check_method, reduce_validated
from .result import CLDReductionResult
from .validation import (
    adjacency_from_pairs,
    groups_from_pairs,
    normalize_means,
    normalize_pairwise_frame,
    validate_adjacency,
)


def reduce_letters(
    post_hoc_results: pd.DataFrame | Sequence[Mapping[str, Any]],
    means: Mapping[Any, float] | pd.Series | pd.DataFrame | None = None,
    *,
    method: str = "assignment_minimum",
    group1: str = "group1",
    group2: str = "group2",
    significant: str = "significant",
    time_limit: float | None = None,
    max_cliques: int | None = 10_000,
) -> CLDReductionResult:
    """Reduce compact letter assignments from pairwise post-hoc results.

    Parameters
    ----------
    post_hoc_results:
        Pairwise comparison results. Each row must identify two groups and
        whether the comparison is statistically significant.
    means:
        Optional group means used for stable display ordering.
    method:
        CLD-sigma `"assignment_minimum"` (default) minimizes assignments.
        CLD-C `"letter_minimum"` minimizes full maximal-clique columns.
        Hyphenated aliases are accepted.
    group1, group2, significant:
        Column names in `post_hoc_results`.
    time_limit:
        Optional solver time limit in seconds.
    max_cliques:
        Optional cap on maximal cliques to enumerate before failing with a
        controlled solver error. Pass `None` to disable the cap.
    """
    frame = normalize_pairwise_frame(
        post_hoc_results,
        group1=group1,
        group2=group2,
        significant=significant,
    )
    groups = groups_from_pairs(frame, means)
    normalized_means = normalize_means(means, groups)
    adjacency = adjacency_from_pairs(frame, groups)
    return reduce_from_adjacency(
        adjacency,
        groups=groups,
        means=normalized_means,
        method=method,
        time_limit=time_limit,
        max_cliques=max_cliques,
    )


def reduce_from_adjacency(
    adjacency: Any,
    groups: Sequence[Any] | None = None,
    means: Mapping[Any, float] | pd.Series | pd.DataFrame | None = None,
    *,
    method: str = "assignment_minimum",
    time_limit: float | None = None,
    max_cliques: int | None = 10_000,
) -> CLDReductionResult:
    """Reduce compact letters directly from a non-significance adjacency matrix.

    `adjacency[i, j] == True` means groups `i` and `j` are not significantly
    different and must share at least one letter in the returned CLD.
    """
    matrix, normalized_groups = validate_adjacency(adjacency, groups)
    normalized_means = normalize_means(means, normalized_groups)
    strategy = check_method(method)
    return reduce_validated(
        matrix, normalized_groups, normalized_means, strategy, time_limit, max_cliques
    )
