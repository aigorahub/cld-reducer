// The display before reduction and the staged solve, against the package and
// against an exhaustive search over every membership subset of small graphs.

import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { beforeAll, describe, expect, it } from "vitest";
import { SolverError, loadSolver, reduceLetters } from "../../js/src/index.js";
import { clock } from "../../js/src/canonical.js";
import { hooks } from "../../js/src/solver.js";
import { maximalCliques } from "../../js/src/cliques.js";
import { parseMeans, parsePairs, type PairRow } from "../src/csv.js";
import { checkReduction } from "../src/data.js";
import { TABLE_II } from "../src/simulate.js";
import { beforeDisplay, stagedSolve } from "../src/staged.js";

const repo = (path: string): string => readFileSync(new URL(`../../${path}`, import.meta.url), "utf8");
const require = createRequire(new URL("../../js/package.json", import.meta.url));

beforeAll(async () => {
  await loadSolver({ wasmBinary: new Uint8Array(readFileSync(require.resolve("highs/runtime"))) });
});

function pairsOf(n: number, edges: number[][]): PairRow[] {
  const equal = new Set(edges.map(([i, j]) => `${Math.min(i, j)},${Math.max(i, j)}`));
  const rows: PairRow[] = [];
  for (let i = 0; i < n; i++) {
    for (let j = i + 1; j < n; j++) rows.push({ group1: `g${i}`, group2: `g${j}`, significant: String(!equal.has(`${i},${j}`)) });
  }
  return rows;
}

/**
 * Lexicographic minima over every display: every set of cliques, of any size and not only maximal
 * ones, that covers each group and each joined pair. It shares no rule with the model: it searches
 * all cliques, and branches on the first group or pair that the chosen cliques do not cover yet.
 */
function exhaustive(n: number, edges: number[][]): { lettersFirst: [number, number]; assignmentsFirst: [number, number] } {
  const joined = (i: number, j: number): boolean => edges.some(([a, b]) => (a === i && b === j) || (a === j && b === i));
  const bits = (mask: number): number[] => Array.from({ length: n }, (_, i) => i).filter((i) => mask & (1 << i));
  const cliques: number[] = [];
  for (let mask = 1; mask < 1 << n; mask++) {
    const g = bits(mask);
    if (g.every((i, k) => g.slice(k + 1).every((j) => joined(i, j)))) cliques.push(mask);
  }
  const elements: number[] = [];
  for (let i = 0; i < n; i++) elements.push(1 << i);
  for (let i = 0; i < n; i++) for (let j = i + 1; j < n; j++) if (joined(i, j)) elements.push((1 << i) | (1 << j));
  let lettersFirst: [number, number] = [Infinity, Infinity];
  let assignmentsFirst: [number, number] = [Infinity, Infinity];
  const search = (chosen: number[], letters: number, assignments: number): void => {
    // Both counts only grow, so stop when neither order can improve.
    const noLetters = letters > lettersFirst[0] || (letters === lettersFirst[0] && assignments >= lettersFirst[1]);
    const noAssignments = assignments > assignmentsFirst[0] || (assignments === assignmentsFirst[0] && letters >= assignmentsFirst[1]);
    if (noLetters && noAssignments) return;
    const open = elements.find((e) => !chosen.some((q) => (q & e) === e));
    if (open === undefined) {
      if (!noLetters) lettersFirst = [letters, assignments];
      if (!noAssignments) assignmentsFirst = [assignments, letters];
      return;
    }
    for (const q of cliques) {
      if ((q & open) === open && !chosen.includes(q)) search([...chosen, q], letters + 1, assignments + bits(q).length);
    }
  };
  search([], 0, 0);
  return { lettersFirst, assignmentsFirst };
}

async function staged(pairs: PairRow[], means: ReturnType<typeof parseMeans> = null) {
  const c = await reduceLetters(pairs, { means, method: "letter_minimum" });
  const sigma = await reduceLetters(pairs, { means, method: "assignment_minimum" });
  const cThenSigma = stagedSolve(pairs, means, "letter_then_assignment", c.stats.objective);
  const sigmaThenC = stagedSolve(pairs, means, "assignment_then_letter", sigma.stats.objective);
  return { c, sigma, cThenSigma, sigmaThenC };
}

describe("before display", () => {
  it("has one letter for each maximal clique and the counts of the package statistics", async () => {
    for (const [pairsFile, meansFile] of [["simple_abc_to_ac_pairs.csv", "simple_abc_to_ac_means.csv"],
                                          ["piepho2004_wheat_pairs.csv", null]] as const) {
      const pairs = parsePairs(repo(`conformance/data/${pairsFile}`));
      const means = meansFile ? parseMeans(repo(`conformance/data/${meansFile}`)) : null;
      const before = beforeDisplay(pairs, means);
      const after = await reduceLetters(pairs, { means });
      expect([before.letters, before.assignments]).toEqual([after.stats.numLettersBefore, after.stats.assignmentsBefore]);
      expect(before.rows.map((r) => r.group)).toEqual(after.groups);
    }
    const simple = beforeDisplay(parsePairs(repo("conformance/data/simple_abc_to_ac_pairs.csv")),
                                 parseMeans(repo("conformance/data/simple_abc_to_ac_means.csv")));
    expect(simple.rows.map((r) => r.letters)).toEqual(["A", "AB", "ABC", "BC", "C"]);
  });
});

describe("staged solve", () => {
  it("equals a search over all displays on every graph of up to 5 vertices and on small random graphs", async () => {
    const graphs = ["exhaustive-n3", "exhaustive-n4", "exhaustive-n5", "random-n06", "random-n07"]
      .flatMap((name) => JSON.parse(repo(`conformance/inputs/${name}.json`)).graphs as { n: number; edges: number[][] }[]);
    let checked = 0;
    for (const { n, edges } of graphs) {
      const adjacency = Array.from({ length: n }, (_, i) => Array.from({ length: n }, (_, j) => i === j));
      for (const [i, j] of edges) adjacency[i][j] = adjacency[j][i] = true;
      if (maximalCliques(adjacency, null).reduce((s, q) => s + q.length, 0) > 14) continue;
      const pairs = pairsOf(n, edges);
      const want = exhaustive(n, edges);
      const got = await staged(pairs);
      expect([got.cThenSigma.stats.numLettersAfter, got.cThenSigma.stats.assignmentsAfter]).toEqual(want.lettersFirst);
      expect([got.sigmaThenC.stats.assignmentsAfter, got.sigmaThenC.stats.numLettersAfter]).toEqual(want.assignmentsFirst);
      expect(checkReduction(got.cThenSigma, "letter_then_assignment")).toBeNull();
      expect(checkReduction(got.sigmaThenC, "assignment_then_letter")).toBeNull();
      checked++;
    }
    expect(checked).toBeGreaterThan(1000);
  });

  it("separates the two orders on the graph of Table II of the 2012 paper", async () => {
    // No letter-minimum display of this graph is assignment-minimum.
    const got = await staged(parsePairs(TABLE_II));
    const { c, sigma, cThenSigma, sigmaThenC } = got;
    expect(cThenSigma.stats.numLettersAfter).toBe(c.stats.numLettersAfter);
    expect(sigmaThenC.stats.assignmentsAfter).toBe(sigma.stats.assignmentsAfter);
    expect(cThenSigma.stats.assignmentsAfter).toBeGreaterThan(sigma.stats.assignmentsAfter);
    expect(sigmaThenC.stats.numLettersAfter).toBeGreaterThan(c.stats.numLettersAfter);
    expect(cThenSigma.stats.assignmentsAfter).toBeLessThanOrEqual(c.stats.assignmentsAfter);
    expect(sigmaThenC.stats.numLettersAfter).toBeLessThanOrEqual(sigma.stats.numLettersAfter);
  });

  it("keeps the first stage value and never does worse than one method alone on the examples", async () => {
    for (const file of ["simple_abc_to_ac_pairs.csv", "piepho2004_wheat_pairs.csv"]) {
      const { c, sigma, cThenSigma, sigmaThenC } = await staged(parsePairs(repo(`conformance/data/${file}`)));
      expect(cThenSigma.stats.numLettersAfter).toBe(c.stats.numLettersAfter);
      expect(cThenSigma.stats.assignmentsAfter).toBeLessThanOrEqual(c.stats.assignmentsAfter);
      expect(sigmaThenC.stats.assignmentsAfter).toBe(sigma.stats.assignmentsAfter);
      expect(sigmaThenC.stats.numLettersAfter).toBeLessThanOrEqual(sigma.stats.numLettersAfter);
    }
  });
});

describe("staged solve time limit", () => {
  const pairs = parsePairs(TABLE_II);

  it("rejects a limit that the package rejects", () => {
    for (const limit of [NaN, Infinity, -1, 0]) {
      expect(() => stagedSolve(pairs, null, "letter_then_assignment", 5, limit)).toThrow(SolverError);
      expect(() => stagedSolve(pairs, null, "assignment_then_letter", 18, limit))
        .toThrow("time_limit must be positive when provided");
    }
  });

  it("counts only the solves, as the package does, and not the preparation before them", () => {
    // A clock that jumps by 10 seconds after its first reading: with a limit of 1 second, a
    // budget that started before the preparation has nothing left for the first solve.
    const real = clock.now;
    let reads = 0;
    clock.now = () => (reads++ === 0 ? 0 : 10 + reads * 1e-6);
    try {
      expect(stagedSolve(pairs, null, "letter_then_assignment", 5, 1).stats.assignmentsAfter).toBe(19);
    } finally {
      clock.now = real;
    }
    // A clock that moves 0.6 seconds at each reading: the solves spend more than the limit.
    reads = 0;
    clock.now = () => reads++ * 0.6;
    try {
      expect(() => stagedSolve(pairs, null, "assignment_then_letter", 18, 1)).toThrow("Time limit reached");
    } finally {
      clock.now = real;
    }
  });
});

describe("staged solve errors", () => {
  it("name the second stage also for a check of the engine on a HiGHS reply", () => {
    const run = hooks.run;
    hooks.run = () => ({ status: "optimal", text: "Optimal", values: new Float64Array(0), objective: 0 });
    try {
      expect(() => stagedSolve(parsePairs(TABLE_II), null, "assignment_then_letter", 18))
        .toThrow(/^staged solve failed: HiGHS returned an invalid solution/);
    } finally {
      hooks.run = run;
    }
  });

  it("name the second stage, also when the third solve finds another minimum than the bound", () => {
    // 20 is not the minimum assignment count of Table II (18): the cliques with the fewest letters
    // within 20 assignments need only 19, so the third solve does not reach the bound.
    expect(() => stagedSolve(parsePairs(TABLE_II), null, "assignment_then_letter", 20))
      .toThrow(/^staged solve failed: /);
  });
});
