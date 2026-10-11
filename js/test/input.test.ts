import { describe, expect, it } from "vitest";
import { InvalidInputError, SolverError, reduceFromAdjacency, reduceLetters } from "../src/index.js";
import { SIMPLE, SIMPLE_LETTERS, SIMPLE_MEANS } from "./helpers.js";

const TRIPLE = [
  { group1: "a", group2: "b", significant: false },
  { group1: "a", group2: "c", significant: true },
  { group1: "b", group2: "c", significant: false },
];

describe("means", () => {
  it("rejects a plain object, because integer-like keys reorder", async () => {
    const means = { "10": 1, "2": 2, "3": 3 };
    await expect(reduceFromAdjacency(SIMPLE.slice(0, 3).map((r) => r.slice(0, 3)), { method: "assignment_minimum", means: means as any, groups: ["10", "2", "3"] }))
      .rejects.toBeInstanceOf(InvalidInputError);
    await expect(reduceLetters(TRIPLE, { method: "assignment_minimum", means: { a: 1, b: 2, c: 3 } as any }))
      .rejects.toThrow(/plain object/);
  });

  it("accepts a Map and an array of { group, mean }, with the same result", async () => {
    const asMap = new Map(SIMPLE_MEANS.map((m) => [m.group, m.mean] as const));
    const a = await reduceFromAdjacency(SIMPLE, { method: "assignment_minimum", means: asMap });
    const b = await reduceFromAdjacency(SIMPLE, { method: "assignment_minimum", means: SIMPLE_MEANS });
    expect(a.letters).toEqual(SIMPLE_LETTERS);
    expect(b).toEqual(a);
  });

  it("the order of the means is the group order for pairs, and means are matched by label for a matrix", async () => {
    const byMeans = await reduceLetters(TRIPLE, { method: "assignment_minimum", means: [
      { group: "c", mean: 1 }, { group: "b", mean: 2 }, { group: "a", mean: 3 }] });
    expect(byMeans.groups).toEqual(["c", "b", "a"]);
    const shuffled = await reduceFromAdjacency(SIMPLE, { method: "assignment_minimum", means: [...SIMPLE_MEANS].reverse() });
    expect(shuffled.groups).toEqual(["1", "2", "3", "4", "5"]);
    expect(shuffled.letters).toEqual(SIMPLE_LETTERS);
  });

  it.each([
    [null, "means must be finite numbers"], ["1", "means must be finite numbers"],
    [NaN, "means must be finite numbers"], [Infinity, "means must be finite numbers"],
  ])("rejects the mean %j", async (mean, message) => {
    await expect(reduceFromAdjacency([[true]], { method: "assignment_minimum", groups: ["a"], means: [{ group: "a", mean: mean as any }] }))
      .rejects.toThrow(message);
  });

  it("rejects a missing group", async () => {
    await expect(reduceFromAdjacency([[true, false], [false, true]], { method: "assignment_minimum", groups: ["a", "b"], means: [{ group: "a", mean: 1 }] }))
      .rejects.toThrow(/means are missing values for groups/);
  });
});

describe("pairs", () => {
  it("takes the group order from first appearance in group1, then group2", async () => {
    const out = await reduceLetters([
      { group1: "b", group2: "a", significant: false },
      { group1: "c", group2: "a", significant: true },
      { group1: "c", group2: "b", significant: false }], { method: "assignment_minimum" });
    expect(out.groups).toEqual(["b", "c", "a"]);
  });

  it("accepts every significance form", async () => {
    const forms = [true, "yes", " NS ", 1, 0, "not significant"];
    const labels = ["w", "x", "y", "z"];
    const rows = [] as Record<string, unknown>[];
    let k = 0;
    for (let i = 0; i < 4; i++) for (let j = i + 1; j < 4; j++) rows.push({ group1: labels[i], group2: labels[j], significant: forms[k++ % forms.length] });
    const out = await reduceLetters(rows, { method: "assignment_minimum" });
    expect(out.groups).toEqual(labels);
    expect(out.stats.numEdges).toBe(3); // " NS ", 0, and "not significant"
  });

  it("supports other column names and ignores extra columns", async () => {
    const out = await reduceLetters(
      TRIPLE.map((r) => ({ u: r.group1, v: r.group2, s: r.significant, note: "x" })),
      { method: "assignment_minimum", group1: "u", group2: "v", significant: "s" });
    expect(out.groups).toEqual(["a", "b", "c"]);
  });

  it.each([
    ["maybe", /cannot coerce significance value to bool/], [null, /cannot coerce/], [2, /cannot coerce/],
    [0.5, /cannot coerce/], ["", /cannot coerce/], [undefined, /cannot coerce/],
  ])("rejects the significance value %j", async (value, message) => {
    await expect(reduceLetters([{ ...TRIPLE[0], significant: value }, TRIPLE[1], TRIPLE[2]], { method: "assignment_minimum" })).rejects.toThrow(message);
  });

  it("reports the structural errors in the documented order", async () => {
    const a = TRIPLE[0];
    await expect(reduceLetters([{ group1: "a", group2: "b" }], { method: "assignment_minimum" })).rejects.toThrow(/missing required columns: \["significant"\]/);
    await expect(reduceLetters([{ ...a, group2: "a" }, TRIPLE[1], TRIPLE[2]], { method: "assignment_minimum" })).rejects.toThrow(/self-comparisons/);
    await expect(reduceLetters([...TRIPLE, { ...a, group1: "b", group2: "a" }], { method: "assignment_minimum" })).rejects.toThrow(/duplicate unordered pairs/);
    await expect(reduceLetters([a, TRIPLE[1]], { method: "assignment_minimum" })).rejects.toThrow(/missing unordered pairwise comparisons/);
    await expect(reduceLetters(TRIPLE, { method: "assignment_minimum", means: [{ group: "a", mean: 1 }, { group: "b", mean: 2 }] }))
      .rejects.toThrow(/groups not present in means\/groups/);
    await expect(reduceLetters([a, TRIPLE[1]], { method: "greedy" })).rejects.toThrow(/missing unordered/);
  });

  it("rejects input that is not an array of objects", async () => {
    await expect(reduceLetters("nope" as any, { method: "assignment_minimum" })).rejects.toBeInstanceOf(InvalidInputError);
    await expect(reduceLetters([1, 2] as any, { method: "assignment_minimum" })).rejects.toBeInstanceOf(InvalidInputError);
  });

  it("converts numeric labels to strings", async () => {
    const out = await reduceLetters([
      { group1: 10, group2: 2, significant: false }, { group1: 10, group2: 3, significant: true },
      { group1: 2, group2: 3, significant: false }], { method: "assignment_minimum" });
    expect(out.groups).toEqual(["10", "2", "3"]);
  });
});

describe("adjacency", () => {
  const two = (m: unknown) => reduceFromAdjacency(m as any, { method: "assignment_minimum", groups: ["a", "b"] });
  it.each([
    [[[1, null], [null, 1]], /must not contain missing values/],
    [[[1, undefined], [undefined, 1]], /must not contain missing values/],
    [[[1, NaN], [NaN, 1]], /must not contain missing values/],
    [[["True", "False"], ["False", "True"]], /only booleans or explicit 0\/1 values/],
    [[[1, 2], [2, 1]], /only booleans or explicit 0\/1 values/],
    [[[1, 0.5], [0.5, 1]], /only booleans or explicit 0\/1 values/],
    [[[1, 0, 0], [0, 1, 0]], /must be a square matrix/],
    [[], /must be a square matrix/],
    [[[1, 1], [0, 1]], /must be symmetric/],
    [[[1, 0], [0, 0]], /diagonal must be/],
  ])("rejects %j", async (matrix, message) => {
    await expect(two(matrix)).rejects.toThrow(message);
  });

  it("reads holes in a sparse array as missing", async () => {
    const sparse: unknown[][] = [[1, 0], [0]];
    sparse[1][1] = undefined;
    delete sparse[1][1];
    sparse[1].length = 2;
    await expect(two(sparse)).rejects.toThrow(/missing values/);
  });

  it("checks groups", async () => {
    await expect(reduceFromAdjacency([[1]], { method: "assignment_minimum", groups: [] })).rejects.toThrow(/at least one group is required/);
    await expect(reduceFromAdjacency([[1, 0], [0, 1]], { method: "assignment_minimum", groups: ["a", "a"] })).rejects.toThrow(/unique after string conversion/);
    await expect(reduceFromAdjacency([[1, 0], [0, 1]], { method: "assignment_minimum", groups: [1, "1"] })).rejects.toThrow(/unique after string conversion/);
    await expect(reduceFromAdjacency([[1, 0], [0, 1]], { method: "assignment_minimum", groups: ["a"] })).rejects.toThrow(/must match adjacency dimensions/);
  });

  it("uses 1-based string labels by default and accepts 0/1 numbers", async () => {
    const out = await reduceFromAdjacency([[1, 0], [0, 1]], { method: "assignment_minimum" });
    expect(out.groups).toEqual(["1", "2"]);
    expect(out.letters).toEqual({ "1": "A", "2": "B" });
  });
});

describe("controls", () => {
  it("checks the method first, then timeLimit, then maxCliques", async () => {
    const m = [[1, 0], [0, 1]];
    await expect(reduceFromAdjacency(m, { method: "greedy", timeLimit: 0 })).rejects.toThrow(/unsupported CLD reduction method/);
    await expect(reduceFromAdjacency(m, { method: "assignment_minimum", timeLimit: 0, maxCliques: 0 })).rejects.toThrow(/time_limit must be positive/);
    await expect(reduceFromAdjacency(m, { method: "assignment_minimum", maxCliques: 0 })).rejects.toBeInstanceOf(SolverError);
    for (const timeLimit of [0, -1, "30", true, NaN, Infinity]) {
      await expect(reduceFromAdjacency(m, { method: "assignment_minimum", timeLimit: timeLimit as any })).rejects.toThrow(/time_limit must be positive when provided/);
    }
    for (const maxCliques of [0, -3, 1.5, "10", true]) {
      await expect(reduceFromAdjacency(m, { method: "assignment_minimum", maxCliques: maxCliques as any })).rejects.toThrow(/max_cliques must be a positive integer or null/);
    }
  });

  it("accepts the hyphenated method and stores the canonical name", async () => {
    const out = await reduceFromAdjacency([[1]], { method: "assignment-minimum" });
    expect(out.method).toBe("assignment_minimum");
  });

  it("applies the clique cap to the count, and null removes it", async () => {
    const identity = [[1, 0, 0], [0, 1, 0], [0, 0, 1]];
    await reduceFromAdjacency(identity, { method: "assignment_minimum", maxCliques: 3 });
    await expect(reduceFromAdjacency(identity, { method: "assignment_minimum", maxCliques: 2 })).rejects.toThrow(/exceeded max_cliques=2/);
    const out = await reduceFromAdjacency(identity, { method: "assignment_minimum", maxCliques: null });
    expect(out.stats.numLettersBefore).toBe(3);
  });
});
