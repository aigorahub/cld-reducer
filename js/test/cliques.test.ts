import { describe, expect, it } from "vitest";
import { maximalCliques } from "../src/cliques.js";
import { SolverError } from "../src/errors.js";

function matrix(n: number, edges: [number, number][]): boolean[][] {
  const m = Array.from({ length: n }, (_, i) => Array.from({ length: n }, (_, j) => i === j));
  for (const [i, j] of edges) m[i][j] = m[j][i] = true;
  return m;
}

function bruteForce(m: boolean[][]): number[][] {
  const n = m.length;
  const cliques: number[][] = [];
  for (let mask = 1; mask < 1 << n; mask++) {
    const s = [...Array(n).keys()].filter((i) => mask >> i & 1);
    if (s.every((a) => s.every((b) => m[a][b]))) cliques.push(s);
  }
  const subset = (a: number[], b: number[]) => a.length < b.length && a.every((x) => b.includes(x));
  return cliques.filter((c) => !cliques.some((d) => subset(c, d)))
    .sort((a, b) => { for (let i = 0; i < Math.min(a.length, b.length); i++) if (a[i] !== b[i]) return a[i] - b[i]; return a.length - b.length; });
}

describe("maximalCliques", () => {
  it("orders the cliques of the renaming example canonically", () => {
    const m = matrix(5, [[0, 1], [0, 2], [0, 3], [0, 4], [1, 4], [2, 4]]);
    expect(maximalCliques(m, null)).toEqual([[0, 1, 4], [0, 2, 4], [0, 3]]);
  });

  it("treats an isolated group as a singleton clique", () => {
    expect(maximalCliques(matrix(3, [[0, 1]]), null)).toEqual([[0, 1], [2]]);
  });

  it("matches brute force on every graph with 4 or 5 groups", () => {
    for (const n of [4, 5]) {
      const pairs: [number, number][] = [];
      for (let i = 0; i < n; i++) for (let j = i + 1; j < n; j++) pairs.push([i, j]);
      for (let mask = 0; mask < 1 << pairs.length; mask++) {
        const m = matrix(n, pairs.filter((_, k) => mask >> k & 1));
        expect(maximalCliques(m, null)).toEqual(bruteForce(m));
      }
    }
  });

  it("counts against the cap", () => {
    const m = matrix(3, []);
    expect(maximalCliques(m, 3)).toHaveLength(3);
    expect(() => maximalCliques(m, 2)).toThrow(SolverError);
  });

  it("does not recurse", () => {
    const n = 300;
    const m = Array.from({ length: n }, () => new Array<boolean>(n).fill(true));
    expect(maximalCliques(m, null)).toEqual([[...Array(n).keys()]]);
  });
});
