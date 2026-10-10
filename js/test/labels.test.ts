import { expect, it } from "vitest";
import { makeLetterLabels } from "../src/labels.js";

it("labels A to Z, then AA, AB, and so on", () => {
  const labels = makeLetterLabels(704);
  expect(labels.slice(0, 3)).toEqual(["A", "B", "C"]);
  expect(labels.slice(25, 29)).toEqual(["Z", "AA", "AB", "AC"]);
  expect(labels.slice(51, 53)).toEqual(["AZ", "BA"]);
  expect(labels.slice(701, 704)).toEqual(["ZZ", "AAA", "AAB"]);
  expect(new Set(labels).size).toBe(704);
  expect(makeLetterLabels(0)).toEqual([]);
  expect(() => makeLetterLabels(-1)).toThrow(RangeError);
});
