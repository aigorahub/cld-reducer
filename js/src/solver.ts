// HiGHS through the npm package `highs` (WebAssembly), with the settings of
// docs/algorithm.md section 6.

import highsImport from "highs";
import type { Highs, InitOptions } from "highs";

type Loader = (options?: InitOptions) => Promise<Highs>;
// `highs` ships an ES module at run time, but TypeScript reads its types as
// CommonJS under NodeNext, so take the loader from either shape.
const highsLoader: Loader = ((highsImport as unknown as { default?: Loader }).default ??
  highsImport) as unknown as Loader;

export interface LoadOptions {
  locateFile?: (file: string, prefix: string) => string;
  /** The bytes of highs.wasm, so that nothing is fetched. */
  wasmBinary?: ArrayBuffer | Uint8Array;
  /** highs.wasm, already compiled. Takes precedence over `wasmBinary`. */
  wasmModule?: WebAssembly.Module;
}

let loading: Promise<Highs> | null = null;
let loadedOptions: LoadOptions | undefined;
let highs: Highs | null = null;

/**
 * Load the WebAssembly solver. Later calls reuse it; concurrent first calls
 * share one load; a failed load is not cached. Calling it again with other
 * options after a successful load throws.
 */
export async function loadSolver(options?: LoadOptions): Promise<void> {
  await getSolver(options);
}

export async function getSolver(options?: LoadOptions): Promise<Highs> {
  if (loading) {
    if (options !== undefined && !sameOptions(options, loadedOptions)) {
      throw new Error("cld-reducer: the solver is already loaded with other options.");
    }
    return loading;
  }
  loadedOptions = options;
  const promise = loadHighs(options);
  loading = promise;
  try {
    highs = await promise;
    return highs;
  } catch (e) {
    if (loading === promise) {
      loading = null;
      loadedOptions = undefined;
    }
    throw e;
  }
}

function sameOptions(a: LoadOptions, b: LoadOptions | undefined): boolean {
  return a.locateFile === b?.locateFile && a.wasmBinary === b?.wasmBinary &&
    a.wasmModule === b?.wasmModule;
}

// highs 1.15.3 lists wasmBinary and wasmModule in its types, but its loader
// ignores them and still reads highs.wasm from disk or the network. Its
// instantiateWasm hook works, so supply the binary through that hook.
function loadHighs(options: LoadOptions | undefined): Promise<Highs> {
  const wasm = options?.wasmModule ?? options?.wasmBinary;
  if (wasm === undefined) return highsLoader(options as InitOptions | undefined);
  let fail!: (reason: unknown) => void;
  const failed = new Promise<never>((_, reject) => { fail = reject; });
  const init = {
    // Without locateFile the loader resolves highs.wasm against import.meta.url,
    // which fails in a bundle that has no URL of its own.
    locateFile: options?.locateFile ?? ((file: string) => file),
    instantiateWasm(imports: WebAssembly.Imports,
                    done: (instance: WebAssembly.Instance) => void): object {
      const ready = wasm instanceof WebAssembly.Module
        ? WebAssembly.instantiate(wasm, imports)
        : WebAssembly.instantiate(wasm as BufferSource, imports).then((r) => r.instance);
      // done() can throw too, for a valid module that is not highs.wasm.
      ready.then(done).catch(fail);
      return {};
    },
  };
  // The loader never settles if instantiation fails, so race it with the failure.
  return Promise.race([highsLoader(init as unknown as InitOptions), failed]);
}

/** The loaded solver, for code that runs after getSolver(). */
export function loadedSolver(): Highs {
  if (!highs) throw new Error("cld-reducer: the solver is not loaded.");
  return highs;
}

// Presolve is the one named difference from R. Tests switch it off to run the
// conformance suite a second time.
export const settings = { presolve: "on" as "on" | "off" };
// Options of the most recent solve, read back from HiGHS. Tests check them.
export const lastOptions: Record<string, unknown> = {};
const OPTION_NAMES = [
  "presolve", "mip_rel_gap", "mip_abs_gap", "primal_feasibility_tolerance",
  "mip_feasibility_tolerance", "time_limit",
] as const;

export type Status = "optimal" | "infeasible" | "time_limit" | "failed";

/** The model of docs/algorithm.md section 4, row-wise. `decisionColumns` supplies ordered objective support. */
export interface Problem {
  numCols: number;
  decisionColumns: number[];
  cost: Float64Array;
  starts: Int32Array;
  indices: Int32Array;
  values: Float64Array;
  rowLower: Float64Array;
  rowUpper: Float64Array;
}

/** What one solve returned: a status, the HiGHS status text, and the column values. */
export interface Outcome {
  status: Status;
  text: string;
  values?: Float64Array;
  objective?: number;
}

const STATUS_TEXT: Record<string, string> = {
  notSet: "Not Set", loadError: "Load error", modelError: "Model error",
  presolveError: "Presolve error", solveError: "Solve error", postsolveError: "Postsolve error",
  empty: "Empty", optimal: "Optimal", infeasible: "Infeasible",
  unboundedOrInfeasible: "Primal infeasible or unbounded", unbounded: "Unbounded",
  objectiveBound: "Bound on objective reached", objectiveTarget: "Target for objective reached",
  timeLimit: "Time limit reached", iterationLimit: "Iteration limit reached", unknown: "Unknown",
  solutionLimit: "Solution limit reached", interrupted: "Interrupted",
};

/**
 * Solve the model with the given column bounds. `sumLimit` adds the row
 * weighted decision cost <= sumLimit; `timeLimit` is the HiGHS time limit in seconds.
 */
export function run(
  problem: Problem, colLower: Float64Array, colUpper: Float64Array,
  sumLimit: number | null, timeLimit: number | null,
): Outcome {
  const h = loadedSolver();
  let { starts, indices, values, rowLower, rowUpper } = problem;
  if (sumLimit !== null) {
    const start = starts[starts.length - 1];
    starts = Int32Array.from([...starts, start + problem.decisionColumns.length]);
    indices = Int32Array.from([...indices, ...problem.decisionColumns]);
    values = Float64Array.from([...values, ...problem.decisionColumns.map(k => problem.cost[k])]);
    rowLower = Float64Array.from([...rowLower, -h.infinity]);
    rowUpper = Float64Array.from([...rowUpper, sumLimit]);
  }
  const integrality = new Int32Array(problem.numCols).fill(h.constants.variableType.integer);
  const model = h.createModel();
  try {
    model.passModel({
      numCols: problem.numCols,
      numRows: rowLower.length,
      sense: h.constants.objectiveSense.minimize,
      colCost: problem.cost,
      colLower,
      colUpper,
      rowLower,
      rowUpper,
      matrix: { format: "csr", numRows: rowLower.length, numCols: problem.numCols,
                starts, indices, values },
      integrality: integrality as unknown as Int32Array,
    });
    // The WebAssembly build is single-threaded and rejects thread options.
    const options: Record<string, number | string | boolean> = {
      output_flag: false,
      presolve: settings.presolve,
      mip_rel_gap: 0,
      mip_abs_gap: 0,
      primal_feasibility_tolerance: 1e-9,
      mip_feasibility_tolerance: 1e-9,
    };
    if (timeLimit !== null) options.time_limit = timeLimit;
    model.options.set(options);
    const code = model.run().modelStatus;
    for (const name of OPTION_NAMES) lastOptions[name] = model.options.get(name);

    const status = h.constants.modelStatus;
    const name = Object.keys(status).find((k) => (status as Record<string, number>)[k] === code);
    const text = STATUS_TEXT[name ?? "unknown"] ?? String(name);
    if (code === status.optimal) {
      return {
        status: "optimal", text,
        values: Float64Array.from(model.getSolution().colValue),
        objective: Number(model.info.get("objective_function_value")),
      };
    }
    // No model here is unbounded, so "unbounded or infeasible" means infeasible.
    if (code === status.infeasible || code === status.unboundedOrInfeasible) {
      return { status: "infeasible", text };
    }
    if (code === status.timeLimit) return { status: "time_limit", text };
    return { status: "failed", text };
  } finally {
    model.dispose();
  }
}

// Tests replace `hooks.run` to reach the failure paths of docs/algorithm.md section 6.
export const hooks = { run };
