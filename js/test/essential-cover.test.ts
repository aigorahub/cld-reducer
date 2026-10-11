import { afterEach, expect, it, vi } from "vitest";
import { clock, essentialCoverCertificate, solveCanonical } from "../src/canonical.js";
import * as api from "../src/index.js";
import { maximalCliques } from "../src/cliques.js";
import { graphContext, methods, type Model, type Strategy } from "../src/model.js";
import { reduceGraphVertices } from "../src/reduction-graph.js";
import * as solver from "../src/solver.js";
import { MULTIPARTITE, SIMPLE } from "./helpers.js";

const realRun = solver.hooks.run, realNow = clock.now;
afterEach(() => { solver.hooks.run = realRun; clock.now = realNow; solver.settings.presolve = "on"; });

const noncontiguous = (): Model => ({
  problem: {numCols:5, decisionColumns:[4,1,3], cost:Float64Array.of(0,3,0,5,2),
    starts:Int32Array.of(0,1,2,3), indices:Int32Array.of(1,4,2), values:Float64Array.of(1,1,1),
    rowLower:Float64Array.of(1,1,1), rowUpper:Float64Array.of(Infinity,Infinity,Infinity)},
  members:[], edges:[], groupColumns:[], edgeEnds:[],
});
const noncontiguousStrategy = (strategy: Strategy): Strategy => ({
  ...strategy, essentialDecisions: () => [1,4], coverage: (_, selected) => selected[0] && selected[1],
});
const modelFor = (adjacency: boolean[][], strategy: Strategy): Model => {
  const reduced = reduceGraphVertices(adjacency);
  const graph = {adjacency:reduced.adjacency, groups:reduced.classes.map((_,i)=>String(i)), means:null};
  return strategy.builder(graphContext(graph,maximalCliques(graph.adjacency,10000),reduced.weights));
};

it("keeps the certificate outside the public package API", () => {
  expect(api).not.toHaveProperty("essentialCoverCertificate");
});

it.each([[0,0],[-1],[5],[0.5],[NaN],Array(1)].map(decisions=>({decisions})))(
  "rejects invalid decision columns before certification: $decisions", ({decisions}) => {
    for (const strategy of methods) {
      const model = noncontiguous();
      model.problem.decisionColumns = decisions;
      model.problem.cost.fill(0);
      const coverage = vi.fn(()=>true);
      solver.hooks.run = vi.fn(()=>{throw new Error("invalid decisions reached solver");});
      expect(()=>solveCanonical(model,null,{...strategy,coverage,essentialDecisions:()=>[]}))
        .toThrow("HiGHS returned an invalid solution");
      expect(coverage).not.toHaveBeenCalled();
      expect(solver.hooks.run).not.toHaveBeenCalled();
    }
  });

it.each(["on","off"] as const)("certifies weighted noncontiguous decisions with presolve %s", async presolve => {
  await api.loadSolver(); solver.settings.presolve = presolve;
  for (const strategy of methods) {
    const model = noncontiguous(), custom = noncontiguousStrategy(strategy);
    const before = structuredClone(model);
    const reference = solveCanonical(model,null,custom,false);
    expect(reference).toEqual({selected:[true,true,false],minimum:5});
    solver.hooks.run = () => { throw new Error("certificate called solver"); };
    expect(solveCanonical(model,null,custom)).toEqual(reference);
    // The helper itself has no clock, solver, or model mutation.
    clock.now = () => { throw new Error("helper read clock"); };
    expect(essentialCoverCertificate(model,model.problem.decisionColumns,[1,4],custom)).toEqual(reference);
    expect(model).toEqual(before);
    solver.hooks.run = realRun; clock.now = realNow;
  }
});

it.each(["on","off"] as const)("uses no solver on essential covers with presolve %s", async presolve => {
  await api.loadSolver(); solver.settings.presolve = presolve;
  const graphs = [SIMPLE, [[true]], Array.from({length:5},()=>Array<boolean>(5).fill(true)),
    Array.from({length:4},(_,i)=>Array.from({length:4},(_,j)=>i===j)),
    [[true,true,false],[true,true,true],[false,true,true]],
    // Weighted true twins in the middle of a path.
    [[true,true,true,false],[true,true,true,true],[true,true,true,true],[false,true,true,true]]];
  for (const strategy of methods) for (const adjacency of graphs) {
    const model = modelFor(adjacency,strategy);
    solver.hooks.run = realRun;
    const reference = solveCanonical(model,null,strategy,false);
    const neverRun = vi.fn(() => { throw new Error("certified public call reached solver"); });
    solver.hooks.run = neverRun;
    expect(solveCanonical(model,null,strategy)).toEqual(reference);
    const result = await api.reduceFromAdjacency(adjacency,{method:strategy.name});
    expect(result.stats.objective).toBe(reference.minimum);
    expect(result.relationshipPreserved).toBe(true);
    expect(neverRun).not.toHaveBeenCalled();
  }
});

it.each(["on","off"] as const)("falls back for an empty essential set on K(2,2,2), presolve %s", async presolve => {
  await api.loadSolver(); solver.settings.presolve = presolve;
  for (const strategy of methods) {
    const model = modelFor(MULTIPARTITE,strategy);
    expect(strategy.essentialDecisions(model)).toEqual([]);
    expect(essentialCoverCertificate(model,model.problem.decisionColumns,[],strategy)).toBeNull();
    const reference = solveCanonical(model,null,strategy,false);
    const observed = vi.fn(realRun); solver.hooks.run = observed;
    expect(solveCanonical(model,null,strategy)).toEqual(reference);
    expect(observed).toHaveBeenCalled();
    solver.hooks.run = realRun;
  }
});

it.each([
  {column:4,cost:0}, {column:4,cost:-1}, {column:4,cost:0.5}, {column:4,cost:NaN},
  {column:4,cost:Infinity}, {column:4,cost:Number.MAX_SAFE_INTEGER+1},
  {column:3,cost:0}, {column:3,cost:-1}, {column:3,cost:0.5},
  {column:3,cost:NaN}, {column:3,cost:Infinity},
  {column:0,cost:1}, {column:0,cost:-1}, {column:0,cost:0.5},
  {column:0,cost:NaN}, {column:0,cost:Infinity},
])("retains the solver path for unsupported cost $cost in column $column", ({column,cost}) => {
  for (const strategy of methods) {
    const model = noncontiguous(), custom = noncontiguousStrategy(strategy);
    model.problem.cost[column] = cost;
    expect(essentialCoverCertificate(model,model.problem.decisionColumns,[1,4],custom)).toBeNull();
    const observed = vi.fn((_p,lower) => {
      expect([...lower]).toEqual([0,1,0,0,1]);
      return {status:"failed" as const,text:"fallback sentinel"};
    });
    solver.hooks.run = observed;
    expect(()=>solveCanonical(model,null,custom)).toThrow(strategy.failurePrefix+"fallback sentinel");
    expect(observed).toHaveBeenCalledOnce();
  }
});

it("retains zero-cost optional decisions in the reference canonical optimum", async () => {
  await api.loadSolver();
  for (const strategy of methods) {
    const model = noncontiguous(), custom = noncontiguousStrategy(strategy);
    model.problem.cost[3] = 0;
    const reference = solveCanonical(model,null,custom,false);
    expect(reference).toEqual({selected:[true,true,true],minimum:5});
    solver.hooks.run = vi.fn(realRun);
    expect(solveCanonical(model,null,custom)).toEqual(reference);
    expect(solver.hooks.run).toHaveBeenCalled();
    solver.hooks.run = realRun;
  }
});

it.each(["sum","length"])("does not certify an inexact sum or incomplete cost vector: %s", kind => {
  for (const strategy of methods) {
    const model = noncontiguous(), custom = noncontiguousStrategy(strategy);
    if (kind === "sum") model.problem.cost[1] = Number.MAX_SAFE_INTEGER;
    else model.problem.cost = model.problem.cost.subarray(0,4);
    expect(essentialCoverCertificate(model,model.problem.decisionColumns,[1,4],custom)).toBeNull();
    solver.hooks.run = vi.fn(()=>({status:"failed" as const,text:"fallback sentinel"}));
    expect(()=>solveCanonical(model,null,custom)).toThrow("fallback sentinel");
    expect(solver.hooks.run).toHaveBeenCalledOnce();
  }
});

it("falls back when a nonempty essential set does not cover", async () => {
  await api.loadSolver();
  const model = noncontiguous();
  for (const strategy of methods) {
    const custom = {...noncontiguousStrategy(strategy),essentialDecisions:()=>[1]};
    expect(essentialCoverCertificate(model,model.problem.decisionColumns,[1],custom)).toBeNull();
    const reference = solveCanonical(model,null,custom,false);
    solver.hooks.run = vi.fn(realRun);
    expect(solveCanonical(model,null,custom)).toEqual(reference);
    expect(solver.hooks.run).toHaveBeenCalled();
    solver.hooks.run = realRun;
  }
});

it.each(["scan","certificate success","certificate failure"])("checks the deadline after %s", phase => {
  for (const strategy of methods) {
    let now = 0; clock.now = () => now;
    const model = noncontiguous();
    const coverage = vi.fn((_model:Model, _selected:boolean[]) => {
      now = 5;
      return phase !== "certificate failure";
    });
    const custom = {...strategy,coverage,essentialDecisions:()=>{
      if (phase === "scan") now = 5;
      return [1,4];
    }};
    solver.hooks.run = vi.fn(()=>{throw new Error("expired certificate reached solver");});
    expect(()=>solveCanonical(model,5,custom)).toThrow(strategy.failurePrefix+"Time limit reached");
    expect(coverage).toHaveBeenCalledTimes(phase === "scan" ? 0 : 1);
    expect(solver.hooks.run).not.toHaveBeenCalled();
  }
});

it("validates malformed essential output before checking an expired scan deadline", () => {
  for (const strategy of methods) {
    let now = 0; clock.now = () => now;
    const custom = {...strategy,essentialDecisions:()=>{now=10;return [4,1];}};
    expect(()=>solveCanonical(noncontiguous(),5,custom)).toThrow("HiGHS returned an invalid solution");
  }
});
