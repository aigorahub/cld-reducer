// The solver side of the page. It runs in a worker, so a long solve does not
// block the page, and the page can stop it: the page terminates the worker.

import { InvalidInputError, SolverError, loadSolver, reduceLetters,
         type CldReduction } from "../../js/src/index.js";
import type { MeanRow, PairRow } from "./csv.js";
import { SECOND_STAGE, type Method, type ResultMethod } from "./data.js";
import { seedAfter, simulate } from "./simulate.js";
import { beforeDisplay, stagedSolve, type Before } from "./staged.js";

export interface Input {
  pairs: PairRow[];
  means: MeanRow[] | null;
}

/**
 * One timed solve of a simulated instance. Null counts mean that it did not
 * finish within the time limit. A null time means that it did not run, because
 * its first stage did not finish.
 */
export interface Solve {
  letters: number | null;
  assignments: number | null;
  milliseconds: number | null;
}

/** All solves of one simulated experiment. */
export interface Instance {
  n: number;
  seed: number;
  lettersBefore: number;
  assignmentsBefore: number;
  edges: number;
  solves: Record<ResultMethod, Solve>;
}

export interface Study {
  sizes: number[];
  count: number;
  firstSeed: number;
  /** Seconds for each solve, as the timeLimit option of the package. */
  timeLimit: number;
}

export type Request =
  | { type: "load"; wasm: Uint8Array }
  | { type: "before"; id: number; input: Input }
  | { type: "run"; id: number; input: Input; methods: Method[]; staged: boolean }
  | { type: "study"; id: number; study: Study };

/** "input" and "solver" are the two error kinds of the package. */
export type ErrorKind = "input" | "solver" | "other";

export type Reply =
  | { type: "ready" }
  | { type: "before"; id: number; before: Before; milliseconds: number }
  | { type: "start"; id: number; method: ResultMethod; stage: 1 | 2 }
  | { type: "result"; id: number; method: ResultMethod; stage: 1 | 2; reduction: CldReduction; milliseconds: number }
  | { type: "instance"; id: number; instance: Instance }
  | { type: "done"; id: number }
  | { type: "error"; id: number | null; kind: ErrorKind; message: string };

const isTimeout = (e: unknown): boolean => e instanceof SolverError && e.message.endsWith("Time limit reached");

/**
 * One solve of the study with its whole time. The timeLimit option covers the solves; clique
 * enumeration and model construction come before it. Table X counts the whole time, so a solve
 * whose whole time passes the limit counts as not finished.
 */
export async function timed(solve: () => Promise<CldReduction> | CldReduction,
                            timeLimit: number): Promise<{ result: CldReduction | null; solve: Solve }> {
  const t0 = performance.now();
  try {
    const result = await solve();
    const milliseconds = performance.now() - t0;
    if (milliseconds > timeLimit * 1000) return { result: null, solve: { letters: null, assignments: null, milliseconds } };
    const s = result.stats;
    return { result, solve: { letters: s.numLettersAfter, assignments: s.assignmentsAfter, milliseconds } };
  } catch (e) {
    if (!isTimeout(e)) throw e;
    return { result: null, solve: { letters: null, assignments: null, milliseconds: performance.now() - t0 } };
  }
}

/** The four solves of one simulated experiment, each within the time limit. */
export async function studyInstance(n: number, seed: number, timeLimit: number): Promise<Instance> {
  const e = simulate(n, seed);
  const pairs: PairRow[] = [];
  for (let i = 0; i < n; i++) {
    for (let j = i + 1; j < n; j++) pairs.push({ group1: e.groups[i], group2: e.groups[j], significant: String(e.significant[i][j]) });
  }
  const means = e.groups.map((group, i) => ({ group, mean: e.means[i] }));
  const options = { means, timeLimit };
  const c = await timed(() => reduceLetters(pairs, { ...options, method: "letter_minimum" }), timeLimit);
  const sigma = await timed(() => reduceLetters(pairs, { ...options, method: "assignment_minimum" }), timeLimit);
  const missing = { result: null, solve: { letters: null, assignments: null, milliseconds: null } };
  const cs = c.result ? await timed(() => stagedSolve(pairs, means, "letter_then_assignment", c.result!.stats.objective,
                                                      timeLimit), timeLimit) : missing;
  const sc = sigma.result ? await timed(() => stagedSolve(pairs, means, "assignment_then_letter", sigma.result!.stats.objective,
                                                          timeLimit), timeLimit) : missing;
  const any = c.result ?? sigma.result;
  const before = beforeDisplay(pairs, means);
  return {
    n, seed, lettersBefore: before.letters, assignmentsBefore: before.assignments,
    edges: any ? any.stats.numEdges : pairs.filter((p) => p.significant === "false").length,
    solves: { letter_minimum: c.solve, assignment_minimum: sigma.solve,
              letter_then_assignment: cs.solve, assignment_then_letter: sc.solve },
  };
}

/** Answer one request. A run solves its methods in order and stops at the first error. */
export async function handle(msg: Request, post: (reply: Reply) => void): Promise<void> {
  const id = msg.type === "load" ? null : msg.id;
  try {
    if (msg.type === "load") {
      await loadSolver({ wasmBinary: msg.wasm });
      post({ type: "ready" });
    } else if (msg.type === "before") {
      const t0 = performance.now();
      const before = beforeDisplay(msg.input.pairs, msg.input.means);
      post({ type: "before", id: msg.id, before, milliseconds: performance.now() - t0 });
    } else if (msg.type === "run") {
      const { pairs, means } = msg.input;
      for (const method of msg.methods) {
        post({ type: "start", id: msg.id, method, stage: 1 });
        let t0 = performance.now();
        const first = await reduceLetters(pairs, { means, method });
        post({ type: "result", id: msg.id, method, stage: 1, reduction: first, milliseconds: performance.now() - t0 });
        if (!msg.staged) continue;
        const order = SECOND_STAGE[method];
        post({ type: "start", id: msg.id, method: order, stage: 2 });
        t0 = performance.now();
        const second = stagedSolve(pairs, means, order, first.stats.objective);
        post({ type: "result", id: msg.id, method: order, stage: 2, reduction: second, milliseconds: performance.now() - t0 });
      }
      post({ type: "done", id: msg.id });
    } else {
      const { sizes, count, firstSeed, timeLimit } = msg.study;
      for (const n of sizes) {
        for (let k = 0; k < count; k++) {
          post({ type: "instance", id: msg.id, instance: await studyInstance(n, seedAfter(firstSeed, k), timeLimit) });
        }
      }
      post({ type: "done", id: msg.id });
    }
  } catch (e) {
    const kind = e instanceof InvalidInputError ? "input" : e instanceof SolverError ? "solver" : "other";
    post({ type: "error", id, kind, message: e instanceof Error ? e.message : String(e) });
  }
}

// In a worker, answer requests in order.
declare const WorkerGlobalScope: unknown;
if (typeof WorkerGlobalScope !== "undefined") {
  const scope = globalThis as unknown as {
    onmessage: ((e: { data: Request }) => void) | null;
    postMessage: (reply: Reply) => void;
  };
  let queue = Promise.resolve();
  scope.onmessage = (e) => {
    queue = queue.then(() => handle(e.data, (r) => scope.postMessage(r)));
  };
}
