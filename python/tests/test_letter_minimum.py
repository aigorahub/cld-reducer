"""CLD-C contract, shared engine failures, and sigma import compatibility."""

import dataclasses

import numpy as np
import pytest

from cld_reducer import SolverError, _solver, canonical, reduce_from_adjacency
from cld_reducer.algorithms.assignment_minimum import reduce_assignment_minimum
from cld_reducer.reduction import METHODS

EDGES = [(0, 2), (0, 3), (0, 4), (0, 5), (1, 2), (1, 3), (1, 4), (1, 5), (2, 3), (2, 5), (3, 4)]
TIED = np.eye(6, dtype=bool)
for i, j in EDGES:
    TIED[i, j] = TIED[j, i] = True


def test_full_columns_alias_and_compatibility(presolve):
    simple = np.array(
        [[1, 1, 1, 0, 0], [1, 1, 1, 1, 0], [1, 1, 1, 1, 1], [0, 1, 1, 1, 1], [0, 0, 1, 1, 1]]
    )
    out = reduce_from_adjacency(simple, method="letter-minimum")
    assert out.method == "letter_minimum"
    assert out.stats["objective"] == out.stats["num_letters_after"] == 3
    assert out.stats["assignments_after"] == 9
    assert out.assignments["3"] == ("A", "B", "C")
    sigma = reduce_assignment_minimum(
        simple, [str(i + 1) for i in range(5)], method="letter_minimum"
    )
    assert sigma.method == "letter_minimum"  # metadata, not dispatch
    assert sigma.stats["objective"] == sigma.stats["assignments_after"] == 8
    assert (
        reduce_assignment_minimum(
            simple, [str(i + 1) for i in range(5)], method="custom-label"
        ).method
        == "custom-label"
    )


@pytest.mark.parametrize("status", [_solver.INFEASIBLE, _solver.FAILED, _solver.TIME_LIMIT])
def test_initial_status(monkeypatch, status):
    monkeypatch.setattr(_solver, "run", lambda *a, **k: _solver.Outcome(status, "status-text"))
    with pytest.raises(SolverError, match="letter-minimum MILP failed: status-text"):
        reduce_from_adjacency(TIED, method="letter_minimum")


@pytest.mark.parametrize(
    "change",
    [
        lambda o: dataclasses.replace(o, values=None),
        lambda o: dataclasses.replace(o, values=np.zeros(5)),
        lambda o: dataclasses.replace(o, values=np.zeros(6)),
        lambda o: dataclasses.replace(o, values=np.ones(6)),
        lambda o: dataclasses.replace(o, values=np.full(6, 0.5)),
        lambda o: dataclasses.replace(o, values=np.full(6, np.nan)),
        lambda o: dataclasses.replace(o, values=np.full(6, 2.0)),
        lambda o: dataclasses.replace(o, objective=np.inf),
        lambda o: dataclasses.replace(o, objective=None),
        lambda o: dataclasses.replace(o, objective=3),
    ],
)
def test_invalid_c_solution(monkeypatch, change):
    real = _solver.run
    monkeypatch.setattr(_solver, "run", lambda *a, **k: change(real(*a, **k)))
    with pytest.raises(SolverError, match="HiGHS returned an invalid solution"):
        reduce_from_adjacency(TIED, method="letter_minimum")


def off_canonical(monkeypatch):
    real = _solver.run
    seen = []

    def run(problem, lower, upper, **kwargs):
        if kwargs["sum_limit"] is None:
            cost = problem.cost.copy()
            cost[problem.decision_columns] += np.linspace(0.001, 0, len(problem.decision_columns))
            problem = dataclasses.replace(problem, cost=cost)
        outcome = real(problem, lower, upper, **kwargs)
        seen.append((kwargs["sum_limit"], outcome.status))
        return outcome

    monkeypatch.setattr(_solver, "run", run)
    return run, seen


def test_c_trial_branches_and_perturbed_objective(monkeypatch, presolve):
    _, seen = off_canonical(monkeypatch)
    out = reduce_from_adjacency(TIED, method="letter_minimum")
    assert out.stats["objective"] == 5
    assert (5, _solver.OPTIMAL) in seen
    assert (5, _solver.INFEASIBLE) in seen
    assert out.letters == {"1": "ABC", "2": "DE", "3": "ABD", "4": "ACE", "5": "CE", "6": "BD"}


@pytest.mark.parametrize("corruption", ["fixing", "objective", "status"])
def test_invalid_c_trial(monkeypatch, corruption):
    run, _ = off_canonical(monkeypatch)

    def wrapper(problem, lower, upper, **kwargs):
        outcome = run(problem, lower, upper, **kwargs)
        if kwargs["sum_limit"] is not None and outcome.status == _solver.OPTIMAL:
            if corruption == "status":
                return _solver.Outcome(_solver.FAILED, "Memory limit reached")
            values = outcome.values.copy()
            if corruption == "fixing":
                values[np.flatnonzero(lower > 0.5)[0]] = 0
            else:
                values[:] = 1
            return dataclasses.replace(outcome, values=values)
        return outcome

    monkeypatch.setattr(_solver, "run", wrapper)
    with pytest.raises(SolverError):
        reduce_from_adjacency(TIED, method="letter_minimum")


@pytest.mark.parametrize("method", ["assignment_minimum", "letter_minimum"])
@pytest.mark.parametrize("phase", ["initial", "trial"])
def test_deadline_owner(monkeypatch, method, phase):
    real = _solver.run
    now = {"v": 0}
    monkeypatch.setattr(canonical, "_now", lambda: now["v"])

    def run(*args, **kwargs):
        if phase == "initial":
            raise AssertionError("expired initial solve reached adapter")
        out = real(*args, **kwargs)
        now["v"] += 10
        return out

    monkeypatch.setattr(_solver, "run", run)
    if phase == "initial":
        times = iter([0, 10])
        monkeypatch.setattr(canonical, "_now", lambda: next(times))
    with pytest.raises(SolverError, match="MILP failed: Time limit reached"):
        reduce_from_adjacency(TIED, method=method, time_limit=5)


@pytest.mark.parametrize("strategy", METHODS)
def test_noncontiguous_decision_indices(strategy):
    from types import SimpleNamespace

    # Auxiliary column 1 is forced on; the cap must exclude it. Canonical order is 2,0.
    problem = _solver.Problem(
        num_cols=3,
        decision_columns=[2, 0],
        cost=np.array([1.0, 0.0, 1.0]),
        start=np.array([0, 2, 3], dtype=np.int32),
        index=np.array([0, 2, 1], dtype=np.int32),
        value=np.ones(3),
        row_lower=np.array([1.0, 1.0]),
        row_upper=np.array([np.inf, np.inf]),
    )
    model = SimpleNamespace(problem=problem)
    custom = dataclasses.replace(strategy, coverage=lambda m, s: any(s))
    selected, optimum = canonical._solve_canonical(model, None, custom)
    assert optimum == 1
    assert selected.tolist() == [True, False]
    out = _solver.run(problem, np.zeros(3), np.ones(3), sum_limit=1)
    assert out.status == _solver.OPTIMAL
    assert out.values[1] == 1


@pytest.mark.parametrize("options", [{"time_limit": 0}, {"max_cliques": 0}, {"max_cliques": 1}])
def test_c_controls(options):
    with pytest.raises(SolverError):
        reduce_from_adjacency(TIED, method="letter_minimum", **options)


def test_c_missing_edge_with_correct_count(monkeypatch):
    monkeypatch.setattr(
        _solver,
        "run",
        lambda *a, **k: _solver.Outcome(
            _solver.OPTIMAL, "Optimal", np.array([1.0, 1.0, 1.0, 1.0, 1.0, 0.0]), 5.0
        ),
    )
    with pytest.raises(SolverError, match="HiGHS returned an invalid solution"):
        reduce_from_adjacency(TIED, method="letter_minimum")


def test_adapter_maps_unbounded_or_infeasible(monkeypatch):
    import highspy

    real = highspy.Highs

    class Ambiguous:
        def __init__(self):
            self.delegate = real()

        def __getattr__(self, name):
            return getattr(self.delegate, name)

        def getModelStatus(self):
            return highspy.HighsModelStatus.kUnboundedOrInfeasible

    monkeypatch.setattr(highspy, "Highs", Ambiguous)
    with pytest.raises(SolverError, match="MILP failed: Primal infeasible or unbounded"):
        reduce_from_adjacency(TIED, method="letter_minimum")
