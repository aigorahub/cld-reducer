#!/usr/bin/env node
// Full correctness check, not acceptance timing. Uses all graph fixtures, both
// presolve modes, both API routes, means and labels. Run after building js/dist:
// node benchmarks/js_driver_conformance.mjs [--repo ABSOLUTE_PATH]
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { Driver } from './js_driver.mjs';

const args = process.argv.slice(2);
assert.ok(args.length === 0 || args.length === 2 && args[0] === '--repo');
const repo = args[1] ?? resolve(dirname(fileURLToPath(import.meta.url)), '..');
const cases = (await Promise.all(['reduce', 'reduce_letter_minimum', 'reduce_weighted'].map(async name =>
  JSON.parse(await readFile(join(repo, 'conformance/fixtures', `${name}.json`), 'utf8')).cases))).flat()
  .flatMap(c => c.sigma_expected ? [c, { ...c, id: `${c.id}/sigma`,
    options: { ...c.options, method: 'assignment_minimum' }, expected: c.sigma_expected }] : [c]);
let checked = 0;
for (const presolve of ['on', 'off']) {
  const driver = new Driver(repo, presolve);
  try {
    for (const c of cases) {
      const expected = c.expected;
      const prepared = { ...c, options: { method: expected.method, ...c.options } };
      const actual = await driver.handle({ action: 'capture', case: prepared });
      assert.equal(actual.ok, true, `${c.id}: ${JSON.stringify(actual)}`);
      const assignments = expected.groups.map(g => expected.assignments[g]);
      const fullExpected = {
        groups: expected.groups,
        assignments,
        letters: expected.groups.map(g => expected.letters[g]),
        adjacency: assignments.map(left => assignments.map(right => left.some(token => right.includes(token)))),
        method: expected.method,
        relationship_preserved: expected.relationship_preserved,
        stats: { ...expected.stats, objective: expected.objective, solver_status: expected.solver_status,
          reduction_pct: expected.reduction_pct.numerator / expected.reduction_pct.denominator * 100 },
        rows: expected.groups.map(g => ({ group: g, letters: expected.letters[g], assignments: expected.assignments[g].join(' ') })),
      };
      assert.deepEqual(actual.result, fullExpected, `${c.id}, presolve ${presolve}`);
      assert.equal(actual.canonical.objective, expected.objective, c.id);
      assert.ok(actual.canonical.selected.every(value => value === 0 || value === 1), c.id);
      // A separate enumeration checks lexicographic maximality of decision
      // vectors on every small graph, independent of solver outcomes.
      if (expected.groups.length <= 4) {
        const prep = await driver.handle({ action: 'preprocess', case: prepared });
        assert.equal(prep.ok, true, c.id);
        assert.equal(actual.canonical.selected.length, prep.metrics.decision_variables, c.id);
        const runtime = driver.runtime;
        const options = { method: expected.method, groups: c.input.groups, means: c.input.means };
        const graph = c.call === 'pairs' ? runtime.input.pairsToGraph(c.input.pairs, { ...options, ...c.options })
          : runtime.input.adjacencyToGraph(c.input.adjacency, options);
        const reduced = runtime.reduction.reduceGraphVertices(graph.adjacency);
        const cliques = runtime.cliques.maximalCliques(reduced.adjacency, 10000);
        const strategy = runtime.input.checkMethod(expected.method);
        const model = strategy.builder(runtime.model.graphContext({ adjacency: reduced.adjacency,
          groups: reduced.classes.map(group => graph.groups[group[0]]), means: null }, cliques, reduced.weights));
        const count = model.problem.decisionColumns.length;
        let best = null;
        let bestCost = Infinity;
        for (let code = 0; code < 2 ** count; code++) {
          const vector = Array.from({ length: count }, (_, k) => Boolean(code & 2 ** (count - k - 1)));
          if (!strategy.coverage(model, vector)) continue;
          const cost = vector.reduce((sum, on, k) => sum + (on ? model.problem.cost[model.problem.decisionColumns[k]] : 0), 0);
          if (cost <= bestCost) { bestCost = cost; best = vector.map(Number); }
        }
        assert.deepEqual(actual.canonical, { selected: best, objective: bestCost }, c.id);
      }
      checked++;
    }
  } finally { await driver.close(); }
  process.stdout.write(`presolve ${presolve}: ${cases.length} fixture captures passed\n`);
}
process.stdout.write(`${checked} complete result and canonical captures passed\n`);
