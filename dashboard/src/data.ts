// Methods, examples, the check of a solver reply, and the result files.

import type { CldReduction } from "../../js/src/index.js";
import type { MeanRow } from "./csv.js";

export type Method = "letter_minimum" | "assignment_minimum";

export interface MethodInfo {
  id: Method;
  name: string;
  /** The one quantity that the method minimizes. */
  minimizes: string;
}

// CLD-C first: it is the default of the package.
export const METHODS: readonly MethodInfo[] = [
  { id: "letter_minimum", name: "CLD-C", minimizes: "Distinct letters" },
  { id: "assignment_minimum", name: "CLD-sigma", minimizes: "Assignments" },
];

export function methodInfo(id: Method): MethodInfo {
  return METHODS.find((m) => m.id === id)!;
}

export interface Example {
  id: string;
  title: string;
  /** Files in conformance/data. build.mjs puts their text into the page. */
  pairsFile: string;
  meansFile: string | null;
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
];

export interface MethodResult {
  method: Method;
  reduction: CldReduction;
  /** Time of the package call in the worker. */
  milliseconds: number;
}

/** The letter tokens of one row of a result. */
export function tokensOf(assignments: string): string[] {
  return assignments === "" ? [] : assignments.split(" ");
}

/** The letters that groups i and j share, in the order of group i. */
export function sharedTokens(tokens: readonly string[][], i: number, j: number): string[] {
  return tokens[i].filter((t) => tokens[j].includes(t));
}

const isCount = (v: unknown): v is number => typeof v === "number" && Number.isInteger(v) && v >= 0;

/**
 * Check a reply before the page shows it. The package makes the same
 * relationship check; this one protects the page from a reply that changed
 * on the way. Returns the first problem, or null.
 */
export function checkReduction(value: unknown, method: Method): string | null {
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

  const tokens = rows.map((row) => tokensOf(row.assignments));
  for (let i = 0; i < n; i++) {
    for (let j = 0; j < n; j++) {
      const share = i === j || sharedTokens(tokens, i, j).length > 0;
      if (share !== adjacency[i][j]) {
        return `The letters of ${groups[i]} and ${groups[j]} do not match the input decision.`;
      }
    }
  }
  const assignments = tokens.reduce((sum, t) => sum + t.length, 0);
  const letters = new Set(tokens.flat()).size;
  if (stats.numGroups !== n || stats.assignmentsAfter !== assignments || stats.numLettersAfter !== letters) {
    return "The statistics of the reply do not match its letters.";
  }
  if (stats.objective !== (method === "letter_minimum" ? letters : assignments)) {
    return "The objective value of the reply does not match its letters.";
  }
  return null;
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

/** The results as CSV: one row for each method and group. */
export function resultsCsv(results: readonly MethodResult[], means: readonly MeanRow[] | null): string {
  const mean = means === null ? null : new Map(means.map((m) => [m.group, m.mean]));
  const head = ["method", "group", ...(mean ? ["mean"] : []), "letters", "assignments"].join(",");
  const lines = results.flatMap(({ method, reduction }) => reduction.rows.map((row) => [
    method, csvField(row.group), ...(mean ? [String(mean.get(row.group) ?? "")] : []),
    csvField(row.letters), csvField(row.assignments),
  ].join(",")));
  return [head, ...lines].join("\n") + "\n";
}

/** The results as JSON, with the exact labels and all statistics. */
export function resultsJson(results: readonly MethodResult[], input: { source: string; pairs: number;
                            means: readonly MeanRow[] | null }, version: string): string {
  return JSON.stringify({
    package: "cld-reducer",
    version,
    input: { source: input.source, pairs: input.pairs, means: input.means },
    results: results.map(({ method, reduction, milliseconds }) => ({
      method,
      minimizes: methodInfo(method).minimizes.toLowerCase(),
      relationshipPreserved: reduction.relationshipPreserved,
      stats: reduction.stats,
      milliseconds: Math.round(milliseconds * 10) / 10,
      rows: reduction.rows.map((row) => ({
        group: row.group, letters: row.letters, assignments: tokensOf(row.assignments),
      })),
    })),
  }, null, 2) + "\n";
}
