import { readFileSync } from "node:fs";
import { join } from "node:path";
import { afterEach, expect, it } from "vitest";
import { clock, solveCanonical } from "../src/canonical.js";
import { loadSolver, reduceFromAdjacency } from "../src/index.js";
import { graphContext, methods, type Model } from "../src/model.js";
import * as solver from "../src/solver.js";
import { CONFORMANCE, hasConformance, SIMPLE } from "./helpers.js";

const realRun = solver.hooks.run, realNow = clock.now;
afterEach(() => { solver.hooks.run = realRun; clock.now = realNow; solver.settings.presolve = "on"; });

it.runIf(hasConformance)("matches independent full Boolean deletion before and after vertex reduction", () => {
  const cases = JSON.parse(readFileSync(join(CONFORMANCE,"fixtures/essential.json"),"utf8")).cases;
  for (const c of cases) {
    const context = graphContext({adjacency:c.adjacency.map((row:number[])=>row.map(Boolean)),
      groups:c.adjacency.map((_:unknown,v:number)=>String(v)),means:null},c.cliques,c.weights);
    for (const [k,strategy] of methods.entries()) {
      expect(strategy.essentialDecisions(strategy.builder(context)), c.id).toEqual(c[k===0?"essential_sigma":"essential_c"]);
    }
  }
});

it.each(["on","off"] as const)("passes essential bounds to every solve with presolve %s", async presolve => {
  solver.settings.presolve = presolve;
  for (const strategy of methods) {
    const calls:{lower:number[];upper:number[];cap:number|null}[]=[];
    solver.hooks.run=(p,l,u,s,t)=>{calls.push({lower:[...l],upper:[...u],cap:s});return realRun(p,l,u,s,t);};
    const out=await reduceFromAdjacency(SIMPLE,{method:strategy.name});
    const required=strategy.countsAssignments?[0,1,2,3,5,6,7,8]:[0,1,2];
    const lower=strategy.countsAssignments?[1,1,1,1,0,1,1,1,1,...Array(9).fill(0)]:[1,1,1];
    expect(calls[0].lower).toEqual(lower);
    expect(calls[0].upper.every(v=>v===1)).toBe(true);expect(calls[0].cap).toBe(null);
    expect(calls.every(c=>required.every(v=>c.lower[v]===1))).toBe(true);
    expect(out.stats.objective).toBe(strategy.countsAssignments?8:3);
  }
});

const tinyModel = ():Model => ({problem:{numCols:2,decisionColumns:[0,1],cost:Float64Array.of(1,1),
  starts:Int32Array.of(0,2),indices:Int32Array.of(0,1),values:Float64Array.of(1,1),
  rowLower:Float64Array.of(1),rowUpper:Float64Array.of(Infinity)},
  members:[],edges:[],groupColumns:[],edgeEnds:[]});

it("rejects a first result that violates a required bound even with valid coverage and cost", () => {
  solver.hooks.run=()=>({status:"optimal",text:"Optimal",values:Float64Array.of(0,1),objective:1});
  for (const strategy of methods) {
    expect(()=>solveCanonical(tinyModel(),null,{...strategy,coverage:(_,x)=>x.some(Boolean),essentialDecisions:()=>[0]})).toThrow("HiGHS returned an invalid solution");
  }
});

it.each([null,[1],[-1],[3],[0.5],[true],[NaN],[2,0],[0,0],[[0]],Array(1)].map(required=>({required})))("rejects malformed scan indices: %j", ({required}) => {
  const model=tinyModel();model.problem.numCols=3;model.problem.decisionColumns=[2,0];
  solver.hooks.run=()=>{throw new Error("invalid scan reached adapter");};
  const custom={...methods[0],essentialDecisions:()=>required as unknown as number[]};
  expect(()=>solveCanonical(model,null,custom)).toThrow("HiGHS returned an invalid solution");
});

it("counts scan time in the existing deadline before the first adapter call", async () => {
  await loadSolver();
  for(const strategy of methods){
    let now=0;clock.now=()=>now;
    solver.hooks.run=()=>{throw new Error("expired scan reached adapter");};
    const context=graphContext({adjacency:SIMPLE,groups:["1","2","3","4","5"],means:null},[[0,1,2],[1,2,3],[2,3,4]]);
    const custom={...strategy,essentialDecisions:(model:Model)=>{now+=10;return strategy.essentialDecisions(model);}};
    expect(()=>solveCanonical(custom.builder(context),5,custom)).toThrow("MILP failed: Time limit reached");
  }
});
