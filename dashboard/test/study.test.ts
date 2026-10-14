import { describe, expect, it } from "vitest";
import { studyCsv, summarize } from "../src/study.js";
import type { Instance } from "../src/worker.js";

const solve = (letters: number | null, assignments: number | null, milliseconds: number) => ({ letters, assignments, milliseconds });
const instance = (n: number, seed: number, cs: number | null, sigma: number | null): Instance => ({
  n, seed, lettersBefore: 5, assignmentsBefore: 20, edges: 10,
  solves: {
    letter_minimum: solve(4, 18, 2), assignment_minimum: solve(sigma === null ? null : 5, sigma, 10),
    letter_then_assignment: solve(cs === null ? null : 4, cs, 6), assignment_then_letter: solve(5, 15, 4),
  },
});

describe("summarize", () => {
  it("averages finished solves, counts the trade-offs, and keeps the slowest time", () => {
    const [row] = summarize([instance(10, 1, 16, 15), instance(10, 2, 15, 15), instance(10, 3, 17, null)]);
    expect(row).toMatchObject({ n: 10, instances: 3, finished: 2, lettersBefore: 5, assignmentsBefore: 20, tradeOff: 1 });
    expect(row.value.assignment_minimum).toBe(15);
    expect(row.value.letter_then_assignment).toBe(16);
    expect(row.max.assignment_minimum).toBe(10);
    expect(row.mean.letter_minimum).toBe(2);
  });

  it("keeps one row for each number of treatments, in the order of the study", () => {
    expect(summarize([instance(20, 1, 1, 1), instance(10, 1, 1, 1), instance(20, 2, 1, 1)]).map((r) => [r.n, r.instances]))
      .toEqual([[20, 2], [10, 1]]);
  });
});

describe("studyCsv", () => {
  it("writes one row for each instance and leaves an unfinished solve empty", () => {
    const lines = studyCsv([instance(10, 3, 17, null)]).trimEnd().split("\n");
    expect(lines[0]).toBe("n,seed,edges,letters_before,assignments_before,letter_minimum_letters,letter_minimum_assignments," +
      "letter_minimum_ms,assignment_minimum_letters,assignment_minimum_assignments,assignment_minimum_ms," +
      "letter_then_assignment_letters,letter_then_assignment_assignments,letter_then_assignment_ms," +
      "assignment_then_letter_letters,assignment_then_letter_assignments,assignment_then_letter_ms");
    expect(lines[1]).toBe("10,3,10,5,20,4,18,2.0,,,10.0,4,17,6.0,5,15,4.0");
  });
});
