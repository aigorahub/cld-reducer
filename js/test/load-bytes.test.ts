// loadSolver with the bytes of highs.wasm (see load.test.ts).

import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { expect, it } from "vitest";
import { loadSolver, reduceFromAdjacency } from "../src/index.js";
import { SIMPLE, SIMPLE_LETTERS } from "./helpers.js";

const require = createRequire(import.meta.url);

it("loads from the bytes of highs.wasm and does not read the file", async () => {
  const bytes = readFileSync(require.resolve("highs/runtime"));
  await loadSolver({ wasmBinary: new Uint8Array(bytes), locateFile: () => "/nonexistent/highs.wasm" });
  const result = await reduceFromAdjacency(SIMPLE);
  expect(result.letters).toEqual(SIMPLE_LETTERS);
});
