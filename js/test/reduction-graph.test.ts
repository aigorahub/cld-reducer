import { expect, it } from "vitest";
import { reduceFromAdjacency } from "../src/index.js";
import { reduceGraphVertices, expandGraphColumns } from "../src/reduction-graph.js";
import { solveCanonical } from "../src/canonical.js";
import { methods, type Model } from "../src/model.js";
import { loadSolver } from "../src/index.js";

it("merges only identical closed neighborhoods", () => {
  const reduced = reduceGraphVertices([[true,true,false,false], [true,true,false,false],
    [false,false,true,false], [false,false,false,true]]);
  expect(reduced.classes).toEqual([[0,1],[2],[3]]);
  expect(reduced.weights).toEqual([2,1,1]);
  expect(expandGraphColumns([[0,2]],reduced.classes)).toEqual([[0,1,3]]);
});

it("defaults to C and counts original vertices for sigma", async () => {
  const graph = Array.from({length:5}, () => new Array<boolean>(5).fill(true));
  const result = await reduceFromAdjacency(graph);
  expect(result).toEqual(await reduceFromAdjacency(graph, {method:"letter_minimum"}));
  expect(result.method).toBe("letter_minimum");
  expect(result.stats.objective).toBe(1);
  const sigma = await reduceFromAdjacency(graph, {method:"assignment_minimum"});
  expect(sigma.stats.objective).toBe(5);
  expect(sigma.stats.assignmentsAfter).toBe(5);
  expect(sigma.stats.numEdges).toBe(10);
});

it("uses weighted costs for canonical trial caps", async () => {
  await loadSolver();
  const model: Model = {
    problem: { numCols: 3, decisionColumns: [0,1,2], cost: new Float64Array([5,1,1]),
      starts: new Int32Array([0,2,4]), indices: new Int32Array([0,1,0,2]),
      values: new Float64Array([1,1,1,1]), rowLower: new Float64Array([1,1]),
      rowUpper: new Float64Array([Infinity,Infinity]) },
    members: [], edges: [], groupColumns: [], edgeEnds: [],
  };
  const strategy = { ...methods[0], coverage: (_: Model, x: boolean[]) => (x[0] || x[1]) && (x[0] || x[2]) };
  expect(solveCanonical(model,null,strategy)).toEqual({minimum:2,selected:[false,true,true]});
});
