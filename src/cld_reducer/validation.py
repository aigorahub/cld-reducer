"""Input normalization and relationship-preservation checks."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
import pandas as pd

from .exceptions import InvalidInputError


def normalize_groups(groups: Sequence[Any]) -> list[str]:
    """Normalize group labels to unique strings while preserving order."""
    normalized = [str(group) for group in groups]
    if len(set(normalized)) != len(normalized):
        msg = "group labels must be unique after string conversion"
        raise InvalidInputError(msg)
    if not normalized:
        msg = "at least one group is required"
        raise InvalidInputError(msg)
    return normalized


def normalize_means(
    means: Mapping[Any, float] | pd.Series | pd.DataFrame | None,
    groups: Sequence[str],
) -> pd.Series | None:
    """Normalize optional group means to a Series indexed by group label."""
    if means is None:
        return None

    if isinstance(means, pd.Series):
        series = means.copy()
    elif isinstance(means, pd.DataFrame):
        if {"group", "mean"}.issubset(means.columns):
            series = means.set_index("group")["mean"]
        elif len(means.columns) >= 2:
            series = means.set_index(means.columns[0])[means.columns[1]]
        else:
            msg = "means DataFrame must have at least two columns or columns named group and mean"
            raise InvalidInputError(msg)
    elif isinstance(means, Mapping):
        series = pd.Series(dict(means))
    else:
        msg = "means must be a mapping, pandas Series, pandas DataFrame, or None"
        raise InvalidInputError(msg)

    series.index = series.index.map(str)
    missing = [group for group in groups if group not in series.index]
    if missing:
        msg = f"means are missing values for groups: {missing}"
        raise InvalidInputError(msg)
    return pd.to_numeric(series.loc[list(groups)], errors="raise")


def normalize_pairwise_frame(
    post_hoc_results: pd.DataFrame | Sequence[Mapping[str, Any]],
    *,
    group1: str = "group1",
    group2: str = "group2",
    significant: str = "significant",
) -> pd.DataFrame:
    """Normalize pairwise post-hoc data to group1/group2/significant columns."""
    frame = pd.DataFrame(post_hoc_results).copy()
    required = {group1, group2, significant}
    missing = sorted(required.difference(frame.columns))
    if missing:
        msg = f"post_hoc_results missing required columns: {missing}"
        raise InvalidInputError(msg)

    normalized = frame[[group1, group2, significant]].rename(
        columns={group1: "group1", group2: "group2", significant: "significant"}
    )
    normalized["group1"] = normalized["group1"].map(str)
    normalized["group2"] = normalized["group2"].map(str)
    normalized["significant"] = normalized["significant"].map(_coerce_bool)

    same_group = normalized["group1"] == normalized["group2"]
    if same_group.any():
        msg = "post_hoc_results must not contain self-comparisons"
        raise InvalidInputError(msg)

    pairs = normalized.apply(lambda row: tuple(sorted((row["group1"], row["group2"]))), axis=1)
    if pairs.duplicated().any():
        duplicates = sorted(set(pairs[pairs.duplicated()].tolist()))
        msg = f"post_hoc_results contains duplicate unordered pairs: {duplicates}"
        raise InvalidInputError(msg)

    return normalized


def groups_from_pairs(
    frame: pd.DataFrame, means: Mapping[Any, float] | pd.Series | pd.DataFrame | None
) -> list[str]:
    """Infer group order from means when supplied, otherwise from pairwise rows."""
    if means is not None:
        if isinstance(means, pd.Series):
            return normalize_groups(means.index.tolist())
        if isinstance(means, pd.DataFrame):
            if "group" in means.columns:
                return normalize_groups(means["group"].tolist())
            if len(means.columns) >= 1:
                return normalize_groups(means.iloc[:, 0].tolist())
        if isinstance(means, Mapping):
            return normalize_groups(list(means.keys()))

    ordered: list[str] = []
    for group in pd.concat([frame["group1"], frame["group2"]], ignore_index=True):
        if group not in ordered:
            ordered.append(group)
    return normalize_groups(ordered)


def adjacency_from_pairs(frame: pd.DataFrame, groups: Sequence[str]) -> np.ndarray:
    """Build a non-significance adjacency matrix from normalized pairwise rows."""
    groups = normalize_groups(groups)
    group_to_index = {group: index for index, group in enumerate(groups)}
    adjacency = np.eye(len(groups), dtype=bool)

    unknown = sorted((set(frame["group1"]) | set(frame["group2"])).difference(group_to_index))
    if unknown:
        msg = f"post_hoc_results contains groups not present in means/groups: {unknown}"
        raise InvalidInputError(msg)

    observed_pairs = {
        tuple(sorted((row.group1, row.group2))) for row in frame.itertuples(index=False)
    }
    expected_pairs = {
        tuple(sorted((groups[index], groups[other_index])))
        for index in range(len(groups))
        for other_index in range(index + 1, len(groups))
    }
    missing_pairs = sorted(expected_pairs.difference(observed_pairs))
    if missing_pairs:
        msg = f"post_hoc_results missing unordered pairwise comparisons: {missing_pairs}"
        raise InvalidInputError(msg)

    for row in frame.itertuples(index=False):
        i = group_to_index[row.group1]
        j = group_to_index[row.group2]
        non_significant = not bool(row.significant)
        adjacency[i, j] = non_significant
        adjacency[j, i] = non_significant

    return adjacency


def validate_adjacency(
    adjacency: Any, groups: Sequence[Any] | None = None
) -> tuple[np.ndarray, list[str]]:
    """Validate and normalize a non-significance adjacency matrix."""
    matrix = _coerce_adjacency_matrix(adjacency)
    if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1]:
        msg = "adjacency must be a square matrix"
        raise InvalidInputError(msg)
    if matrix.shape[0] == 0:
        msg = "adjacency must contain at least one group"
        raise InvalidInputError(msg)
    if not np.array_equal(matrix, matrix.T):
        msg = "adjacency must be symmetric"
        raise InvalidInputError(msg)
    if not np.all(np.diag(matrix)):
        msg = "adjacency diagonal must be True"
        raise InvalidInputError(msg)

    if groups is None:
        normalized_groups = [str(index + 1) for index in range(matrix.shape[0])]
    else:
        normalized_groups = normalize_groups(groups)
        if len(normalized_groups) != matrix.shape[0]:
            msg = "number of groups must match adjacency dimensions"
            raise InvalidInputError(msg)

    return matrix, normalized_groups


def _coerce_adjacency_matrix(adjacency: Any) -> np.ndarray:
    raw = np.asarray(adjacency)
    matrix = np.empty(raw.shape, dtype=bool)
    try:
        missing = pd.isna(raw)
    except TypeError:
        missing = np.zeros(raw.shape, dtype=bool)
    if bool(np.asarray(missing).any()):
        msg = "adjacency must not contain missing values"
        raise InvalidInputError(msg)

    for index, value in np.ndenumerate(raw):
        if _is_explicit_bool_value(value):
            matrix[index] = bool(value)
        else:
            msg = "adjacency must contain only booleans or explicit 0/1 values"
            raise InvalidInputError(msg)
    return matrix


def _is_explicit_bool_value(value: Any) -> bool:
    return (
        isinstance(value, (bool, np.bool_))
        or (isinstance(value, (int, np.integer)) and value in {0, 1})
        or (isinstance(value, (float, np.floating)) and value in {0.0, 1.0})
    )


def reconstruct_adjacency_from_assignments(
    assignments: Mapping[str, Sequence[str]], groups: Sequence[str]
) -> np.ndarray:
    """Reconstruct pairwise sharing relationships from letter assignments."""
    matrix = np.eye(len(groups), dtype=bool)
    assignment_sets = {group: set(assignments[group]) for group in groups}
    for i, group_i in enumerate(groups):
        for j in range(i + 1, len(groups)):
            group_j = groups[j]
            shares_letter = bool(assignment_sets[group_i] & assignment_sets[group_j])
            matrix[i, j] = shares_letter
            matrix[j, i] = shares_letter
    return matrix


def count_assignments(assignments: Mapping[str, Sequence[str]]) -> int:
    """Count total letter assignments across all groups."""
    return sum(len(value) for value in assignments.values())


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, (int, np.integer)) and value in {0, 1}:
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "t", "yes", "y", "1", "significant"}:
            return True
        if normalized in {"false", "f", "no", "n", "0", "not significant", "ns"}:
            return False
    msg = f"cannot coerce significance value to bool: {value!r}"
    raise InvalidInputError(msg)
