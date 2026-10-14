import { SolverError } from "./errors.js";
import { hooks, type Outcome } from "./solver.js";
import type { Model, Strategy } from "./model.js";
export const clock = { now: (): number => performance.now() / 1000 };
const INTEGRALITY_TOLERANCE = 1e-6;
const INVALID_SOLUTION = "HiGHS returned an invalid solution";
type CanonicalSolution = { selected: boolean[]; minimum: number };

/** Internal proof: required decisions cover, so every other vector costs more. */
export function essentialCoverCertificate(
  model: Model, decisions: number[], required: number[], strategy: Strategy,
): CanonicalSolution | null {
  const { cost, numCols } = model.problem;
  if (cost.length !== numCols) return null;
  const decisionSet = new Set(decisions);
  for (let v = 0; v < numCols; v++) {
    // Use exact integer arithmetic; other objective contracts use the solver.
    if (decisionSet.has(v) ? !Number.isSafeInteger(cost[v]) || cost[v] <= 0 : cost[v] !== 0) return null;
  }
  const requiredSet = new Set(required);
  const selected = decisions.map(v => requiredSet.has(v));
  const minimum = decisions.reduce((sum, v, k) => sum + (selected[k] ? cost[v] : 0), 0);
  if (!Number.isSafeInteger(minimum) || !strategy.coverage(model, selected)) return null;
  return { selected, minimum };
}

/** Certify the essential cover or solve and fix decisions in canonical order. */
export function solveCanonical(model: Model, timeLimit: number | null, strategy: Strategy, certificate = true): CanonicalSolution {
  const { problem } = model;
  const decisions = problem.decisionColumns;
  const decisionSet = new Set(decisions);
  if (decisionSet.size !== decisions.length) throw new SolverError(INVALID_SOLUTION);
  for (const v of decisions) {
    if (!Number.isInteger(v) || v < 0 || v >= problem.numCols) throw new SolverError(INVALID_SOLUTION);
  }
  const deadline = timeLimit !== null ? clock.now() + timeLimit : null;
  const required = strategy.essentialDecisions(model);
  if (!Array.isArray(required)) throw new SolverError(INVALID_SOLUTION);
  let previous = -1;
  for (const v of required) {
    if (!Number.isInteger(v) || !decisionSet.has(v) || v <= previous) throw new SolverError(INVALID_SOLUTION);
    previous = v;
  }
  remainingTime(deadline, strategy);
  if (certificate) {
    const certified = essentialCoverCertificate(model, decisions, required, strategy);
    remainingTime(deadline, strategy);
    if (certified !== null) return certified;
  }
  let colLower = new Float64Array(problem.numCols);
  const colUpper = new Float64Array(problem.numCols).fill(1);
  for (const v of required) colLower[v] = 1;

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

function remainingTime(deadline: number | null, strategy: Strategy): number | null {
  if (deadline === null) return null;
  const remaining = deadline - clock.now();
  if (remaining <= 0) throw new SolverError(strategy.failurePrefix + "Time limit reached");
  return remaining;
}

function solve(
  model: Model, colLower: Float64Array, colUpper: Float64Array,
  sumLimit: number | null, deadline: number | null, strategy: Strategy,
): Outcome {
  const remaining = remainingTime(deadline, strategy);
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
