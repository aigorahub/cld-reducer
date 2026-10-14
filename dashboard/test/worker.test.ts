// The worker protocol, run in Node.js with the same code the page uses, and
// compared with the shared conformance fixtures.

import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { describe, expect, it } from "vitest";
import type { CldReduction } from "../../js/src/index.js";
import { hooks } from "../../js/src/solver.js";
import { TEMPLATE_MEANS, TEMPLATE_PAIRS, parseMeans, parsePairs, type PairRow } from "../src/csv.js";
import { checkReduction, explain, type Method } from "../src/data.js";
import { handle, studyInstance, type Input, type Reply } from "../src/worker.js";

const repo = (path: string): string => readFileSync(new URL(`../../${path}`, import.meta.url), "utf8");
const require = createRequire(new URL("../../js/package.json", import.meta.url));
const wasm = new Uint8Array(readFileSync(require.resolve("highs/runtime")));

const simple: Input = {
  pairs: parsePairs(repo("conformance/data/simple_abc_to_ac_pairs.csv")),
  means: parseMeans(repo("conformance/data/simple_abc_to_ac_means.csv")),
};
const wheat: Input = { pairs: parsePairs(repo("conformance/data/piepho2004_wheat_pairs.csv")), means: null };

async function ask(msg: Parameters<typeof handle>[0]): Promise<Reply[]> {
  const replies: Reply[] = [];
  await handle(msg, (r) => replies.push(r));
  return replies;
}

async function solve(input: Input, method: Method): Promise<CldReduction> {
  const reply = (await ask({ type: "run", id: 1, input, methods: [method], staged: false })).find((r) => r.type === "result");
  if (reply?.type !== "result") throw new Error("no result");
  return reply.reduction;
}

async function errorOf(pairs: PairRow[], means: Input["means"] = null): Promise<Reply> {
  const replies = await ask({ type: "run", id: 7, input: { pairs, means }, methods: ["letter_minimum"], staged: false });
  return replies[replies.length - 1];
}

interface Expected {
  groups: string[];
  letters: Record<string, string>;
  assignments: Record<string, string[]>;
  stats: Record<string, number>;
  objective: number;
  method: string;
}

function fixture(file: string, id: string): Expected {
  const found = JSON.parse(repo(`conformance/fixtures/${file}.json`)).cases.find((c: { id: string }) => c.id === id);
  if (!found) throw new Error(`no fixture ${id}`);
  return found.expected;
}

/** A result in the form of a fixture, so that the two compare exactly. */
function shape(r: CldReduction): Expected {
  const s = r.stats;
  return {
    groups: r.groups,
    letters: Object.fromEntries(r.rows.map((row) => [row.group, row.letters])),
    assignments: Object.fromEntries(r.rows.map((row) => [row.group, row.assignments.split(" ")])),
    stats: { assignments_before: s.assignmentsBefore, assignments_after: s.assignmentsAfter,
             num_letters_before: s.numLettersBefore, num_letters_after: s.numLettersAfter,
             num_groups: s.numGroups, num_edges: s.numEdges },
    objective: s.objective,
    method: r.method,
  };
}

function pick(e: Expected): Expected {
  return { groups: e.groups, letters: e.letters, assignments: e.assignments, stats: e.stats,
           objective: e.objective, method: e.method };
}

describe("worker", () => {
  it("loads the solver from bytes", async () => {
    expect(await ask({ type: "load", wasm })).toEqual([{ type: "ready" }]);
  });

  it("reports each method in order and then done", async () => {
    const replies = await ask({ type: "run", id: 3, input: simple, methods: ["letter_minimum", "assignment_minimum"], staged: false });
    expect(replies.map((r) => r.type)).toEqual(["start", "result", "start", "result", "done"]);
    expect(replies.every((r) => r.type !== "ready" && r.id === 3)).toBe(true);
    expect(replies.flatMap((r) => r.type === "result" ? [[r.method, r.reduction.method]] : [])).toEqual([
      ["letter_minimum", "letter_minimum"], ["assignment_minimum", "assignment_minimum"],
    ]);
    const first = replies[1];
    expect(first.type === "result" && first.milliseconds >= 0).toBe(true);
  });

  it.each([
    ["simple", "letter_minimum", "reduce_letter_minimum", "c/hand/simple-abc-pairs-means"],
    ["simple", "assignment_minimum", "reduce", "hand/simple-abc-pairs-means"],
    ["wheat", "letter_minimum", "reduce_letter_minimum", "c/hand/wheat"],
    ["wheat", "assignment_minimum", "reduce", "hand/wheat"],
  ] as const)("solves the %s example with %s as the conformance fixture %s %s", async (name, method, file, id) => {
    const reduction = await solve(name === "simple" ? simple : wheat, method);
    expect(shape(reduction)).toEqual(pick(fixture(file, id)));
    expect(checkReduction(reduction, method)).toBeNull();
    // A structured clone, as a worker message makes it, passes the same check.
    expect(checkReduction(structuredClone(reduction), method)).toBeNull();
  });

  it("solves the templates", async () => {
    const input = { pairs: parsePairs(TEMPLATE_PAIRS), means: parseMeans(TEMPLATE_MEANS) };
    const reduction = await solve(input, "letter_minimum");
    // The means give the group order, and the higher mean takes the earlier letter.
    expect(reduction.rows).toEqual([
      { group: "Control", letters: "C", assignments: "C" },
      { group: "Low dose", letters: "BC", assignments: "B C" },
      { group: "Mid dose", letters: "AB", assignments: "A B" },
      { group: "High dose", letters: "A", assignments: "A" },
    ]);
  });

  // The public result does not say which path produced it, so the browser
  // test relies on this classification of its cases.
  it("needs HiGHS for wheat with CLD-sigma only", async () => {
    const run = hooks.run;
    let calls = 0;
    hooks.run = (...args) => { calls++; return run(...args); };
    try {
      const callsOf = async (input: Input, method: Method): Promise<number> => {
        calls = 0;
        await solve(input, method);
        return calls;
      };
      expect(await callsOf(simple, "letter_minimum")).toBe(0);
      expect(await callsOf(simple, "assignment_minimum")).toBe(0);
      expect(await callsOf(wheat, "letter_minimum")).toBe(0);
      expect(await callsOf(wheat, "assignment_minimum")).toBeGreaterThan(0);
    } finally {
      hooks.run = run;
    }
  });

  it("returns an input error of the package as a reply, with a sentence that explains it", async () => {
    const pair = (group1: string, group2: string, significant = "false"): PairRow => ({ group1, group2, significant });
    const cases: [PairRow[], Input["means"], string][] = [
      [[pair("a", "b"), pair("a", "c")], null, "post_hoc_results missing unordered pairwise comparisons: "],
      [[pair("a", "b"), pair("b", "a")], null, "post_hoc_results contains duplicate unordered pairs: "],
      [[pair("a", "a")], null, "post_hoc_results must not contain self-comparisons"],
      [[pair("a", "b", "maybe")], null, "cannot coerce significance value to bool: "],
      [[pair("a", "b", "")], null, "cannot coerce significance value to bool: "],
      [[pair("a", "b")], [{ group: "a", mean: 1 }], "post_hoc_results contains groups not present in means/groups: "],
      [[pair("a", "b")], [{ group: "a", mean: 1 }, { group: "a", mean: 2 }], "group labels must be unique after string conversion"],
      [[], null, "at least one group is required"],
    ];
    for (const [pairs, means, prefix] of cases) {
      const reply = await errorOf(pairs, means);
      expect(reply).toMatchObject({ type: "error", id: 7, kind: "input" });
      const message = reply.type === "error" ? reply.message : "";
      expect(message.startsWith(prefix), message).toBe(true);
      expect(explain(message), prefix).not.toBeNull();
    }
  });

  it("stops a run at the first error", async () => {
    const replies = await ask({ type: "run", id: 4, input: { pairs: [], means: null },
                                methods: ["letter_minimum", "assignment_minimum"], staged: false });
    expect(replies.map((r) => r.type)).toEqual(["start", "error"]);
  });

  it("returns the clique limit of the package as a solver error", async () => {
    // 14 pairs of groups that differ, and all other pairs equal: 2^14 maximal cliques.
    const pairs: PairRow[] = [];
    for (let i = 0; i < 28; i++) {
      for (let j = i + 1; j < 28; j++) {
        pairs.push({ group1: `g${i}`, group2: `g${j}`, significant: String(j === i + 1 && i % 2 === 0) });
      }
    }
    const reply = await errorOf(pairs);
    expect(reply).toMatchObject({ type: "error", kind: "solver" });
    const message = reply.type === "error" ? reply.message : "";
    expect(message).toMatch(/^maximal clique enumeration exceeded max_cliques=10000/);
    expect(explain(message)).toContain("10,000");
  });

  it("runs a second stage after each method when asked", async () => {
    const replies = await ask({ type: "run", id: 5, input: simple, methods: ["letter_minimum", "assignment_minimum"], staged: true });
    expect(replies.map((r) => (r.type === "start" || r.type === "result" ? `${r.type} ${r.method} ${r.stage}` : r.type))).toEqual([
      "start letter_minimum 1", "result letter_minimum 1", "start letter_then_assignment 2", "result letter_then_assignment 2",
      "start assignment_minimum 1", "result assignment_minimum 1", "start assignment_then_letter 2",
      "result assignment_then_letter 2", "done",
    ]);
    const counts = replies.flatMap((r) => (r.type === "result"
      ? [[r.method, r.reduction.stats.numLettersAfter, r.reduction.stats.assignmentsAfter, checkReduction(r.reduction, r.method)]] : []));
    // The simple example: CLD-C has 3 letters and 9 assignments; its second stage keeps 3 letters with 8 assignments.
    expect(counts).toEqual([
      ["letter_minimum", 3, 9, null], ["letter_then_assignment", 3, 8, null],
      ["assignment_minimum", 3, 8, null], ["assignment_then_letter", 3, 8, null],
    ]);
  });

  it("returns the display before reduction, and an input error as a reply", async () => {
    const [before] = await ask({ type: "before", id: 6, input: wheat });
    expect(before.type === "before" && [before.id, before.before.letters, before.before.assignments]).toEqual([6, 4, 56]);
    const [bad] = await ask({ type: "before", id: 8, input: { pairs: [{ group1: "a", group2: "b", significant: "false" },
                                                                         { group1: "a", group2: "c", significant: "true" }], means: null } });
    expect(bad).toMatchObject({ type: "error", id: 8, kind: "input" });
  });

  it("runs a study and returns one reply for each instance", async () => {
    const replies = await ask({ type: "study", id: 9, study: { sizes: [8, 12], count: 2, firstSeed: 5, timeLimit: 30 } });
    expect(replies.map((r) => (r.type === "instance" ? `${r.instance.n}/${r.instance.seed}` : r.type)))
      .toEqual(["8/5", "8/6", "12/5", "12/6", "done"]);
  });

  it("solves a simulated instance with four consistent solves", async () => {
    const i = await studyInstance(20, 3, 30);
    const s = i.solves;
    for (const m of ["letter_minimum", "assignment_minimum", "letter_then_assignment", "assignment_then_letter"] as const) {
      expect(s[m].letters).not.toBeNull();
      expect(s[m].milliseconds).toBeGreaterThanOrEqual(0);
    }
    expect(s.letter_minimum.letters!).toBeLessThanOrEqual(i.lettersBefore);
    expect(s.assignment_minimum.assignments!).toBeLessThanOrEqual(i.assignmentsBefore);
    expect(s.letter_then_assignment.letters).toBe(s.letter_minimum.letters);
    expect(s.letter_then_assignment.assignments!).toBeGreaterThanOrEqual(s.assignment_minimum.assignments!);
    expect(s.assignment_then_letter.assignments).toBe(s.assignment_minimum.assignments);
    expect(s.assignment_then_letter.letters!).toBeGreaterThanOrEqual(s.letter_minimum.letters!);
  });

  it("records a solve that reaches the time limit as not finished", async () => {
    const run = hooks.run;
    hooks.run = () => ({ status: "time_limit", text: "Time limit reached" });
    try {
      // CLD-sigma on this instance needs HiGHS, so it reaches the stub.
      const i = await studyInstance(30, 1, 30);
      const unfinished = Object.values(i.solves).filter((x) => x.letters === null);
      expect(unfinished.length).toBeGreaterThan(0);
      expect(unfinished.every((x) => x.assignments === null)).toBe(true);
      // A second stage whose first stage did not finish does not run, and it has no time.
      expect(i.solves.assignment_minimum.letters).toBeNull();
      expect(i.solves.assignment_then_letter.milliseconds).toBeNull();
      expect(i.solves.assignment_minimum.milliseconds).toBeGreaterThanOrEqual(0);
    } finally {
      hooks.run = run;
    }
  });
});
