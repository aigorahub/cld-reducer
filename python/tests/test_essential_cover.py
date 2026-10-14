"""Certificate proof conditions and equality with the canonical solver reference."""

from dataclasses import replace
from functools import partial
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from conftest import needs_conformance
from test_conformance import REDUCE_CASES, actual_of, mismatches, run_case
from test_solver import SIMPLE

from cld_reducer import SolverError, _solver, canonical, reduce_from_adjacency, reduction
from cld_reducer.cliques import maximal_cliques
from cld_reducer.context import graph_context
from cld_reducer.reduction import METHODS


def sparse_model(strategy):
    """Decision order differs from column order; auxiliary column 1 is forced on."""
    problem = _solver.Problem(
        num_cols=5,
        decision_columns=[4, 0, 2],
        cost=np.array([7.0, 0.0, 11.0, 0.0, 3.0]),
        start=np.array([0, 1, 2, 3], dtype=np.int32),
        index=np.array([0, 4, 1], dtype=np.int32),
        value=np.ones(3),
        row_lower=np.ones(3),
        row_upper=np.full(3, np.inf),
    )
    custom = replace(
        strategy,
        coverage=lambda _, selected: bool(selected[0] and selected[1]),
        essential_decisions=lambda _: [0, 4],
    )
    return SimpleNamespace(problem=problem), custom


@pytest.mark.parametrize("strategy", METHODS, ids=lambda s: s.name)
def test_weighted_noncontiguous_certificate_matches_reference(strategy, presolve, monkeypatch):
    model, custom = sparse_model(strategy)
    reference, objective = canonical._solve_canonical(model, None, custom, _certificate=False)
    monkeypatch.setattr(_solver, "run", lambda *a, **k: pytest.fail("certificate used the solver"))
    selected, minimum = canonical._solve_canonical(model, None, custom)
    assert selected.tolist() == reference.tolist() == [True, True, False]
    assert minimum == objective == 10


def test_certificate_sums_original_integer_costs_without_overflow(monkeypatch):
    model, strategy = sparse_model(METHODS[0])
    model.problem = replace(
        model.problem, cost=np.array([2**62 + 1, 0, 1, 0, 2**62 + 3], dtype=np.int64)
    )
    monkeypatch.setattr(canonical, "_now", lambda: pytest.fail("helper read the clock"))
    monkeypatch.setattr(_solver, "run", lambda *a, **k: pytest.fail("helper used the solver"))
    selected, minimum = canonical._essential_cover_certificate(
        model, model.problem.decision_columns, [0, 4], strategy
    )
    assert selected.tolist() == [True, True, False]
    assert minimum == 2**63 + 4
    assert type(minimum) is int


@pytest.mark.parametrize("column", [0, 2])
@pytest.mark.parametrize("cost", [0, -1, 0.5, np.nan, np.inf, -np.inf])
def test_invalid_selected_or_optional_cost_falls_back(monkeypatch, column, cost):
    model, strategy = sparse_model(METHODS[0])
    model.problem.cost[column] = cost
    assert_fallback(monkeypatch, model, strategy)


@pytest.mark.parametrize("cost", [1, -1, 0.5, np.nan, np.inf])
def test_nonzero_or_nonfinite_auxiliary_cost_falls_back(monkeypatch, cost):
    model, strategy = sparse_model(METHODS[0])
    model.problem.cost[1] = cost
    assert_fallback(monkeypatch, model, strategy)


@pytest.mark.parametrize("cost", [[1, 0], [[7, 0, 11, 0, 3]], [True] * 5, [1j] * 5])
def test_unsupported_cost_array_falls_back(monkeypatch, cost):
    model, strategy = sparse_model(METHODS[0])
    model.problem = replace(model.problem, cost=np.asarray(cost))
    assert_fallback(monkeypatch, model, strategy)


def assert_fallback(monkeypatch, model, strategy):
    def fallback(problem, lower, upper, **options):
        assert problem is model.problem
        assert lower.tolist() == [1, 0, 0, 0, 1]
        assert upper.tolist() == [1] * 5
        assert options["sum_limit"] is None
        raise SolverError("reference adapter reached")

    monkeypatch.setattr(_solver, "run", fallback)
    assert (
        canonical._essential_cover_certificate(
            model, model.problem.decision_columns, [0, 4], strategy
        )
        is None
    )
    with pytest.raises(SolverError, match="^reference adapter reached$"):
        canonical._solve_canonical(model, None, strategy)


@pytest.mark.parametrize("strategy", METHODS, ids=lambda s: s.name)
@pytest.mark.parametrize("graph", [np.eye(3, dtype=bool), np.ones((5, 5), dtype=bool), SIMPLE])
def test_certified_public_calls_do_not_use_solver(monkeypatch, strategy, graph):
    monkeypatch.setattr(_solver, "run", lambda *a, **k: pytest.fail("certificate used the solver"))
    result = reduce_from_adjacency(graph, method=strategy.name)
    assert result.relationship_preserved is True
    assert result.adjacency == tuple(tuple(bool(value) for value in row) for row in graph)


@pytest.mark.parametrize("strategy", METHODS, ids=lambda s: s.name)
@pytest.mark.parametrize("isolated", [False, True])
def test_uncovered_essential_set_uses_solver(monkeypatch, strategy, isolated, presolve):
    # K(2,2,2) has no essential decisions. An added isolate requires a decision,
    # but that decision still cannot cover the multipartite component.
    graph = np.fromfunction(lambda i, j: (i // 2 != j // 2) | (i == j), (6, 6), dtype=int)
    if isolated:
        larger = np.eye(7, dtype=bool)
        larger[:6, :6] = graph
        graph = larger
    context = graph_context(
        graph, list(map(str, range(len(graph)))), None, maximal_cliques(graph, max_cliques=10_000)
    )
    model = strategy.builder(context)
    required = strategy.essential_decisions(model)
    assert bool(required) is isolated
    assert (
        canonical._essential_cover_certificate(
            model, model.problem.decision_columns, required, strategy
        )
        is None
    )
    real, calls = _solver.run, []

    def run(*args, **kwargs):
        calls.append(kwargs["sum_limit"])
        return real(*args, **kwargs)

    monkeypatch.setattr(_solver, "run", run)
    actual = canonical._solve_canonical(model, None, strategy)
    assert len(calls) > 1
    assert calls[0] is None
    reference = canonical._solve_canonical(model, None, strategy, _certificate=False)
    assert actual[0].tolist() == reference[0].tolist()
    assert actual[1] == reference[1]


@pytest.mark.parametrize("strategy", METHODS, ids=lambda s: s.name)
@pytest.mark.parametrize("phase", ["scan", "certificate", "uncovered"])
def test_deadline_checks_scan_and_certificate_before_return_or_solver(monkeypatch, strategy, phase):
    now, visited = [0], []
    model, custom = sparse_model(strategy)
    real_certificate = canonical._essential_cover_certificate

    def scan(_):
        visited.append("scan")
        if phase == "scan":
            now[0] = 5
        return [0, 4]

    def certificate(*args):
        visited.append("certificate")
        result = real_certificate(*args)
        now[0] = 5
        return None if phase == "uncovered" else result

    custom = replace(custom, essential_decisions=scan)
    monkeypatch.setattr(canonical, "_now", lambda: now[0])
    monkeypatch.setattr(canonical, "_essential_cover_certificate", certificate)
    monkeypatch.setattr(
        _solver, "run", lambda *a, **k: pytest.fail("expired budget reached solver")
    )
    with pytest.raises(SolverError) as caught:
        canonical._solve_canonical(model, 5, custom)
    assert str(caught.value) == strategy.failure_prefix + "Time limit reached"
    assert visited == (["scan"] if phase == "scan" else ["scan", "certificate"])


@pytest.mark.parametrize("decisions", [[0, 0], [-1], [5], [0.5]])
def test_invalid_decisions_stop_before_certificate(monkeypatch, decisions):
    model, strategy = sparse_model(METHODS[0])
    model.problem = replace(model.problem, decision_columns=decisions)
    monkeypatch.setattr(
        canonical,
        "_essential_cover_certificate",
        lambda *a: pytest.fail("invalid decisions reached helper"),
    )
    with pytest.raises(SolverError, match="HiGHS returned an invalid solution"):
        canonical._solve_canonical(model, None, strategy)


@needs_conformance
@pytest.mark.parametrize("case", REDUCE_CASES, ids=lambda case: case["id"])
def test_all_fixture_outputs_and_vectors_match_reference(case, presolve, monkeypatch):
    records = []

    def solve(model, time_limit, strategy, *, _certificate=True):
        selected, objective = canonical._solve_canonical(
            model, time_limit, strategy, _certificate=_certificate
        )
        records.append((selected.tolist(), objective))
        return selected, objective

    variants = [(case, case["expected"])]
    if "sigma_expected" in case:
        variants.append(
            (
                {**case, "options": {**case["options"], "method": "assignment_minimum"}},
                case["sigma_expected"],
            )
        )
    for variant, expected in variants:
        records.clear()
        monkeypatch.setattr(reduction, "_solve_canonical", solve)
        actual = run_case(variant)
        monkeypatch.setattr(reduction, "_solve_canonical", partial(solve, _certificate=False))
        reference = run_case(variant)
        assert actual == reference
        pd.testing.assert_frame_equal(actual.to_frame(), reference.to_frame())
        assert len(records) == 2
        assert records[0] == records[1]
        assert mismatches(actual_of(actual), expected) == []
