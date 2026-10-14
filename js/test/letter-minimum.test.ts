import { afterEach, expect, it } from "vitest";
import { reduceFromAdjacency, SolverError } from "../src/index.js";
import { clock, solveCanonical } from "../src/canonical.js";
import { methods, type Model } from "../src/model.js";
import * as solver from "../src/solver.js";
const real = solver.hooks.run;
const now = clock.now;
afterEach(() => { solver.hooks.run = real; clock.now = now; });
const edges = [[0,2],[0,3],[0,4],[0,5],[1,2],[1,3],[1,4],[1,5],[2,3],[2,5],[3,4]];
const tied = Array.from({length:6}, (_,i) => Array.from({length:6}, (_,j) => i===j || edges.some(([a,b]) => i===a && j===b || i===b && j===a)));
it("uses full columns and normalized C metadata", async () => {
  const simple = [[1,1,1,0,0],[1,1,1,1,0],[1,1,1,1,1],[0,1,1,1,1],[0,0,1,1,1]];
  const out = await reduceFromAdjacency(simple, {method:"letter-minimum"});
  expect(out.method).toBe("letter_minimum");
  expect(out.stats.objective).toBe(3); expect(out.stats.assignmentsAfter).toBe(9);
  expect(out.assignments["3"]).toEqual(["A","B","C"]);
});
it("uses feasible and infeasible C canonical trials with perturbed initial costs", async () => {
  const statuses: string[] = [];
  solver.hooks.run = (problem,lo,hi,cap,time) => {
    if (cap === null) {
      const cost = Float64Array.from(problem.cost);
      problem.decisionColumns.forEach((v,k) => cost[v] += .001*(problem.decisionColumns.length-1-k)/(problem.decisionColumns.length-1));
      problem = {...problem,cost};
    }
    const out = real(problem,lo,hi,cap,time);
    if (cap !== null) statuses.push(out.status);
    if (out.status === "infeasible") out.values = Float64Array.of(NaN);
    return out;
  };
  const out = await reduceFromAdjacency(tied,{method:"letter_minimum"});
  expect(statuses).toContain("optimal"); expect(statuses).toContain("infeasible");
  expect(out.stats.objective).toBe(5);
  expect(out.groups.map(g => out.letters[g])).toEqual(["ABC","DE","ABD","ACE","CE","BD"]);
});
it.each(["none","length","zero","full","fractional","nan","two","objective","infinite","status"])("rejects invalid C outcome: %s", async kind => {
  solver.hooks.run = (...args) => {
    const out = real(...args);
    if (kind === "status") return {status:"infeasible",text:"status-text"};
    if (kind === "none") out.values = undefined;
    if (kind === "length") out.values = new Float64Array(5);
    if (["zero","full","fractional","nan","two"].includes(kind)) out.values!.fill(({zero:0,full:1,fractional:.5,nan:NaN,two:2} as Record<string,number>)[kind]);
    if (kind === "objective") out.objective = 3;
    if (kind === "infinite") out.objective = Infinity;
    return out;
  };
  await expect(reduceFromAdjacency(tied,{method:"letter_minimum"})).rejects.toThrow(kind === "status" ? "letter-minimum MILP failed: status-text" : "HiGHS returned an invalid solution");
});
it("caps only noncontiguous native decisions and visits their declared order", async () => {
  await reduceFromAdjacency([[1]]);
  const problem: solver.Problem = {numCols:3,decisionColumns:[2,0],cost:Float64Array.of(1,0,1),
    starts:Int32Array.of(0,2,3),indices:Int32Array.of(0,2,1),values:Float64Array.of(1,1,1),
    rowLower:Float64Array.of(1,1),rowUpper:Float64Array.of(Infinity,Infinity)};
  const out = real(problem,new Float64Array(3),new Float64Array(3).fill(1),1,null);
  expect(out.status).toBe("optimal"); expect(out.values![1]).toBe(1);
  for (const strategy of methods) {
    const model: Model = {problem,members:[],edges:[],groupColumns:[],edgeEnds:[]};
    const out = solveCanonical(model,null,{...strategy,coverage:(_,s)=>s.some(Boolean)});
    expect(out.minimum).toBe(1); expect(out.selected).toEqual([true,false]);
  }
});
it("checks the C deadline before the initial adapter call", async () => {
  let calls = 0;
  clock.now = () => calls++ ? 10 : 0;
  solver.hooks.run = () => { throw new Error("expired solve reached adapter"); };
  await expect(reduceFromAdjacency(tied,{method:"letter_minimum",timeLimit:5})).rejects.toThrow("letter-minimum MILP failed: Time limit reached");
});

it.each(["fixing","count","status"])("rejects bad feasible C trials: %s", async kind => {
  solver.hooks.run = (problem,lo,hi,cap,time) => {
    if (cap === null) {
      const cost = Float64Array.from(problem.cost);
      problem.decisionColumns.forEach((v,k) => cost[v] += .001*(5-k)/5);
      problem = {...problem,cost};
    }
    const out = real(problem,lo,hi,cap,time);
    if (cap !== null && out.status === "optimal") {
      if (kind === "status") return {status:"failed",text:"Memory limit reached"};
      if (kind === "fixing") out.values![Array.from(lo).findIndex(v => v > .5)] = 0;
      if (kind === "count") out.values!.fill(1);
    }
    return out;
  };
  await expect(reduceFromAdjacency(tied,{method:"letter_minimum"})).rejects.toThrow(SolverError);
});
it("rejects missing C edge coverage at the correct decision count", async () => {
  solver.hooks.run = () => ({status:"optimal",text:"Optimal",objective:5,values:Float64Array.of(1,1,1,1,1,0)});
  await expect(reduceFromAdjacency(tied,{method:"letter_minimum"})).rejects.toThrow("HiGHS returned an invalid solution");
});
it("checks the shared C budget before trials", async () => {
  let elapsed = 0;
  clock.now = () => elapsed;
  solver.hooks.run = (...args) => { const out = real(...args); elapsed += 10; return out; };
  await expect(reduceFromAdjacency(tied,{method:"letter_minimum",timeLimit:5})).rejects.toThrow("letter-minimum MILP failed: Time limit reached");
});
it("validates C controls", async () => {
  await expect(reduceFromAdjacency(tied,{method:"letter_minimum",timeLimit:0})).rejects.toThrow("time_limit");
  await expect(reduceFromAdjacency(tied,{method:"letter_minimum",maxCliques:0})).rejects.toThrow("max_cliques");
});
