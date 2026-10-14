// Summaries and the result file of the simulation study.

import { maximalCliques } from "../../js/src/cliques.js";
import { DEFAULT_MAX_CLIQUES } from "../../js/src/input.js";
import { isTime, type ResultMethod } from "./data.js";
import { seedAfter, simulate } from "./simulate.js";
import type { Instance, Solve, Study } from "./worker.js";

export const ALL_METHODS: readonly ResultMethod[] = ["letter_minimum", "assignment_minimum",
                                                    "letter_then_assignment", "assignment_then_letter"];

/** The largest value; Math.max(...values) fails for a very long list. */
export const largest = (values: readonly number[]): number => values.reduce((a, b) => Math.max(a, b), -Infinity);

/** The time of the slowest solve of a study, or null when no solve ran. */
export function slowest(instances: readonly Instance[]): number | null {
  const times = instances.flatMap((i) => ALL_METHODS.flatMap((m) => {
    const t = i.solves[m].milliseconds;
    return t === null ? [] : [t];
  }));
  return times.length ? largest(times) : null;
}

/** The treatment count and seed of the instance at a position of a study, or null after its last instance. */
export function planned(study: Study, index: number): { n: number; seed: number } | null {
  const size = Math.floor(index / study.count);
  return size < study.sizes.length ? { n: study.sizes[size], seed: seedAfter(study.firstSeed, index % study.count) } : null;
}

/** What the page knows of an instance without a solve. It finds them from the seeded generator. */
export interface InstanceFacts {
  edges: number;
  lettersBefore: number;
  assignmentsBefore: number;
  /** The size of the largest maximal clique. */
  largest: number;
}

/** The facts of the instance with n treatments and a seed, or null when it has too many maximal cliques. */
export function instanceFacts(n: number, seed: number): InstanceFacts | null {
  const { significant } = simulate(n, seed);
  // The upper triangle, as the worker reads the decisions.
  const adjacency = significant.map((_, i) => significant.map((__, j) => i === j || !significant[Math.min(i, j)][Math.max(i, j)]));
  let edges = 0;
  for (let i = 0; i < n; i++) for (let j = i + 1; j < n; j++) edges += Number(!significant[i][j]);
  let cliques: number[][];
  try {
    cliques = maximalCliques(adjacency, DEFAULT_MAX_CLIQUES);
  } catch {
    return null;
  }
  return { edges, lettersBefore: cliques.length, assignmentsBefore: cliques.reduce((t, q) => t + q.length, 0),
           largest: largest(cliques.map((q) => q.length)) };
}

const whole = (v: unknown, min: number): v is number => typeof v === "number" && Number.isInteger(v) && v >= min;

/** Letter and assignment counts of a display of n groups: each group and each letter has at least one assignment. */
const counts = (letters: unknown, assignments: unknown, n: number): boolean =>
  whole(letters, 1) && whole(assignments, n) && letters <= assignments && assignments <= n * letters;

/**
 * Check one instance reply of a study before the page keeps it: the planned
 * treatment count and seed; the edge count and counts before reduction of its
 * graph; letter and assignment counts that a display of that graph can have;
 * times, with a finished solve under the time limit; a second stage exactly
 * when its first stage finished; and the order of
 * the minimums of the four solves. It does not prove that a count is minimal.
 * Returns the first problem, or null.
 */
export function checkInstance(value: unknown, n: number, seed: number, facts: InstanceFacts | null,
                              timeLimit: number): string | null {
  if (value === null || typeof value !== "object") return "The reply holds no instance.";
  const i = value as Record<string, unknown>;
  if (i.n !== n || i.seed !== seed) return `The reply is not for the instance with ${n} treatments and seed ${seed}.`;
  if (!facts) return "The page cannot find the maximal cliques of the instance.";
  if (i.edges !== facts.edges) return "The edge count of the instance does not match its graph.";
  if (i.lettersBefore !== facts.lettersBefore || i.assignmentsBefore !== facts.assignmentsBefore) {
    return "The counts before reduction of the instance do not match its graph.";
  }
  // A letter has at most `largest` groups and covers at most largest(largest - 1)/2 edges.
  const fits = (letters: number, assignments: number): boolean =>
    assignments <= letters * facts.largest && letters * (facts.largest * (facts.largest - 1)) / 2 >= facts.edges;
  const solves = i.solves as Record<string, unknown> | null | undefined;
  if (solves === null || typeof solves !== "object") return "The instance has no solves.";
  for (const m of ALL_METHODS) {
    const s = solves[m] as Record<string, unknown> | null | undefined;
    if (s === null || typeof s !== "object") return `The instance has no ${m} solve.`;
    const ran = s.milliseconds !== null;
    if (ran && !isTime(s.milliseconds)) return `The time of the ${m} solve is not a time.`;
    const finished = s.letters !== null || s.assignments !== null;
    if (finished && !counts(s.letters, s.assignments, n)) return `The counts of the ${m} solve are not possible.`;
    if (finished && !fits(s.letters as number, s.assignments as number)) return `The counts of the ${m} solve do not fit its graph.`;
    if (finished && !ran) return `The ${m} solve has a result but did not run.`;
    if (finished && (s.milliseconds as number) >= timeLimit * 1000) return `The ${m} solve did not finish under the time limit.`;
  }
  const { letter_minimum: c, assignment_minimum: sigma, letter_then_assignment: cs, assignment_then_letter: sc } =
    solves as Record<ResultMethod, Solve>;
  if (c.milliseconds === null || sigma.milliseconds === null) return "A first stage of the instance did not run.";
  if ((cs.milliseconds !== null) !== (c.letters !== null) || (sc.milliseconds !== null) !== (sigma.letters !== null)) {
    return "A second stage of the instance runs when its first stage did not finish, or the reverse.";
  }
  // Each finished solve is exact, so its counts keep this order. A null count did not finish.
  const le = (a: number | null, b: number | null): boolean => a === null || b === null || a <= b;
  const eq = (a: number | null, b: number | null): boolean => a === null || b === null || a === b;
  const ordered =
    le(c.letters, i.lettersBefore as number) && le(sigma.assignments, i.assignmentsBefore as number) &&
    le(c.letters, sigma.letters) && le(sigma.assignments, c.assignments) &&
    eq(cs.letters, c.letters) && le(cs.assignments, c.assignments) && le(sigma.assignments, cs.assignments) &&
    eq(sc.assignments, sigma.assignments) && le(sc.letters, sigma.letters) && le(c.letters, sc.letters);
  // A display with both minimums exists exactly when each second stage reaches the minimum of the other method.
  const both = [cs.assignments, sigma.assignments, sc.letters, c.letters].every((v) => v !== null);
  const agree = !both || (cs.assignments === sigma.assignments) === (sc.letters === c.letters);
  return ordered && agree ? null : "The solves of the instance do not keep the order of the minimums.";
}

/** The figures of one number of treatments. */
export interface Summary {
  n: number;
  instances: number;
  /** Instances in which all four solves finished within the time limit. */
  finished: number;
  lettersBefore: number;
  assignmentsBefore: number;
  /** The mean letters (CLD-C, CLD-sigma then CLD-C) or assignments (the other two) of the finished solves. */
  value: Record<ResultMethod, number | null>;
  /** The share of the assignments that CLD-sigma removes, over the instances in which it finished. */
  assignmentsRemoved: number | null;
  /** Times of the solves that ran; null when none ran. */
  mean: Record<ResultMethod, number | null>;
  max: Record<ResultMethod, number | null>;
  /** Instances in which the second stage after CLD-C still has more assignments than CLD-sigma. */
  tradeOff: number;
  /** Instances in which both of those solves finished, so that the comparison is known. */
  tradeOffKnown: number;
  /**
   * Over the instances in which CLD-sigma finished, as Table X averages over the searches that
   * finished: their count, their mean assignments before reduction, and the mean time of CLD-sigma.
   */
  sigmaFinished: number;
  sigmaBefore: number | null;
  sigmaTime: number | null;
}

const average = (values: number[]): number | null =>
  (values.length ? values.reduce((a, b) => a + b, 0) / values.length : null);

export function summarize(instances: readonly Instance[]): Summary[] {
  const sizes = [...new Set(instances.map((i) => i.n))];
  return sizes.map((n) => {
    const group = instances.filter((i) => i.n === n);
    const pick = (m: ResultMethod, key: "letters" | "assignments"): number | null =>
      average(group.flatMap((i) => { const v = i.solves[m][key]; return v === null ? [] : [v]; }));
    const times = (m: ResultMethod): number[] => group.flatMap((i) => {
      const t = i.solves[m].milliseconds;
      return t === null ? [] : [t];
    });
    const byMethod = (f: (m: ResultMethod) => number | null): Record<ResultMethod, number | null> =>
      Object.fromEntries(ALL_METHODS.map((m) => [m, f(m)])) as Record<ResultMethod, number | null>;
    const solved = group.filter((i) => i.solves.assignment_minimum.assignments !== null);
    const before = solved.reduce((t, i) => t + i.assignmentsBefore, 0);
    const after = solved.reduce((t, i) => t + i.solves.assignment_minimum.assignments!, 0);
    return {
      n,
      instances: group.length,
      finished: group.filter((i) => ALL_METHODS.every((m) => i.solves[m].letters !== null)).length,
      lettersBefore: average(group.map((i) => i.lettersBefore))!,
      assignmentsBefore: average(group.map((i) => i.assignmentsBefore))!,
      value: {
        letter_minimum: pick("letter_minimum", "letters"),
        assignment_minimum: pick("assignment_minimum", "assignments"),
        letter_then_assignment: pick("letter_then_assignment", "assignments"),
        assignment_then_letter: pick("assignment_then_letter", "letters"),
      },
      assignmentsRemoved: before > 0 ? 1 - after / before : null,
      mean: byMethod((m) => average(times(m))),
      max: byMethod((m) => (times(m).length ? largest(times(m)) : null)),
      tradeOff: group.filter((i) => {
        const cs = i.solves.letter_then_assignment.assignments;
        const sigma = i.solves.assignment_minimum.assignments;
        return cs !== null && sigma !== null && cs > sigma;
      }).length,
      tradeOffKnown: group.filter((i) => i.solves.letter_then_assignment.assignments !== null &&
                                         i.solves.assignment_minimum.assignments !== null).length,
      sigmaFinished: solved.length,
      sigmaBefore: average(solved.map((i) => i.assignmentsBefore)),
      sigmaTime: average(solved.map((i) => i.solves.assignment_minimum.milliseconds!)),
    };
  });
}

/** One row for each instance, with the letters, assignments, and time of each solve. */
export function studyCsv(instances: readonly Instance[]): string {
  const head = ["n", "seed", "edges", "letters_before", "assignments_before",
                ...ALL_METHODS.flatMap((m) => [`${m}_letters`, `${m}_assignments`, `${m}_ms`])];
  const lines = instances.map((i) => [i.n, i.seed, i.edges, i.lettersBefore, i.assignmentsBefore,
    ...ALL_METHODS.flatMap((m) => [i.solves[m].letters ?? "", i.solves[m].assignments ?? "",
                                   i.solves[m].milliseconds?.toFixed(1) ?? ""])].join(","));
  return [head.join(","), ...lines].join("\n") + "\n";
}
