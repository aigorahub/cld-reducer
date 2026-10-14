import { afterEach, expect, it, vi } from "vitest";
import { reduceFromAdjacency } from "../src/reduce.js";
import { clock, planCertificate, solveCanonical } from "../src/canonical.js";
import { graphContext, methods, type DecisionData } from "../src/model.js";
import { maximalCliques } from "../src/cliques.js";
import { hooks, getSolver } from "../src/solver.js";
const realRun = hooks.run, realClock = clock.now;
afterEach(() => { hooks.run = realRun; clock.now = realClock; vi.restoreAllMocks(); });
const complete = Array.from({length:5}, () => Array(5).fill(true));
const isolates = Array.from({length:4}, (_,i) => Array.from({length:4}, (_,j) => i === j));
const simple = Array.from({length:5}, (_,i) => Array.from({length:5}, (_,j) =>
  i === j || [[0,1,2],[1,2,3],[2,3,4]].some(q => q.includes(i) && q.includes(j))));
const fallback = Array.from({length:6}, (_,i) => Array.from({length:6}, (_,j) => i === j || Math.floor(i/2) !== Math.floor(j/2)));
function planFor(graph: boolean[][], strategy = methods[0]) {
  return strategy.planner(graphContext({adjacency:graph, groups:graph.map((_,k)=>String(k)),means:null},
    maximalCliques(graph, 10000), undefined, strategy.countsAssignments));
}
it.each(methods)("$name certifies before compilation", async strategy => {
  vi.spyOn(strategy, "compiler").mockImplementation(() => { throw new Error("compiler called"); });
  vi.spyOn(strategy, "builder").mockImplementation(() => { throw new Error("builder called"); });
  hooks.run = () => { throw new Error("solver called"); };
  for (const graph of [complete, isolates, simple]) {
    expect((await reduceFromAdjacency(graph, {method:strategy.name})).relationshipPreserved).toBe(true);
  }
});
it.each(methods)("$name scans and compiles once on fallback", async strategy => {
  await getSolver();
  for (const graph of [fallback, fallback.map(row => [...row,false]).concat([Array(6).fill(false).concat(true)])]) {
    const plan = planFor(graph,strategy);
    const reference = solveCanonical(strategy.builder(plan.context), null, strategy, false);
    const compiler = vi.fn(strategy.compiler), scan = vi.fn(strategy.essentialDecisions);
    expect(solveCanonical(plan, null, {...strategy,compiler,essentialDecisions:scan})).toEqual(reference);
    expect(compiler).toHaveBeenCalledTimes(1); expect(scan).toHaveBeenCalledTimes(1);
  }
});
it.each(methods)("$name excludes compilation time but retains scan and proof time", strategy => {
  const plan = planFor(fallback,strategy); let now = 0; clock.now = () => now;
  const custom = {...strategy,
    essentialDecisions: (data: DecisionData) => { now += 2; return strategy.essentialDecisions(data); },
    coverage: (data: DecisionData, selected: boolean[]) => { now += 1; return strategy.coverage(data,selected); },
    compiler: (data: typeof plan) => { now += 100; return strategy.compiler(data); },
  };
  hooks.run = (_p,_l,_u,_cap,remaining) => { expect(remaining).toBe(7); throw new Error("budget verified"); };
  expect(() => solveCanonical(plan,10,custom)).toThrow("budget verified");
});
it.each(["scan","certificate"])("expiry in %s prevents compilation", phase => {
  for (const strategy of methods) {
    const plan = planFor(simple,strategy); let now = 0; clock.now = () => now;
    const compiler = vi.fn(strategy.compiler);
    const custom = {...strategy,compiler,
      essentialDecisions: (data: DecisionData) => { if (phase === "scan") now = 5; return strategy.essentialDecisions(data); },
      coverage: (data: DecisionData, selected: boolean[]) => { now = 5; return strategy.coverage(data,selected); },
    };
    expect(() => solveCanonical(plan,5,custom)).toThrow("Time limit reached");
    expect(compiler).not.toHaveBeenCalled();
  }
});
it.each([null,[true],[-1],[999],[0.5],[1,0],[0,0],Array(1)])("rejects malformed plan scan %j", required => {
  const strategy = methods[1], plan = planFor(simple,strategy);
  expect(() => solveCanonical(plan,null,{...strategy,essentialDecisions:()=>required as number[]})).toThrow("invalid solution");
});
it.each([0,-1,0.5,NaN,Infinity,Number.MAX_SAFE_INTEGER+1])("rejects certificate cost %s", cost => {
  const strategy = methods[1], plan = planFor(simple,strategy); plan.cost[0] = cost;
  expect(planCertificate(plan,strategy.essentialDecisions(plan),strategy)).toBe(null);
});
it("rejects an unsafe summed objective", () => {
  const strategy = methods[1], plan = planFor(simple,strategy); plan.cost.fill(Number.MAX_SAFE_INTEGER);
  expect(planCertificate(plan,strategy.essentialDecisions(plan),strategy)).toBe(null);
});
it("maps plan essentials to noncontiguous native columns without changing canonical order", async () => {
  await getSolver();
  const strategy = methods[1], plan = planFor(simple,strategy); plan.cost = [3,7,11];
  const custom = {...strategy, essentialDecisions:()=>[0,1],
    coverage: (_: DecisionData, x: boolean[]) => x[0] && x[1],
    compiler: () => ({ members:[], edges:[], groupColumns:[], edgeEnds:[], problem: {
      numCols:5, decisionColumns:[4,0,2], cost:Float64Array.of(7,0,11,0,3),
      starts:Int32Array.of(0,1,2,3), indices:Int32Array.of(0,4,1), values:Float64Array.of(1,1,1),
      rowLower:Float64Array.of(1,1,1), rowUpper:Float64Array.of(Infinity,Infinity,Infinity),
    } }),
  };
  let calls = 0;
  hooks.run = (...args) => {
    if (calls++ === 0) expect([...args[1]]).toEqual([1,0,0,0,1]);
    return realRun(...args);
  };
  expect(solveCanonical(plan,null,custom,false)).toEqual({selected:[true,true,false],minimum:10});
  expect(calls).toBeGreaterThan(0);
});

it.each(["count","duplicate","range","decision_cost","auxiliary_cost","cost_length"])(
  "rejects invalid compiled %s before the solver", defect => {
    const strategy = methods[0], plan = planFor(simple,strategy);
    const model = strategy.compiler(plan), problem = model.problem;
    if (defect === "count") problem.decisionColumns.pop();
    else if (defect === "duplicate") problem.decisionColumns[1] = problem.decisionColumns[0];
    else if (defect === "range") problem.decisionColumns[0] = problem.numCols;
    else if (defect === "decision_cost") problem.cost[0] += 1;
    else if (defect === "auxiliary_cost") problem.cost[plan.decisionCount] = 1;
    else problem.cost = problem.cost.slice(0,-1);
    const run = vi.fn(() => { throw new Error("invalid model reached solver"); });
    hooks.run = run;
    expect(() => solveCanonical(plan,null,{...strategy,compiler:()=>model},false))
      .toThrow("HiGHS returned an invalid solution");
    expect(run).not.toHaveBeenCalled();
  }
);
