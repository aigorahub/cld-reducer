// Check the npm package without publishing it: `npm pack --dry-run` lists only the
// files that belong in the package, dist/index.d.ts declares the public API, and
// the packed tarball installs in an empty folder and reduces the simple example.
//
// Run from js/ after `npm run build`: node scripts/check-package.mjs
import { spawnSync } from "node:child_process";
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const npm = (args, cwd) => {
  const r = spawnSync("npm", args, { cwd, encoding: "utf8", shell: process.platform === "win32" });
  if (r.status !== 0) throw new Error(`npm ${args.join(" ")} failed:\n${r.stderr}`);
  return r.stdout;
};

const pack = JSON.parse(npm(["pack", "--dry-run", "--json"]))[0];
const files = pack.files.map((f) => f.path.replaceAll("\\", "/"));
const allowed = (p) => ["package.json", "README.md", "LICENSE"].includes(p) || /^dist\/[^/]+\.(js|d\.ts)$/.test(p);
const extra = files.filter((p) => !allowed(p));
if (extra.length) throw new Error(`unexpected files in the package: ${extra.join(", ")}`);
for (const need of ["package.json", "README.md", "LICENSE", "dist/index.js", "dist/index.d.ts"]) {
  if (!files.includes(need)) throw new Error(`missing from the package: ${need}`);
}
console.log(`package contents: ${files.length} files, only package.json, README.md, LICENSE, and dist/`);

const declarations = readFileSync("dist/index.d.ts", "utf8");
for (const name of ["reduceLetters", "reduceFromAdjacency", "loadSolver",
                    "CldReducerError", "InvalidInputError", "SolverError"]) {
  if (!new RegExp(`\\b${name}\\b`).test(declarations)) throw new Error(`dist/index.d.ts does not declare ${name}`);
}
console.log("dist/index.d.ts declares the functions and the three error classes");

const work = mkdtempSync(join(tmpdir(), "cld-reducer-pack-"));
const out = join(work, "pack");
mkdirSync(out);
const tarball = join(out, npm(["pack", "--pack-destination", out]).trim().split(/\r?\n/).pop());
const project = join(work, "clean");
mkdirSync(project);
writeFileSync(join(project, "package.json"), JSON.stringify({ name: "smoke", private: true, type: "module" }));
npm(["install", tarball], project);
writeFileSync(join(project, "example.mjs"), `
import { reduceFromAdjacency } from "cld-reducer";
const matrix = [[1,1,1,0,0],[1,1,1,1,0],[1,1,1,1,1],[0,1,1,1,1],[0,0,1,1,1]];
const means = new Map([["1", 3.73], ["2", 3.57], ["3", 3.46], ["4", 3.33], ["5", 3.3]]);
const result = await reduceFromAdjacency(matrix, { means });
console.log(JSON.stringify(result.letters));
`);
const run = spawnSync(process.execPath, ["example.mjs"], { cwd: project, encoding: "utf8" });
if (run.status !== 0) throw new Error(`the installed package failed:\n${run.stderr}`);
const expected = '{"1":"A","2":"AB","3":"AC","4":"BC","5":"C"}';
if (run.stdout.trim() !== expected) throw new Error(`unexpected display: ${run.stdout}`);
console.log(`clean install prints ${run.stdout.trim()}`);
