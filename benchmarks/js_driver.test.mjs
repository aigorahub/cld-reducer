// Run after npm ci && npm run build in js/:
// node --test benchmarks/js_driver.test.mjs
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { readFile, readdir, stat } from 'node:fs/promises';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import { Driver, prepareCase, profileSource } from './js_driver.mjs';

const repo = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const fixture = async name => JSON.parse(await readFile(join(repo, 'conformance', 'fixtures', `${name}.json`), 'utf8')).cases;
const abc = method => ({ id: 'abc', call: 'adjacency', options: { method },
  input: { adjacency: [[1, 1, 0], [1, 1, 1], [0, 1, 1]], groups: ['', '__proto__', '2'] } });
const multipartite = (parts, method = 'letter_minimum') => ({ id: `multipartite-${parts}`, call: 'adjacency',
  options: { method }, input: { adjacency: Array.from({ length: 3 * parts }, (_, i) =>
    Array.from({ length: 3 * parts }, (_, j) => i === j || Math.floor(i / 3) !== Math.floor(j / 3))) } });
const check = response => { assert.equal(response.ok, true, JSON.stringify(response)); return response; };
const call = (driver, action, c = abc('assignment_minimum')) => driver.handle({ action, case: c, iterations: 1 });

function hookState(runtime) {
  return { run: runtime.solver.hooks.run, create: runtime.solver.loadedSolver().createModel,
    strategy: runtime.model.methods.map(s => [s.builder, s.essentialDecisions, s.decoder]) };
}

test('version loads without solving; first measure is first solve', async () => {
  const driver = new Driver(repo);
  const solver = await import('../js/dist/solver.js');
  const original = solver.hooks.run;
  let solves = 0;
  solver.hooks.run = (...args) => { solves++; return original(...args); };
  try {
    const version = check(await driver.handle({ action: 'version' }));
    assert.equal(solves, 0);
    assert.equal(version.language, 'javascript');
    assert.ok(version.module_load_ns > 0);
    assert.ok(version.solver_load_ns > 0);
    assert.equal(typeof version.dependencies.highs, 'string');
    assert.equal(version.settings.presolve, 'on');
    assert.equal(check(await call(driver, 'measure')).iterations, 1);
    assert.equal(solves, 1);
    assert.equal(driver.profileRuntime, null);
  } finally { solver.hooks.run = original; await driver.close(); }
});

test('measure times only complete public calls and normalizes after the timer stops', async () => {
  const driver = new Driver(repo);
  const originalClock = process.hrtime.bigint;
  let ticks = 0;
  let calls = 0;
  const stats = { get objective() { assert.equal(ticks, 2); return 1; } };
  const result = { groups: ['A'], assignments: { A: ['A'] }, letters: { A: 'A' },
    adjacency: [[true]], method: 'letter_minimum', relationshipPreserved: true,
    stats, rows: [{ group: 'A', letters: 'A', assignments: 'A' }] };
  driver.runtime = { api: { async reduceFromAdjacency(data, options) {
    assert.equal(ticks, 1);
    assert.deepEqual(data, [[1]]);
    assert.equal(options.method, 'letter_minimum');
    calls++; return result;
  } } };
  process.hrtime.bigint = () => BigInt(++ticks * 100);
  try {
    const actual = await driver.measure(prepareCase({ call: 'adjacency',
      input: { adjacency: [[1]] }, options: { method: 'letter_minimum' } }), 3);
    assert.equal(calls, 3);
    assert.equal(ticks, 2);
    assert.equal(actual.elapsed_ns, 100);
    assert.equal(actual.result.stats.objective, 1);
  } finally { process.hrtime.bigint = originalClock; }
});

test('capture and profile preserve complete output and restore hooks with presolve on and off', async () => {
  for (const presolve of ['on', 'off']) {
    const driver = new Driver(repo, presolve);
    try {
      await driver.load();
      const original = hookState(driver.runtime);
      for (const method of ['letter_minimum', 'assignment_minimum']) {
        const c = abc(method);
        const measured = check(await call(driver, 'measure', c));
        const captured = check(await call(driver, 'capture', c));
        const profiled = check(await call(driver, 'profile', c));
        assert.deepEqual(captured.result, measured.result);
        assert.deepEqual(profiled.result, measured.result);
        assert.deepEqual(profiled.canonical, captured.canonical);
        assert.deepEqual(hookState(driver.runtime), original);
        assert.equal(driver.profileRuntime.probe.current, null);
        assert.equal(profiled.metrics.essential_cover, true);
        assert.equal(profiled.metrics.essential_decisions, method === 'letter_minimum' ? 2 : 4);
        assert.equal(profiled.metrics.decision_variables, captured.canonical.selected.length);
        assert.equal(profiled.metrics.solve_count, 1);
        assert.ok(profiled.metrics.solver_total_ns >= profiled.phases_ns.initial_optimization);
        assert.ok(profiled.metrics.solver_total_ns < profiled.phases_ns.total);
        assert.equal(profiled.result.stats.reduction_pct, 0);
        assert.deepEqual(profiled.result.groups, ['', '__proto__', '2']);
        assert.equal(profiled.profile_notes.patch_sha256.length, 64);
        assert.equal(profiled.profile_notes.source_head.length, 40);
        for (const value of Object.values(profiled.phases_ns)) assert.ok(Number.isSafeInteger(value) && value >= 0);
        assert.equal(driver.runtime.solver.lastOptions.presolve, presolve);
      }
      const temp = driver.temp;
      await driver.close();
      await assert.rejects(stat(temp), { code: 'ENOENT' });
    } finally { await driver.close(); }
  }
});

test('profile counts feasible and infeasible canonical trials on a graph with no essentials', async () => {
  const driver = new Driver(repo);
  try {
    const result = check(await call(driver, 'profile', multipartite(3, 'assignment_minimum')));
    const m = result.metrics;
    assert.equal(m.essential_decisions, 0);
    assert.equal(m.essential_cover, false);
    assert.equal(m.solve_count, 1 + m.canonical_feasible_trials + m.canonical_infeasible_trials);
    assert.equal(m.canonical_infeasible_trials, m.final_zero_decisions);
    assert.ok(m.canonical_infeasible_trials > 0);
    assert.ok(m.canonical_feasible_trials > 0);
    assert.equal(result.phases_ns.canonical_trials, result.profile_notes.canonical_feasible_trials_ns +
      result.profile_notes.canonical_infeasible_trials_ns);
    assert.equal(m.solver_counters.runs.length, m.solve_count);
  } finally { await driver.close(); }
});

test('profile preserves pair routes, custom columns, means ordering and labels', async () => {
  const driver = new Driver(repo);
  try {
    const cases = (await fixture('reduce')).filter(c => c.id.startsWith('hand/'));
    for (const original of cases) {
      const c = { ...original, options: { method: original.expected.method, ...original.options } };
      const captured = check(await call(driver, 'capture', c));
      const profiled = check(await call(driver, 'profile', c));
      assert.deepEqual(profiled.result, captured.result, c.id);
      assert.deepEqual(profiled.canonical, captured.canonical, c.id);
      const preprocessed = check(await call(driver, 'preprocess', c));
      for (const key of ['vertices_before', 'vertices_after', 'edges', 'maximal_cliques',
        'decision_variables', 'auxiliary_variables', 'constraints', 'nonzeros', 'essential_decisions', 'essential_cover']) {
        assert.equal(profiled.metrics[key], preprocessed.metrics[key], `${c.id} ${key}`);
      }
    }
  } finally { await driver.close(); }
});

test('capture ignores auxiliary columns, including noncontiguous decision columns', async () => {
  const driver = new Driver(repo);
  await driver.load();
  const strategy = driver.runtime.model.methods.find(s => s.name === 'assignment_minimum');
  const builder = strategy.builder;
  const essential = strategy.essentialDecisions;
  const normal = check(await call(driver, 'capture'));
  strategy.builder = context => {
    const model = builder(context);
    const p = model.problem;
    model.problem = { ...p, numCols: p.numCols + 1,
      decisionColumns: p.decisionColumns.map(k => k + 1),
      cost: Float64Array.from([0, ...p.cost]), indices: Int32Array.from(p.indices, k => k + 1) };
    return model;
  };
  strategy.essentialDecisions = model => essential(model).map(k => k + 1);
  try {
    const captured = check(await call(driver, 'capture'));
    assert.deepEqual(captured.result, normal.result);
    assert.deepEqual(captured.canonical, normal.canonical);
    assert.equal(captured.canonical.selected.length, 4);
  } finally { strategy.builder = builder; strategy.essentialDecisions = essential; await driver.close(); }
});

test('failures restore capture and profile hooks, including native model methods', async () => {
  const driver = new Driver(repo);
  await driver.load();
  const copy = await driver.getProfileRuntime();
  const originalRun = driver.runtime.solver.hooks.run;
  const originalCreate = driver.runtime.solver.loadedSolver().createModel;
  try {
    for (const action of ['capture', 'profile']) {
      const runtime = action === 'capture' ? driver.runtime : copy.runtime;
      const decoder = runtime.model.methods[0].decoder;
      const faultDecoder = () => { throw new Error('decoder fault'); };
      runtime.model.methods[0].decoder = faultDecoder;
      try {
        const result = await call(driver, action);
        assert.equal(result.ok, false);
        assert.equal(result.error.message, 'decoder fault');
        assert.equal(runtime.model.methods[0].decoder, faultDecoder);
        assert.equal(driver.runtime.solver.hooks.run, originalRun);
        assert.equal(driver.runtime.solver.loadedSolver().createModel, originalCreate);
        assert.equal(copy.probe.current, null);
      } finally { runtime.model.methods[0].decoder = decoder; }
      driver.runtime.solver.hooks.run = () => { throw new Error('adapter fault'); };
      const before = hookState(runtime);
      const result = await call(driver, action);
      assert.equal(result.ok, false);
      assert.equal(result.error.message, 'adapter fault');
      assert.deepEqual(hookState(runtime), before);
      driver.runtime.solver.hooks.run = originalRun;
      check(await call(driver, 'measure'));
    }
    const highs = driver.runtime.solver.loadedSolver();
    let native;
    let pass;
    let run;
    highs.createModel = function (...args) {
      native = originalCreate.apply(this, args);
      native.passModel = function () { throw new Error('native load fault'); };
      pass = native.passModel;
      run = native.run;
      return native;
    };
    const result = await call(driver, 'profile');
    assert.equal(result.ok, false);
    assert.equal(result.error.message, 'native load fault');
    assert.equal(native.passModel, pass);
    assert.equal(native.run, run);
    assert.equal(Object.hasOwn(native, 'run'), false);
    assert.equal(copy.probe.current, null);
  } finally {
    driver.runtime.solver.hooks.run = originalRun;
    driver.runtime.solver.loadedSolver().createModel = originalCreate;
    await driver.close();
  }
});

test('preprocessing calls production builders and enforces cap without any solve', async () => {
  const driver = new Driver(repo);
  await driver.load();
  const original = driver.runtime.solver.hooks.run;
  driver.runtime.solver.hooks.run = () => { throw new Error('optimization must not run'); };
  try {
    for (const parts of [6, 7, 8]) for (const method of ['letter_minimum', 'assignment_minimum']) {
      const result = check(await call(driver, 'preprocess', multipartite(parts, method)));
      assert.equal(result.metrics.maximal_cliques, 3 ** parts);
      assert.equal(result.metrics.vertices_before, 3 * parts);
      assert.equal(result.metrics.vertices_after, 3 * parts);
      assert.equal(result.metrics.edges, 9 * parts * (parts - 1) / 2);
      assert.equal(result.metrics.decision_variables, 3 ** parts * (method === 'letter_minimum' ? 1 : parts));
      assert.equal(result.metrics.solve_count, 0);
      assert.equal(result.metrics.essential_cover, false);
      assert.equal(result.metrics.selected, null);
      assert.equal(result.phases_ns.initial_optimization, null);
      assert.ok(result.profile_notes.unavailable_phases.initial_optimization);
    }
    const capped = await call(driver, 'preprocess', multipartite(9));
    assert.equal(capped.ok, false);
    assert.equal(capped.error.kind, 'SolverError');
    assert.match(capped.error.message, /max_cliques=10000/);
    assert.equal(Object.hasOwn(capped, 'result'), false);
  } finally { driver.runtime.solver.hooks.run = original; await driver.close(); }
});

test('all package validation error fixtures survive conversion and each action', async () => {
  const driver = new Driver(repo);
  try {
    for (const original of await fixture('errors')) {
      const c = { ...original, options: { method: 'letter_minimum', ...original.options } };
      for (const action of ['capture', 'profile', 'preprocess', 'measure']) {
        const result = await call(driver, action, c);
        assert.equal(result.ok, false, `${c.id} ${action}`);
        assert.equal(result.error.kind, c.expected.kind === 'solver' ? 'SolverError' : 'InvalidInputError', `${c.id} ${action}`);
        assert.ok(result.error.message.startsWith(c.expected.message_prefix), `${c.id} ${action}: ${result.error.message}`);
        assert.equal(Object.hasOwn(result, 'result'), false);
      }
    }
    check(await call(driver, 'measure'));
  } finally { await driver.close(); }
});

test('JSONL recovers from malformed requests and resolves --repo independently of cwd', () => {
  const input = ['{', 'null', JSON.stringify({ action: 'unknown' }), JSON.stringify({ action: 'version' }),
    JSON.stringify({ action: 'measure', case: abc('letter_minimum'), iterations: 0 }),
    JSON.stringify({ action: 'capture', case: { ...abc('letter_minimum'), options: {} } }),
    JSON.stringify({ action: 'measure', case: abc('letter_minimum'), iterations: 1 })].join('\n') + '\n';
  const child = spawnSync(process.execPath, [join(repo, 'benchmarks/js_driver.mjs'), '--repo', repo, '--presolve', 'off'],
    { cwd: '/', input, encoding: 'utf8', timeout: 30_000 });
  assert.equal(child.status, 0, child.stderr);
  assert.equal(child.stderr, '');
  const results = child.stdout.trimEnd().split('\n').map(line => JSON.parse(line));
  assert.equal(results.length, 7);
  assert.deepEqual(results.map(r => r.ok), [false, false, false, true, false, false, true]);
  assert.equal(results[3].settings.presolve, 'off');
  assert.equal(results[4].error.kind, 'ProtocolError');
  assert.equal(results[5].error.kind, 'ProtocolError');
});

test('profile source patches fail closed and target dist remains unchanged', async () => {
  const before = new Map(await Promise.all((await readdir(join(repo, 'js/dist'))).map(async name =>
    [name, await readFile(join(repo, 'js/dist', name))])));
  assert.throws(() => profileSource('export const changed = true;'), /Unsupported profile build/);
  const driver = new Driver(repo);
  try { check(await call(driver, 'profile')); } finally { await driver.close(); }
  for (const [name, data] of before) assert.deepEqual(await readFile(join(repo, 'js/dist', name)), data);
});
