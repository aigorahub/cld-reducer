// Reduce compact letter displays while preserving pairwise statistical
// relationships. JavaScript port of the cld-reducer R and Python packages; see
// docs/algorithm.md in https://github.com/aigorahub/cld-reducer for the specification.

export { reduceLetters, reduceFromAdjacency, type CldReduction, type CldStats } from "./reduce.js";
export { loadSolver, type LoadOptions } from "./solver.js";
export { CldReducerError, InvalidInputError, SolverError } from "./errors.js";
export type { ReduceOptions, Means } from "./input.js";
