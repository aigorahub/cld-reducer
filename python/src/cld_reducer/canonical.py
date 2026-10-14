"""One canonical binary solve loop and deadline for all reduction strategies."""

import time
from math import isfinite
from numbers import Integral, Real
from typing import Any

import numpy as np

from . import _solver
from .exceptions import SolverError

_now = time.monotonic
_INTEGRALITY_TOLERANCE = 1e-6
_INVALID_SOLUTION = "HiGHS returned an invalid solution"


def _solve_canonical(model: Any, time_limit: float | None, strategy: Any) -> tuple[np.ndarray, int]:
    """Solve once, then fix decisions in the model's canonical order under one deadline."""
    problem = model.problem
    decisions = problem.decision_columns
    if len(set(decisions)) != len(decisions) or any(
        not isinstance(v, Integral) or v < 0 or v >= problem.num_cols for v in decisions
    ):
        raise SolverError(_INVALID_SOLUTION)
    deadline = _now() + time_limit if time_limit is not None else None
    col_lower = np.zeros(problem.num_cols)
    col_upper = np.ones(problem.num_cols)

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


def _solve(
    model: Any,
    col_lower: np.ndarray,
    col_upper: np.ndarray,
    sum_limit: int | None,
    deadline: float | None,
    strategy: Any,
) -> _solver.Outcome:
    remaining = None
    if deadline is not None:
        remaining = deadline - _now()
        if remaining <= 0:
            msg = strategy.failure_prefix + "Time limit reached"
            raise SolverError(msg)
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
