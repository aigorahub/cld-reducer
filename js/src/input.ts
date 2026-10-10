// Input checks. They follow docs/algorithm.md sections 1, 2, and 6, in the same order,
// with the stable message prefixes of section 10.

import { InvalidInputError, SolverError } from "./errors.js";

/** Group means: a Map from group label to mean, or an array of `{ group, mean }`. */
export type Means = ReadonlyMap<string, number> | ReadonlyArray<{ group: string; mean: number }>;

export interface ReduceOptions {
  /** Group means. A plain object is rejected: integer-like keys would reorder the groups. */
  means?: Means | null;
  /** Reduction method. Only "assignment_minimum" (or "assignment-minimum") exists. */
  method?: string;
  /** One time budget in seconds for all solves of the call. */
  timeLimit?: number | null;
  /** Cap on maximal cliques (default 10000). `null` removes the cap. */
  maxCliques?: number | null;
  /** Column names of the pairwise rows (`reduceLetters` only). */
  group1?: string;
  group2?: string;
  significant?: string;
  /** Group labels for an adjacency matrix (`reduceFromAdjacency` only). */
  groups?: readonly unknown[] | null;
}

export interface Graph {
  groups: string[];
  /** Symmetric, diagonal true. */
  adjacency: boolean[][];
  means: number[] | null;
}

const TRUE_WORDS = new Set(["true", "t", "yes", "y", "1", "significant"]);
const FALSE_WORDS = new Set(["false", "f", "no", "n", "0", "not significant", "ns"]);
export const DEFAULT_MAX_CLIQUES = 10000;

const fail = (message: string): never => { throw new InvalidInputError(message); };
const list = (items: readonly string[]): string => JSON.stringify(items);

export function coerceSignificance(value: unknown): boolean {
  if (typeof value === "boolean") return value;
  if (typeof value === "number" && (value === 0 || value === 1)) return value === 1;
  if (typeof value === "string") {
    // Trim spaces, tabs, carriage returns, and line feeds only (section 1), as R and Python do.
    const text = value.replace(/^[ \t\r\n]+|[ \t\r\n]+$/g, "").toLowerCase();
    if (TRUE_WORDS.has(text)) return true;
    if (FALSE_WORDS.has(text)) return false;
  }
  return fail(`cannot coerce significance value to bool: ${JSON.stringify(value) ?? String(value)}`);
}

function labelOf(value: unknown): string {
  if (value === null || value === undefined || (typeof value === "number" && Number.isNaN(value))) {
    return fail("group labels must not be missing");
  }
  return typeof value === "string" ? value : String(value);
}

function checkGroups(groups: readonly unknown[]): string[] {
  const labels = groups.map(labelOf);
  if (new Set(labels).size !== labels.length) {
    fail("group labels must be unique after string conversion");
  }
  if (labels.length === 0) fail("at least one group is required");
  return labels;
}

/** The (group, mean) entries of a Map or an array; anything else is rejected. */
function meansEntries(means: unknown): { group: string; mean: unknown }[] | null {
  if (means === null || means === undefined) return null;
  if (means instanceof Map) {
    return [...means.entries()].map(([group, mean]) => ({ group: labelOf(group), mean }));
  }
  if (Array.isArray(means)) {
    return means.map((entry: unknown) => {
      if (entry === null || typeof entry !== "object" || !("group" in entry)) {
        return fail("means must be a Map or an array of { group, mean } objects");
      }
      const e = entry as { group: unknown; mean?: unknown };
      return { group: labelOf(e.group), mean: e.mean };
    });
  }
  return fail("means must be a Map or an array of { group, mean } objects, not a plain object " +
              "(integer-like keys would reorder the groups)");
}

function matchMeans(
  entries: { group: string; mean: unknown }[] | null, groups: string[],
): number[] | null {
  if (entries === null) return null;
  const table = new Map<string, unknown>();
  const repeated: string[] = [];
  for (const { group, mean } of entries) {
    if (table.has(group)) { if (!repeated.includes(group)) repeated.push(group); } else table.set(group, mean);
  }
  if (repeated.length > 0) fail(`means contain duplicate groups: ${list(repeated)}`);
  const missing = groups.filter((g) => !table.has(g));
  if (missing.length > 0) fail(`means are missing values for groups: ${list(missing)}`);
  return groups.map((g) => {
    const value = table.get(g);
    if (typeof value !== "number" || !Number.isFinite(value)) fail("means must be finite numbers");
    return value as number;
  });
}

/** Section 1: pairwise rows (and optional means) to a graph. */
export function pairsToGraph(pairs: unknown, options: ReduceOptions): Graph {
  const col1 = options.group1 ?? "group1";
  const col2 = options.group2 ?? "group2";
  const colSig = options.significant ?? "significant";
  if (!Array.isArray(pairs)) fail("pairs must be an array of row objects");
  const rows = pairs as unknown[];
  const present = new Set<string>();
  for (let i = 0; i < rows.length; i++) {
    const row = rows[i];
    if (row === null || typeof row !== "object") fail("every row of pairs must be an object");
    for (const key of Object.keys(row as object)) present.add(key);
  }
  // An empty array has no column names to check: it is a table with zero rows (section 1).
  const missingColumns = rows.length === 0 ? []
    : [...new Set([col1, col2, colSig])].filter((c) => !present.has(c)).sort();
  if (missingColumns.length > 0) {
    fail(`post_hoc_results missing required columns: ${list(missingColumns)}`);
  }
  const entries = rows.map((row) => {
    const r = row as Record<string, unknown>;
    return { a: labelOf(r[col1]), b: labelOf(r[col2]), significant: undefined as boolean | undefined };
  });
  rows.forEach((row, i) => { entries[i].significant = coerceSignificance((row as Record<string, unknown>)[colSig]); });
  if (entries.some((e) => e.a === e.b)) fail("post_hoc_results must not contain self-comparisons");
  // Pair keys use the positions of exact labels, not joined text, so no label can make two
  // pairs share a key.
  const index = new Map<string, number>();
  for (const e of entries) for (const g of [e.a, e.b]) if (!index.has(g)) index.set(g, index.size);
  const key = (a: string, b: string): string | null => {
    const i = index.get(a);
    const j = index.get(b);
    return i === undefined || j === undefined ? null : `${Math.min(i, j)},${Math.max(i, j)}`;
  };
  const shown = (a: string, b: string): string => (a <= b ? `${a}|${b}` : `${b}|${a}`);
  const seen = new Set<string>();
  const duplicates = new Set<string>();
  for (const e of entries) {
    const k = key(e.a, e.b)!;
    if (seen.has(k)) duplicates.add(shown(e.a, e.b)); else seen.add(k);
  }
  if (duplicates.size > 0) {
    fail(`post_hoc_results contains duplicate unordered pairs: ${list([...duplicates].sort())}`);
  }

  const means = meansEntries(options.means);
  let groups: string[];
  if (means !== null) {
    groups = checkGroups(means.map((m) => m.group));
  } else {
    const order: string[] = [];
    for (const e of entries) if (!order.includes(e.a)) order.push(e.a);
    for (const e of entries) if (!order.includes(e.b)) order.push(e.b);
    groups = checkGroups(order);
  }
  const meanValues = matchMeans(means, groups);
  const position = new Map(groups.map((g, i) => [g, i] as const));
  const unknown = [...new Set(entries.flatMap((e) => [e.a, e.b]).filter((g) => !position.has(g)))].sort();
  if (unknown.length > 0) {
    fail(`post_hoc_results contains groups not present in means/groups: ${list(unknown)}`);
  }
  const missingPairs: string[] = [];
  for (let i = 0; i < groups.length; i++) {
    for (let j = i + 1; j < groups.length; j++) {
      const k = key(groups[i], groups[j]);
      if (k === null || !seen.has(k)) missingPairs.push(`${groups[i]}|${groups[j]}`);
    }
  }
  if (missingPairs.length > 0) {
    fail(`post_hoc_results missing unordered pairwise comparisons: ${list(missingPairs.sort())}`);
  }
  const n = groups.length;
  const adjacency = Array.from({ length: n }, (_, i) => Array.from({ length: n }, (_, j) => i === j));
  for (const e of entries) {
    if (e.significant === false) {
      const i = position.get(e.a)!;
      const j = position.get(e.b)!;
      adjacency[i][j] = adjacency[j][i] = true;
    }
  }
  return { groups, adjacency, means: meanValues };
}

/** Section 2: an adjacency matrix (and optional groups and means) to a graph. */
export function adjacencyToGraph(adjacency: unknown, options: ReduceOptions): Graph {
  const raw = Array.isArray(adjacency) ? (adjacency as unknown[]) : [];
  // Index every cell: for...of and forEach skip the holes of sparse arrays, which read as missing.
  const cells: unknown[] = [];
  for (let i = 0; i < raw.length; i++) {
    const row = raw[i];
    if (Array.isArray(row)) for (let j = 0; j < row.length; j++) cells.push(row[j]);
  }
  if (cells.some((v) => v === null || v === undefined || (typeof v === "number" && Number.isNaN(v)))) {
    fail("adjacency must not contain missing values");
  }
  if (cells.some((v) => !(typeof v === "boolean" || v === 0 || v === 1))) {
    fail("adjacency must contain only booleans or explicit 0/1 values");
  }
  const size = raw.length;
  if (!Array.isArray(adjacency) || size === 0 ||
      raw.some((row) => !Array.isArray(row) || row.length !== size)) {
    fail("adjacency must be a square matrix");
  }
  const cell = raw.map((row) => (row as unknown[]).map((v) => v === true || v === 1));
  for (let i = 0; i < size; i++) {
    for (let j = 0; j < size; j++) if (cell[i][j] !== cell[j][i]) fail("adjacency must be symmetric");
  }
  if (!cell.every((row, i) => row[i])) fail("adjacency diagonal must be true");

  let groups: string[];
  if (options.groups === undefined || options.groups === null) {
    groups = Array.from({ length: size }, (_, i) => String(i + 1));
  } else {
    if (!Array.isArray(options.groups)) fail("groups must be an array of labels");
    groups = checkGroups(options.groups as unknown[]);
    if (groups.length !== size) fail("number of groups must match adjacency dimensions");
  }
  return { groups, adjacency: cell, means: matchMeans(meansEntries(options.means), groups) };
}

export function checkMethod(method: unknown): void {
  const value = method ?? "assignment_minimum";
  if (value !== "assignment_minimum" && value !== "assignment-minimum") {
    fail(`unsupported CLD reduction method: '${String(value)}'`);
  }
}

export function checkControls(options: ReduceOptions): { timeLimit: number | null; maxCliques: number | null } {
  const timeLimit = options.timeLimit ?? null;
  if (timeLimit !== null && (typeof timeLimit !== "number" || !Number.isFinite(timeLimit) || timeLimit <= 0)) {
    throw new SolverError("time_limit must be positive when provided");
  }
  const cap = options.maxCliques === undefined ? DEFAULT_MAX_CLIQUES : options.maxCliques;
  if (cap !== null && (typeof cap !== "number" || !Number.isInteger(cap) || cap < 1)) {
    throw new SolverError("max_cliques must be a positive integer or null");
  }
  return { timeLimit, maxCliques: cap };
}
