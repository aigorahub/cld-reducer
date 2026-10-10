import type { Graph } from "./input.js";
import type { Problem } from "./solver.js";
export interface Model {
  problem: Problem;
  members: [number, number][];       // (clique, group) of each x variable, canonical order
  edges: [number, number][];
  groupColumns: number[][];          // x variables of each group
  coverageColumns?: number[][];
  edgeEnds: [number, number][][];    // per edge: the two x variables of each covering clique
}

/** The model of section 4. */
export function buildModel(context: Context): Model {
  const { adjacency, cliques, edges, cliquesOf } = context;
  const n = adjacency.length;
  const members: [number, number][] = [];
  const xIndex = new Map<string, number>();
  cliques.forEach((clique, c) => {
    for (const g of clique) {
      xIndex.set(`${c},${g}`, members.length);
      members.push([c, g]);
    }
  });
  const numX = members.length;

  const yPairs: [number, number][] = [];   // (edge, clique)
  edges.forEach(([i, j], e) => {
    const inJ = new Set(cliquesOf[j]);
    for (const c of cliquesOf[i]) if (inJ.has(c)) yPairs.push([e, c]);
  });

  const rows: [number, number][][] = [];
  const rowLower: number[] = [];
  const rowUpper: number[] = [];
  const inf = Infinity;
  for (let g = 0; g < n; g++) {                       // every group has a letter
    rows.push(cliquesOf[g].map((c) => [xIndex.get(`${c},${g}`)!, 1]));
    rowLower.push(1); rowUpper.push(inf);
  }
  const byEdge: number[][] = edges.map(() => []);
  yPairs.forEach(([e], k) => byEdge[e].push(numX + k));
  for (let e = 0; e < edges.length; e++) {            // every edge is covered
    rows.push(byEdge[e].map((col) => [col, 1]));
    rowLower.push(1); rowUpper.push(inf);
  }
  yPairs.forEach(([e, c], k) => {                     // a covering clique needs both ends
    for (const g of edges[e]) {
      rows.push([[numX + k, 1], [xIndex.get(`${c},${g}`)!, -1]]);
      rowLower.push(-inf); rowUpper.push(0);
    }
  });

  const starts = [0];
  const indices: number[] = [];
  const values: number[] = [];
  for (const row of rows) {
    for (const [col, coefficient] of row) { indices.push(col); values.push(coefficient); }
    starts.push(indices.length);
  }
  const numCols = numX + yPairs.length;
  const cost = new Float64Array(numCols);
  cost.fill(1, 0, numX);
  const edgeEnds: [number, number][][] = edges.map(() => []);
  for (const [e, c] of yPairs) {
    edgeEnds[e].push([xIndex.get(`${c},${edges[e][0]}`)!, xIndex.get(`${c},${edges[e][1]}`)!]);
  }
  return {
    problem: {
      numCols, decisionColumns: Array.from({length: numX}, (_, k) => k), cost,
      starts: Int32Array.from(starts), indices: Int32Array.from(indices),
      values: Float64Array.from(values),
      // Infinite row bounds become the solver's infinity inside run().
      rowLower: Float64Array.from(rowLower), rowUpper: Float64Array.from(rowUpper),
    },
    members, edges,
    groupColumns: cliquesOf.map((cs, g) => cs.map((c) => xIndex.get(`${c},${g}`)!)),
    edgeEnds,
  };
}

/** The selected members of each clique's letter, dropping empty columns. */
export function selectedColumns(cliques: number[][], model: Model, selected: boolean[]): number[][] {
  const columns: number[][] = cliques.map(() => []);
  model.members.forEach(([c, g], k) => { if (selected[k]) columns[c].push(g); });
  return columns.filter((column) => column.length > 0);
}


export function assignmentCoverage(model: Model, selected: boolean[]): boolean {
  return model.groupColumns.every(cs => cs.some(k => selected[k])) &&
    model.edgeEnds.every(ends => ends.some(([a,b]) => selected[a] && selected[b]));
}
export interface Strategy {
  name: string; aliases: string[]; failurePrefix: string; countsAssignments: boolean;
  builder: typeof buildModel; coverage: typeof assignmentCoverage; decoder: typeof selectedColumns;
}

export interface Context extends Graph {
  cliques: number[][]; edges: [number, number][]; cliquesOf: number[][];
}
export function graphContext(graph: Graph, cliques: number[][]): Context {
  const edges: [number, number][] = [];
  for (let i=0; i<graph.groups.length; i++) for (let j=i+1; j<graph.groups.length; j++) {
    if (graph.adjacency[i][j]) edges.push([i,j]);
  }
  const cliquesOf = graph.groups.map((_,g) => cliques.flatMap((q,c) => q.includes(g) ? [c] : []));
  return { ...graph, cliques, edges, cliquesOf };
}
function buildLetterModel(context: Context): Model {
  const { cliques, edges, cliquesOf } = context;
  const rows = [...cliquesOf, ...edges.map(([i,j]) => cliquesOf[i].filter(c => cliques[c].includes(j)))];
  const starts = [0];
  const indices: number[] = [];
  for (const row of rows) { indices.push(...row); starts.push(indices.length); }
  const n = cliques.length;
  return {
    problem: { numCols: n, decisionColumns: Array.from({length:n}, (_,k) => k),
      cost: new Float64Array(n).fill(1), starts: Int32Array.from(starts),
      indices: Int32Array.from(indices), values: new Float64Array(indices.length).fill(1),
      rowLower: new Float64Array(rows.length).fill(1), rowUpper: new Float64Array(rows.length).fill(Infinity) },
    members: [], edges, groupColumns: [], edgeEnds: [], coverageColumns: rows,
  };
}
function letterCoverage(model: Model, selected: boolean[]): boolean {
  return model.coverageColumns!.every(cs => cs.some(c => selected[c]));
}
function letterColumns(cliques: number[][], model: Model, selected: boolean[]): number[][] {
  return cliques.filter((_,c) => selected[c]).map(q => [...q]);
}
export const methods: Strategy[] = [
  { name: "assignment_minimum", aliases: ["assignment_minimum", "assignment-minimum"],
    failurePrefix: "assignment-minimum MILP failed: ", countsAssignments: true,
    builder: buildModel, coverage: assignmentCoverage, decoder: selectedColumns },
  { name: "letter_minimum", aliases: ["letter_minimum", "letter-minimum"],
    failurePrefix: "letter-minimum MILP failed: ", countsAssignments: false,
    builder: buildLetterModel, coverage: letterCoverage, decoder: letterColumns },
];
