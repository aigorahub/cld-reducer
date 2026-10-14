"""One canonical binary solve loop and deadline for all reduction strategies."""

import time
from math import isfinite
from numbers import Integral, Real
from typing import Any

import numpy as np

from . import _solver
from .context import DecisionPlan
from .exceptions import SolverError

_now = time.monotonic
_INTEGRALITY_TOLERANCE = 1e-6
_INVALID_SOLUTION = "HiGHS returned an invalid solution"


def _essential_cover_certificate(
    model: Any, decisions: list[int], required: list[int], strategy: Any
) -> tuple[np.ndarray, int] | None:
    """Certify the unique optimum when positive-cost essential decisions cover the graph."""
    cost = np.asarray(model.problem.cost)
    if cost.shape != (model.problem.num_cols,) or cost.dtype.kind not in "iuf":
        return None
    decision_cost = cost[decisions]
    if (
        not np.all(np.isfinite(cost))
        or np.any(decision_cost <= 0)
        or (cost.dtype.kind == "f" and np.any(decision_cost != np.floor(decision_cost)))
    ):
        return None
    decision_mask = np.zeros(model.problem.num_cols, dtype=bool)
    decision_mask[decisions] = True
    if np.any(cost[~decision_mask] != 0):
        return None
    essential = set(required)
    selected = np.asarray([column in essential for column in decisions], dtype=bool)
    if not strategy.coverage(model, selected):
        return None
    # Every feasible vector contains the essentials. Any extra decision adds cost.
    # Sum original integer costs without floating point or fixed-width accumulation.
    return selected, sum(int(cost[column]) for column in required)


def _solve_canonical(
    model: Any, time_limit: float | None, strategy: Any, *, _certificate: bool = True
) -> tuple[np.ndarray, int]:
    """Certify or solve, then fix canonical decisions under one shared deadline."""
    if isinstance(model, DecisionPlan):
        return _solve_plan(model, time_limit, strategy, _certificate=_certificate)
    problem = model.problem
    decisions = problem.decision_columns
    decision_set = set(decisions)
    if len(decision_set) != len(decisions) or any(
        not isinstance(v, Integral) or v < 0 or v >= problem.num_cols for v in decisions
    ):
        raise SolverError(_INVALID_SOLUTION)
    deadline = _now() + time_limit if time_limit is not None else None
    required = strategy.essential_decisions(model)
    if (
        not isinstance(required, list)
        or any(
            isinstance(v, bool) or not isinstance(v, Integral) or v not in decision_set
            for v in required
        )
        or any(a >= b for a, b in zip(required, required[1:], strict=False))
    ):
        raise SolverError(_INVALID_SOLUTION)
    _remaining_time(deadline, strategy)
    if _certificate:
        certificate = _essential_cover_certificate(model, decisions, required, strategy)
        _remaining_time(deadline, strategy)
        if certificate is not None:
            return certificate
    return _canonical_trials(model, strategy, required, deadline)


def _canonical_trials(model, strategy, required, deadline):
    problem = model.problem
    decisions = problem.decision_columns
    col_lower = np.zeros(problem.num_cols)
    col_upper = np.ones(problem.num_cols)
    col_lower[required] = 1.0
    outcome = _solve(model, col_lower, col_upper, None, deadline, strategy)
    selected = _check_solution(model, outcome, col_lower, col_upper, None, strategy)
    minimum = int(round(float(outcome.objective)))
    selected_decisions = selected

    for k, v in enumerate(decisions):
        if selected_decisions[k]:
            col_lower[v] = 1.0
            continue
        trial_lower = col_lower.copy()
        trial_lower[v] = 1.0
        outcome = _solve(model, trial_lower, col_upper, minimum, deadline, strategy)
        if outcome.status == _solver.INFEASIBLE:
            col_upper[v] = 0.0
            continue
        selected_decisions = _check_solution(
            model, outcome, trial_lower, col_upper, minimum, strategy
        )
        col_lower = trial_lower
    return selected_decisions, minimum


def _remaining_time(deadline: float | None, strategy: Any) -> float | None:
    if deadline is not None:
        remaining = deadline - _now()
        if remaining <= 0:
            msg = strategy.failure_prefix + "Time limit reached"
            raise SolverError(msg)
        return remaining
    return None


def _solve(
    model: Any,
    col_lower: np.ndarray,
    col_upper: np.ndarray,
    sum_limit: int | None,
    deadline: float | None,
    strategy: Any,
) -> _solver.Outcome:
    remaining = _remaining_time(deadline, strategy)
    outcome = _solver.run(
        model.problem, col_lower, col_upper, sum_limit=sum_limit, time_limit=remaining
    )
    if outcome.status == _solver.INFEASIBLE and sum_limit is not None:
        return outcome
    if outcome.status != _solver.OPTIMAL:
        msg = strategy.failure_prefix + outcome.text
        raise SolverError(msg)
    return outcome


def _check_solution(
    model: Any,
    outcome: _solver.Outcome,
    col_lower: np.ndarray,
    col_upper: np.ndarray,
    expected_sum: int | None,
    strategy: Any,
) -> np.ndarray:
    """Docs/algorithm.md section 6, checks 2 to 5. Returns the rounded x as booleans."""
    decisions = model.problem.decision_columns
    values = outcome.values
    if values is None or len(values) != model.problem.num_cols:
        raise SolverError(_INVALID_SOLUTION)
    x = np.asarray(values[decisions], dtype=np.float64)
    # Each membership must be 0 or 1 within the tolerance; an integral 2 or -1 is invalid too.
    near_zero = np.abs(x) <= _INTEGRALITY_TOLERANCE
    near_one = np.abs(x - 1.0) <= _INTEGRALITY_TOLERANCE
    if not np.all(np.isfinite(x) & (near_zero | near_one)):
        raise SolverError(_INVALID_SOLUTION)
    rounded = x > 0.5
    if np.any(rounded & (col_upper[decisions] < 0.5)) or np.any(
        ~rounded & (col_lower[decisions] > 0.5)
    ):
        raise SolverError(_INVALID_SOLUTION)
    if not strategy.coverage(model, rounded):
        raise SolverError(_INVALID_SOLUTION)
    total = int(np.dot(model.problem.cost[decisions], rounded))
    if expected_sum is None and (
        not isinstance(outcome.objective, Real) or not isfinite(float(outcome.objective))
    ):
        raise SolverError(_INVALID_SOLUTION)
    wanted = expected_sum if expected_sum is not None else int(round(float(outcome.objective)))
    if total != wanted:
        raise SolverError(_INVALID_SOLUTION)
    return rounded


def _plan_certificate(plan, required, strategy):
    cost = plan.cost
    if any(
        isinstance(v, bool) or not isinstance(v, Real) or not isfinite(v) or v <= 0 or int(v) != v
        for v in cost
    ):
        return None
    selected = np.zeros(plan.decision_count, dtype=bool)
    selected[required] = True
    if not strategy.coverage(plan, selected):
        return None
    return selected, sum(int(cost[k]) for k in required)


def _solve_plan(plan, time_limit, strategy, *, _certificate=True):
    count = plan.decision_count
    if len(plan.cost) != count:
        raise SolverError(_INVALID_SOLUTION)
    deadline = _now() + time_limit if time_limit is not None else None
    required = strategy.essential_decisions(plan)
    if (
        not isinstance(required, list)
        or any(
            isinstance(v, bool) or not isinstance(v, Integral) or v < 0 or v >= count
            for v in required
        )
        or any(a >= b for a, b in zip(required, required[1:], strict=False))
    ):
        raise SolverError(_INVALID_SOLUTION)
    _remaining_time(deadline, strategy)
    if _certificate:
        certified = _plan_certificate(plan, required, strategy)
        _remaining_time(deadline, strategy)
        if certified is not None:
            return certified
    # Pause only compilation. Validation and all canonical work consume the budget.
    remaining = _remaining_time(deadline, strategy)
    model = strategy.compiler(plan)
    deadline = _now() + remaining if remaining is not None else None
    problem = model.problem
    decisions = problem.decision_columns
    if (
        len(decisions) != count
        or len(set(decisions)) != count
        or any(
            isinstance(v, bool) or not isinstance(v, Integral) or v < 0 or v >= problem.num_cols
            for v in decisions
        )
        or len(problem.cost) != problem.num_cols
    ):
        raise SolverError(_INVALID_SOLUTION)
    decision_set = set(decisions)
    if any(problem.cost[v] != plan.cost[k] for k, v in enumerate(decisions)) or any(
        cost != 0 for v, cost in enumerate(problem.cost) if v not in decision_set
    ):
        raise SolverError(_INVALID_SOLUTION)
    return _canonical_trials(model, strategy, [decisions[k] for k in required], deadline)
