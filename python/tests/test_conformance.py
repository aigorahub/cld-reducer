"""Run the shared conformance fixtures (conformance/fixtures) against the package."""

from __future__ import annotations

import json
from typing import Any

import numpy as np
import pandas as pd
import pytest
from conftest import CONFORMANCE, fixture_cases, needs_conformance

from cld_reducer import (
    InvalidInputError,
    SolverError,
    reduce_from_adjacency,
    reduce_letters,
)
from cld_reducer.labels import make_letter_labels

pytestmark = needs_conformance

REDUCE_CASES = fixture_cases("reduce")
ERROR_CASES = fixture_cases("errors")
LABEL_CASES = fixture_cases("labels")
EXPECTED_KINDS = {"invalid_input": InvalidInputError, "solver": SolverError}


def run_case(case: dict[str, Any]):
    options = dict(case["options"])
    means = case["input"].get("means")
    means_frame = pd.DataFrame(means) if means is not None else None
    if case["call"] == "pairs":
        pairs = pd.DataFrame(case["input"]["pairs"])
        return reduce_letters(pairs, means_frame, **options)
    matrix = np.array(case["input"]["adjacency"], dtype=object)
    return reduce_from_adjacency(matrix, case["input"].get("groups"), means_frame, **options)


def actual_of(result) -> dict[str, Any]:
    stats = result.stats
    return {
        "groups": list(result.groups),
        "assignments": {g: list(t) for g, t in result.assignments.items()},
        "letters": dict(result.letters),
        "stats": {
            key: stats[key]
            for key in (
                "assignments_before",
                "assignments_after",
                "num_letters_before",
                "num_letters_after",
                "num_groups",
                "num_edges",
            )
        },
        "solver_status": stats["solver_status"],
        "objective": stats["objective"],
        "reduction_pct": stats["reduction_pct"],
        "method": result.method,
        "relationship_preserved": result.relationship_preserved,
    }


def percent(parts: dict[str, int]) -> float:
    return parts["numerator"] / parts["denominator"] * 100


def mismatches(actual: dict[str, Any], expected: dict[str, Any]) -> list[str]:
    """The pass rule of conformance/README.md for one reduce case."""
    problems = []
    for key in ("groups", "assignments", "letters", "stats", "solver_status", "objective"):
        if actual[key] != expected[key]:
            problems.append(key)
    if actual["reduction_pct"] != percent(expected["reduction_pct"]):
        problems.append("reduction_pct")
    if actual["method"] != expected["method"]:
        problems.append("method")
    if actual["relationship_preserved"] is not True:
        problems.append("relationship_preserved")
    return problems


def as_actual(bad: dict[str, Any]) -> dict[str, Any]:
    out = dict(bad)
    out["reduction_pct"] = percent(bad["reduction_pct"])
    return out


def test_checker_rejects_wrong_results() -> None:
    wheat = next(c for c in REDUCE_CASES if c["id"] == "hand/wheat")
    expected = wheat["expected"]
    assert mismatches(as_actual(expected), expected) == []
    checker = json.loads((CONFORMANCE / "fixtures" / "checker.json").read_text(encoding="utf-8"))
    wrong = [wheat["non_canonical"]] + [b["result"] for b in checker["bad"]]
    assert len(wrong) == 3
    for bad in wrong:
        assert mismatches(as_actual(bad), expected) != []


@pytest.mark.parametrize("case", REDUCE_CASES, ids=[c["id"] for c in REDUCE_CASES])
def test_reduce_fixture(case: dict[str, Any], presolve: str) -> None:
    result = run_case(case)
    assert mismatches(actual_of(result), case["expected"]) == []


@pytest.mark.parametrize("case", ERROR_CASES, ids=[c["id"] for c in ERROR_CASES])
def test_error_fixture(case: dict[str, Any]) -> None:
    expected = case["expected"]
    with pytest.raises(EXPECTED_KINDS[expected["kind"]]) as caught:
        run_case(case)
    assert str(caught.value).startswith(expected["message_prefix"])
    if expected["kind"] == "invalid_input":
        assert not isinstance(caught.value, SolverError)


@pytest.mark.parametrize("case", LABEL_CASES, ids=[c["id"] for c in LABEL_CASES])
def test_label_fixture(case: dict[str, Any]) -> None:
    assert make_letter_labels(case["count"]) == case["labels"]
