"""Public API for CLD reduction."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import pandas as pd

from .algorithms.assignment_minimum import reduce_assignment_minimum
from .exceptions import InvalidInputError
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
        Reduction algorithm. Currently only `"assignment_minimum"` is supported.
    group1, group2, significant:
        Column names in `post_hoc_results`.
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
    return reduce_from_adjacency(adjacency, groups=groups, means=normalized_means, method=method)


def reduce_from_adjacency(
    adjacency: Any,
    groups: Sequence[Any] | None = None,
    means: Mapping[Any, float] | pd.Series | pd.DataFrame | None = None,
    *,
    method: str = "assignment_minimum",
) -> CLDReductionResult:
    """Reduce compact letters directly from a non-significance adjacency matrix.

    `adjacency[i, j] == True` means groups `i` and `j` are not significantly
    different and must share at least one letter in the returned CLD.
    """
    matrix, normalized_groups = validate_adjacency(adjacency, groups)
    normalized_means = normalize_means(means, normalized_groups)
    if method in {"assignment_minimum", "assignment-minimum"}:
        return reduce_assignment_minimum(
            matrix,
            normalized_groups,
            normalized_means,
            method="assignment_minimum",
        )
    msg = f"unsupported CLD reduction method: {method!r}"
    raise InvalidInputError(msg)
