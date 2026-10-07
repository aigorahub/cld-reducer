// The reduction itself: docs/algorithm.md sections 3 to 9.

import { maximalCliques } from "./cliques.js";
import { SolverError } from "./errors.js";
import {
  adjacencyToGraph, checkControls, checkMethod, pairsToGraph,
  type Graph, type ReduceOptions,
} from "./input.js";
import { makeLetterLabels } from "./labels.js";
import { getSolver, hooks, type Outcome, type Problem } from "./solver.js";

export interface CldStats {
  assignmentsBefore: number;
  assignmentsAfter: number;
  /** (before - after) / before * 100, not rounded. */
  reductionPct: number;
  numLettersBefore: number;
  numLettersAfter: number;
  numGroups: number;
  numEdges: number;
  solverStatus: string;
  objective: number;
}

export interface CldReduction {
  /** Group label to display string. Use `groups` for the order. */
  letters: Record<string, string>;
  /** Group label to letter tokens. */
  assignments: Record<string, string[]>;
  groups: string[];
  /** One row per group, in order; `assignments` is the tokens joined by spaces. */
  rows: { group: string; letters: string; assignments: string }[];
  stats: CldStats;
  method: string;
  relationshipPreserved: boolean;
  adjacency: boolean[][];
}

// The clock behind the shared time budget, in seconds. Tests replace it.
export const clock = { now: (): number => performance.now() / 1000 };

const INTEGRALITY_TOLERANCE = 1e-6;
const INVALID_SOLUTION = "HiGHS returned an invalid solution";

interface Model {
  problem: Problem;
  members: [number, number][];       // (clique, group) of each x variable, canonical order
  edges: [number, number][];
  groupColumns: number[][];          // x variables of each group
  edgeEnds: [number, number][][];    // per edge: the two x variables of each covering clique
}

/** Reduce compact letters from pairwise post-hoc results. */
export async function reduceLetters(
  pairs: ReadonlyArray<Record<string, unknown>>, options: ReduceOptions = {},
): Promise<CldReduction> {
  return reduceGraph(pairsToGraph(pairs, options), options);
}

/** Reduce compact letters from a non-significance adjacency matrix. */
export async function reduceFromAdjacency(
  adjacency: ReadonlyArray<ReadonlyArray<boolean | number>>, options: ReduceOptions = {},
): Promise<CldReduction> {
  return reduceGraph(adjacencyToGraph(adjacency, options), options);
}

async function reduceGraph(graph: Graph, options: ReduceOptions): Promise<CldReduction> {
  checkMethod(options.method);
  const { timeLimit, maxCliques } = checkControls(options);
  const { groups, adjacency, means } = graph;
  const cliques = maximalCliques(adjacency, maxCliques);
  const model = buildModel(adjacency, cliques);
  await getSolver();
  const { selected, minimum } = solveCanonical(model, timeLimit);

  const columns = selectedColumns(cliques, model, selected);
  const tokens = assignLetters(columns, groups.length, means);
  const assignments = Object.fromEntries(groups.map((g, i) => [g, tokens[i]]));
  const display = tokens.map(formatTokens);
  const letters = Object.fromEntries(groups.map((g, i) => [g, display[i]]));

  const share = (i: number, j: number): boolean => tokens[i].some((t) => tokens[j].includes(t));
  for (let i = 0; i < groups.length; i++) {
    for (let j = 0; j < groups.length; j++) {
      if (share(i, j) !== adjacency[i][j]) {
        throw new SolverError("optimized letters did not preserve the input pairwise relationships");
      }
    }
  }

  const before = model.members.length;
  const after = tokens.reduce((s, t) => s + t.length, 0);
  return {
    letters,
    assignments,
    groups: [...groups],
    rows: groups.map((g, i) => ({ group: g, letters: display[i], assignments: tokens[i].join(" ") })),
    stats: {
      assignmentsBefore: before,
      assignmentsAfter: after,
      reductionPct: before ? (before - after) / before * 100 : 0,
      numLettersBefore: cliques.length,
      numLettersAfter: columns.length,
      numGroups: groups.length,
      numEdges: model.edges.length,
      solverStatus: "Optimal",
      objective: minimum,
    },
    method: "assignment_minimum",
    relationshipPreserved: true,
    adjacency: adjacency.map((row) => [...row]),
  };
}

/** The model of section 4. */
function buildModel(adjacency: boolean[][], cliques: number[][]): Model {
  const n = adjacency.length;
  const members: [number, number][] = [];
  const xIndex = new Map<string, number>();
  const cliquesOf: number[][] = Array.from({ length: n }, () => []);
  cliques.forEach((clique, c) => {
    for (const g of clique) {
      xIndex.set(`${c},${g}`, members.length);
      members.push([c, g]);
      cliquesOf[g].push(c);
    }
  });
  const edges: [number, number][] = [];
  for (let i = 0; i < n; i++) for (let j = i + 1; j < n; j++) if (adjacency[i][j]) edges.push([i, j]);
  const numX = members.length;

  const yPairs: [number, number][] = [];   // (edge, clique)
  edges.forEach(([i, j], e) => {
    const inJ = new Set(cliquesOf[j]);
    for (const c of cliquesOf[i]) if (inJ.has(c)) yPairs.push([e, c]);
  });

  const rows: [number, number][][] = [];
  const rowLower: number[] = [];
  const rowUpper: number[] = [];
  const inf = Infinity;
  for (let g = 0; g < n; g++) {                       // every group has a letter
    rows.push(cliquesOf[g].map((c) => [xIndex.get(`${c},${g}`)!, 1]));
    rowLower.push(1); rowUpper.push(inf);
  }
  const byEdge: number[][] = edges.map(() => []);
  yPairs.forEach(([e], k) => byEdge[e].push(numX + k));
  for (let e = 0; e < edges.length; e++) {            // every edge is covered
    rows.push(byEdge[e].map((col) => [col, 1]));
    rowLower.push(1); rowUpper.push(inf);
  }
  yPairs.forEach(([e, c], k) => {                     // a covering clique needs both ends
    for (const g of edges[e]) {
      rows.push([[numX + k, 1], [xIndex.get(`${c},${g}`)!, -1]]);
      rowLower.push(-inf); rowUpper.push(0);
    }
  });

  const starts = [0];
  const indices: number[] = [];
  const values: number[] = [];
  for (const row of rows) {
    for (const [col, coefficient] of row) { indices.push(col); values.push(coefficient); }
    starts.push(indices.length);
  }
  const numCols = numX + yPairs.length;
  const cost = new Float64Array(numCols);
  cost.fill(1, 0, numX);
  const edgeEnds: [number, number][][] = edges.map(() => []);
  for (const [e, c] of yPairs) {
    edgeEnds[e].push([xIndex.get(`${c},${edges[e][0]}`)!, xIndex.get(`${c},${edges[e][1]}`)!]);
  }
  return {
    problem: {
      numCols, numX, cost,
      starts: Int32Array.from(starts), indices: Int32Array.from(indices),
      values: Float64Array.from(values),
      // Infinite row bounds become the solver's infinity inside run().
      rowLower: Float64Array.from(rowLower), rowUpper: Float64Array.from(rowUpper),
    },
    members, edges,
    groupColumns: cliquesOf.map((cs, g) => cs.map((c) => xIndex.get(`${c},${g}`)!)),
    edgeEnds,
  };
}

/** Section 5: solve once, then fix the memberships in (clique, group) order. */
function solveCanonical(model: Model, timeLimit: number | null): { selected: boolean[]; minimum: number } {
  const { problem } = model;
  const numX = problem.numX;
  const deadline = timeLimit !== null ? clock.now() + timeLimit : null;
  let colLower = new Float64Array(problem.numCols);
  const colUpper = new Float64Array(problem.numCols).fill(1);

  let outcome = solve(model, colLower, colUpper, null, deadline);
  let selected = checkSolution(model, outcome, colLower, colUpper, null);
  const minimum = Math.round(outcome.objective as number);

  for (let v = 0; v < numX; v++) {
    if (selected[v]) { colLower[v] = 1; continue; }
    const trial = Float64Array.from(colLower);
    trial[v] = 1;
    outcome = solve(model, trial, colUpper, minimum, deadline);
    if (outcome.status === "infeasible") { colUpper[v] = 0; continue; }
    selected = checkSolution(model, outcome, trial, colUpper, minimum);
    colLower = trial;
  }
  return { selected, minimum };
}

function solve(
  model: Model, colLower: Float64Array, colUpper: Float64Array,
  sumLimit: number | null, deadline: number | null,
): Outcome {
  let remaining: number | null = null;
  if (deadline !== null) {
    remaining = deadline - clock.now();
    if (remaining <= 0) throw new SolverError("assignment-minimum MILP failed: Time limit reached");
  }
  const outcome = hooks.run(model.problem, colLower, colUpper, sumLimit, remaining);
  if (outcome.status === "infeasible" && sumLimit !== null) return outcome;
  if (outcome.status !== "optimal") {
    throw new SolverError(`assignment-minimum MILP failed: ${outcome.text}`);
  }
  return outcome;
}

/** Section 6, checks 2 to 5. Returns the rounded x as booleans. */
function checkSolution(
  model: Model, outcome: Outcome, colLower: Float64Array, colUpper: Float64Array,
  expectedSum: number | null,
): boolean[] {
  const { numX, numCols } = model.problem;
  const values = outcome.values;
  if (!values || values.length !== numCols) throw new SolverError(INVALID_SOLUTION);
  const rounded: boolean[] = [];
  for (let k = 0; k < numX; k++) {
    const x = values[k];
    // Each membership must be 0 or 1 within the tolerance; an integral 2 or -1 is invalid too.
    const binary = Math.abs(x) <= INTEGRALITY_TOLERANCE || Math.abs(x - 1) <= INTEGRALITY_TOLERANCE;
    if (!Number.isFinite(x) || !binary) throw new SolverError(INVALID_SOLUTION);
    const on = x > 0.5;
    if ((on && colUpper[k] < 0.5) || (!on && colLower[k] > 0.5)) throw new SolverError(INVALID_SOLUTION);
    rounded.push(on);
  }
  for (const columns of model.groupColumns) {
    if (!columns.some((k) => rounded[k])) throw new SolverError(INVALID_SOLUTION);
  }
  for (const ends of model.edgeEnds) {
    if (!ends.some(([a, b]) => rounded[a] && rounded[b])) throw new SolverError(INVALID_SOLUTION);
  }
  const total = rounded.filter(Boolean).length;
  const wanted = expectedSum ?? Math.round(outcome.objective as number);
  if (total !== wanted) throw new SolverError(INVALID_SOLUTION);
  return rounded;
}

/** The selected members of each clique's letter, dropping empty columns. */
function selectedColumns(cliques: number[][], model: Model, selected: boolean[]): number[][] {
  const columns: number[][] = cliques.map(() => []);
  model.members.forEach(([c, g], k) => { if (selected[k]) columns[c].push(g); });
  return columns.filter((column) => column.length > 0);
}

/** Section 7: sort the columns, label them, and collect each group's tokens. */
function assignLetters(columns: number[][], numGroups: number, means: number[] | null): string[][] {
  const key = (members: number[]): [number, number] => {
    const lowest = Math.min(...members);
    return means ? [-Math.max(...members.map((g) => means[g])), lowest] : [lowest, lowest];
  };
  // Array.prototype.sort is stable, so equal keys keep the canonical clique order.
  const order = columns.map((_, c) => c).sort((a, b) => {
    const [a1, a2] = key(columns[a]);
    const [b1, b2] = key(columns[b]);
    return a1 !== b1 ? (a1 < b1 ? -1 : 1) : a2 - b2;
  });
  const labels = makeLetterLabels(order.length);
  const tokens: string[][] = Array.from({ length: numGroups }, () => []);
  order.forEach((column, k) => { for (const g of columns[column]) tokens[g].push(labels[k]); });
  return tokens;
}

function formatTokens(tokens: string[]): string {
  return tokens.every((t) => t.length === 1) ? tokens.join("") : tokens.join(" ");
}
