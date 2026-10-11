import { SolverError } from "./errors.js";
import { hooks, type Outcome } from "./solver.js";
import type { Model, Strategy } from "./model.js";
export const clock = { now: (): number => performance.now() / 1000 };
const INTEGRALITY_TOLERANCE = 1e-6;
const INVALID_SOLUTION = "HiGHS returned an invalid solution";
/** Section 5: solve once, then fix the memberships in (clique, group) order. */
export function solveCanonical(model: Model, timeLimit: number | null, strategy: Strategy): { selected: boolean[]; minimum: number } {
  const { problem } = model;
  const decisions = problem.decisionColumns;
  if (new Set(decisions).size !== decisions.length || decisions.some(v => !Number.isInteger(v) || v < 0 || v >= problem.numCols)) {
    throw new SolverError(INVALID_SOLUTION);
  }
  const deadline = timeLimit !== null ? clock.now() + timeLimit : null;
  let colLower = new Float64Array(problem.numCols);
  const colUpper = new Float64Array(problem.numCols).fill(1);

  let outcome = solve(model, colLower, colUpper, null, deadline, strategy);
  let selected = checkSolution(model, outcome, colLower, colUpper, null, strategy);
  const minimum = Math.round(outcome.objective as number);

  for (const [k, v] of decisions.entries()) {
    if (selected[k]) { colLower[v] = 1; continue; }
    const trial = Float64Array.from(colLower);
    trial[v] = 1;
    outcome = solve(model, trial, colUpper, minimum, deadline, strategy);
    if (outcome.status === "infeasible") { colUpper[v] = 0; continue; }
    selected = checkSolution(model, outcome, trial, colUpper, minimum, strategy);
    colLower = trial;
  }
  return { selected, minimum };
}

function solve(
  model: Model, colLower: Float64Array, colUpper: Float64Array,
  sumLimit: number | null, deadline: number | null, strategy: Strategy,
): Outcome {
  let remaining: number | null = null;
  if (deadline !== null) {
    remaining = deadline - clock.now();
    if (remaining <= 0) throw new SolverError(strategy.failurePrefix + "Time limit reached");
  }
  const outcome = hooks.run(model.problem, colLower, colUpper, sumLimit, remaining);
  if (outcome.status === "infeasible" && sumLimit !== null) return outcome;
  if (outcome.status !== "optimal") {
    throw new SolverError(strategy.failurePrefix + outcome.text);
  }
  return outcome;
}

/** Section 6, checks 2 to 5. Returns the rounded x as booleans. */
function checkSolution(
  model: Model, outcome: Outcome, colLower: Float64Array, colUpper: Float64Array,
  expectedSum: number | null, strategy: Strategy,
): boolean[] {
  const { decisionColumns, numCols } = model.problem;
  const values = outcome.values;
  if (!values || values.length !== numCols) throw new SolverError(INVALID_SOLUTION);
  const rounded: boolean[] = [];
  for (const k of decisionColumns) {
    const x = values[k];
    // Each membership must be 0 or 1 within the tolerance; an integral 2 or -1 is invalid too.
    const binary = Math.abs(x) <= INTEGRALITY_TOLERANCE || Math.abs(x - 1) <= INTEGRALITY_TOLERANCE;
    if (!Number.isFinite(x) || !binary) throw new SolverError(INVALID_SOLUTION);
    const on = x > 0.5;
    if ((on && colUpper[k] < 0.5) || (!on && colLower[k] > 0.5)) throw new SolverError(INVALID_SOLUTION);
    rounded.push(on);
  }
  if (!strategy.coverage(model, rounded)) throw new SolverError(INVALID_SOLUTION);
  if (expectedSum === null && !Number.isFinite(outcome.objective)) throw new SolverError(INVALID_SOLUTION);
  const total = rounded.reduce((sum, on, k) => sum + (on ? model.problem.cost[decisionColumns[k]] : 0), 0);
  const wanted = expectedSum ?? Math.round(outcome.objective as number);
  if (total !== wanted) throw new SolverError(INVALID_SOLUTION);
  return rounded;
}
