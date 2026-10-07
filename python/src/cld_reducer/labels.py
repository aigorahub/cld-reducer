"""Letter-label utilities for compact letter displays."""

from __future__ import annotations


def make_letter_labels(count: int) -> list[str]:
    """Return spreadsheet-style uppercase labels: A..Z, AA..AZ, BA...

    Parameters
    ----------
    count:
        Number of labels to generate.
    """
    if count < 0:
        msg = "count must be non-negative"
        raise ValueError(msg)
    return [_label_at(index) for index in range(count)]


def _label_at(index: int) -> str:
    if index < 0:
        msg = "label index must be non-negative"
        raise ValueError(msg)

    alphabet_size = 26
    label = ""
    value = index
    while True:
        value, remainder = divmod(value, alphabet_size)
        label = chr(ord("A") + remainder) + label
        if value == 0:
            return label
        value -= 1
