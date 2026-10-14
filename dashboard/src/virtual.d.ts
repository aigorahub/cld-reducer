// Modules that build.mjs makes at build time.

declare module "virtual:highs-wasm" {
  /** highs.wasm, gzip-compressed and base64-encoded. */
  const base64: string;
  export default base64;
}

declare module "virtual:worker-source" {
  /** The bundled worker (src/worker.ts) as source text. */
  const source: string;
  export default source;
}

declare module "virtual:repository" {
  const repository: {
    /** The version in js/package.json. */
    version: string;
    /** The text of each example file in conformance/data, by file name. */
    examples: Record<string, string>;
  };
  export default repository;
}
