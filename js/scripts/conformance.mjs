// Run the shared conformance fixtures (conformance/README.md) against the built
// package, with presolve on and off. Plain Node.js, because a solve blocks the
// thread and a test runner's worker messages do not tolerate that.
//
// Run from js/ after `npm run build`: node scripts/conformance.mjs
import { cpSync, mkdtempSync, readFileSync, rmSync, symlinkSync, unlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import {
  InvalidInputError, SolverError, reduceFromAdjacency, reduceLetters,
} from "../dist/index.js";
import { makeLetterLabels } from "../dist/labels.js";
import { loadedSolver, settings } from "../dist/solver.js";
import { graphContext, methods } from "../dist/model.js";

const root = new URL("../../conformance/", import.meta.url);
const read = (path) => JSON.parse(readFileSync(new URL(path, root), "utf8"));
const cases = (kind) => read(`fixtures/${kind}.json`).cases;

const failures = [];
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

// Exercise the private certificate=false seam through the same public rendering
// path. Only this disposable copy changes the fourth internal engine argument.
const temporary = mkdtempSync(join(tmpdir(), "cld-certificate-reference-"));
process.on("exit", () => rmSync(temporary, {recursive:true, force:true}));
const referenceDist = join(temporary,"dist");
cpSync(new URL("../dist/",import.meta.url),referenceDist,{recursive:true});
writeFileSync(join(temporary,"package.json"),'{"type":"module"}\n');
unlinkSync(join(referenceDist,"solver.js"));
symlinkSync(fileURLToPath(new URL("../dist/solver.js",import.meta.url)),join(referenceDist,"solver.js"));
const reducePath = join(referenceDist,"reduce.js");
const source = readFileSync(reducePath,"utf8");
const invocation = "solveCanonical(model, timeLimit, strategy)";
if (source.split(invocation).length !== 2) throw new Error("reference engine call is missing or ambiguous");
writeFileSync(reducePath,source.replace(invocation,"solveCanonical(model, timeLimit, strategy, false)"));
const referenceApi = await import(pathToFileURL(join(referenceDist,"index.js")));
const referenceMethods = (await import(pathToFileURL(join(referenceDist,"model.js")))).methods;
function observeCanonical(registry) {
  const observation = {value:null};
  for (const strategy of registry) {
    const decoder = strategy.decoder;
    strategy.decoder = (cliques,model,selected) => {
      observation.value = {selected:[...selected],minimum:selected.reduce((sum,on,k)=>
        sum+(on?model.problem.cost[model.problem.decisionColumns[k]]:0),0)};
      return decoder(cliques,model,selected);
    };
  }
  return observation;
}
const candidateCanonical = observeCanonical(methods);
const referenceCanonical = observeCanonical(referenceMethods);

for (const c of cases("essential")) {
  const context=graphContext({adjacency:c.adjacency.map(row=>row.map(Boolean)),
    groups:c.adjacency.map((_,v)=>String(v)),means:null},c.cliques,c.weights);
  for (const [k,strategy] of methods.entries()) {
    const actual=strategy.essentialDecisions(strategy.builder(context));
    if (!same(actual,c[k===0?"essential_sigma":"essential_c"])) failures.push(`${c.id}: essential decisions differ for ${strategy.name}`);
  }
}
console.log(`essential scan: ${cases("essential").length} cases checked for both methods`);

/** Call the package the way the fixture says. */
function call(c, api = {reduceLetters,reduceFromAdjacency}) {
  const o = c.options;
  const options = {};
  // Historical sigma fixtures predate the C default. Keep their inputs frozen.
  if (!("method" in o) && c.expected?.method === "assignment_minimum") options.method = "assignment_minimum";
  if (c.input.means != null) options.means = c.input.means;
  for (const key of ["group1", "group2", "significant", "method"]) {
    if (key in o) options[key] = o[key];
  }
  if ("max_cliques" in o) options.maxCliques = o.max_cliques;
  if ("time_limit" in o) options.timeLimit = o.time_limit;
  if (c.call === "pairs") return api.reduceLetters(c.input.pairs, options);
  if (c.input.groups != null) options.groups = c.input.groups;
  return api.reduceFromAdjacency(c.input.adjacency, options);
}

async function differentialCall(c) {
  candidateCanonical.value = referenceCanonical.value = null;
  const actual = await call(c);
  const reference = await call(c,referenceApi);
  if (!same(actual,reference)) failures.push(`${c.id}: full public output differs from certificate=false`);
  if (!candidateCanonical.value || !referenceCanonical.value || !same(candidateCanonical.value,referenceCanonical.value)) {
    failures.push(`${c.id}: canonical vector or objective differs from certificate=false`);
  }
  return actual;
}

const percent = (p) => p.numerator / p.denominator * 100;

/** The pass rule of conformance/README.md for one reduce case. Returns the keys that differ. */
function mismatches(actual, expected) {
  const problems = [];
  for (const key of ["groups", "assignments", "letters", "stats", "solver_status", "objective"]) {
    if (!same(actual[key], expected[key])) problems.push(key);
  }
  if (actual.reduction_pct !== percent(expected.reduction_pct)) problems.push("reduction_pct");
  if (actual.method !== expected.method) problems.push("method");
  if (actual.relationship_preserved !== true) problems.push("relationship_preserved");
  return problems;
}

/** The fixture shape of a result. Object keys are compared per group, in `groups` order. */
function actualOf(r) {
  const s = r.stats;
  return {
    groups: r.groups,
    assignments: Object.fromEntries(r.groups.map((g) => [g, r.assignments[g]])),
    letters: Object.fromEntries(r.groups.map((g) => [g, r.letters[g]])),
    stats: {
      assignments_before: s.assignmentsBefore, assignments_after: s.assignmentsAfter,
      num_letters_before: s.numLettersBefore, num_letters_after: s.numLettersAfter,
      num_groups: s.numGroups, num_edges: s.numEdges,
    },
    solver_status: s.solverStatus,
    objective: s.objective,
    reduction_pct: s.reductionPct,
    method: r.method,
    relationship_preserved: r.relationshipPreserved,
  };
}

/** A fixture `expected` with its keys in `groups` order, so that JSON comparison is exact. */
function ordered(e) {
  return {
    ...e,
    assignments: Object.fromEntries(e.groups.map((g) => [g, e.assignments[g]])),
    letters: Object.fromEntries(e.groups.map((g) => [g, e.letters[g]])),
  };
}

const reduceCases = [...cases("reduce"), ...cases("reduce_letter_minimum"), ...cases("reduce_weighted")];

// The checker must reject the three wrong wheat results and accept the right one.
{
  const wheat = reduceCases.find((c) => c.id === "hand/wheat");
  const expected = ordered(wheat.expected);
  const asActual = (bad) => ({ ...ordered(bad), reduction_pct: percent(bad.reduction_pct) });
  if (mismatches(asActual(wheat.expected), expected).length !== 0) {
    throw new Error("the conformance checker rejects the expected wheat result");
  }
  const wrong = [wheat.non_canonical, ...read("fixtures/checker.json").bad.map((b) => b.result)];
  if (wrong.some((bad) => mismatches(asActual(bad), expected).length === 0)) {
    throw new Error("the conformance checker accepts a wrong result");
  }
  for (const bad of read("fixtures/checker.json").letter_bad) {
    const matching = ordered(reduceCases.find(c => c.id === bad.case).expected);
    if (mismatches(asActual(matching), matching).length || !mismatches(asActual(bad.result), matching).length) {
      throw new Error(`C checker failed: ${bad.case} ${bad.name}`);
    }
  }
}

const counts = {};
const count = (k) => { counts[k] = (counts[k] ?? 0) + 1; };

for (const presolve of ["on", "off"]) {
  settings.presolve = presolve;
  for (const c of reduceCases) {
    try {
      const actual = actualOf(await differentialCall(c));
      const bad = mismatches(actual, ordered(c.expected));
      if (bad.length) failures.push(`${c.id} (presolve ${presolve}): differs in ${bad.join(", ")}`);
      if (c.sigma_expected) {
        const sigma = {...c, options:{...c.options,method:"assignment_minimum"}};
        const badSigma = mismatches(actualOf(await differentialCall(sigma)), ordered(c.sigma_expected));
        if (badSigma.length) failures.push(`${c.id} sigma: differs in ${badSigma.join(", ")}`);
      }
    } catch (e) {
      failures.push(`${c.id} (presolve ${presolve}): threw ${e}`);
    }
    count(`reduce (presolve ${presolve})`);
  }
}
settings.presolve = "on";

const kinds = { invalid_input: InvalidInputError, solver: SolverError };
for (const c of cases("errors")) {
  try {
    await call(c);
    failures.push(`${c.id}: no error`);
  } catch (e) {
    const want = c.expected;
    if (!(e instanceof kinds[want.kind])) failures.push(`${c.id}: ${e?.name}: ${e?.message}`);
    else if (!e.message.startsWith(want.message_prefix)) failures.push(`${c.id}: message ${e.message}`);
  }
  count("errors");
}

for (const c of cases("labels")) {
  if (!same(makeLetterLabels(c.count), c.labels)) failures.push(`labels ${c.id}`);
  count("labels");
}

const v = loadedSolver().version;
console.log(`highs ${v.string}`);
for (const [k, n] of Object.entries(counts)) console.log(`${k}: ${n} cases`);
if (failures.length) {
  console.log(`${failures.length} failures`);
  console.log(failures.slice(0, 50).join("\n"));
  process.exit(1);
}
console.log("all conformance fixtures pass");
console.log("full public outputs and canonical vectors match certificate=false with presolve on and off");
