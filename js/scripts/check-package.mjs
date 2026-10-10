// Build one npm tarball, inspect its file list, then install and compile a consumer.
// An optional destination keeps those same bytes for the publication workflow.
//
// Run from js/ after `npm run build`: node scripts/check-package.mjs
import { spawnSync } from "node:child_process";
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const npm = (args, cwd) => {
  const r = spawnSync("npm", args, { cwd, encoding: "utf8", shell: process.platform === "win32" });
  if (r.status !== 0) throw new Error(`npm ${args.join(" ")} failed:\n${r.stderr}`);
  return r.stdout;
};

const work = mkdtempSync(join(tmpdir(), "cld-reducer-pack-"));
const out = process.argv[2] ? resolve(process.argv[2]) : join(work, "pack");
mkdirSync(out, { recursive: true });
const pack = JSON.parse(npm(["pack", "--json", "--pack-destination", out]))[0];
const tarball = join(out, pack.filename);
const files = pack.files.map((f) => f.path.replaceAll("\\", "/"));
const allowed = (p) => ["package.json", "README.md", "LICENSE", "NOTICE"].includes(p) || /^dist\/[^/]+\.(js|d\.ts)$/.test(p);
const extra = files.filter((p) => !allowed(p));
if (extra.length) throw new Error(`unexpected files in the package: ${extra.join(", ")}`);
for (const need of ["package.json", "README.md", "LICENSE", "NOTICE", "dist/index.js", "dist/index.d.ts"]) {
  if (!files.includes(need)) throw new Error(`missing from the package: ${need}`);
}
console.log(`package contents: ${files.length} files, only package.json, README.md, LICENSE, NOTICE, and dist/`);

const declarations = readFileSync("dist/index.d.ts", "utf8");
for (const name of ["reduceLetters", "reduceFromAdjacency", "loadSolver",
                    "CldReducerError", "InvalidInputError", "SolverError"]) {
  if (!new RegExp(`\\b${name}\\b`).test(declarations)) throw new Error(`dist/index.d.ts does not declare ${name}`);
}
console.log("dist/index.d.ts declares the functions and the three error classes");

const project = join(work, "clean");
mkdirSync(project);
writeFileSync(join(project, "package.json"), JSON.stringify({ name: "smoke", private: true, type: "module" }));
npm(["install", tarball], project);
writeFileSync(join(project, "example.mjs"), `
import { reduceFromAdjacency } from "cld-reducer";
const matrix = [[1,1,1,0,0],[1,1,1,1,0],[1,1,1,1,1],[0,1,1,1,1],[0,0,1,1,1]];
const means = new Map([["1", 3.73], ["2", 3.57], ["3", 3.46], ["4", 3.33], ["5", 3.3]]);
const result = await reduceFromAdjacency(matrix, { means });
const c = await reduceFromAdjacency(matrix, {means, method:"letter-minimum"});
if (c.method !== "letter_minimum" || c.stats.objective !== 3 || c.stats.assignmentsAfter !== 9 || c.letters["3"] !== "ABC") throw new Error("installed C behavior differs");
console.log(JSON.stringify(result.letters));
`);
const run = spawnSync(process.execPath, ["example.mjs"], { cwd: project, encoding: "utf8" });
if (run.status !== 0) throw new Error(`the installed package failed:\n${run.stderr}`);
const expected = '{"1":"A","2":"AB","3":"AC","4":"BC","5":"C"}';
if (run.stdout.trim() !== expected) throw new Error(`unexpected display: ${run.stdout}`);
console.log(`clean install prints ${run.stdout.trim()}`);

// Compile against declarations resolved from the installed tarball.
writeFileSync(join(project, "consumer.ts"), `
import { reduceLetters, reduceFromAdjacency, loadSolver,
  CldReducerError, InvalidInputError, SolverError,
  type CldReduction, type CldStats, type LoadOptions,
  type ReduceOptions, type Means } from "cld-reducer";
const options: ReduceOptions = {method: "letter_minimum"};
const runtimeString: ReduceOptions = {method: "unsupported-for-runtime-validation"};
void runtimeString;
const means: Means = new Map([["a", 1]]);
const loading: LoadOptions = {};
const solver = loadSolver(loading);
const reduction: Promise<CldReduction> = reduceFromAdjacency([[true]], { ...options, means });
void reduceLetters([{ group1: "a", group2: "b", significant: false }]);
void reduction.then((result) => { const stats: CldStats = result.stats; return stats; });
void [solver, CldReducerError, InvalidInputError, SolverError];
`);
const compiler = new URL("../node_modules/typescript/bin/tsc", import.meta.url);
const typed = spawnSync(process.execPath, [fileURLToPath(compiler), "--noEmit", "--strict",
  "--module", "NodeNext", "--moduleResolution", "NodeNext", "--target", "ES2022", "consumer.ts"],
  { cwd: project, encoding: "utf8" });
if (typed.status !== 0) throw new Error(`installed declarations failed:\n${typed.stdout}\n${typed.stderr}`);
console.log("installed TypeScript consumer compiles");
