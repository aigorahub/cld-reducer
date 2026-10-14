"""Stable shared display formatting."""

import pandas as pd

from .labels import make_letter_labels


def _assign_letter_tokens(
    columns: list[list[int]],
    num_groups: int,
    means: pd.Series | None,
    groups: list[str],
) -> list[tuple[str, ...]]:
    order = sorted(range(len(columns)), key=lambda c: _column_sort_key(columns[c], groups, means))
    labels = make_letter_labels(len(order))
    tokens: list[list[str]] = [[] for _ in range(num_groups)]
    for label, column in zip(labels, order, strict=True):
        for group_index in columns[column]:
            tokens[group_index].append(label)
    return [tuple(value) for value in tokens]


def _format_letter_tokens(tokens: tuple[str, ...]) -> str:
    if all(len(token) == 1 for token in tokens):
        return "".join(tokens)
    return " ".join(tokens)


def _column_sort_key(
    members: list[int],
    groups: list[str],
    means: pd.Series | None,
) -> tuple[float, int]:
    lowest = min(members)
    if means is not None:
        highest_mean = max(float(means[groups[index]]) for index in members)
        return (-highest_mean, lowest)
    return (float(lowest), lowest)
