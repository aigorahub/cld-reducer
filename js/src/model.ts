import type { Graph } from "./input.js";
import type { Problem } from "./solver.js";
export interface Model extends DecisionData { problem: Problem; }
export interface DecisionData {
  members: [number, number][];       // (clique, group) of each x variable, canonical order
  edges: [number, number][];
  groupColumns: number[][];          // x variables of each group
  coverageColumns?: number[][];
  edgeEnds: [number, number][][];    // per edge: the two x variables of each covering clique
}

/** Sorted incidence positions shared by the two endpoints. */
export function* sharedPositions(left: number[], right: number[]): Generator<[number, number]> {
  let i = 0, j = 0;
  while (i < left.length && j < right.length) {
    if (left[i] === right[j]) { yield [i++, j++]; }
    else if (left[i] < right[j]) i++;
    else j++;
  }
}

export interface DecisionPlan extends DecisionData {
  context: Context;
  cost: number[];
  decisionCount: number;
}

export function buildAssignmentPlan(context: Context): DecisionPlan {
  const members: [number, number][] = context.members ?? [];
  const groupColumns: number[][] = context.groupColumns ?? context.groups.map(() => []);
  if (!context.members) context.cliques.forEach((clique, c) => {
    for (const g of clique) { groupColumns[g].push(members.length); members.push([c, g]); }
  });
  const edgeEnds = context.edges.map(([i,j]) =>
    [...sharedPositions(context.cliquesOf[i], context.cliquesOf[j])]
      .map(([a,b]): [number, number] => [groupColumns[i][a], groupColumns[j][b]]));
  return { context, members, groupColumns, edgeEnds, edges: context.edges,
    decisionCount: members.length, cost: members.map(([,g]) => context.weights[g]) };
}

/** Legacy compiled-model entry point. */
export function buildModel(context: Context): Model {
  return compileAssignmentPlan(buildAssignmentPlan(context));
}

export function compileAssignmentPlan(plan: DecisionPlan): Model {
  const numX = plan.decisionCount;
  const numY = plan.edgeEnds.reduce((n, ends) => n + ends.length, 0);
  const rows: [number, number][][] = plan.groupColumns.map(cs => cs.map(k => [k, 1]));
  const rowLower = rows.map(() => 1), rowUpper = rows.map(() => Infinity);
  let witness = numX;
  for (const ends of plan.edgeEnds) {
    rows.push(ends.map((_, k) => [witness + k, 1]));
    rowLower.push(1); rowUpper.push(Infinity);
    witness += ends.length;
  }
  witness = numX;
  for (const ends of plan.edgeEnds) for (const pair of ends) {
    for (const k of pair) {
      rows.push([[witness, 1], [k, -1]]);
      rowLower.push(-Infinity); rowUpper.push(0);
    }
    witness++;
  }
  const starts = [0], indices: number[] = [], values: number[] = [];
  for (const row of rows) {
    for (const [k,v] of row) { indices.push(k); values.push(v); }
    starts.push(indices.length);
  }
  const cost = new Float64Array(numX + numY);
  cost.set(plan.cost);
  return { ...plan, problem: {
    numCols: numX + numY, decisionColumns: Array.from({length:numX}, (_,k) => k), cost,
    starts: Int32Array.from(starts), indices: Int32Array.from(indices),
    values: Float64Array.from(values), rowLower: Float64Array.from(rowLower),
    rowUpper: Float64Array.from(rowUpper),
  } };
}

/** The selected members of each clique's letter, dropping empty columns. */
export function selectedColumns(cliques: number[][], model: DecisionData, selected: boolean[]): number[][] {
  const columns: number[][] = cliques.map(() => []);
  model.members.forEach(([c, g], k) => { if (selected[k]) columns[c].push(g); });
  return columns.filter((column) => column.length > 0);
}


export function assignmentCoverage(model: DecisionData, selected: boolean[]): boolean {
  return model.groupColumns.every(cs => cs.some(k => selected[k])) &&
    model.edgeEnds.every(ends => ends.some(([a,b]) => selected[a] && selected[b]));
}
export function assignmentEssentialDecisions(model: DecisionData): number[] {
  const required = new Set<number>();
  for (const columns of model.groupColumns) if (columns.length === 1) required.add(columns[0]);
  for (const ends of model.edgeEnds) if (ends.length === 1) {
    required.add(ends[0][0]); required.add(ends[0][1]);
  }
  return [...required].sort((a,b) => a-b);
}
export interface Strategy {
  name: string; aliases: string[]; failurePrefix: string; countsAssignments: boolean;
  builder: typeof buildModel; coverage: typeof assignmentCoverage; decoder: typeof selectedColumns;
  essentialDecisions: (model: DecisionData) => number[];
  planner: (context: Context) => DecisionPlan;
  compiler: (plan: DecisionPlan) => Model;
}

export interface Context extends Graph {
  members?: [number, number][]; groupColumns?: number[][];
  cliques: number[][]; edges: [number, number][]; cliquesOf: number[][]; weights: number[];
}
export function graphContext(graph: Graph, cliques: number[][], weights = graph.groups.map(() => 1), assignments = false): Context {
  const edges: [number, number][] = [];
  for (let i=0; i<graph.groups.length; i++) for (let j=i+1; j<graph.groups.length; j++) {
    if (graph.adjacency[i][j]) edges.push([i,j]);
  }
  const cliquesOf: number[][] = graph.groups.map(() => []);
  const members: [number, number][] | undefined = assignments ? [] : undefined;
  const groupColumns = assignments ? graph.groups.map((): number[] => []) : undefined;
  cliques.forEach((q,c) => { for (const g of q) {
    cliquesOf[g].push(c);
    if (members && groupColumns) { groupColumns[g].push(members.length); members.push([c,g]); }
  } });
  return { ...graph, cliques, edges, cliquesOf, weights, members, groupColumns };
}
function buildLetterPlan(context: Context): DecisionPlan {
  const { cliques, edges, cliquesOf } = context;
  const rows = [...cliquesOf, ...edges.map(([i,j]) =>
    [...sharedPositions(cliquesOf[i], cliquesOf[j])].map(([a]) => cliquesOf[i][a]))];
  return { context, decisionCount: cliques.length, cost: cliques.map(() => 1),
    members: [], edges, groupColumns: [], edgeEnds: [], coverageColumns: rows };
}
function buildLetterModel(context: Context): Model { return compileLetterPlan(buildLetterPlan(context)); }
function compileLetterPlan(plan: DecisionPlan): Model {
  const rows = plan.coverageColumns!;
  const starts = [0];
  const indices: number[] = [];
  for (const row of rows) { indices.push(...row); starts.push(indices.length); }
  const n = plan.decisionCount;
  return {
    problem: { numCols: n, decisionColumns: Array.from({length:n}, (_,k) => k),
      cost: new Float64Array(n).fill(1), starts: Int32Array.from(starts),
      indices: Int32Array.from(indices), values: new Float64Array(indices.length).fill(1),
      rowLower: new Float64Array(rows.length).fill(1), rowUpper: new Float64Array(rows.length).fill(Infinity) },
    ...plan,
  };
}
function letterCoverage(model: DecisionData, selected: boolean[]): boolean {
  return model.coverageColumns!.every(cs => cs.some(c => selected[c]));
}
function letterEssentialDecisions(model: DecisionData): number[] {
  return [...new Set(model.coverageColumns!.filter(cs => cs.length === 1).map(cs => cs[0]))].sort((a,b) => a-b);
}
function letterColumns(cliques: number[][], model: DecisionData, selected: boolean[]): number[][] {
  return cliques.filter((_,c) => selected[c]).map(q => [...q]);
}
export const methods: Strategy[] = [
  { name: "assignment_minimum", aliases: ["assignment_minimum", "assignment-minimum"],
    failurePrefix: "assignment-minimum MILP failed: ", countsAssignments: true,
    planner: buildAssignmentPlan, compiler: compileAssignmentPlan, builder: buildModel, coverage: assignmentCoverage, essentialDecisions: assignmentEssentialDecisions, decoder: selectedColumns },
  { name: "letter_minimum", aliases: ["letter_minimum", "letter-minimum"],
    failurePrefix: "letter-minimum MILP failed: ", countsAssignments: false,
    planner: buildLetterPlan, compiler: compileLetterPlan, builder: buildLetterModel, coverage: letterCoverage, essentialDecisions: letterEssentialDecisions, decoder: letterColumns },
];
