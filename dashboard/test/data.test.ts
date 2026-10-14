import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import type { CldReduction } from "../../js/src/index.js";
import { parseMeans, parsePairs } from "../src/csv.js";
import { EXAMPLES, METHODS, checkReduction, count, duration, explain, meanText, resultsCsv, resultsJson,
         sharedTokens, tokensOf, type MethodResult } from "../src/data.js";

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
  it("lists CLD-C first, with the one quantity that each method minimizes", () => {
    expect(METHODS.map((m) => [m.id, m.name, m.minimizes])).toEqual([
      ["letter_minimum", "CLD-C", "Distinct letters"], ["assignment_minimum", "CLD-sigma", "Assignments"],
    ]);
  });
});

describe("examples", () => {
  it("name files that the conformance manifest pins", () => {
    const pinned = Object.keys(JSON.parse(repo("conformance/manifest.json")).data);
    const used = EXAMPLES.flatMap((e) => [e.pairsFile, ...(e.meansFile ? [e.meansFile] : [])]);
    expect([...used].sort()).toEqual([...pinned].sort());
  });

  it("describe the size of their data", () => {
    for (const example of EXAMPLES) {
      const pairs = parsePairs(repo(`conformance/data/${example.pairsFile}`));
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

  it("rejects statistics that do not match the letters", () => {
    const more = { ...chain(), stats: { ...chain().stats, assignmentsAfter: 5 } };
    expect(checkReduction(more, "letter_minimum")).toBe("The statistics of the reply do not match its letters.");
    const objective = { ...chain(), stats: { ...chain().stats, objective: 4 } };
    expect(checkReduction(objective, "letter_minimum")).toBe("The objective value of the reply does not match its letters.");
    // For CLD-sigma the objective is the number of assignments.
    expect(checkReduction({ ...objective, method: "assignment_minimum" }, "assignment_minimum")).toBeNull();
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
    return { method: "letter_minimum", reduction, milliseconds: 12.345 };
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

  it("write JSON with the exact labels, the statistics, and the package version", () => {
    const file = JSON.parse(resultsJson([result()], { source: "Pasted text", pairs: 3, means: null }, "9.9.9"));
    expect(file).toEqual({
      package: "cld-reducer", version: "9.9.9",
      input: { source: "Pasted text", pairs: 3, means: null },
      results: [{
        method: "letter_minimum", minimizes: "distinct letters", relationshipPreserved: true,
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
