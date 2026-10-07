"""HiGHS through highspy, with the settings of docs/algorithm.md section 6."""

from __future__ import annotations

from dataclasses import dataclass

import highspy
import numpy as np


@dataclass
class Settings:
    """Presolve is the one setting that differs between languages (R turns it off).

    Tests switch it off to run the conformance suite a second time.
    """

    presolve: str = "on"


settings = Settings()
# The options of the most recent solve, read back from HiGHS. Tests check them.
last_options: dict[str, object] = {}

OPTION_NAMES = (
    "presolve",
    "mip_rel_gap",
    "mip_abs_gap",
    "primal_feasibility_tolerance",
    "mip_feasibility_tolerance",
    "threads",
    "time_limit",
)

OPTIMAL = "optimal"
INFEASIBLE = "infeasible"
TIME_LIMIT = "time_limit"
FAILED = "failed"


@dataclass(frozen=True)
class Problem:
    """The model of docs/algorithm.md section 4 in row-wise sparse form.

    The first `num_x` columns are the membership variables x; the rest are the y variables.
    """

    num_cols: int
    num_x: int
    cost: np.ndarray
    start: np.ndarray
    index: np.ndarray
    value: np.ndarray
    row_lower: np.ndarray
    row_upper: np.ndarray


@dataclass(frozen=True)
class Outcome:
    """What one solve returned: a status, the HiGHS status text, and the column values."""

    status: str
    text: str
    values: np.ndarray | None = None
    objective: float | None = None


def run(
    problem: Problem,
    col_lower: np.ndarray,
    col_upper: np.ndarray,
    *,
    sum_limit: int | None = None,
    time_limit: float | None = None,
) -> Outcome:
    """Solve the model with the given column bounds.

    `sum_limit` adds the row `sum(x) <= sum_limit`. `time_limit` is the HiGHS time limit in
    seconds for this solve.
    """
    start, index, value = problem.start, problem.index, problem.value
    row_lower, row_upper = problem.row_lower, problem.row_upper
    if sum_limit is not None:
        extra = np.arange(problem.num_x, dtype=np.int32)
        start = np.concatenate([start, [start[-1] + problem.num_x]]).astype(np.int32)
        index = np.concatenate([index, extra])
        value = np.concatenate([value, np.ones(problem.num_x)])
        row_lower = np.concatenate([row_lower, [-highspy.kHighsInf]])
        row_upper = np.concatenate([row_upper, [float(sum_limit)]])

    lp = highspy.HighsLp()
    lp.num_col_ = problem.num_cols
    lp.num_row_ = len(row_lower)
    lp.col_cost_ = problem.cost
    lp.col_lower_ = col_lower
    lp.col_upper_ = col_upper
    lp.integrality_ = [highspy.HighsVarType.kInteger] * problem.num_cols
    lp.row_lower_ = row_lower
    lp.row_upper_ = row_upper
    lp.a_matrix_.format_ = highspy.MatrixFormat.kRowwise
    lp.a_matrix_.num_col_ = problem.num_cols
    lp.a_matrix_.num_row_ = len(row_lower)
    lp.a_matrix_.start_ = start
    lp.a_matrix_.index_ = index
    lp.a_matrix_.value_ = value
    lp.sense_ = highspy.ObjSense.kMinimize

    h = highspy.Highs()
    h.setOptionValue("output_flag", False)
    h.setOptionValue("presolve", settings.presolve)
    h.setOptionValue("mip_rel_gap", 0.0)
    h.setOptionValue("mip_abs_gap", 0.0)
    h.setOptionValue("primal_feasibility_tolerance", 1e-9)
    h.setOptionValue("mip_feasibility_tolerance", 1e-9)
    h.setOptionValue("threads", 1)
    if time_limit is not None:
        h.setOptionValue("time_limit", float(time_limit))
    h.passModel(lp)
    h.run()

    last_options.clear()
    for name in OPTION_NAMES:
        option = h.getOptionValue(name)
        # highspy 1.15 returns (status, value).
        last_options[name] = option[1] if isinstance(option, tuple) else option

    status = h.getModelStatus()
    text = h.modelStatusToString(status)
    if status == highspy.HighsModelStatus.kOptimal:
        values = np.asarray(h.getSolution().col_value, dtype=np.float64)
        return Outcome(OPTIMAL, text, values, float(h.getInfo().objective_function_value))
    # No model here is unbounded, so HiGHS's "unbounded or infeasible" means infeasible.
    if status in (
        highspy.HighsModelStatus.kInfeasible,
        highspy.HighsModelStatus.kUnboundedOrInfeasible,
    ):
        return Outcome(INFEASIBLE, text)
    if status == highspy.HighsModelStatus.kTimeLimit:
        return Outcome(TIME_LIMIT, text)
    return Outcome(FAILED, text)
