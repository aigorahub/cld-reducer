// The solver side of the page. It runs in a worker, so a long solve does not
// block the page, and the page can stop it: the page terminates the worker.

import { InvalidInputError, SolverError, loadSolver, reduceLetters,
         type CldReduction } from "../../js/src/index.js";
import type { MeanRow, PairRow } from "./csv.js";
import type { Method } from "./data.js";

export interface Input {
  pairs: PairRow[];
  means: MeanRow[] | null;
}

export type Request =
  | { type: "load"; wasm: Uint8Array }
  | { type: "run"; id: number; input: Input; methods: Method[] };

/** "input" and "solver" are the two error kinds of the package. */
export type ErrorKind = "input" | "solver" | "other";

export type Reply =
  | { type: "ready" }
  | { type: "start"; id: number; method: Method }
  | { type: "result"; id: number; method: Method; reduction: CldReduction; milliseconds: number }
  | { type: "done"; id: number }
  | { type: "error"; id: number | null; kind: ErrorKind; message: string };

/** Answer one request. A run solves its methods in order and stops at the first error. */
export async function handle(msg: Request, post: (reply: Reply) => void): Promise<void> {
  const id = msg.type === "load" ? null : msg.id;
  try {
    if (msg.type === "load") {
      await loadSolver({ wasmBinary: msg.wasm });
      post({ type: "ready" });
      return;
    }
    for (const method of msg.methods) {
      post({ type: "start", id: msg.id, method });
      const t0 = performance.now();
      const reduction = await reduceLetters(msg.input.pairs, { means: msg.input.means, method });
      post({ type: "result", id: msg.id, method, reduction, milliseconds: performance.now() - t0 });
    }
    post({ type: "done", id: msg.id });
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
