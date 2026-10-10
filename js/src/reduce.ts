// The reduction itself: docs/algorithm.md sections 3 to 9.

import { maximalCliques } from "./cliques.js";
import { SolverError } from "./errors.js";
import {
  adjacencyToGraph, checkControls, checkMethod, pairsToGraph,
  type Graph, type ReduceOptions,
} from "./input.js";
import { assignLetters, formatTokens } from "./display.js";
import { solveCanonical } from "./canonical.js";
import { graphContext } from "./model.js";
import { getSolver } from "./solver.js";

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
  const strategy = checkMethod(options.method);
  const { timeLimit, maxCliques } = checkControls(options);
  const { groups, adjacency, means } = graph;
  const cliques = maximalCliques(adjacency, maxCliques);
  const model = strategy.builder(graphContext(graph, cliques));
  await getSolver();
  const { selected, minimum } = solveCanonical(model, timeLimit, strategy);

  const columns = strategy.decoder(cliques, model, selected);
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

  const before = cliques.reduce((sum, q) => sum + q.length, 0);
  const after = tokens.reduce((s, t) => s + t.length, 0);
  if (minimum !== (strategy.countsAssignments ? after : columns.length)) throw new SolverError("HiGHS returned an invalid solution");
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
    method: strategy.name,
    relationshipPreserved: true,
    adjacency: adjacency.map((row) => [...row]),
  };
}
