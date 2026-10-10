"""Solver settings and the failure paths of docs/algorithm.md section 6."""

from __future__ import annotations

import dataclasses
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from cld_reducer import SolverError, _solver, canonical, reduce_from_adjacency, reduce_letters

WHEAT_CSV = "piepho2004_wheat_pairs.csv"

EXPECTED_OPTIONS = {
    "mip_rel_gap": 0.0,
    "mip_abs_gap": 0.0,
    "primal_feasibility_tolerance": 1e-9,
    "mip_feasibility_tolerance": 1e-9,
    "threads": 1,
}

# Groups 1 to 5 of the simple example: the canonical solve needs at least two solves.
SIMPLE = np.array(
    [
        [1, 1, 1, 0, 0],
        [1, 1, 1, 1, 0],
        [1, 1, 1, 1, 1],
        [0, 1, 1, 1, 1],
        [0, 0, 1, 1, 1],
    ],
    dtype=bool,
)


def record_runs(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
    """Wrap the solver call and keep the HiGHS options read back after each solve."""
    seen: list[dict[str, object]] = []
    real = _solver.run

    def wrapper(*args, **kwargs):
        outcome = real(*args, **kwargs)
        seen.append(dict(_solver.last_options))
        return outcome

    monkeypatch.setattr(_solver, "run", wrapper)
    return seen


def test_every_solve_uses_the_documented_settings(
    monkeypatch: pytest.MonkeyPatch, presolve: str
) -> None:
    seen = record_runs(monkeypatch)

    reduce_from_adjacency(SIMPLE)

    assert len(seen) >= 2
    for options in seen:
        for name, value in EXPECTED_OPTIONS.items():
            assert options[name] == value, name
        assert options["presolve"] == presolve


def test_highs_version_is_reported() -> None:
    import highspy

    version = highspy.Highs().version()
    print("highspy HiGHS version", version)
    assert tuple(int(part) for part in version.split(".")[:2]) >= (1, 15)


def test_time_limit_is_passed_to_highs(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = record_runs(monkeypatch)

    reduce_from_adjacency(SIMPLE, time_limit=30)

    assert 0 < seen[0]["time_limit"] <= 30


def test_time_budget_is_shared_across_solves(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = {"now": 0.0}
    real = _solver.run
    limits: list[float | None] = []

    def wrapper(*args, **kwargs):
        limits.append(kwargs["time_limit"])
        outcome = real(*args, **kwargs)
        clock["now"] += 10.0  # every solve "takes" 10 seconds
        return outcome

    monkeypatch.setattr(canonical, "_now", lambda: clock["now"])
    monkeypatch.setattr(_solver, "run", wrapper)

    with pytest.raises(SolverError, match="assignment-minimum MILP failed: Time limit reached"):
        reduce_from_adjacency(SIMPLE, time_limit=5)

    # The first solve got the whole budget; the second would get -5 seconds, so it never ran.
    assert limits == [5.0]


def test_no_time_limit_means_no_deadline(monkeypatch: pytest.MonkeyPatch) -> None:
    limits: list[float | None] = []
    real = _solver.run

    def wrapper(*args, **kwargs):
        limits.append(kwargs["time_limit"])
        return real(*args, **kwargs)

    monkeypatch.setattr(_solver, "run", wrapper)

    reduce_from_adjacency(SIMPLE)

    assert limits and all(limit is None for limit in limits)


@pytest.mark.parametrize(
    ("status", "text"),
    [
        (_solver.FAILED, "Unbounded"),
        (_solver.TIME_LIMIT, "Time limit reached"),
        (_solver.INFEASIBLE, "Infeasible"),
    ],
)
def test_non_optimal_first_solve_raises_solver_error(
    monkeypatch: pytest.MonkeyPatch, status: str, text: str
) -> None:
    monkeypatch.setattr(_solver, "run", lambda *a, **k: _solver.Outcome(status, text))

    with pytest.raises(SolverError, match=f"assignment-minimum MILP failed: {text}"):
        reduce_from_adjacency(SIMPLE)


def test_non_optimal_later_solve_raises_solver_error(monkeypatch: pytest.MonkeyPatch) -> None:
    real = _solver.run
    calls = {"n": 0}

    def wrapper(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return real(*args, **kwargs)
        return _solver.Outcome(_solver.FAILED, "Memory limit reached")

    monkeypatch.setattr(_solver, "run", wrapper)

    with pytest.raises(SolverError, match="assignment-minimum MILP failed: Memory limit"):
        reduce_from_adjacency(SIMPLE)


def corrupt(outcome: _solver.Outcome, change) -> _solver.Outcome:
    values = outcome.values.copy()
    change(values)
    return dataclasses.replace(outcome, values=values)


@pytest.mark.parametrize(
    "change",
    [
        lambda v: v.__setitem__(slice(0, None), 0.0),  # nothing selected: groups uncovered
        lambda v: v.__setitem__(0, 0.5),  # fractional membership
        lambda v: v.__setitem__(0, np.nan),
        lambda v: v.__setitem__(slice(0, 9), 1.0),  # every membership: sum(x) is not the minimum
    ],
    ids=["all-zero", "fractional", "nan", "sum-differs-from-objective"],
)
def test_scripted_invalid_first_solution_raises(monkeypatch: pytest.MonkeyPatch, change) -> None:
    real = _solver.run
    monkeypatch.setattr(_solver, "run", lambda *a, **k: corrupt(real(*a, **k), change))

    with pytest.raises(SolverError, match="HiGHS returned an invalid solution"):
        reduce_from_adjacency(SIMPLE)


def wheat_pairs() -> pd.DataFrame:
    """The Piepho (2004) example: its canonical solve has feasible re-solves."""
    return pd.read_csv(Path(__file__).resolve().parents[1] / "examples" / WHEAT_CSV)


def test_wheat_needs_several_solves_and_matches_the_paper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = record_runs(monkeypatch)

    result = reduce_letters(wheat_pairs())

    assert result.stats["assignments_before"] == 56
    assert result.stats["assignments_after"] == 44
    assert result.stats["num_letters_after"] == 4
    assert len(seen) > 12


def first_solve_off_canonical(monkeypatch: pytest.MonkeyPatch):
    """Make the first solve return a minimal display other than the canonical one.

    HiGHS may return the canonical optimum of the wheat example at once, which would leave
    no feasible re-solve to test. A tiny extra cost on the early memberships moves the first
    solution away from it; the later solves are unchanged. Returns the solver function that
    was in place, for the test to wrap.
    """
    real = _solver.run

    def perturbed(problem, col_lower, col_upper, *, sum_limit=None, time_limit=None):
        if sum_limit is None:
            k = np.arange(len(problem.decision_columns))
            cost = problem.cost.copy()
            cost[problem.decision_columns] = 1 + 1e-3 * (len(problem.decision_columns) - k) / len(
                problem.decision_columns
            )
            problem = dataclasses.replace(problem, cost=cost)
        return real(problem, col_lower, col_upper, sum_limit=sum_limit, time_limit=time_limit)

    monkeypatch.setattr(_solver, "run", perturbed)
    return perturbed


def test_scripted_invalid_later_solution_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    real = first_solve_off_canonical(monkeypatch)
    calls = {"optimal_after_first": 0}

    def wrapper(*args, **kwargs):
        outcome = real(*args, **kwargs)
        if kwargs["sum_limit"] is not None and outcome.status == _solver.OPTIMAL:
            calls["optimal_after_first"] += 1
            return corrupt(outcome, lambda v: v.__setitem__(slice(0, None), 0.0))
        return outcome

    monkeypatch.setattr(_solver, "run", wrapper)

    with pytest.raises(SolverError, match="HiGHS returned an invalid solution"):
        reduce_letters(wheat_pairs())

    assert calls["optimal_after_first"] == 1


def test_solution_violating_a_fixing_is_invalid(monkeypatch: pytest.MonkeyPatch) -> None:
    real = first_solve_off_canonical(monkeypatch)

    def wrapper(problem, col_lower, col_upper, **kwargs):
        outcome = real(problem, col_lower, col_upper, **kwargs)
        if outcome.status == _solver.OPTIMAL and kwargs["sum_limit"] is not None:
            values = outcome.values.copy()
            fixed = problem.decision_columns[
                np.flatnonzero(col_lower[problem.decision_columns] > 0.5)[0]
            ]
            values[fixed] = 0.0  # report a membership fixed to one as zero
            return dataclasses.replace(outcome, values=values)
        return outcome

    monkeypatch.setattr(_solver, "run", wrapper)

    with pytest.raises(SolverError, match="HiGHS returned an invalid solution"):
        reduce_letters(wheat_pairs())


def test_solution_that_leaves_an_edge_uncovered_is_invalid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real = _solver.run

    def wrapper(problem, col_lower, col_upper, **kwargs):
        outcome = real(problem, col_lower, col_upper, **kwargs)
        if kwargs["sum_limit"] is None:
            # Drop the first membership that is selected but not needed to hold a group.
            values = outcome.values.copy()
            values[
                problem.decision_columns[np.flatnonzero(values[problem.decision_columns] > 0.5)[0]]
            ] = 0.0
            return dataclasses.replace(outcome, values=values)
        return outcome

    monkeypatch.setattr(_solver, "run", wrapper)

    with pytest.raises(SolverError, match="HiGHS returned an invalid solution"):
        reduce_from_adjacency(SIMPLE)


def test_stats_use_the_documented_status_and_unrounded_percentage() -> None:
    pairs = pd.DataFrame(
        [
            {"group1": "a", "group2": "b", "significant": False},
            {"group1": "a", "group2": "c", "significant": True},
            {"group1": "b", "group2": "c", "significant": False},
        ]
    )

    result = reduce_letters(pairs)

    assert result.stats["solver_status"] == "Optimal"
    assert result.stats["objective"] == result.stats["assignments_after"] == 4
    assert result.stats["reduction_pct"] == (4 - 4) / 4 * 100
    wide = reduce_from_adjacency(SIMPLE)
    assert wide.stats["reduction_pct"] == (9 - 8) / 9 * 100
    assert wide.stats["reduction_pct"] != round(wide.stats["reduction_pct"], 1)
