// Maximal cliques in the canonical order of docs/algorithm.md section 3.

import { SolverError } from "./errors.js";

/**
 * All maximal cliques of the graph, each as ascending group indices, sorted
 * lexicographically. Bron-Kerbosch with pivoting, without recursion. With
 * `maxCliques` set, throws a SolverError as soon as more cliques are found.
 */
export function maximalCliques(
  adjacency: ReadonlyArray<ReadonlyArray<boolean>>,
  maxCliques: number | null,
): number[][] {
  const size = adjacency.length;
  const neighbors: Set<number>[] = adjacency.map((row, i) => {
    const set = new Set<number>();
    row.forEach((connected, j) => { if (connected && j !== i) set.add(j); });
    return set;
  });
  const found: number[][] = [];

  const pivotCandidates = (p: Set<number>, x: Set<number>): number[] => {
    let best = -1;
    let bestCount = -1;
    for (const u of [...p, ...x]) {
      let count = 0;
      for (const v of p) if (neighbors[u].has(v)) count++;
      if (count > bestCount) { best = u; bestCount = count; }
    }
    return [...p].filter((v) => !neighbors[best].has(v)).sort((a, b) => a - b);
  };
  const intersect = (a: Set<number>, b: Set<number>): Set<number> => {
    const out = new Set<number>();
    for (const v of a) if (b.has(v)) out.add(v);
    return out;
  };

  const everyone = new Set<number>(Array.from({ length: size }, (_, i) => i));
  // Each frame: clique so far, candidates p, excluded x, vertices to branch on, next index.
  const frames: { r: number[]; p: Set<number>; x: Set<number>; branch: number[]; next: number }[] =
    [{ r: [], p: everyone, x: new Set(), branch: pivotCandidates(everyone, new Set()), next: 0 }];
  while (frames.length > 0) {
    const frame = frames[frames.length - 1];
    if (frame.next >= frame.branch.length) { frames.pop(); continue; }
    const v = frame.branch[frame.next++];
    const childR = [...frame.r, v];
    const childP = intersect(frame.p, neighbors[v]);
    const childX = intersect(frame.x, neighbors[v]);
    frame.p.delete(v);
    frame.x.add(v);
    if (childP.size === 0 && childX.size === 0) {
      found.push(childR.sort((a, b) => a - b));
      if (maxCliques !== null && found.length > maxCliques) {
        throw new SolverError(
          `maximal clique enumeration exceeded max_cliques=${maxCliques}; ` +
          "increase maxCliques or pass null to disable the cap");
      }
    } else if (childP.size > 0) {
      frames.push({ r: childR, p: childP, x: childX, branch: pivotCandidates(childP, childX), next: 0 });
    }
  }
  return found.sort(compareLists);
}

function compareLists(a: number[], b: number[]): number {
  const n = Math.min(a.length, b.length);
  for (let i = 0; i < n; i++) if (a[i] !== b[i]) return a[i] - b[i];
  return a.length - b.length;
}
