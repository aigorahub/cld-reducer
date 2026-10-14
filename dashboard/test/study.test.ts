import { describe, expect, it } from "vitest";
import { checkInstance, largest, planned, slowest, studyCsv, summarize } from "../src/study.js";
import type { Instance } from "../src/worker.js";

const solve = (letters: number | null, assignments: number | null, milliseconds: number | null) =>
  ({ letters, assignments, milliseconds });
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

describe("summarize with solves that did not finish or did not run", () => {
  it("leaves a second stage that did not run out of the times, and gives no time when none ran", () => {
    const ran = instance(10, 1, 16, 15);
    ran.solves.assignment_then_letter.milliseconds = 1000;
    const skipped = instance(10, 2, 16, null);
    skipped.solves.assignment_then_letter = solve(null, null, null);
    const [row] = summarize([ran, skipped]);
    expect(row.mean.assignment_then_letter).toBe(1000);
    expect(row.max.assignment_then_letter).toBe(1000);
    const [none] = summarize([skipped]);
    expect([none.mean.assignment_then_letter, none.max.assignment_then_letter]).toEqual([null, null]);
  });

  it("computes the share removed over the instances in which CLD-sigma finished", () => {
    const finished = instance(10, 1, 20, 20);
    const unfinished = instance(10, 2, 20, null);
    unfinished.assignmentsBefore = 100;
    const [row] = summarize([finished, unfinished]);
    expect(row.assignmentsRemoved).toBe(0);
    expect(summarize([unfinished])[0].assignmentsRemoved).toBeNull();
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

describe("checkInstance", () => {
  // 10 treatments: CLD-C 4 letters and 18 assignments, CLD-sigma 5 letters and 15 assignments.
  const valid = (): Instance => ({
    n: 10, seed: 3, lettersBefore: 5, assignmentsBefore: 20, edges: 10,
    solves: {
      letter_minimum: solve(4, 18, 2), assignment_minimum: solve(5, 15, 10),
      letter_then_assignment: solve(4, 16, 6), assignment_then_letter: solve(5, 15, 4),
    },
  });
  const altered = (f: (i: Instance) => void): Instance => { const i = valid(); f(i); return i; };

  it("accepts a possible instance, also with a first stage that did not finish", () => {
    expect(checkInstance(valid(), 10, 3)).toBeNull();
    expect(checkInstance(altered((i) => {
      i.solves.letter_minimum = solve(null, null, 30000);
      i.solves.letter_then_assignment = solve(null, null, null);
    }), 10, 3)).toBeNull();
  });

  it("rejects another instance, impossible counts or times, and a reply that is no instance", () => {
    expect(checkInstance(valid(), 10, 4)).toBe("The reply is not for the instance with 10 treatments and seed 4.");
    expect(checkInstance(altered((i) => { i.edges = 46; }), 10, 3)).toBe("The edge count of the instance is not possible.");
    expect(checkInstance(altered((i) => { i.assignmentsBefore = 9; }), 10, 3))
      .toBe("The counts before reduction of the instance are not possible.");
    expect(checkInstance(altered((i) => { i.solves.assignment_minimum.milliseconds = -1; }), 10, 3))
      .toBe("The time of the assignment_minimum solve is not a time.");
    expect(checkInstance(altered((i) => { i.solves.letter_minimum.letters = null; }), 10, 3))
      .toBe("The counts of the letter_minimum solve are not possible.");
    expect(checkInstance(altered((i) => { i.solves.assignment_then_letter.milliseconds = null; }), 10, 3))
      .toBe("The assignment_then_letter solve has a result but did not run.");
    expect(checkInstance("instance", 10, 3)).toBe("The reply holds no instance.");
  });

  it("rejects a second stage that runs without its first stage, or does not run after it", () => {
    const message = "A second stage of the instance runs when its first stage did not finish, or the reverse.";
    expect(checkInstance(altered((i) => { i.solves.letter_minimum = solve(null, null, 30000); }), 10, 3)).toBe(message);
    expect(checkInstance(altered((i) => { i.solves.assignment_then_letter = solve(null, null, null); }), 10, 3)).toBe(message);
  });

  it("rejects counts that break the order of the minimums", () => {
    const message = "The solves of the instance do not keep the order of the minimums.";
    for (const f of [
      (i: Instance) => { i.solves.letter_then_assignment = solve(999, 999, 1); },
      (i: Instance) => { i.solves.letter_then_assignment.letters = 5; },
      (i: Instance) => { i.solves.letter_then_assignment.assignments = 14; },
      (i: Instance) => { i.solves.assignment_then_letter.assignments = 16; },
      (i: Instance) => { i.solves.assignment_then_letter.letters = 3; },
      (i: Instance) => { i.solves.letter_minimum.letters = 6; },
      (i: Instance) => { i.solves.assignment_minimum.assignments = 21; },
    ]) expect(checkInstance(altered(f), 10, 3)).toBe(message);
  });
});

describe("planned and largest", () => {
  it("give the treatment count and seed of each position, and null after the last", () => {
    const study = { sizes: [10, 15], count: 2, firstSeed: 5, timeLimit: 30 };
    expect([0, 1, 2, 3, 4].map((k) => planned(study, k)))
      .toEqual([{ n: 10, seed: 5 }, { n: 10, seed: 6 }, { n: 15, seed: 5 }, { n: 15, seed: 6 }, null]);
  });

  it("give the slowest solve of the largest study that the page allows", () => {
    // Treatments 2 to 80 with 1,000 instances each: 79,000 instances and 316,000 times.
    const many = Array.from({ length: 79000 }, (_, k) => instance(10, k, 16, 15));
    many[500].solves.assignment_minimum.milliseconds = 12345;
    expect(slowest(many)).toBe(12345);
    expect(slowest([])).toBeNull();
  });

  it("find the largest value of a list too long for Math.max(...values)", () => {
    const values = Array.from({ length: 500000 }, (_, k) => k % 1000);
    expect(() => Math.max(...values)).toThrow(RangeError);
    expect(largest(values)).toBe(999);
  });
});
