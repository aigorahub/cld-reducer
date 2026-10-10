import { existsSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

export const CONFORMANCE = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "conformance");
export const hasConformance = existsSync(join(CONFORMANCE, "data"));

/** The simple ABC example as an adjacency matrix (groups "1" to "5"). */
export const SIMPLE: boolean[][] = [
  [true, true, true, false, false],
  [true, true, true, true, false],
  [true, true, true, true, true],
  [false, true, true, true, true],
  [false, false, true, true, true],
];

export const SIMPLE_MEANS = [
  { group: "1", mean: 3.73 }, { group: "2", mean: 3.57 }, { group: "3", mean: 3.46 },
  { group: "4", mean: 3.33 }, { group: "5", mean: 3.3 },
];

export const SIMPLE_LETTERS = { "1": "A", "2": "AB", "3": "AC", "4": "BC", "5": "C" };

/** Rows of a conformance CSV (any line ending). */
export function readCsv(name: string): Record<string, string>[] {
  const lines = readFileSync(join(CONFORMANCE, "data", name), "utf8").split(/\r?\n/).filter(Boolean);
  const head = lines[0].split(",");
  return lines.slice(1).map((line) => {
    const cells = line.split(",");
    return Object.fromEntries(head.map((h, i) => [h, cells[i]]));
  });
}

export function wheatPairs(): Record<string, unknown>[] {
  return readCsv("piepho2004_wheat_pairs.csv");
}
