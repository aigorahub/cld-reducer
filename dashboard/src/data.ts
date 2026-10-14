// Methods, examples, the check of a solver reply, and the result files.

import type { CldReduction } from "../../js/src/index.js";
import { maximalCliques } from "../../js/src/cliques.js";
import { DEFAULT_MAX_CLIQUES, pairsToGraph, type Graph } from "../../js/src/input.js";
import type { MeanRow, PairRow } from "./csv.js";
import { TABLE_II } from "./simulate.js";

export type Method = "letter_minimum" | "assignment_minimum";
/** The experimental two-stage orders of the page (src/staged.ts). */
export type StagedOrder = "letter_then_assignment" | "assignment_then_letter";
export type ResultMethod = Method | StagedOrder;

/** The objective value of a result is its letter count for these methods, else its assignment count. */
const COUNTS_LETTERS: readonly ResultMethod[] = ["letter_minimum", "assignment_then_letter"];

export interface MethodInfo {
  id: ResultMethod;
  name: string;
  /** What the method minimizes. */
  minimizes: string;
}

// CLD-C first: it is the default of the package.
export const METHODS: readonly (MethodInfo & { id: Method })[] = [
  { id: "letter_minimum", name: "CLD-C", minimizes: "Distinct letters" },
  { id: "assignment_minimum", name: "CLD-sigma", minimizes: "Assignments" },
];

/** The second stages of the page. They are experimental and not part of the packages. */
export const STAGES: readonly (MethodInfo & { id: StagedOrder })[] = [
  { id: "letter_then_assignment", name: "CLD-C then CLD-sigma",
    minimizes: "Assignments, among displays with the fewest letters" },
  { id: "assignment_then_letter", name: "CLD-sigma then CLD-C",
    minimizes: "Letters, among displays with the fewest assignments" },
];

/** The second stage that follows each method. */
export const SECOND_STAGE: Readonly<Record<Method, StagedOrder>> = {
  letter_minimum: "letter_then_assignment",
  assignment_minimum: "assignment_then_letter",
};

export function methodInfo(id: ResultMethod): MethodInfo {
  return [...METHODS, ...STAGES].find((m) => m.id === id)!;
}

export interface Example {
  id: string;
  title: string;
  /** Files in conformance/data. build.mjs puts their text into the page. */
  pairsFile: string | null;
  meansFile: string | null;
  /** The decisions as text, for an example without a file. */
  pairsText?: string;
  description: string;
  sources: { text: string; url: string }[];
}

// Source notes follow js/NOTICE.
export const EXAMPLES: readonly Example[] = [
  {
    id: "simple", title: "Simple example",
    pairsFile: "simple_abc_to_ac_pairs.csv", meansFile: "simple_abc_to_ac_means.csv",
    description: "5 groups with means and 10 pairwise decisions. The teaching example of the 2012 paper.",
    sources: [{ text: "Ennis, Fayle, and Ennis (2012)", url: "https://doi.org/10.1145/2133803.2275596" }],
  },
  {
    id: "wheat", title: "Wheat yield",
    pairsFile: "piepho2004_wheat_pairs.csv", meansFile: null,
    description: "20 wheat treatments and 190 pairwise decisions, without means.",
    sources: [
      { text: "Piepho (2004)", url: "https://doi.org/10.1198/1061860043515" },
      { text: "Table VIII of Ennis, Fayle, and Ennis (2012)", url: "https://doi.org/10.1145/2133803.2275596" },
    ],
  },
  {
    id: "table-ii", title: "Table II graph",
    pairsFile: null, meansFile: null, pairsText: TABLE_II,
    description: "8 groups and 28 pairwise decisions, without means. No letter-minimum display of this graph is assignment-minimum.",
    sources: [{ text: "Table II of Ennis, Fayle, and Ennis (2012)", url: "https://doi.org/10.1145/2133803.2275596" }],
  },
];

export interface MethodResult {
  method: ResultMethod;
  /** 1 for a package method, 2 for the second stage that follows it. */
  stage: 1 | 2;
  reduction: CldReduction;
  /** Time of the package call in the worker. */
  milliseconds: number;
}

/** The letter tokens of one row of a result. */
export function tokensOf(assignments: string): string[] {
  return assignments === "" ? [] : assignments.split(" ");
}

/** The display string of letter tokens, as the package writes it (docs/algorithm.md section 7). */
export function displayOf(tokens: readonly string[]): string {
  return tokens.every((t) => t.length === 1) ? tokens.join("") : tokens.join(" ");
}

/** The letters that groups i and j share, in the order of group i. */
export function sharedTokens(tokens: readonly string[][], i: number, j: number): string[] {
  return tokens[i].filter((t) => tokens[j].includes(t));
}

const isCount = (v: unknown): v is number => typeof v === "number" && Number.isInteger(v) && v >= 0;

/** A time in milliseconds: a finite number that is not negative. */
export const isTime = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v) && v >= 0;

/**
 * Check a reply before the page shows it. The package makes the same
 * relationship check; this one protects the page from a reply that changed
 * on the way. Returns the first problem, or null.
 */
export function checkReduction(value: unknown, method: ResultMethod): string | null {
  if (value === null || typeof value !== "object") return "The reply holds no result.";
  const r = value as Partial<CldReduction>;
  if (r.method !== method) return `The reply is for the method ${String(r.method)}, not ${method}.`;
  if (r.relationshipPreserved !== true) return "The reply does not confirm the relationship check.";
  const { groups, rows, adjacency, stats } = r;
  if (!Array.isArray(groups) || groups.length === 0 || !groups.every((g) => typeof g === "string")) {
    return "The reply has no list of groups.";
  }
  const n = groups.length;
  if (!Array.isArray(rows) || rows.length !== n) return "The reply does not have one row for each group.";
  for (let i = 0; i < n; i++) {
    const row = rows[i] as unknown;
    if (row === null || typeof row !== "object") return "A row of the reply is not a record.";
    const { group, letters, assignments } = row as Record<string, unknown>;
    if (group !== groups[i] || typeof letters !== "string" || typeof assignments !== "string") {
      return "A row of the reply does not match its group.";
    }
  }
  if (!Array.isArray(adjacency) || adjacency.length !== n ||
      !adjacency.every((line) => Array.isArray(line) && line.length === n &&
                                 line.every((cell) => typeof cell === "boolean"))) {
    return "The reply has no relationship matrix of the right size.";
  }
  if (stats === null || typeof stats !== "object") return "The reply has no statistics.";
  const counts = [stats.assignmentsBefore, stats.assignmentsAfter, stats.numLettersBefore,
                  stats.numLettersAfter, stats.numGroups, stats.numEdges, stats.objective];
  if (!counts.every(isCount)) return "A statistic of the reply is not a whole number.";
  if (typeof stats.reductionPct !== "number" || !Number.isFinite(stats.reductionPct)) {
    return "The reduction percentage of the reply is not a number.";
  }
  if (typeof stats.solverStatus !== "string") return "The solver status of the reply is not a text.";

  const problem = checkLetters(groups, rows, adjacency);
  if (problem) return problem;
  const tokens = rows.map((row) => tokensOf(row.assignments));
  const assignments = tokens.reduce((sum, t) => sum + t.length, 0);
  const letters = new Set(tokens.flat()).size;
  if (stats.numGroups !== n || stats.assignmentsAfter !== assignments || stats.numLettersAfter !== letters) {
    return "The statistics of the reply do not match its letters.";
  }
  if (stats.objective !== (COUNTS_LETTERS.includes(method) ? letters : assignments)) {
    return "The objective value of the reply does not match its letters.";
  }
  // Every method chooses among the maximal cliques, so neither count can grow.
  if (assignments > stats.assignmentsBefore || letters > stats.numLettersBefore) {
    return "The reply has more letters or assignments than the display before reduction.";
  }
  const before = stats.assignmentsBefore;
  if (Math.abs(stats.reductionPct - (before ? (before - assignments) / before * 100 : 0)) > 1e-9) {
    return "The reduction percentage of the reply does not match its counts.";
  }
  return null;
}

interface LetterRow {
  group: string;
  letters: string;
  assignments: string;
}

/**
 * Check letter rows against a relationship matrix: each row has distinct
 * letters and their display string, and two groups share a letter exactly when
 * the matrix joins them. Returns the first problem, or null.
 */
function checkLetters(groups: readonly string[], rows: readonly LetterRow[],
                      adjacency: readonly (readonly boolean[])[]): string | null {
  const n = groups.length;
  const tokens = rows.map((row) => tokensOf(row.assignments));
  for (let i = 0; i < n; i++) {
    const own = tokens[i];
    if (own.length === 0 || own.includes("") || new Set(own).size !== own.length) {
      return `The letter tokens of ${groups[i]} are not a list of distinct letters.`;
    }
    // The page shows and exports the display string, so it must be the one of the tokens.
    if (rows[i].letters !== displayOf(own)) return `The display of ${groups[i]} does not match its letter tokens.`;
  }
  // A display before reduction can have thousands of letters, so look them up in sets.
  const sets = tokens.map((own) => new Set(own));
  const shares = (i: number, j: number): boolean => {
    const [few, many] = tokens[i].length <= tokens[j].length ? [tokens[i], sets[j]] : [tokens[j], sets[i]];
    return few.some((t) => many.has(t));
  };
  for (let i = 0; i < n; i++) {
    for (let j = 0; j < n; j++) {
      if ((i === j || shares(i, j)) !== adjacency[i][j]) {
        return `The letters of ${groups[i]} and ${groups[j]} do not match the input decision.`;
      }
    }
  }
  return null;
}

/** The groups and decisions of the input, as the package reads them, or null. */
function inputGraph(pairs: readonly PairRow[], means: readonly MeanRow[] | null): Graph | null {
  try {
    return pairsToGraph(pairs, { means: means as MeanRow[] | null });
  } catch {
    return null;
  }
}

/**
 * Check that a result that passed checkReduction is for the input of its run:
 * the same groups in the same order, and the same decision for each pair.
 */
export function checkInput(result: CldReduction, pairs: readonly PairRow[],
                           means: readonly MeanRow[] | null): string | null {
  const graph = inputGraph(pairs, means);
  if (!graph) return "The page cannot read the decisions of the input.";
  if (JSON.stringify(graph.groups) !== JSON.stringify(result.groups)) return "The reply has other groups than the input.";
  const n = graph.groups.length;
  let edges = 0;
  for (let i = 0; i < n; i++) {
    for (let j = 0; j < n; j++) {
      if (graph.adjacency[i][j] !== result.adjacency[i][j]) {
        return `The reply changes the decision for ${graph.groups[i]} and ${graph.groups[j]}.`;
      }
      if (j > i && graph.adjacency[i][j]) edges++;
    }
  }
  if (result.stats.numEdges !== edges) return "The edge count of the reply does not match the input.";
  return null;
}

/**
 * Check a display before reduction against the input that the page sent for
 * it: one row for each group, letters that match the decisions, and counts
 * that match the letters. Returns the first problem, or null.
 */
export function checkBefore(value: unknown, pairs: readonly PairRow[], means: readonly MeanRow[] | null): string | null {
  if (value === null || typeof value !== "object") return "The reply holds no display before reduction.";
  const { rows, letters, assignments } = value as Record<string, unknown>;
  const graph = inputGraph(pairs, means);
  if (!graph) return "The page cannot read the decisions of the input.";
  const { groups } = graph;
  if (!Array.isArray(rows) || rows.length !== groups.length ||
      !rows.every((row: unknown, i) => {
        if (row === null || typeof row !== "object") return false;
        const r = row as Record<string, unknown>;
        return r.group === groups[i] && typeof r.letters === "string" && typeof r.assignments === "string";
      })) {
    return "The display before reduction does not have one row for each group of the input.";
  }
  const problem = checkLetters(groups, rows as LetterRow[], graph.adjacency);
  if (problem) return problem;
  const tokens = (rows as LetterRow[]).map((row) => tokensOf(row.assignments));
  if (letters !== new Set(tokens.flat()).size || assignments !== tokens.reduce((sum, t) => sum + t.length, 0)) {
    return "The counts of the display before reduction do not match its letters.";
  }
  // The groups of a letter are pairwise joined (checkLetters). The letters must also be the
  // maximal cliques of the input, each one once. The page finds them itself.
  let cliques: number[][];
  try {
    cliques = maximalCliques(graph.adjacency, DEFAULT_MAX_CLIQUES);
  } catch {
    return "The page cannot find the maximal cliques of the input.";
  }
  const maximal = new Set(cliques.map((q) => [...q].sort((a, b) => a - b).join(",")));
  const members = new Map<string, number[]>();
  tokens.forEach((own, i) => own.forEach((t) => {
    const list = members.get(t);
    if (list) list.push(i); else members.set(t, [i]);
  }));
  const seen = new Set<string>();
  for (const [t, list] of members) {
    const key = list.join(",");
    if (seen.has(key)) return `Letter ${t} before reduction has the same groups as another letter.`;
    seen.add(key);
    if (!maximal.has(key)) return `Letter ${t} before reduction is not a maximal clique of the input.`;
  }
  if (members.size !== maximal.size) return "The display before reduction misses a maximal clique of the input.";
  return null;
}

/**
 * Check a second stage against its first stage: it keeps the minimum of the
 * first stage, and the other quantity is not larger. Returns the problem, or null.
 */
export function checkStage(first: CldReduction, second: CldReduction, order: StagedOrder): string | null {
  const a = first.stats, b = second.stats;
  const kept = order === "letter_then_assignment"
    ? b.numLettersAfter === a.numLettersAfter && b.assignmentsAfter <= a.assignmentsAfter
    : b.assignmentsAfter === a.assignmentsAfter && b.numLettersAfter <= a.numLettersAfter;
  return kept ? null : "The second stage does not keep the minimum of the first stage.";
}

// One sentence in plain words for a message of the package, found by its
// stable prefix (docs/algorithm.md section 10).
const EXPLANATIONS: readonly [string, string][] = [
  ["post_hoc_results missing unordered pairwise comparisons: ",
   "Every pair of groups needs one row. A missing pair is an error. The page does not read it as a significant difference."],
  ["post_hoc_results contains duplicate unordered pairs: ", "Each pair of groups can have one row only."],
  ["post_hoc_results must not contain self-comparisons", "A row cannot compare a group with itself."],
  ["cannot coerce significance value to bool: ",
   "A decision must be true or false, yes or no, 1 or 0, or significant or ns."],
  ["post_hoc_results contains groups not present in means/groups: ",
   "When there are means, every group of the decisions needs a mean."],
  ["group labels must be unique after string conversion", "The means name a group more than once."],
  ["at least one group is required", "The input has no groups."],
  ["maximal clique enumeration exceeded max_cliques=",
   "The page uses the package limit of 10,000 maximal cliques. This input has more."],
];

export function explain(message: string): string | null {
  return EXPLANATIONS.find(([prefix]) => message.startsWith(prefix))?.[1] ?? null;
}

// Formats

export function count(n: number, one: string, many: string): string {
  return `${n.toLocaleString("en-US")} ${n === 1 ? one : many}`;
}

export function duration(milliseconds: number): string {
  if (milliseconds < 1) return "<1 ms";
  if (milliseconds < 1000) return `${Math.round(milliseconds)} ms`;
  const s = milliseconds / 1000;
  return s < 10 ? `${s.toFixed(2)} s` : `${s.toFixed(1)} s`;
}

/** A mean as text, without the noise of binary fractions. */
export function meanText(mean: number): string {
  return String(Number(mean.toPrecision(12)));
}

// Result files

function csvField(value: string): string {
  // A leading = + - @ makes a spreadsheet read the text as a formula.
  const safe = /^[=+\-@\t\r]/.test(value) ? `'${value}` : value;
  return /[",\n\r]/.test(safe) ? `"${safe.replace(/"/g, '""')}"` : safe;
}

/** The display before reduction, as the result files write it. */
export interface BeforeRows {
  rows: readonly { group: string; letters: string; assignments: string }[];
  letters: number;
  assignments: number;
  milliseconds: number;
}

/** The results as CSV: one row for each group before reduction, then one for each method and group. */
export function resultsCsv(results: readonly MethodResult[], means: readonly MeanRow[] | null,
                           before: BeforeRows | null = null): string {
  const mean = means === null ? null : new Map(means.map((m) => [m.group, m.mean]));
  const head = ["method", "group", ...(mean ? ["mean"] : []), "letters", "assignments"].join(",");
  const sets: [string, readonly { group: string; letters: string; assignments: string }[]][] = [
    ...(before ? [["before", before.rows] as [string, BeforeRows["rows"]]] : []),
    ...results.map(({ method, reduction }): [string, BeforeRows["rows"]] => [method, reduction.rows]),
  ];
  const lines = sets.flatMap(([method, rows]) => rows.map((row) => [
    method, csvField(row.group), ...(mean ? [String(mean.get(row.group) ?? "")] : []),
    csvField(row.letters), csvField(row.assignments),
  ].join(",")));
  return [head, ...lines].join("\n") + "\n";
}

/** A time to a tenth of a millisecond. Math.round(ms * 10) / 10 overflows for a very large time. */
const tenths = (ms: number): number => Number(ms.toFixed(1));

/** The results as JSON, with the exact labels and all statistics. */
export function resultsJson(results: readonly MethodResult[], input: { source: string; pairs: number;
                            means: readonly MeanRow[] | null }, version: string,
                            before: BeforeRows | null = null): string {
  const rowsOf = (rows: BeforeRows["rows"]) => rows.map((row) => ({
    group: row.group, letters: row.letters, assignments: tokensOf(row.assignments),
  }));
  return JSON.stringify({
    package: "cld-reducer",
    version,
    input: { source: input.source, pairs: input.pairs, means: input.means },
    before: before && { letters: before.letters, assignments: before.assignments,
                        milliseconds: tenths(before.milliseconds), rows: rowsOf(before.rows) },
    results: results.map(({ method, stage, reduction, milliseconds }) => ({
      method,
      stage,
      minimizes: methodInfo(method).minimizes.toLowerCase(),
      relationshipPreserved: reduction.relationshipPreserved,
      stats: reduction.stats,
      milliseconds: tenths(milliseconds),
      rows: reduction.rows.map((row) => ({
        group: row.group, letters: row.letters, assignments: tokensOf(row.assignments),
      })),
    })),
  }, null, 2) + "\n";
}

// Section 8 of Ennis, Fayle, and Ennis (2012)

/**
 * Table X: for each number of means N, the percentage of FIND-AM searches that
 * finished within 30 seconds (PC), their mean time in seconds (ET), and the mean
 * assignments of the maximal covering (MA) and of the exact solution (EA), over
 * the searches that finished. 1,000 simulations for each N.
 */
export const TABLE_X: readonly { n: number; pc: number; et: number; ma: number; ea: number }[] = [
  [10, 100.0, 0.000, 14.381, 13.980], [11, 100.0, 0.000, 16.361, 15.789], [12, 100.0, 0.000, 18.826, 17.930],
  [13, 100.0, 0.000, 21.295, 20.136], [14, 100.0, 0.000, 23.915, 22.330], [15, 100.0, 0.000, 26.717, 24.660],
  [16, 100.0, 0.003, 29.673, 27.056], [17, 100.0, 0.002, 32.527, 29.334], [18, 100.0, 0.020, 36.032, 32.078],
  [19, 99.7, 0.058, 39.886, 34.897], [20, 99.9, 0.058, 42.873, 37.181], [21, 99.4, 0.078, 46.522, 39.802],
  [22, 99.3, 0.169, 49.395, 42.021], [23, 99.0, 0.271, 53.924, 45.164], [24, 97.2, 0.404, 58.031, 48.051],
  [25, 95.6, 0.691, 62.252, 51.002], [26, 91.7, 0.712, 64.907, 53.103], [27, 87.3, 0.729, 68.841, 55.969],
  [28, 81.4, 1.235, 72.641, 58.534], [29, 76.4, 1.881, 76.271, 61.232], [30, 70.4, 7.626, 80.026, 63.966],
  [31, 59.6, 2.109, 83.151, 66.218], [32, 49.2, 2.547, 86.079, 68.675], [33, 41.9, 2.831, 88.341, 70.501],
  [34, 33.7, 3.487, 91.018, 72.605], [35, 26.5, 4.071, 95.883, 76.102], [36, 20.0, 4.817, 98.200, 78.170],
  [37, 15.9, 4.106, 101.182, 80.465], [38, 11.1, 6.157, 103.946, 82.108], [39, 11.1, 4.442, 106.396, 84.793],
  [40, 6.5, 4.787, 108.769, 87.077], [41, 4.7, 6.983, 113.596, 89.234], [42, 4.0, 4.461, 112.300, 91.000],
  [43, 2.8, 6.535, 118.071, 94.679], [44, 1.3, 11.457, 120.462, 96.231], [45, 0.8, 10.444, 124.000, 99.750],
].map(([n, pc, et, ma, ea]) => ({ n, pc, et, ma, ea }));

/** Table XI: graphs out of 1,000 for which no letter-minimum covering is assignment-minimum. Other N: 0. */
export const TABLE_XI: Readonly<Record<number, number>> = {
  21: 2, 22: 1, 24: 1, 25: 1, 26: 3, 27: 4, 28: 2, 29: 4, 31: 2, 33: 2, 34: 2, 38: 1,
};
