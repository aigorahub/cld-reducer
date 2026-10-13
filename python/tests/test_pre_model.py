"""The public certificate does not construct a BIP; fallback preserves its contract."""

from dataclasses import replace

import numpy as np
import pytest
from test_essential_cover import sparse_model
from test_solver import SIMPLE

from cld_reducer import SolverError, _solver, canonical, reduce_from_adjacency, reduction
from cld_reducer.cliques import maximal_cliques
from cld_reducer.context import graph_context
from cld_reducer.reduction import METHODS


def plan_for(adjacency, strategy):
    context = graph_context(
        adjacency,
        list(map(str, range(len(adjacency)))),
        None,
        maximal_cliques(adjacency, max_cliques=10000),
        assignments=strategy.counts_assignments,
    )
    return strategy.planner(context)


@pytest.mark.parametrize("adjacency", [np.ones((5, 5), bool), np.eye(4, dtype=bool), SIMPLE])
@pytest.mark.parametrize("strategy", METHODS, ids=lambda s: s.name)
def test_public_certificate_never_compiles(adjacency, strategy, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("certified public call constructed a BIP or called HiGHS")

    custom = replace(strategy, builder=forbidden, compiler=forbidden)
    monkeypatch.setattr(reduction, "METHODS", (custom,))
    monkeypatch.setattr(_solver, "run", forbidden)
    result = reduce_from_adjacency(adjacency, method=strategy.name)
    assert result.relationship_preserved
    assert result.stats["solver_status"] == "Optimal"


@pytest.mark.parametrize("strategy", METHODS, ids=lambda s: s.name)
@pytest.mark.parametrize("with_isolate", [False, True])
def test_fallback_compiles_once_and_scans_once(
    strategy, with_isolate, solver_graph, monkeypatch, presolve
):
    graph = solver_graph
    if with_isolate:
        graph = np.eye(7, dtype=bool)
        graph[:6, :6] = solver_graph
    plan = plan_for(graph, strategy)
    expected, optimum = canonical._solve_canonical(
        strategy.builder(plan.context), None, strategy, _certificate=False
    )
    calls = {"scan": 0, "compile": 0}

    def scan(data):
        calls["scan"] += 1
        return strategy.essential_decisions(data)

    def compile_plan(data):
        assert data is plan
        calls["compile"] += 1
        return strategy.compiler(data)

    selected, minimum = canonical._solve_canonical(
        plan, None, replace(strategy, compiler=compile_plan, essential_decisions=scan)
    )
    assert calls == {"scan": 1, "compile": 1}
    assert selected.tolist() == expected.tolist()
    assert minimum == optimum
    assert bool(strategy.essential_decisions(plan)) is with_isolate


@pytest.mark.parametrize("strategy", METHODS, ids=lambda s: s.name)
def test_compilation_pauses_only_its_own_time(strategy, solver_graph, monkeypatch):
    plan = plan_for(solver_graph, strategy)
    now = 0
    monkeypatch.setattr(canonical, "_now", lambda: now)

    def scan(data):
        nonlocal now
        now += 2
        return strategy.essential_decisions(data)

    def coverage(data, selected):
        nonlocal now
        now += 1
        return strategy.coverage(data, selected)

    def compiler(data):
        nonlocal now
        now += 100
        return strategy.compiler(data)

    def run(problem, lower, upper, **options):
        assert options["time_limit"] == 7
        raise SolverError("remaining budget verified")

    monkeypatch.setattr(_solver, "run", run)
    custom = replace(strategy, essential_decisions=scan, coverage=coverage, compiler=compiler)
    with pytest.raises(SolverError, match="remaining budget verified"):
        canonical._solve_canonical(plan, 10, custom)


@pytest.mark.parametrize("strategy", METHODS, ids=lambda s: s.name)
@pytest.mark.parametrize("phase", ["scan", "certificate"])
def test_expired_plan_never_compiles(strategy, phase, monkeypatch):
    plan = plan_for(SIMPLE, strategy)
    now = 0
    monkeypatch.setattr(canonical, "_now", lambda: now)

    def scan(data):
        nonlocal now
        if phase == "scan":
            now = 5
        return strategy.essential_decisions(data)

    def coverage(data, selected):
        nonlocal now
        now = 5
        return strategy.coverage(data, selected)

    def forbidden(_):
        pytest.fail("expired plan compiled")

    with pytest.raises(SolverError, match="Time limit reached"):
        canonical._solve_canonical(
            plan,
            5,
            replace(strategy, compiler=forbidden, coverage=coverage, essential_decisions=scan),
        )


@pytest.mark.parametrize("required", [None, [True], [-1], [999], [0.5], [1, 0], [0, 0]])
def test_plan_rejects_malformed_scan_before_compiler(required):
    strategy = METHODS[1]
    plan = plan_for(SIMPLE, strategy)
    with pytest.raises(SolverError, match="invalid solution"):
        canonical._solve_canonical(
            plan, None, replace(strategy, essential_decisions=lambda _: required)
        )


@pytest.mark.parametrize("cost", [0, -1, 0.5, np.nan, np.inf, True])
def test_plan_cost_proof_is_defensive(cost):
    strategy = METHODS[1]
    plan = plan_for(SIMPLE, strategy)
    bad = replace(plan, cost=[cost] + plan.cost[1:])
    assert canonical._plan_certificate(bad, strategy.essential_decisions(bad), strategy) is None


def test_plan_preserves_noncontiguous_compiler_mapping(presolve):
    strategy = METHODS[1]
    plan = replace(plan_for(SIMPLE, strategy), cost=[3, 7, 11])
    model, legacy = sparse_model(strategy)
    custom = replace(legacy, essential_decisions=lambda _: [0, 1], compiler=lambda _: model)
    selected, minimum = canonical._solve_canonical(plan, None, custom, _certificate=False)
    assert selected.tolist() == [True, True, False]
    assert minimum == 10


def test_plan_integer_cost_sum_is_exact():
    strategy = METHODS[1]
    plan = replace(plan_for(SIMPLE, strategy), cost=[2**62 + 1, 2**62 + 3, 1])
    _, minimum = canonical._solve_canonical(plan, None, strategy)
    assert minimum == 2**63 + 5
