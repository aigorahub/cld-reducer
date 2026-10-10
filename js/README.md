# cld-reducer for JavaScript

Reduce compact letter displays (CLDs) while preserving the pairwise statistical relationships they encode. This is the JavaScript and TypeScript package of the [cld-reducer repository](https://github.com/aigorahub/cld-reducer), which also holds an R package and a Python package. All three solve the assignment-minimum clique covering of Ennis, Fayle, and Ennis (2012), <https://doi.org/10.1145/2133803.2275596>, as a mixed-integer program with [HiGHS](https://highs.dev), and they return the same display for the same input. The rules they follow are in `docs/algorithm.md` in the repository.

The solver is HiGHS compiled to WebAssembly (the npm package [`highs`](https://www.npmjs.com/package/highs)). The only runtime dependency is `highs`. ESM only, Node.js 22 or later, TypeScript declarations included.

## Installation

The npm project lookup returned 404 on 2026-10-09. After publication:

```sh
npm install cld-reducer
```

Until then, build it from a clone of the repository and install the tarball:

```sh
cd js
npm ci
npm pack
npm install ./cld-reducer-0.2.0.tgz   # in your own project
```

## Usage

```js
import { reduceLetters } from "cld-reducer";

const labels = ["1", "2", "3", "4", "5"];
const notSignificant = new Set(["1,2", "1,3", "2,3", "2,4", "3,4", "3,5", "4,5"]);
const pairs = [];
for (let i = 0; i < labels.length; i++) {
  for (let j = i + 1; j < labels.length; j++) {
    pairs.push({ group1: labels[i], group2: labels[j], significant: !notSignificant.has(`${labels[i]},${labels[j]}`) });
  }
}
const means = new Map([["1", 3.73], ["2", 3.57], ["3", 3.46], ["4", 3.33], ["5", 3.3]]);

const result = await reduceLetters(pairs, { means });
console.log(result.letters);
// { '1': 'A', '2': 'AB', '3': 'AC', '4': 'BC', '5': 'C' }
console.log(result.stats);
// {
//   assignmentsBefore: 9,
//   assignmentsAfter: 8,
//   reductionPct: 11.11111111111111,
//   numLettersBefore: 3,
//   numLettersAfter: 3,
//   numGroups: 5,
//   numEdges: 7,
//   solverStatus: 'Optimal',
//   objective: 8
// }
```

Group 3 would be `ABC` in the standard maximal display; the reduced display drops the `B` and still preserves every relationship.

If you already have the non-significance matrix, use `reduceFromAdjacency`. `adjacency[i][j]` true (or 1) means groups `i` and `j` are not significantly different and must share a letter:

```js
import { reduceFromAdjacency } from "cld-reducer";

const result = await reduceFromAdjacency(
  [[1, 1, 0], [1, 1, 1], [0, 1, 1]],
  { groups: ["low", "mid", "high"] },
);
console.log(result.letters);
// { low: 'A', mid: 'AB', high: 'B' }
```

## API

```ts
reduceLetters(pairs, options?): Promise<CldReduction>
reduceFromAdjacency(adjacency, options?): Promise<CldReduction>
loadSolver(options?): Promise<void>
```

**`pairs`** is an array of row objects with the keys `group1`, `group2`, and `significant` (other keys are ignored; the option names below change the key names). `significant` can be a boolean, the number 0 or 1, or a string such as `"yes"`, `"no"`, `"ns"`, `"significant"`. Every unordered pair of groups needs exactly one row. Labels are converted to strings.

**Options**

| Option | Meaning |
|---|---|
| `means` | A `Map` from group label to mean, or an array of `{ group, mean }`. The means set the letter order (higher means first). For `reduceLetters`, the order of the means is also the group order; without means it is the order of first appearance. A plain object is rejected, because JavaScript puts integer-like keys first and the group order decides ties. Every mean must be a finite number. |
| `groups` | Labels for the rows of an adjacency matrix (default `"1"` to `"n"`). |
| `group1`, `group2`, `significant` | Key names in the pairwise rows. |
| `method` | `"assignment_minimum"` (the only method; `"assignment-minimum"` is accepted too). |
| `timeLimit` | One time budget in seconds for all solves of the call. |
| `maxCliques` | Cap on maximal cliques, 10000 by default; `null` removes the cap. |

**Result** (`CldReduction`): `letters` and `assignments` (objects keyed by group label), `groups` (the order), `rows` (one `{ group, letters, assignments }` per group, in order, with the tokens joined by spaces), `stats`, `method`, `relationshipPreserved`, and `adjacency`. Use `groups` or `rows` for the order, because JavaScript objects list integer-like keys first. `letters` joins one character tokens without a separator and longer tokens (after `Z`: `AA`, `AB`, and so on) with single spaces; `assignments` is the safe machine form. `stats.reductionPct` is not rounded.

**Errors** are `InvalidInputError` (malformed input) and `SolverError` (solver failures, an invalid `timeLimit` or `maxCliques`, or too many cliques), both subclasses of `CldReducerError`. The message prefixes are the ones listed in `docs/algorithm.md`.

When several optimal displays exist, the one returned is the lexicographically greatest membership vector in canonical order (`docs/algorithm.md` section 5), so R, Python, and JavaScript agree on tied inputs.

## The solve blocks the thread

The solve is synchronous inside the returned promise and blocks the JavaScript thread until it finishes. Typical inputs take milliseconds, but a large display can take longer. Run big inputs in a worker thread (Node.js `worker_threads` or a Web Worker), and use `timeLimit` to bound the time.

## Loading the WebAssembly solver

The first call loads the solver; later calls reuse it. Concurrent first calls share one load, and a failed load is not cached. `loadSolver` is optional: call it to load early or to control where `highs.wasm` comes from.

```js
import { loadSolver } from "cld-reducer";

// In a browser or a bundle: say where highs.wasm is served from ...
await loadSolver({ locateFile: (file) => `/assets/${file}` });
// ... or pass the bytes (an ArrayBuffer or Uint8Array), or a compiled WebAssembly.Module.
// With wasmBinary or wasmModule, nothing is read from disk or fetched.
await loadSolver({ wasmBinary: bytes });
```

Calling `loadSolver` again with different options after a successful load throws.

## Differences from the R and Python packages

- The functions are asynchronous and return promises.
- Names are camelCase (`reductionPct`, `timeLimit`), and the options are in one object.
- Means are a `Map` or an array, never a plain object.
- HiGHS presolve is on, as in Python. The R package turns it off because the CRAN `highs` package bundles HiGHS 1.14. The WebAssembly build is single-threaded, so no thread option is set.

## Development

```sh
cd js
npm ci
npm run typecheck
npm run build
npm test
npm run test:conformance   # runs every fixture in ../conformance with presolve on and off
```

## License

MIT. See `LICENSE`.

## Release checks

`npm run check:package` builds one tarball, checks its file list, installs it in
an empty project, runs the WASM solver, and compiles a TypeScript consumer against
its installed declarations. The release workflow retains that exact tarball.
See `docs/releasing.md` in the repository for release steps. `NOTICE` records the
example data sources and the maintainer approval recorded on 2026-10-10.
