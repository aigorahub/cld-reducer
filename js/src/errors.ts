// The two error kinds of docs/algorithm.md section 10.

/** Base class of every error that cld-reducer throws on purpose. */
export class CldReducerError extends Error {
  constructor(message: string) {
    super(message);
    this.name = new.target.name;
  }
}

/** The input data is malformed or inconsistent. */
export class InvalidInputError extends CldReducerError {}

/** The optimization model cannot be solved, or a control value is invalid. */
export class SolverError extends CldReducerError {}
