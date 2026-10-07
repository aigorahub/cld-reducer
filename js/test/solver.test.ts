// Solver settings, disposal, and the failure paths of docs/algorithm.md section 6.
import highsImport from "highs";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SolverError, loadSolver, reduceFromAdjacency, reduceLetters } from "../src/index.js";
import { clock } from "../src/reduce.js";
import * as solver from "../src/solver.js";
import { SIMPLE, hasConformance, wheatPairs } from "./helpers.js";

const realRun = solver.hooks.run;
const realNow = clock.now;
afterEach(() => {
  solver.hooks.run = realRun;
  clock.now = realNow;
  solver.settings.presolve = "on";
});

describe("settings", () => {
  it.each(["on", "off"] as const)("every solve uses the documented settings (presolve %s)", async (presolve) => {
    solver.settings.presolve = presolve;
    const seen: Record<string, unknown>[] = [];
    solver.hooks.run = (...args) => {
      const out = realRun(...args);
      seen.push({ ...solver.lastOptions });
      return out;
    };
    await reduceFromAdjacency(SIMPLE);
    expect(seen.length).toBeGreaterThanOrEqual(2);
    for (const o of seen) {
      expect(o).toMatchObject({ presolve, mip_rel_gap: 0, mip_abs_gap: 0,
                                primal_feasibility_tolerance: 1e-9, mip_feasibility_tolerance: 1e-9 });
    }
  });

  it("passes the time limit to HiGHS", async () => {
    const seen: unknown[] = [];
    solver.hooks.run = (...args) => { const out = realRun(...args); seen.push(solver.lastOptions.time_limit); return out; };
    await reduceFromAdjacency(SIMPLE, { timeLimit: 30 });
    expect(seen[0]).toBeGreaterThan(0);
    expect(seen[0]).toBeLessThanOrEqual(30);
  });

  it("reports the HiGHS version", async () => {
    await loadSolver();
    const v = solver.loadedSolver().version;
    console.log(`highs npm package ${JSON.stringify(v)}`);
    expect(v.major * 100 + v.minor).toBeGreaterThanOrEqual(115);
  });
});

describe("failure paths", () => {
  it("a time budget is shared across solves", async () => {
    let now = 0;
    clock.now = () => now;
    const limits: (number | null)[] = [];
    solver.hooks.run = (problem, lower, upper, sumLimit, timeLimit) => {
      limits.push(timeLimit);
      const out = realRun(problem, lower, upper, sumLimit, timeLimit);
      now += 10; // every solve "takes" 10 seconds
      return out;
    };
    await expect(reduceFromAdjacency(SIMPLE, { timeLimit: 5 }))
      .rejects.toThrow(/assignment-minimum MILP failed: Time limit reached/);
    // The first solve got the whole budget; the second would get -5 seconds, so it never ran.
    expect(limits).toEqual([5]);
  });

  it("no time limit means no deadline", async () => {
    const limits: (number | null)[] = [];
    solver.hooks.run = (p, l, u, s, t) => { limits.push(t); return realRun(p, l, u, s, t); };
    await reduceFromAdjacency(SIMPLE);
    expect(limits.length).toBeGreaterThan(0);
    expect(limits.every((t) => t === null)).toBe(true);
  });

  it.each([
    ["failed", "Unbounded"], ["time_limit", "Time limit reached"], ["infeasible", "Infeasible"],
  ] as const)("a first solve with status %s is a solver error", async (status, text) => {
    solver.hooks.run = () => ({ status, text });
    await expect(reduceFromAdjacency(SIMPLE)).rejects.toThrow(
      new RegExp(`assignment-minimum MILP failed: ${text}`));
    await expect(reduceFromAdjacency(SIMPLE)).rejects.toBeInstanceOf(SolverError);
  });

  it("a non optimal later solve is a solver error", async () => {
    let calls = 0;
    solver.hooks.run = (...args) => {
      calls++;
      return calls === 1 ? realRun(...args) : { status: "failed", text: "Memory limit reached" };
    };
    await expect(reduceFromAdjacency(SIMPLE)).rejects.toThrow(/assignment-minimum MILP failed: Memory limit/);
  });

  const corrupt = (change: (v: Float64Array) => void): typeof solver.hooks.run =>
    (...args) => {
      const out = realRun(...args);
      if (out.values) { const v = Float64Array.from(out.values); change(v); return { ...out, values: v }; }
      return out;
    };

  it.each([
    ["all zero", (v: Float64Array) => v.fill(0, 0)],
    ["fractional", (v: Float64Array) => { v[0] = 0.5; }],
    ["NaN", (v: Float64Array) => { v[0] = NaN; }],
    ["sum differs from the objective", (v: Float64Array) => v.fill(1, 0, 9)],
  ])("a scripted invalid first solution (%s) is rejected", async (_name, change) => {
    solver.hooks.run = corrupt(change);
    await expect(reduceFromAdjacency(SIMPLE)).rejects.toThrow(/HiGHS returned an invalid solution/);
  });

  it("a solution that leaves an edge uncovered is rejected", async () => {
    solver.hooks.run = (problem, lower, upper, sumLimit, t) => {
      const out = realRun(problem, lower, upper, sumLimit, t);
      if (sumLimit !== null || !out.values) return out;
      const v = Float64Array.from(out.values);
      v[v.findIndex((x, k) => k < problem.numX && x > 0.5)] = 0;
      return { ...out, values: v };
    };
    await expect(reduceFromAdjacency(SIMPLE)).rejects.toThrow(/HiGHS returned an invalid solution/);
  });

  // The first solve of the wheat example may already return the canonical optimum, which
  // would leave no feasible re-solve to test. A tiny extra cost on the early memberships
  // moves the first solution away from it; the later solves are unchanged.
  const offCanonicalFirstSolve = (): typeof solver.hooks.run => (problem, lower, upper, sumLimit, t) => {
    if (sumLimit === null) {
      const cost = Float64Array.from(problem.cost);
      for (let k = 0; k < problem.numX; k++) cost[k] = 1 + 1e-3 * (problem.numX - k) / problem.numX;
      return realRun({ ...problem, cost }, lower, upper, sumLimit, t);
    }
    return realRun(problem, lower, upper, sumLimit, t);
  };

  it.runIf(hasConformance)("scripted invalid later solutions are rejected (wheat has feasible re-solves)", async () => {
    let later = 0;
    const first = offCanonicalFirstSolve();
    solver.hooks.run = (problem, lower, upper, sumLimit, t) => {
      const out = first(problem, lower, upper, sumLimit, t);
      if (sumLimit !== null && out.status === "optimal") {
        later++;
        return { ...out, values: new Float64Array(out.values!.length) };
      }
      return out;
    };
    await expect(reduceLetters(wheatPairs())).rejects.toThrow(/HiGHS returned an invalid solution/);
    expect(later).toBe(1);
  });

  it.runIf(hasConformance)("a solution that violates a fixing is rejected", async () => {
    const first = offCanonicalFirstSolve();
    solver.hooks.run = (problem, lower, upper, sumLimit, t) => {
      const out = first(problem, lower, upper, sumLimit, t);
      if (sumLimit !== null && out.status === "optimal") {
        const v = Float64Array.from(out.values!);
        v[lower.findIndex((x, k) => k < problem.numX && x > 0.5)] = 0;
        return { ...out, values: v };
      }
      return out;
    };
    await expect(reduceLetters(wheatPairs())).rejects.toThrow(/HiGHS returned an invalid solution/);
  });
});

describe("loading and disposal", () => {
  it("concurrent calls give independent correct results", async () => {
    const results = await Promise.all([
      reduceFromAdjacency(SIMPLE), reduceFromAdjacency([[true]]), reduceFromAdjacency(SIMPLE, { groups: ["a", "b", "c", "d", "e"] }),
    ]);
    expect(results[0].letters["3"]).toBe("AC");
    expect(results[1].letters["1"]).toBe("A");
    expect(results[2].letters.c).toBe("AC");
  });

  it("every model is disposed, also when a solve fails", async () => {
    const h = solver.loadedSolver();
    const create = h.createModel.bind(h);
    const models: { disposed: boolean }[] = [];
    const spy = vi.spyOn(h, "createModel").mockImplementation((...a: any[]) => {
      const m = create(...(a as [])) as any;
      models.push(m);
      return m;
    });
    await reduceFromAdjacency(SIMPLE);
    const ok = models.length;
    solver.hooks.run = (problem, lower, upper, sumLimit, t) => {
      realRun(problem, lower, upper, sumLimit, t);
      throw new Error("boom after the solve");
    };
    await expect(reduceFromAdjacency(SIMPLE)).rejects.toThrow(/boom/);
    spy.mockRestore();
    expect(ok).toBeGreaterThanOrEqual(2);
    expect(models.length).toBeGreaterThan(ok);
    expect(models.every((m) => m.disposed)).toBe(true);
  });

  it("loading again with other options throws", async () => {
    await loadSolver();
    await expect(loadSolver({ locateFile: (f) => f })).rejects.toThrow(/already loaded/);
  });

  it("the highs package exports a loader", () => {
    const loader = (highsImport as any).default ?? highsImport;
    expect(typeof loader).toBe("function");
  });
});
