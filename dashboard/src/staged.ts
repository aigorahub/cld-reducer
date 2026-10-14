// The display before reduction, and the experimental staged solve of the page.
// Both use the package's own modules: input checks, maximal cliques, vertex
// reduction, the CLD-sigma model, the canonical engine, and letter assignment.
// Neither is part of the specification or of the R, Python, and npm packages.
// docs/plans/dashboard-staged-solve/plan.md states the model and its proof.

import type { CldReduction } from "../../js/src/index.js";
import { maximalCliques } from "../../js/src/cliques.js";
import { clock, solveCanonical } from "../../js/src/canonical.js";
import { assignLetters, formatTokens } from "../../js/src/display.js";
import { SolverError } from "../../js/src/errors.js";
import { DEFAULT_MAX_CLIQUES, checkControls, pairsToGraph } from "../../js/src/input.js";
import {
  assignmentCoverage, assignmentEssentialDecisions, buildAssignmentPlan, compileAssignmentPlan, graphContext,
  methods, selectedColumns, type Model, type Strategy,
} from "../../js/src/model.js";
import { expandGraphColumns, reduceGraphVertices } from "../../js/src/reduction-graph.js";
import type { MeanRow, PairRow } from "./csv.js";
import type { StagedOrder } from "./data.js";

export interface Before {
  rows: { group: string; letters: string; assignments: string }[];
  letters: number;
  assignments: number;
}

/** The display with one letter for each maximal clique, in the letter order of the package. */
export function beforeDisplay(pairs: PairRow[], means: MeanRow[] | null): Before {
  const graph = pairsToGraph(pairs, { means });
  const cliques = maximalCliques(graph.adjacency, DEFAULT_MAX_CLIQUES);
  const tokens = assignLetters(cliques, graph.groups.length, graph.means);
  return {
    rows: graph.groups.map((group, i) => ({ group, letters: formatTokens(tokens[i]), assignments: tokens[i].join(" ") })),
    letters: cliques.length,
    assignments: tokens.reduce((sum, t) => sum + t.length, 0),
  };
}

const ASSIGNMENTS = methods.find((m) => m.name === "assignment_minimum")!;
const FAILED = "staged solve failed: ";

/**
 * The second stage. For "letter_then_assignment", `bound` is the minimum letter
 * count and the result has the fewest assignments among displays with that many
 * letters. For "assignment_then_letter", `bound` is the minimum assignment count
 * and the result has the fewest letters among displays with that many assignments.
 */
export function stagedSolve(pairs: PairRow[], means: MeanRow[] | null, order: StagedOrder, bound: number,
                            timeLimit: number | null = null): CldReduction {
  const limit = checkControls({ timeLimit }).timeLimit;
  // One budget for the solves, as in the package (docs/algorithm.md): input checks, vertex
  // reduction, clique enumeration, and model construction are not part of it.
  let spent = 0;
  const timed = <T>(solve: (left: number | null) => T): T => {
    const left = limit === null ? null : limit - spent;
    if (left !== null && left <= 0) throw new SolverError(FAILED + "Time limit reached");
    const t0 = clock.now();
    try {
      return solve(left);
    } finally {
      spent += clock.now() - t0;
    }
  };
  const graph = pairsToGraph(pairs, { means });
  const { groups, adjacency } = graph;
  const reduced = reduceGraphVertices(adjacency);
  const small = { adjacency: reduced.adjacency, groups: reduced.classes.map((c) => groups[c[0]]), means: null };
  const cliques = maximalCliques(reduced.adjacency, DEFAULT_MAX_CLIQUES);
  const context = graphContext(small, cliques, reduced.weights, true);
  const plan = buildAssignmentPlan(context);
  const base = compileAssignmentPlan(plan).problem;

  // Add one column u(c) for each clique, the rows x(c, g) - u(c) <= 0, and the bound row.
  const first = base.numCols;
  const numCols = first + cliques.length;
  const starts = Array.from(base.starts);
  const indices = Array.from(base.indices);
  const values = Array.from(base.values);
  const rowLower = Array.from(base.rowLower);
  const rowUpper = Array.from(base.rowUpper);
  const addRow = (entries: [number, number][], lower: number, upper: number): void => {
    for (const [k, v] of entries) { indices.push(k); values.push(v); }
    starts.push(indices.length);
    rowLower.push(lower);
    rowUpper.push(upper);
  };
  plan.members.forEach(([c], k) => addRow([[k, 1], [first + c, -1]], -Infinity, 0));
  const lettersFirst = order === "letter_then_assignment";
  if (lettersFirst) addRow(cliques.map((_, c) => [first + c, 1]), -Infinity, bound);
  else addRow(plan.members.map(([, g], k) => [k, reduced.weights[g]]), -Infinity, bound);

  const cost = new Float64Array(numCols);
  if (lettersFirst) cost.set(plan.cost);
  else cost.fill(1, first);
  const problem = {
    numCols, cost,
    decisionColumns: lettersFirst ? plan.members.map((_, k) => k) : cliques.map((_, c) => first + c),
    starts: Int32Array.from(starts), indices: Int32Array.from(indices), values: Float64Array.from(values),
    rowLower: Float64Array.from(rowLower), rowUpper: Float64Array.from(rowUpper),
  };
  const model: Model = { ...plan, problem };

  let columns: number[][];
  if (lettersFirst) {
    const used = (selected: boolean[]): number => new Set(plan.members.filter((_, k) => selected[k]).map(([c]) => c)).size;
    const strategy: Strategy = {
      ...ASSIGNMENTS, name: order, failurePrefix: FAILED,
      coverage: (m, selected) => assignmentCoverage(m, selected) && used(selected) <= bound,
      essentialDecisions: assignmentEssentialDecisions,
    };
    // The decisions are the memberships, with positive weights, so the essential cover proof applies.
    const { selected } = timed((left) => solveCanonical(model, left, strategy));
    columns = selectedColumns(cliques, plan, selected);
  } else {
    // A vertex or edge that one clique alone covers forces that clique.
    const cover = [...context.cliquesOf, ...context.edges.map(([i, j]) =>
      context.cliquesOf[i].filter((c) => context.cliquesOf[j].includes(c)))];
    const forced = [...new Set(cover.filter((row) => row.length === 1).map((row) => first + row[0]))].sort((a, b) => a - b);
    const strategy: Strategy = {
      ...ASSIGNMENTS, name: order, failurePrefix: FAILED, countsAssignments: false,
      coverage: (_m, selected) => cover.every((row) => row.some((c) => selected[c])),
      essentialDecisions: () => forced,
    };
    // A cover by the chosen cliques does not prove a membership set within the bound, so no proof here.
    const chosen = timed((left) => solveCanonical(model, left, strategy, false)).selected;
    // Canonical memberships inside the chosen cliques. Their minimum must be the bound.
    const subset = cliques.filter((_, c) => chosen[c]);
    const subPlan = ASSIGNMENTS.planner(graphContext(small, subset, reduced.weights, true));
    // The failure prefix of the second stage, so that an error names the second stage.
    const inner = timed((left) => solveCanonical(subPlan, left, { ...ASSIGNMENTS, failurePrefix: FAILED }));
    if (inner.minimum !== bound) throw new SolverError(FAILED + "HiGHS returned an invalid solution");
    columns = ASSIGNMENTS.decoder(subset, subPlan, inner.selected);
    if (columns.length !== subset.length) throw new SolverError(FAILED + "HiGHS returned an invalid solution");
  }

  const expanded = expandGraphColumns(columns, reduced.classes);
  const tokens = assignLetters(expanded, groups.length, graph.means);
  for (let i = 0; i < groups.length; i++) {
    for (let j = 0; j < groups.length; j++) {
      if (tokens[i].some((t) => tokens[j].includes(t)) !== adjacency[i][j]) {
        throw new SolverError(FAILED + "optimized letters did not preserve the input pairwise relationships");
      }
    }
  }
  const before = cliques.reduce((sum, q) => sum + q.reduce((s, g) => s + reduced.weights[g], 0), 0);
  const after = tokens.reduce((sum, t) => sum + t.length, 0);
  const letters = expanded.length;
  // The first stage is optimal, so the second stage keeps its value exactly.
  if (lettersFirst ? letters !== bound : after !== bound) throw new SolverError(FAILED + "HiGHS returned an invalid solution");
  const display = tokens.map(formatTokens);
  return {
    letters: Object.fromEntries(groups.map((g, i) => [g, display[i]])),
    assignments: Object.fromEntries(groups.map((g, i) => [g, tokens[i]])),
    groups: [...groups],
    rows: groups.map((g, i) => ({ group: g, letters: display[i], assignments: tokens[i].join(" ") })),
    stats: {
      assignmentsBefore: before, assignmentsAfter: after,
      reductionPct: before ? (before - after) / before * 100 : 0,
      numLettersBefore: cliques.length, numLettersAfter: letters, numGroups: groups.length,
      numEdges: adjacency.reduce((sum, row, i) => sum + row.filter((edge, j) => j > i && edge).length, 0),
      solverStatus: "Optimal",
      objective: lettersFirst ? after : letters,
    },
    method: order,
    relationshipPreserved: true,
    adjacency: adjacency.map((row) => [...row]),
  };
}
