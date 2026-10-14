"""Exact removal scans and their bounds at the solver boundary."""

from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest
from conftest import fixture_cases, needs_conformance
from test_solver import SIMPLE

from cld_reducer import SolverError, _solver, canonical, reduce_from_adjacency
from cld_reducer.context import graph_context
from cld_reducer.reduction import METHODS


@needs_conformance
@pytest.mark.parametrize("case", fixture_cases("essential"), ids=lambda c: c["id"])
def test_scan_matches_independent_boolean_deletion(case):
    adjacency = np.asarray(case["adjacency"], dtype=bool)
    cliques = [tuple(c) for c in case["cliques"]]
    context = graph_context(
        adjacency, list(map(str, range(len(adjacency)))), None, cliques, case["weights"]
    )
    for strategy, key in zip(METHODS, ["essential_sigma", "essential_c"], strict=True):
        model = strategy.builder(context)
        assert strategy.essential_decisions(model) == case[key]


@pytest.mark.parametrize("strategy", METHODS, ids=lambda s: s.name)
def test_essential_bounds_reach_every_solve(monkeypatch, strategy, presolve, reference_engine):
    calls = []
    real = _solver.run

    def run(problem, lower, upper, **options):
        calls.append((lower.copy(), upper.copy(), options["sum_limit"]))
        return real(problem, lower, upper, **options)

    monkeypatch.setattr(_solver, "run", run)
    result = reduce_from_adjacency(SIMPLE, method=strategy.name)
    if strategy.counts_assignments:
        required = [0, 1, 2, 3, 5, 6, 7, 8]
        assert calls[0][0].tolist() == [1, 1, 1, 1, 0, 1, 1, 1, 1] + [0] * 9
        assert result.stats["objective"] == 8
    else:
        required = [0, 1, 2]
        assert calls[0][0].tolist() == [1, 1, 1]
        assert result.stats["objective"] == 3
    assert calls[0][2] is None
    assert np.all(calls[0][1] == 1)
    assert all(np.all(lower[required] == 1) for lower, _, _ in calls)


@pytest.mark.parametrize("strategy", METHODS, ids=lambda s: s.name)
def test_required_bound_violation_on_first_solve_is_rejected(monkeypatch, strategy):
    # Keep coverage and objective consistent. Only the required bound check can reject this.
    model = SimpleNamespace(
        problem=_solver.Problem(
            num_cols=2,
            decision_columns=[0, 1],
            cost=np.ones(2),
            start=np.array([0, 2]),
            index=np.array([0, 1]),
            value=np.ones(2),
            row_lower=np.ones(1),
            row_upper=np.full(1, np.inf),
        )
    )
    custom = replace(
        strategy, coverage=lambda _, x: bool(x.any()), essential_decisions=lambda _: [0]
    )
    monkeypatch.setattr(
        _solver,
        "run",
        lambda *a, **k: _solver.Outcome(_solver.OPTIMAL, "Optimal", np.array([0.0, 1.0]), 1.0),
    )
    with pytest.raises(SolverError, match="HiGHS returned an invalid solution"):
        canonical._solve_canonical(model, None, custom, _certificate=False)


@pytest.mark.parametrize(
    "required", [None, [1], [-1], [3], [0.5], [True], [float("nan")], [2, 0], [0, 0], [[0]]]
)
def test_malformed_scan_stops_before_adapter(monkeypatch, required):
    problem = SimpleNamespace(num_cols=3, decision_columns=[2, 0])
    strategy = replace(METHODS[0], essential_decisions=lambda _: required)

    def forbidden(*a, **k):
        pytest.fail("invalid scan reached the adapter")

    monkeypatch.setattr(_solver, "run", forbidden)
    monkeypatch.setattr(canonical, "_essential_cover_certificate", forbidden)
    with pytest.raises(SolverError, match="HiGHS returned an invalid solution"):
        canonical._solve_canonical(SimpleNamespace(problem=problem), None, strategy)


@pytest.mark.parametrize("strategy", METHODS, ids=lambda s: s.name)
def test_scan_time_uses_existing_deadline(monkeypatch, strategy):
    now = [0.0]
    real_scan = strategy.essential_decisions

    def scan(model):
        now[0] += 10
        return real_scan(model)

    monkeypatch.setattr(canonical, "_now", lambda: now[0])
    monkeypatch.setattr(_solver, "run", lambda *a, **k: pytest.fail("expired scan reached adapter"))
    custom = replace(strategy, essential_decisions=scan)
    context = graph_context(SIMPLE, list("12345"), None, [(0, 1, 2), (1, 2, 3), (2, 3, 4)])
    with pytest.raises(SolverError, match="MILP failed: Time limit reached"):
        canonical._solve_canonical(custom.builder(context), 5, custom)
