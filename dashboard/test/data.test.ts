import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import type { CldReduction } from "../../js/src/index.js";
import { parseMeans, parsePairs } from "../src/csv.js";
import { beforeDisplay } from "../src/staged.js";
import { EXAMPLES, METHODS, SECOND_STAGE, STAGES, TABLE_X, checkBefore, checkInput, checkReduction, checkStage, count,
         displayOf, duration, explain, isTime, meanText, methodInfo, resultsCsv, resultsJson, sharedTokens, tokensOf,
         type MethodResult } from "../src/data.js";

const repo = (path: string): string => readFileSync(new URL(`../../${path}`, import.meta.url), "utf8");

/** A valid CLD-C result for three groups in a chain: low = mid, mid = high, low and high differ. */
function chain(): CldReduction {
  return {
    letters: { low: "A", mid: "AB", high: "B" },
    assignments: { low: ["A"], mid: ["A", "B"], high: ["B"] },
    groups: ["low", "mid", "high"],
    rows: [
      { group: "low", letters: "A", assignments: "A" },
      { group: "mid", letters: "AB", assignments: "A B" },
      { group: "high", letters: "B", assignments: "B" },
    ],
    stats: { assignmentsBefore: 4, assignmentsAfter: 4, reductionPct: 0, numLettersBefore: 2, numLettersAfter: 2,
             numGroups: 3, numEdges: 2, solverStatus: "Optimal", objective: 2 },
    method: "letter_minimum",
    relationshipPreserved: true,
    adjacency: [[true, true, false], [true, true, true], [false, true, true]],
  };
}

describe("methods", () => {
  it("follow each method with the stage that minimizes the other quantity", () => {
    expect(SECOND_STAGE).toEqual({ letter_minimum: "letter_then_assignment", assignment_minimum: "assignment_then_letter" });
    expect(STAGES.map((s) => methodInfo(s.id).name)).toEqual(["CLD-C then CLD-sigma", "CLD-sigma then CLD-C"]);
  });

  it("lists CLD-C first, with the one quantity that each method minimizes", () => {
    expect(METHODS.map((m) => [m.id, m.name, m.minimizes])).toEqual([
      ["letter_minimum", "CLD-C", "Distinct letters"], ["assignment_minimum", "CLD-sigma", "Assignments"],
    ]);
  });
});

describe("examples", () => {
  it("name files that the conformance manifest pins", () => {
    const pinned = Object.keys(JSON.parse(repo("conformance/manifest.json")).data);
    const used = EXAMPLES.flatMap((e) => [...(e.pairsFile ? [e.pairsFile] : []), ...(e.meansFile ? [e.meansFile] : [])]);
    expect([...used].sort()).toEqual([...pinned].sort());
  });

  it("describe the size of their data", () => {
    for (const example of EXAMPLES) {
      const pairs = parsePairs(example.pairsText ?? repo(`conformance/data/${example.pairsFile}`));
      const groups = new Set(pairs.flatMap((p) => [p.group1, p.group2])).size;
      expect(example.description).toContain(`${groups} `);
      expect(example.description).toContain(`${pairs.length} pairwise decisions`);
      expect(example.description.includes("without means")).toBe(example.meansFile === null);
      if (example.meansFile) expect(parseMeans(repo(`conformance/data/${example.meansFile}`))).toHaveLength(groups);
    }
  });

  it("cite the sources of js/NOTICE", () => {
    const notice = repo("js/NOTICE");
    for (const source of EXAMPLES.flatMap((e) => e.sources)) {
      expect(notice).toContain(source.url.replace("https://doi.org/", "doi:"));
    }
  });
});

describe("checkReduction", () => {
  it("accepts a valid result", () => {
    expect(checkReduction(chain(), "letter_minimum")).toBeNull();
  });

  it("rejects a reply that is not a complete result of the requested method", () => {
    expect(checkReduction(null, "letter_minimum")).toBe("The reply holds no result.");
    expect(checkReduction(chain(), "assignment_minimum")).toMatch(/^The reply is for the method letter_minimum/);
    expect(checkReduction({ ...chain(), relationshipPreserved: false }, "letter_minimum"))
      .toBe("The reply does not confirm the relationship check.");
    expect(checkReduction({ ...chain(), groups: [] }, "letter_minimum")).toBe("The reply has no list of groups.");
    expect(checkReduction({ ...chain(), rows: chain().rows.slice(1) }, "letter_minimum"))
      .toBe("The reply does not have one row for each group.");
    expect(checkReduction({ ...chain(), rows: [...chain().rows].reverse() }, "letter_minimum"))
      .toBe("A row of the reply does not match its group.");
    expect(checkReduction({ ...chain(), adjacency: [[true]] }, "letter_minimum"))
      .toBe("The reply has no relationship matrix of the right size.");
    expect(checkReduction({ ...chain(), stats: { ...chain().stats, objective: 1.5 } }, "letter_minimum"))
      .toBe("A statistic of the reply is not a whole number.");
  });

  it("rejects letters that do not give back the input decisions", () => {
    const merged = chain();
    merged.rows[2] = { group: "high", letters: "A", assignments: "A" };
    expect(checkReduction(merged, "letter_minimum")).toBe("The letters of low and high do not match the input decision.");
    const split = chain();
    split.rows[1] = { group: "mid", letters: "A", assignments: "A" };
    expect(checkReduction(split, "letter_minimum")).toBe("The letters of mid and high do not match the input decision.");
  });

  it("rejects a display string or a token list that does not match the letters", () => {
    const display = chain();
    display.rows[0] = { group: "low", letters: "WRONG", assignments: "A" };
    expect(checkReduction(display, "letter_minimum")).toBe("The display of low does not match its letter tokens.");
    const spaced = chain();
    spaced.rows[1] = { group: "mid", letters: "A B", assignments: "A B" };
    expect(checkReduction(spaced, "letter_minimum")).toBe("The display of mid does not match its letter tokens.");
    const twice = chain();
    twice.rows[1] = { group: "mid", letters: "AAB", assignments: "A A B" };
    expect(checkReduction(twice, "letter_minimum")).toBe("The letter tokens of mid are not a list of distinct letters.");
    const none = chain();
    none.rows[2] = { group: "high", letters: "", assignments: "" };
    expect(checkReduction(none, "letter_minimum")).toBe("The letter tokens of high are not a list of distinct letters.");
  });

  it("rejects statistics that do not match the letters", () => {
    const more = { ...chain(), stats: { ...chain().stats, assignmentsAfter: 5 } };
    expect(checkReduction(more, "letter_minimum")).toBe("The statistics of the reply do not match its letters.");
    const objective = { ...chain(), stats: { ...chain().stats, objective: 4 } };
    expect(checkReduction(objective, "letter_minimum")).toBe("The objective value of the reply does not match its letters.");
    // For CLD-sigma and its second stage the objective is the number of assignments; for the other two, letters.
    expect(checkReduction({ ...objective, method: "assignment_minimum" }, "assignment_minimum")).toBeNull();
    expect(checkReduction({ ...objective, method: "letter_then_assignment" }, "letter_then_assignment")).toBeNull();
    expect(checkReduction({ ...chain(), method: "assignment_then_letter" }, "assignment_then_letter")).toBeNull();
    expect(checkReduction({ ...objective, method: "assignment_then_letter" }, "assignment_then_letter"))
      .toBe("The objective value of the reply does not match its letters.");
  });
});

describe("checkReduction of the statistics that the page shows and exports", () => {
  it("rejects more letters or assignments than before, and a percentage or status that does not fit", () => {
    const r = chain();
    r.stats.assignmentsBefore = 3;
    expect(checkReduction(r, "letter_minimum")).toBe("The reply has more letters or assignments than the display before reduction.");
    const s = chain();
    s.stats.numLettersBefore = 1;
    expect(checkReduction(s, "letter_minimum")).toBe("The reply has more letters or assignments than the display before reduction.");
    const t = chain();
    t.stats.reductionPct = 25;
    expect(checkReduction(t, "letter_minimum")).toBe("The reduction percentage of the reply does not match its counts.");
    const u = chain() as unknown as { stats: Record<string, unknown> };
    delete u.stats.reductionPct;
    expect(checkReduction(u, "letter_minimum")).toBe("The reduction percentage of the reply is not a number.");
    const v = chain() as unknown as { stats: Record<string, unknown> };
    v.stats.solverStatus = 1;
    expect(checkReduction(v, "letter_minimum")).toBe("The solver status of the reply is not a text.");
  });

  it("accepts a time that is a finite number and not negative", () => {
    expect([0, 1.5, 30000].every(isTime)).toBe(true);
    expect([NaN, -1, Infinity, "1", null].some(isTime)).toBe(false);
  });
});

describe("checkInput", () => {
  const pairs = (lowHigh: string, extra = "low") => [
    { group1: extra, group2: "mid", significant: "false" },
    { group1: "mid", group2: "high", significant: "false" },
    { group1: extra, group2: "high", significant: lowHigh },
  ];

  it("accepts a result for the groups and decisions of the input", () => {
    expect(checkInput(chain(), pairs("true"), null)).toBeNull();
  });

  it("rejects a result that is consistent in itself but has another decision or other groups", () => {
    expect(checkInput(chain(), pairs("false"), null)).toBe("The reply changes the decision for low and high.");
    expect(checkInput(chain(), pairs("true", "other"), null)).toBe("The reply has other groups than the input.");
    expect(checkInput(chain(), pairs("true").slice(0, 2), null)).toBe("The page cannot read the decisions of the input.");
    const r = chain();
    r.stats.numEdges = 3;
    expect(checkInput(r, pairs("true"), null)).toBe("The edge count of the reply does not match the input.");
  });
});

describe("checkBefore", () => {
  const pairs = [
    { group1: "low", group2: "mid", significant: "false" },
    { group1: "mid", group2: "high", significant: "false" },
    { group1: "low", group2: "high", significant: "true" },
  ];
  const before = () => ({ rows: chain().rows.map((r) => ({ ...r })), letters: 2, assignments: 4 });

  it("accepts letters that give back the input decisions, with their counts", () => {
    expect(checkBefore(before(), pairs, null)).toBeNull();
  });

  it("rejects other letters, other counts, other groups, and no display", () => {
    const b = before();
    b.rows[2] = { group: "high", letters: "A", assignments: "A" };
    expect(checkBefore(b, pairs, null)).toBe("The letters of low and high do not match the input decision.");
    expect(checkBefore({ ...before(), assignments: 5 }, pairs, null))
      .toBe("The counts of the display before reduction do not match its letters.");
    expect(checkBefore({ ...before(), rows: before().rows.slice(1) }, pairs, null))
      .toBe("The display before reduction does not have one row for each group of the input.");
    expect(checkBefore(null, pairs, null)).toBe("The reply holds no display before reduction.");
  });

  it("checks a display with 8,192 letters fast enough for the page", () => {
    const pairs = [];
    for (let i = 0; i < 26; i++) {
      for (let j = i + 1; j < 26; j++) pairs.push({ group1: `g${i}`, group2: `g${j}`, significant: String(j === i + 1 && i % 2 === 0) });
    }
    const before = beforeDisplay(pairs, null);
    expect(before.letters).toBe(8192);
    const t0 = performance.now();
    expect(checkBefore(before, pairs, null)).toBeNull();
    expect(performance.now() - t0).toBeLessThan(2000);
  });

  it("rejects a letter that is not a maximal clique, and two letters with the same groups", () => {
    // Three groups that do not differ: the one maximal clique is all three.
    const all = [
      { group1: "a", group2: "b", significant: "false" },
      { group1: "b", group2: "c", significant: "false" },
      { group1: "a", group2: "c", significant: "false" },
    ];
    const display = (a: string, b: string, c: string) => {
      const rows = [["a", a], ["b", b], ["c", c]].map(([group, t]) => ({ group, letters: displayOf(t.split(" ")), assignments: t }));
      const tokens = rows.map((r) => r.assignments.split(" "));
      return { rows, letters: new Set(tokens.flat()).size, assignments: tokens.flat().length };
    };
    expect(checkBefore(display("A", "A", "A"), all, null)).toBeNull();
    expect(checkBefore(display("A B", "A B", "A"), all, null)).toBe("Letter B before reduction is not a maximal clique of the input.");
    expect(checkBefore(display("A B", "A B", "A B"), all, null)).toBe("Letter B before reduction has the same groups as another letter.");
    const triangle = [
      { group1: "a", group2: "b", significant: "false" }, { group1: "b", group2: "c", significant: "false" },
      { group1: "a", group2: "c", significant: "false" }, { group1: "a", group2: "x", significant: "false" },
      { group1: "b", group2: "x", significant: "false" }, { group1: "c", group2: "x", significant: "true" },
    ];
    const four = (rows: [string, string][]) => {
      const r = rows.map(([group, t]) => ({ group, letters: displayOf(t.split(" ")), assignments: t }));
      const tokens = r.map((row) => row.assignments.split(" "));
      return { rows: r, letters: new Set(tokens.flat()).size, assignments: tokens.flat().length };
    };
    // Maximal cliques {a, b, c} and {a, b, x}: both are needed, so drop nothing here; check the complete one.
    expect(checkBefore(four([["a", "A B"], ["b", "A B"], ["c", "A"], ["x", "B"]]), triangle, null)).toBeNull();
    // The triangle a, b, c is a maximal clique, but the cliques a b x, b c y, and a c z cover its pairs.
    // A display without it still matches every decision, and the page finds that it is incomplete.
    const joined = new Set(["a,b", "b,c", "a,c", "a,x", "b,x", "b,y", "c,y", "a,z", "c,z"]);
    const names = ["a", "b", "c", "x", "y", "z"];
    const sun = names.flatMap((g, i) => names.slice(i + 1).map((h) => ({ group1: g, group2: h, significant: String(!joined.has(`${g},${h}`)) })));
    const full: [string, string][] = [["a", "A B C"], ["b", "A B D"], ["c", "A C D"], ["x", "B"], ["y", "D"], ["z", "C"]];
    expect(checkBefore(four(full), sun, null)).toBeNull();
    const without = four(full.map(([g, t]) => [g, t.split(" ").filter((l) => l !== "A").join(" ")]));
    expect(checkBefore(without, sun, null)).toBe("The display before reduction misses a maximal clique of the input.");
  });
});

describe("checkStage", () => {
  const withStats = (letters: number, assignments: number): CldReduction =>
    ({ ...chain(), stats: { ...chain().stats, numLettersAfter: letters, assignmentsAfter: assignments } });
  it("requires the second stage to keep the minimum of the first and not to be worse in the other quantity", () => {
    expect(checkStage(withStats(3, 9), withStats(3, 8), "letter_then_assignment")).toBeNull();
    expect(checkStage(withStats(3, 9), withStats(4, 8), "letter_then_assignment"))
      .toBe("The second stage does not keep the minimum of the first stage.");
    expect(checkStage(withStats(3, 9), withStats(3, 10), "letter_then_assignment")).not.toBeNull();
    expect(checkStage(withStats(4, 8), withStats(3, 8), "assignment_then_letter")).toBeNull();
    expect(checkStage(withStats(4, 8), withStats(3, 9), "assignment_then_letter")).not.toBeNull();
    expect(checkStage(withStats(4, 8), withStats(5, 8), "assignment_then_letter")).not.toBeNull();
  });
});

describe("shared letters", () => {
  it("are the tokens that two rows have in common", () => {
    const tokens = ["A B", "B AA", "", "AA"].map(tokensOf);
    expect(tokens).toEqual([["A", "B"], ["B", "AA"], [], ["AA"]]);
    expect(sharedTokens(tokens, 0, 1)).toEqual(["B"]);
    expect(sharedTokens(tokens, 1, 3)).toEqual(["AA"]);
    expect(sharedTokens(tokens, 0, 3)).toEqual([]);
  });

  it("display without a separator when every token has one character, else with spaces", () => {
    expect(displayOf(["A", "B", "C"])).toBe("ABC");
    expect(displayOf(["Z", "AA"])).toBe("Z AA");
    expect(displayOf([])).toBe("");
  });
});

describe("explain", () => {
  it("has a sentence for the missing pair rule and none for an unknown message", () => {
    expect(explain('post_hoc_results missing unordered pairwise comparisons: ["a|b"]')).toContain("A missing pair is an error.");
    expect(explain("something else")).toBeNull();
  });
});

describe("formats", () => {
  it("write counts, durations, and means", () => {
    expect(count(1, "letter", "letters")).toBe("1 letter");
    expect(count(1200, "pair", "pairs")).toBe("1,200 pairs");
    expect([0.2, 16.4, 999.4, 1240, 12340].map(duration)).toEqual(["<1 ms", "16 ms", "999 ms", "1.24 s", "12.3 s"]);
    expect([3.3, 0.1 + 0.2, -100].map(meanText)).toEqual(["3.3", "0.3", "-100"]);
  });
});

describe("result files", () => {
  const result = (): MethodResult => {
    const reduction = chain();
    reduction.groups[0] = reduction.rows[0].group = '=SUM(A1), "low"';
    return { method: "letter_minimum", stage: 1, reduction, milliseconds: 12.345 };
  };

  it("write CSV with one row for each method and group, and guard a spreadsheet formula", () => {
    expect(resultsCsv([result()], null)).toBe(
      "method,group,letters,assignments\n" +
      'letter_minimum,"\'=SUM(A1), ""low""",A,A\n' +
      "letter_minimum,mid,AB,A B\n" +
      "letter_minimum,high,B,B\n");
    const means = [{ group: "mid", mean: 2.5 }, { group: "high", mean: 1 }];
    expect(resultsCsv([{ ...result(), reduction: chain() }], means).split("\n").slice(0, 3)).toEqual([
      "method,group,mean,letters,assignments", "letter_minimum,low,,A,A", "letter_minimum,mid,2.5,AB,A B",
    ]);
  });

  it("write a very large time in JSON as a number", () => {
    const file = JSON.parse(resultsJson([{ ...result(), milliseconds: 1e308 }], { source: "x", pairs: 3, means: null }, "1.0.0"));
    expect(file.results[0].milliseconds).toBe(1e308);
  });

  it("write JSON with the exact labels, the statistics, and the package version", () => {
    const file = JSON.parse(resultsJson([result()], { source: "Pasted text", pairs: 3, means: null }, "9.9.9"));
    expect(file).toEqual({
      package: "cld-reducer", version: "9.9.9",
      input: { source: "Pasted text", pairs: 3, means: null },
      before: null,
      results: [{
        method: "letter_minimum", stage: 1, minimizes: "distinct letters", relationshipPreserved: true,
        stats: chain().stats, milliseconds: 12.3,
        rows: [
          { group: '=SUM(A1), "low"', letters: "A", assignments: ["A"] },
          { group: "mid", letters: "AB", assignments: ["A", "B"] },
          { group: "high", letters: "B", assignments: ["B"] },
        ],
      }],
    });
  });
});

describe("result files with the display before reduction", () => {
  it("put the before rows first and record each stage", () => {
    const before = { rows: [{ group: "low", letters: "A", assignments: "A" }, { group: "mid", letters: "AB", assignments: "A B" },
                            { group: "high", letters: "B", assignments: "B" }], letters: 2, assignments: 4, milliseconds: 0.44 };
    const stage2: MethodResult = { method: "letter_then_assignment", stage: 2, reduction: { ...chain(), method: "letter_then_assignment",
      stats: { ...chain().stats, objective: 4 } }, milliseconds: 3 };
    const csv = resultsCsv([{ method: "letter_minimum", stage: 1, reduction: chain(), milliseconds: 1 }, stage2], null, before)
      .trimEnd().split("\n");
    expect(csv.map((l) => l.split(",")[0])).toEqual(["method", "before", "before", "before", "letter_minimum", "letter_minimum",
      "letter_minimum", "letter_then_assignment", "letter_then_assignment", "letter_then_assignment"]);
    const json = JSON.parse(resultsJson([stage2], { source: "x", pairs: 3, means: null }, "1.0.0", before));
    expect(json.before).toEqual({ letters: 2, assignments: 4, milliseconds: 0.4,
      rows: [{ group: "low", letters: "A", assignments: ["A"] }, { group: "mid", letters: "AB", assignments: ["A", "B"] },
             { group: "high", letters: "B", assignments: ["B"] }] });
    expect(json.results[0]).toMatchObject({ method: "letter_then_assignment", stage: 2,
                                            minimizes: "assignments, among displays with the fewest letters" });
  });
});

describe("Table X", () => {
  it("has N from 10 to 45 with the published first and last rows", () => {
    expect(TABLE_X.map((r) => r.n)).toEqual(Array.from({ length: 36 }, (_, k) => k + 10));
    expect(TABLE_X[0]).toEqual({ n: 10, pc: 100, et: 0, ma: 14.381, ea: 13.98 });
    expect(TABLE_X[35]).toEqual({ n: 45, pc: 0.8, et: 10.444, ma: 124, ea: 99.75 });
  });
});
