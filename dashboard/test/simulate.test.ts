import { describe, expect, it } from "vitest";
import { maximalCliques } from "../../js/src/cliques.js";
import { parsePairs } from "../src/csv.js";
import { MODEL, TABLE_II, experimentCsv, gamma, normal, repairEigenvalues, simulate, symmetricEigen, uniform } from "../src/simulate.js";

const mean = (a: number[]): number => a.reduce((x, y) => x + y, 0) / a.length;
const variance = (a: number[]): number => a.reduce((x, y) => x + (y - mean(a)) ** 2, 0) / (a.length - 1);

describe("random numbers", () => {
  it("repeat for a seed and stay in [0, 1)", () => {
    const a = uniform(7), b = uniform(7), c = uniform(8);
    const first = Array.from({ length: 1000 }, a);
    expect(Array.from({ length: 1000 }, b)).toEqual(first);
    expect(Array.from({ length: 5 }, c)).not.toEqual(first.slice(0, 5));
    expect(first.every((u) => u >= 0 && u < 1)).toBe(true);
  });

  it("have the moments of the normal and gamma distributions of Section 3.2", () => {
    const rand = uniform(11);
    const z = normal(rand);
    const normals = Array.from({ length: 40000 }, z);
    expect(mean(normals)).toBeCloseTo(0, 1);
    expect(variance(normals)).toBeCloseTo(1, 1);
    const gammas = Array.from({ length: 40000 }, () => gamma(rand, z, MODEL.gammaShape, MODEL.gammaScale));
    // Mean shape * scale = 1.767; variance shape * scale^2 = 0.758.
    expect(Math.abs(mean(gammas) - 1.767)).toBeLessThan(0.02);
    expect(Math.abs(variance(gammas) - 0.758)).toBeLessThan(0.03);
    expect(gammas.every((g) => g > 0)).toBe(true);
  });
});

describe("symmetricEigen", () => {
  it("gives back the matrix from its eigenvalues and eigenvectors", () => {
    const a = [[4, 1, 0.5], [1, 3, -0.2], [0.5, -0.2, -1]];
    const { values, vectors } = symmetricEigen(a);
    for (let i = 0; i < 3; i++) {
      for (let j = 0; j < 3; j++) {
        const back = values.reduce((s, d, k) => s + vectors[i][k] * d * vectors[j][k], 0);
        expect(back).toBeCloseTo(a[i][j], 10);
      }
    }
    expect(values.reduce((s, d) => s + d, 0)).toBeCloseTo(6, 10);
  });
});

describe("repairEigenvalues", () => {
  it("sets an eigenvalue that is not positive to the smallest positive one and keeps the diagonal", () => {
    // Eigenvalues -0.8, 1.9, and 1.9: the repair gives 1.9 three times, so R becomes 1.9 times I.
    const r = repairEigenvalues([[1, 0.9, -0.9], [0.9, 1, 0.9], [-0.9, 0.9, 1]]);
    for (let i = 0; i < 3; i++) {
      for (let j = 0; j < 3; j++) expect(r[i][j]).toBeCloseTo(i === j ? 1.9 : 0, 10);
    }
    // A matrix with positive eigenvalues stays as it is.
    const ok = [[1, 0.2], [0.2, 1]];
    expect(repairEigenvalues(ok).flat().map((v) => Number(v.toFixed(12)))).toEqual(ok.flat());
  });
});

describe("simulate", () => {
  it("repeats for the same n and seed, and differs for another seed", () => {
    expect(simulate(20, 3)).toEqual(simulate(20, 3));
    expect(simulate(20, 4).significant).not.toEqual(simulate(20, 3).significant);
  });

  it("orders T1 to Tn from the highest mean down, with a symmetric decision matrix", () => {
    const e = simulate(25, 9);
    expect(e.groups).toEqual(Array.from({ length: 25 }, (_, k) => `T${k + 1}`));
    expect(e.means.every((m, k) => k === 0 || e.means[k - 1] >= m)).toBe(true);
    for (let i = 0; i < 25; i++) {
      expect(e.significant[i][i]).toBe(false);
      for (let j = 0; j < 25; j++) expect(e.significant[i][j]).toBe(e.significant[j][i]);
    }
  });

  it("declares a pair significant less often when the two means are close", () => {
    // About half of all pairs differ significantly under these parameters.
    let close = 0, closeSignificant = 0, far = 0, farSignificant = 0;
    for (let seed = 1; seed <= 60; seed++) {
      const e = simulate(20, seed);
      for (let i = 0; i < 20; i++) {
        for (let j = i + 1; j < 20; j++) {
          const d = Math.abs(e.means[i] - e.means[j]);
          if (d < 1) { close++; closeSignificant += Number(e.significant[i][j]); }
          if (d > 8) { far++; farSignificant += Number(e.significant[i][j]); }
        }
      }
    }
    expect(closeSignificant / close).toBeLessThan(0.05);
    expect(farSignificant / far).toBeGreaterThan(0.95);
  });

  it("writes the decisions and means files of the page", () => {
    const e = simulate(4, 2);
    const files = experimentCsv(e);
    const rows = parsePairs(files.pairs);
    expect(rows).toHaveLength(6);
    expect(rows[0]).toEqual({ group1: "T1", group2: "T2", significant: String(e.significant[0][1]) });
    expect(files.means.split("\n")[1]).toBe(`T1,${e.means[0].toFixed(3)}`);
  });

  it("rejects fewer than two treatments", () => {
    expect(() => simulate(1, 1)).toThrow(RangeError);
  });
});

describe("Table II graph", () => {
  it("has the 7 maximal cliques of the membership matrix of the 2012 paper", () => {
    const rows = parsePairs(TABLE_II);
    const n = 8;
    const adjacency = Array.from({ length: n }, (_, i) => Array.from({ length: n }, (_, j) => i === j));
    for (const r of rows) {
      if (r.significant === "false") {
        const i = Number(r.group1) - 1, j = Number(r.group2) - 1;
        adjacency[i][j] = adjacency[j][i] = true;
      }
    }
    // Columns a to g of Table II, with vertices 1 to 8 as 0 to 7.
    const columns = [[0, 1, 2, 4], [0, 1, 2, 6], [0, 3, 6], [1, 2, 4, 5, 7], [3, 5, 7], [1, 2, 6, 7], [3, 6, 7]];
    const sort = (list: number[][]): string[] => list.map((q) => q.join(",")).sort();
    expect(sort(maximalCliques(adjacency, null))).toEqual(sort(columns));
  });
});
