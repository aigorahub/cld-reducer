import { describe, expect, it } from "vitest";
import { reduceFromAdjacency, reduceLetters } from "../src/index.js";
import { SIMPLE, SIMPLE_LETTERS, SIMPLE_MEANS, hasConformance, readCsv, wheatPairs } from "./helpers.js";

const matrix = (n: number, edges: [number, number][]) => {
  const m = Array.from({ length: n }, (_, i) => Array.from({ length: n }, (_, j) => i === j));
  for (const [i, j] of edges) m[i][j] = m[j][i] = true;
  return m;
};

describe("reduction", () => {
  it("reduces the simple ABC example to AC", async () => {
    const out = await reduceFromAdjacency(SIMPLE, { method: "assignment_minimum", means: SIMPLE_MEANS });
    expect(out.letters).toEqual(SIMPLE_LETTERS);
    expect(out.assignments["3"]).toEqual(["A", "C"]);
    expect(out.stats).toMatchObject({
      assignmentsBefore: 9, assignmentsAfter: 8, numLettersBefore: 3, numLettersAfter: 3,
      numGroups: 5, numEdges: 7, solverStatus: "Optimal", objective: 8,
    });
    expect(out.stats.reductionPct).toBe((9 - 8) / 9 * 100);
    expect(out.relationshipPreserved).toBe(true);
    expect(out.rows[2]).toEqual({ group: "3", letters: "AC", assignments: "A C" });
    expect(out.method).toBe("assignment_minimum");
    expect(out.adjacency).toEqual(SIMPLE);
  });

  it("renames letters through the canonical clique order (D4 example)", async () => {
    const m = matrix(5, [[0, 1], [0, 2], [0, 3], [0, 4], [1, 4], [2, 4]]);
    const out = await reduceFromAdjacency(m, { method: "assignment_minimum", groups: ["0", "1", "2", "3", "4"] });
    expect(out.letters).toEqual({ "0": "ABC", "1": "A", "2": "B", "3": "C", "4": "AB" });
  });

  it("uses labels after Z, with spaces in the display", async () => {
    const star = matrix(28, Array.from({ length: 27 }, (_, i) => [0, i + 1] as [number, number]));
    const out = await reduceFromAdjacency(star, { method: "assignment_minimum" });
    const tokens = out.assignments["1"];
    expect(tokens).toHaveLength(27);
    expect(tokens.slice(-2)).toEqual(["Z", "AA"]);
    expect(out.letters["1"].split(" ")).toEqual(tokens);
  });

  it("keeps __proto__ and integer-like labels as ordinary groups", async () => {
    const out = await reduceFromAdjacency(matrix(3, [[0, 1]]), { method: "assignment_minimum", groups: ["__proto__", "10", "2"] });
    expect(out.groups).toEqual(["__proto__", "10", "2"]);
    expect(Object.keys(out.letters)).toContain("__proto__");
    expect(out.letters["__proto__"]).toBe("A");
  });

  it.runIf(hasConformance)("reduces the Piepho (2004) wheat example from 56 to 44 assignments", async () => {
    const out = await reduceLetters(wheatPairs(), { method: "assignment_minimum" });
    expect(out.stats).toMatchObject({
      assignmentsBefore: 56, assignmentsAfter: 44, numLettersBefore: 4, numLettersAfter: 4, numGroups: 20,
    });
    expect(out.stats.reductionPct).toBe(12 / 56 * 100);
    expect(readCsv("piepho2004_wheat_pairs.csv")).toHaveLength(190);
  });

  it("returns the same result for the pairs and the adjacency route", async () => {
    const labels = ["1", "2", "3", "4", "5"];
    const rows: Record<string, unknown>[] = [];
    for (let i = 0; i < 5; i++) for (let j = i + 1; j < 5; j++) rows.push({ group1: labels[i], group2: labels[j], significant: !SIMPLE[i][j] });
    const a = await reduceLetters(rows, { method: "assignment_minimum", means: SIMPLE_MEANS });
    const b = await reduceFromAdjacency(SIMPLE, { method: "assignment_minimum", means: SIMPLE_MEANS });
    expect(a).toEqual(b);
  });
});
