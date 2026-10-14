// Input rules and solution checks of docs/algorithm.md sections 1, 2, and 6 that the final
// review (round 1) asked to pin: binary memberships, missing labels, duplicate mean labels,
// ASCII-only trimming, zero rows, and label-exact pairs.
import { afterEach, describe, expect, it } from "vitest";
import { InvalidInputError, SolverError, reduceFromAdjacency, reduceLetters } from "../src/index.js";
import * as solver from "../src/solver.js";

const realRun = solver.hooks.run;
afterEach(() => { solver.hooks.run = realRun; });

const PATH3 = [[true, true, false], [true, true, true], [false, true, true]];

function allPairs(labels: string[], nonsignificant: Set<string>) {
  const rows: { group1: unknown; group2: unknown; significant: unknown }[] = [];
  for (let i = 0; i < labels.length; i++) {
    for (let j = i + 1; j < labels.length; j++) {
      rows.push({ group1: labels[i], group2: labels[j], significant: !nonsignificant.has(`${i},${j}`) });
    }
  }
  return rows;
}

describe("binary memberships (section 6, check 2)", () => {
  it.each([["two", 2], ["minus one", -1], ["infinite", Infinity]])(
    "a membership of %s is an invalid solution", async (_name, value) => {
      solver.hooks.run = (problem, lower, upper, sumLimit, t) => {
        const out = realRun(problem, lower, upper, sumLimit, t);
        if (!out.values) return out;
        const v = Float64Array.from(out.values);
        v[0] = value as number;
        return { ...out, values: v };
      };
      await expect(reduceFromAdjacency([[true]], { method: "assignment_minimum" })).rejects.toThrow(SolverError);
      await expect(reduceFromAdjacency([[true]], { method: "assignment_minimum" })).rejects.toThrow(/HiGHS returned an invalid solution/);
    });
});

describe("input rules (sections 1 and 2)", () => {
  it("rejects duplicate mean labels for adjacency input", async () => {
    const means = [{ group: "a", mean: 1 }, { group: "b", mean: 2 }, { group: "c", mean: 3 }, { group: "a", mean: 9 }];
    await expect(reduceFromAdjacency(PATH3, { method: "assignment_minimum", groups: ["a", "b", "c"], means }))
      .rejects.toThrow(/^means contain duplicate groups: /);
    await expect(reduceFromAdjacency(PATH3, { method: "assignment_minimum", groups: ["a", "b", "c"], means }))
      .rejects.toThrow(InvalidInputError);
  });

  it.each([["null", null], ["undefined", undefined], ["NaN", NaN]])("rejects a missing label (%s)", async (_name, label) => {
    const rows = allPairs(["a", "b", "c"], new Set(["0,1", "1,2"]));
    rows[1].group2 = label;
    await expect(reduceLetters(rows, { method: "assignment_minimum" })).rejects.toThrow(/^group labels must not be missing/);
    await expect(reduceFromAdjacency([[true, false], [false, true]], { method: "assignment_minimum", groups: ["a", label] }))
      .rejects.toThrow(/^group labels must not be missing/);
  });

  it("checks missing labels before significance", async () => {
    const rows = allPairs(["a", "b", "c"], new Set());
    rows[0].significant = "maybe";
    rows[1].group1 = null;
    await expect(reduceLetters(rows, { method: "assignment_minimum" })).rejects.toThrow(/^group labels must not be missing/);
  });

  it("treats an empty array as a table with zero rows", async () => {
    const result = await reduceLetters([], { method: "assignment_minimum", means: new Map([["a", 1]]) });
    expect(result.letters).toEqual({ a: "A" });
    await expect(reduceLetters([], { method: "assignment_minimum" })).rejects.toThrow(/^at least one group is required/);
  });

  it("trims only spaces, tabs, carriage returns, and line feeds", async () => {
    const rows = (value: string) => [{ group1: "a", group2: "b", significant: value }];
    expect((await reduceLetters(rows(" ns\t\r\n"), { method: "assignment_minimum" })).letters).toEqual({ a: "A", b: "A" });
    await expect(reduceLetters(rows("ns\u00a0"), { method: "assignment_minimum" })).rejects.toThrow(/^cannot coerce significance value to bool: /);
  });

  it.each(["\r", "\u0000", "|", ","])("identifies pairs by exact labels (separator %j)", async (sep) => {
    const labels = ["a", `b${sep}c`, `a${sep}b`, "c"];
    const rows = allPairs(labels, new Set(["0,1", "1,2", "2,3"]));
    const result = await reduceLetters(rows, { method: "assignment_minimum" });
    expect(result.groups).toEqual(labels);
    await expect(reduceLetters(rows.slice(1), { method: "assignment_minimum" })).rejects.toThrow(/^post_hoc_results missing unordered pairwise comparisons: /);
  });

  it("keeps the empty-string label", async () => {
    const result = await reduceFromAdjacency([[true, false], [false, true]], { method: "assignment_minimum", groups: ["", "b"] });
    expect(result.rows.map((r) => [r.group, r.letters])).toEqual([["", "A"], ["b", "B"]]);
  });
});
