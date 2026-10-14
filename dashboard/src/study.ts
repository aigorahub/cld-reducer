// Summaries and the result file of the simulation study.

import type { ResultMethod } from "./data.js";
import type { Instance } from "./worker.js";

export const ALL_METHODS: readonly ResultMethod[] = ["letter_minimum", "assignment_minimum",
                                                    "letter_then_assignment", "assignment_then_letter"];

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
      max: byMethod((m) => (times(m).length ? Math.max(...times(m)) : null)),
      tradeOff: group.filter((i) => {
        const cs = i.solves.letter_then_assignment.assignments;
        const sigma = i.solves.assignment_minimum.assignments;
        return cs !== null && sigma !== null && cs > sigma;
      }).length,
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
