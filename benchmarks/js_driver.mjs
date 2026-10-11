#!/usr/bin/env node
// Development JSONL driver. Only measure() supplies full API timing evidence.
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { cp, mkdtemp, readFile, realpath, rm, symlink, unlink, writeFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { tmpdir } from 'node:os';
import { dirname, isAbsolute, join, resolve } from 'node:path';
import { createInterface } from 'node:readline';
import { fileURLToPath, pathToFileURL } from 'node:url';

const now = () => process.hrtime.bigint();
const elapsed = start => Number(now() - start);
const PHASES = ['input', 'vertex_reduction', 'enumeration', 'model_construction',
  'essential_scan', 'adapter_setup', 'model_load', 'initial_optimization',
  'canonical_trials', 'output_expansion', 'final_validation', 'total'];
const unavailable = reason => ({ available: false, reason });
const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);

export class ProtocolError extends Error {
  constructor(message) { super(message); this.name = 'ProtocolError'; }
}

export function prepareCase(c) {
  if (!object(c) || !object(c.input) || !object(c.options)) {
    throw new ProtocolError('case must contain input and options objects');
  }
  if (!['adjacency', 'pairs'].includes(c.call)) throw new ProtocolError('case.call must be adjacency or pairs');
  if (!Object.hasOwn(c.options, 'method')) throw new ProtocolError('case.options.method must be explicit');
  // JSON arrays already are the public JavaScript containers. Leave validation
  // and coercion to the API, including malformed values and missing fields.
  const options = {};
  for (const key of ['method', 'group1', 'group2', 'significant']) {
    if (Object.hasOwn(c.options, key)) options[key] = c.options[key];
  }
  for (const [source, target] of [['max_cliques', 'maxCliques'], ['time_limit', 'timeLimit']]) {
    if (Object.hasOwn(c.options, source)) options[target] = c.options[source];
  }
  for (const key of ['means', ...(c.call === 'adjacency' ? ['groups'] : [])]) {
    if (Object.hasOwn(c.input, key)) options[key] = c.input[key];
  }
  return { call: c.call, data: c.input[c.call === 'pairs' ? 'pairs' : 'adjacency'], options };
}

export function normalizeResult(r) {
  return {
    groups: [...r.groups],
    assignments: r.groups.map(g => [...r.assignments[g]]),
    letters: r.groups.map(g => r.letters[g]),
    adjacency: r.adjacency.map(row => [...row]),
    method: r.method,
    relationship_preserved: r.relationshipPreserved,
    stats: Object.fromEntries(Object.entries(r.stats).map(([key, value]) =>
      [key.replace(/[A-Z]/g, letter => `_${letter.toLowerCase()}`), value])),
    rows: r.rows.map(row => ({ ...row })),
  };
}

async function modules(dist) {
  const get = name => import(pathToFileURL(join(dist, `${name}.js`)).href);
  const [api, solver, model, input, reduction, cliques] = await Promise.all(
    ['index', 'solver', 'model', 'input', 'reduction-graph', 'cliques'].map(get));
  return { api, solver, model, input, reduction, cliques };
}

function invoke(runtime, prepared) {
  return prepared.call === 'pairs'
    ? runtime.api.reduceLetters(prepared.data, prepared.options)
    : runtime.api.reduceFromAdjacency(prepared.data, prepared.options);
}

// Restore own properties exactly. Model methods can come from a prototype.
function replace(target, key, replacement, restores) {
  const descriptor = Object.getOwnPropertyDescriptor(target, key);
  target[key] = replacement;
  restores.push(() => {
    if (descriptor) Object.defineProperty(target, key, descriptor);
    else delete target[key];
  });
}

function collector() {
  const phases = Object.fromEntries(PHASES.map(key => [key, null]));
  const state = {
    phases, model: null, context: null, required: null, canonical: null,
    verticesBefore: null, edgesBefore: null, solves: 0, feasible: 0, infeasible: 0,
    feasibleNs: 0, infeasibleNs: 0, solverTotalNs: 0, counters: [], nativeRuns: 0, solverSettings: [],
    add(key, duration) { phases[key] = (phases[key] ?? 0) + duration; },
    timed(key, callback) {
      const start = now();
      try { return callback(); } finally { state.add(key, elapsed(start)); }
    },
    markGraph(adjacency) {
      state.verticesBefore = adjacency.length;
      state.edgesBefore = adjacency.reduce((sum, row, i) => sum + row.filter((v, j) => j > i && v).length, 0);
    },
  };
  return state;
}

function canonicalOf(model, selected) {
  if (!Array.isArray(selected) || selected.length !== model.problem.decisionColumns.length ||
      selected.some(value => typeof value !== 'boolean')) {
    throw new Error('The runtime decoder did not receive the canonical decision vector');
  }
  return {
    selected: selected.map(Number),
    objective: selected.reduce((sum, on, k) =>
      sum + (on ? model.problem.cost[model.problem.decisionColumns[k]] : 0), 0),
  };
}

function instrumentStrategies(runtime, state, restores, profile) {
  for (const strategy of runtime.model.methods) {
    const originalDecoder = strategy.decoder;
    replace(strategy, 'decoder', function (cliques, model, selected) {
      state.canonical = canonicalOf(model, selected);
      return originalDecoder.call(this, cliques, model, selected);
    }, restores);
    if (!profile) continue;
    const originalBuilder = strategy.builder;
    replace(strategy, 'builder', function (context) {
      state.context = context;
      state.model = state.timed('model_construction', () => originalBuilder.call(this, context));
      return state.model;
    }, restores);
    const originalEssential = strategy.essentialDecisions;
    replace(strategy, 'essentialDecisions', function (model) {
      const required = state.timed('essential_scan', () => originalEssential.call(this, model));
      state.required = [...required];
      return required;
    }, restores);
  }
}

function readCounters(model) {
  const result = {};
  for (const name of ['mip_node_count', 'simplex_iteration_count', 'ipm_iteration_count', 'pdlp_iteration_count']) {
    try {
      const value = model.info.get(name);
      result[name] = value < 0 ? unavailable('HiGHS returned a negative unavailable value')
        : typeof value === 'bigint' && value > BigInt(Number.MAX_SAFE_INTEGER) ? value.toString() : Number(value);
    } catch (error) { result[name] = unavailable(error.message); }
  }
  return result;
}

function instrumentSolver(runtime, state, restores) {
  const hooks = runtime.solver.hooks;
  const originalRun = hooks.run;
  replace(hooks, 'run', function (...args) {
    const trial = args[3] !== null;
    state.solves++;
    const start = now();
    let outcome;
    try { outcome = originalRun.apply(this, args); return outcome; }
    finally {
      const duration = elapsed(start);
      state.solverTotalNs += duration;
      if (trial) {
        state.add('canonical_trials', duration);
        if (outcome?.status === 'optimal') { state.feasible++; state.feasibleNs += duration; }
        if (outcome?.status === 'infeasible') { state.infeasible++; state.infeasibleNs += duration; }
      }
    }
  }, restores);
  const highs = runtime.solver.loadedSolver();
  const originalCreate = highs.createModel;
  replace(highs, 'createModel', function (...args) {
    const model = state.timed('adapter_setup', () => originalCreate.apply(this, args));
    const pass = model.passModel;
    replace(model, 'passModel', function (...values) {
      return state.timed('model_load', () => pass.apply(this, values));
    }, restores);
    const set = model.options.set;
    replace(model.options, 'set', function (...values) {
      return state.timed('adapter_setup', () => set.apply(this, values));
    }, restores);
    const run = model.run;
    replace(model, 'run', function (...values) {
      const first = state.nativeRuns++ === 0;
      const start = now();
      let outcome;
      try { outcome = run.apply(this, values); return outcome; }
      finally {
        const duration = elapsed(start);
        const keys = ['presolve', 'output_flag', 'mip_rel_gap', 'mip_abs_gap',
          'primal_feasibility_tolerance', 'mip_feasibility_tolerance'];
        state.solverSettings.push({ solve: state.nativeRuns,
          values: Object.fromEntries(keys.map(key => [key, model.options.get(key)])),
          excluded_values: { time_limit: Number.isFinite(model.options.get('time_limit'))
            ? model.options.get('time_limit') : null } });
        if (first) state.add('initial_optimization', duration);
        state.counters.push({ run: state.nativeRuns, model_status: outcome?.modelStatus ?? null,
          elapsed_ns: duration, values: readCounters(model) });
      }
    }, restores);
    return model;
  }, restores);
}

function metricsOf(runtime, state) {
  const model = state.model;
  if (!model || !state.context || !state.required) throw new Error('Runtime model/essential hooks were not observed');
  const strategy = state.strategy;
  const decisions = model.problem.decisionColumns;
  const essential = new Set(state.required);
  const selected = state.canonical?.selected ?? null;
  return {
    vertices_before: state.verticesBefore,
    vertices_after: state.context.adjacency.length,
    edges: state.edgesBefore,
    edges_after: state.context.edges.length,
    maximal_cliques: state.context.cliques.length,
    decision_variables: decisions.length,
    auxiliary_variables: model.problem.numCols - decisions.length,
    constraints: model.problem.rowLower.length,
    nonzeros: model.problem.values.length,
    essential_decisions: state.required.length,
    essential_cover: strategy.coverage(model, decisions.map(k => essential.has(k))),
    solve_count: state.solves,
    solver_total_ns: state.solverTotalNs,
    canonical_feasible_trials: state.feasible,
    canonical_infeasible_trials: state.infeasible,
    final_zero_decisions: selected ? selected.filter(value => value === 0).length : null,
    selected,
    objective: state.canonical?.objective ?? null,
    solver_settings: { available: state.solverSettings.length > 0, records: state.solverSettings,
      source: 'Native model.options.get after each actual optimization',
      excluded: 'time_limit varies with the shared deadline; null means infinite',
      thread_constraint: { kind: 'single_threaded_api', threads: 1, native_option: false },
      thread_control: 'The single-threaded data-only API rejects threads and parallel options' },
    solver_counters: state.counters.length ? { available: true, runs: state.counters }
      : unavailable('No native solver run occurred'),
  };
}

function patchOnce(source, search, replacement) {
  const first = source.indexOf(search);
  if (first < 0 || source.indexOf(search, first + search.length) >= 0) {
    throw new Error(`Unsupported profile build: expected one source anchor ${JSON.stringify(search)}`);
  }
  return source.slice(0, first) + replacement + source.slice(first + search.length);
}

// Patch only an isolated built module. Fail closed if a later runtime changes
// the observed boundaries. No loader or optimization runs during patch setup.
export function profileSource(source) {
  let patched = 'import { probe } from "./benchmark-probes.js";\n' + source;
  const wrappers = [];
  for (const [name, phase] of Object.entries({ adjacencyToGraph: 'input', pairsToGraph: 'input',
    checkControls: 'input', checkMethod: 'input', reduceGraphVertices: 'vertex_reduction',
    maximalCliques: 'enumeration', graphContext: 'model_construction' })) {
    const pattern = new RegExp(`(import\\s*\\{[^}]*?)\\b${name}\\b([^}]*\\}\\s*from)`, 'g');
    let count = 0;
    patched = patched.replace(pattern, (_, prefix, suffix) => {
      count++; return `${prefix}${name} as __bench_${name}${suffix}`;
    });
    if (count !== 1) throw new Error(`Unsupported profile build: missing import ${name}`);
    wrappers.push(`const ${name} = (...args) => { ${name === 'reduceGraphVertices' ? 'probe.current.markGraph(args[0]); ' : ''}` +
      `return probe.current.timed(${JSON.stringify(phase)}, () => __bench_${name}(...args)); };`);
  }
  patched = patchOnce(patched, 'const columns = expandGraphColumns(',
    'const __bench_output_start = process.hrtime.bigint();\n    const columns = expandGraphColumns(');
  patched = patchOnce(patched, 'const share = ',
    'probe.current.add("output_expansion", Number(process.hrtime.bigint() - __bench_output_start));\n' +
    '    const __bench_validation_start = process.hrtime.bigint();\n    const share = ');
  patched = patchOnce(patched, 'return {\n        letters,',
    'probe.current.add("final_validation", Number(process.hrtime.bigint() - __bench_validation_start));\n' +
    '    return {\n        letters,');
  return patched + '\n' + wrappers.join('\n') + '\n';
}

function profileNotes(state, patch, preprocessing = false) {
  const reasons = {};
  for (const [key, value] of Object.entries(state.phases)) {
    if (value === null) reasons[key] = preprocessing ? 'Preprocessing stops before optimization and display output'
      : 'This path did not execute the observed phase';
  }
  return {
    ...patch,
    clock: 'process.hrtime.bigint, integer nanoseconds',
    timings: 'Instrumented diagnostic timings. canonical_trials includes adapter_setup, model_load and native optimization for trial calls. Do not sum overlapping phases. total includes probe overhead but excludes hook installation, result normalization and metric reporting.',
    phase_scope: {
      input: 'Public graph normalization, method and control validation; JSON conversion is outside timing',
      model_construction: 'Actual graphContext plus strategy.builder',
      adapter_setup: 'Native model creation and options.set calls; other adapter bookkeeping remains in total/canonical_trials',
      initial_optimization: 'First native model.run call only',
      output_expansion: 'Decoder, expansion, letter ordering, assignments and letter maps; result-object assembly remains in total',
      final_validation: 'Relationship reconstruction, before/after counts and objective check',
    },
    edges: 'edges is the input graph edge count; edges_after is the reduced graph edge count',
    unavailable_phases: reasons,
    unavailable_metrics: preprocessing ? { selected: 'No optimization was requested', objective: 'No optimization was requested',
      final_zero_decisions: 'No optimization was requested' } : {},
    canonical_feasible_trials_ns: state.feasibleNs,
    canonical_infeasible_trials_ns: state.infeasibleNs,
    full_call_overhead: preprocessing ? null : state.overhead,
  };
}

export class Driver {
  constructor(repo, presolve = 'on') {
    if (!isAbsolute(repo)) throw new ProtocolError('--repo must be an absolute path');
    if (!['on', 'off'].includes(presolve)) throw new ProtocolError('--presolve must be on or off');
    this.repo = repo;
    this.presolve = presolve;
    this.runtime = null;
    this.loadPromise = null;
    this.profileRuntime = null;
    this.temp = null;
  }

  async load() {
    if (this.loadPromise) return this.loadPromise;
    this.loadPromise = this.loadOnce().catch(error => { this.loadPromise = null; throw error; });
    return this.loadPromise;
  }

  async loadOnce() {
    this.repo = await realpath(this.repo);
    this.dist = join(this.repo, 'js', 'dist');
    const start = now();
    this.runtime = await modules(this.dist);
    this.moduleLoadNs = elapsed(start);
    this.runtime.solver.settings.presolve = this.presolve;
    const solverStart = now();
    await this.runtime.api.loadSolver();
    this.solverLoadNs = elapsed(solverStart);
    const packageJson = JSON.parse(await readFile(join(this.repo, 'js', 'package.json'), 'utf8'));
    const require = createRequire(join(this.repo, 'js', 'package.json'));
    const highsPackage = JSON.parse(await readFile(join(dirname(dirname(require.resolve('highs'))), 'package.json'), 'utf8'));
    try { this.sourceHead = execFileSync('git', ['-C', this.repo, 'rev-parse', 'HEAD'], { encoding: 'utf8' }).trim(); }
    catch { this.sourceHead = null; }
    const solverVersion = this.runtime.solver.loadedSolver().version;
    this.versionInfo = {
      language: 'javascript', runtime: process.version, runtime_versions: { ...process.versions },
      package_version: packageJson.version, dependencies: { highs: highsPackage.version },
      solver_version: solverVersion.string, solver: { ...solverVersion }, source_head: this.sourceHead,
      module_load_ns: this.moduleLoadNs, solver_load_ns: this.solverLoadNs,
      settings_kind: 'declared_contract',
      settings_notes: 'Profiles record native options from actual solves',
      settings: { presolve: this.presolve, output_flag: false, mip_rel_gap: 0, mip_abs_gap: 0,
        primal_feasibility_tolerance: 1e-9, mip_feasibility_tolerance: 1e-9,
        threads: 1, thread_setting: 'WebAssembly build is single threaded; no thread option is set',
        time_limit: 'Per case time_limit; shared canonical deadline in the production API' },
    };
  }

  async getProfileRuntime() {
    if (this.profileRuntime) return this.profileRuntime;
    const source = await readFile(join(this.dist, 'reduce.js'), 'utf8');
    const patched = profileSource(source);
    const temp = await mkdtemp(join(tmpdir(), 'cld-js-profile-'));
    try {
      const dist = join(temp, 'dist');
      await cp(this.dist, dist, { recursive: true });
      await writeFile(join(temp, 'package.json'), '{"type":"module"}\n');
      await symlink(join(this.repo, 'js', 'node_modules'), join(temp, 'node_modules'), 'dir');
      // Reuse the already loaded solver. Any hooks are temporary and restored.
      await unlink(join(dist, 'solver.js'));
      await symlink(join(this.dist, 'solver.js'), join(dist, 'solver.js'));
      await writeFile(join(dist, 'reduce.js'), patched);
      await writeFile(join(dist, 'benchmark-probes.js'), 'export const probe = { current: null };\n');
      const runtime = await modules(dist);
      const { probe } = await import(pathToFileURL(join(dist, 'benchmark-probes.js')).href);
      this.profileRuntime = { runtime, probe, notes: {
        source_head: this.sourceHead,
        source_head_unavailable_reason: this.sourceHead === null ? 'Target is not a Git checkout' : null,
        source_file: 'js/dist/reduce.js',
        source_sha256: createHash('sha256').update(source).digest('hex'),
        patched_source_sha256: createHash('sha256').update(patched).digest('hex'),
        patch_sha256: createHash('sha256').update(source + '\0' + patched).digest('hex'),
        patch_hash_definition: 'SHA256(original source, NUL, instrumented source)',
        measurement_build: 'Target js/dist is unchanged; temporary copy supplies profile calls only',
      } };
      this.temp = temp;
      return this.profileRuntime;
    } catch (error) { await rm(temp, { recursive: true, force: true }); throw error; }
  }

  async measure(prepared, iterations) {
    if (!Number.isSafeInteger(iterations) || iterations < 1) throw new ProtocolError('iterations must be a positive safe integer');
    // Keep the public call, await and loop as the entire measured region.
    const call = prepared.call === 'pairs' ? this.runtime.api.reduceLetters : this.runtime.api.reduceFromAdjacency;
    let result;
    const start = now();
    for (let i = 0; i < iterations; i++) result = await call(prepared.data, prepared.options);
    const elapsed_ns = elapsed(start);
    return { elapsed_ns, iterations, result: normalizeResult(result) };
  }

  async capture(prepared, profile) {
    const copy = profile ? await this.getProfileRuntime() : null;
    const runtime = copy?.runtime ?? this.runtime;
    // Repeated profile requests warm both the production module and the same
    // disposable profile module. The coordinator discards the warmup records.
    let referenceNs = null;
    let referenceResult = null;
    if (profile) {
      const start = now();
      referenceResult = await invoke(this.runtime, prepared);
      referenceNs = elapsed(start);
    }
    const state = collector();
    const restores = [];
    let result;
    try {
      instrumentStrategies(runtime, state, restores, profile);
      if (profile) {
        replace(copy.probe, 'current', state, restores);
        instrumentSolver(runtime, state, restores);
      }
      const start = now();
      result = await invoke(runtime, prepared);
      state.phases.total = elapsed(start);
    } finally { for (const restore of restores.reverse()) restore(); }
    if (!state.canonical) throw new Error('The runtime did not call the canonical decoder');
    if (state.canonical.objective !== result.stats.objective) throw new Error('Captured objective differs from public objective');
    const response = { result: normalizeResult(result), canonical: state.canonical };
    if (profile) {
      state.strategy = runtime.model.methods.find(s => s.name === result.method);
      // The wrapper observes the absence of canonical calls too.
      state.phases.canonical_trials ??= 0;
      response.metrics = metricsOf(runtime, state);
      response.phases_ns = state.phases;
      if (JSON.stringify(normalizeResult(referenceResult)) !== JSON.stringify(response.result)) {
        throw new Error('Profile and uninstrumented reference returned different results');
      }
      state.overhead = { reference_ns: referenceNs, instrumented_ns: state.phases.total, uninstrumented_calls: 1,
        instrumented_minus_reference_ns: state.phases.total - referenceNs,
        ratio: referenceNs > 0 ? state.phases.total / referenceNs : null,
        note: 'One preceding uninstrumented full call. The signed difference includes runtime noise and probe cost; no subtraction is applied. Warmup requests use this same profile module.' };
      response.profile_notes = profileNotes(state, copy.notes);
    }
    return response;
  }

  preprocess(prepared) {
    const runtime = this.runtime;
    const state = collector();
    const start = now();
    const graph = state.timed('input', () => prepared.call === 'pairs'
      ? runtime.input.pairsToGraph(prepared.data, prepared.options)
      : runtime.input.adjacencyToGraph(prepared.data, prepared.options));
    const strategy = state.timed('input', () => runtime.input.checkMethod(prepared.options.method));
    const controls = state.timed('input', () => runtime.input.checkControls(prepared.options));
    state.markGraph(graph.adjacency);
    const reduced = state.timed('vertex_reduction', () => runtime.reduction.reduceGraphVertices(graph.adjacency));
    const smallGraph = { adjacency: reduced.adjacency,
      groups: reduced.classes.map(group => graph.groups[group[0]]), means: null };
    const cliques = state.timed('enumeration', () => runtime.cliques.maximalCliques(reduced.adjacency, controls.maxCliques));
    state.context = state.timed('model_construction', () => runtime.model.graphContext(smallGraph, cliques, reduced.weights));
    state.model = state.timed('model_construction', () => strategy.builder(state.context));
    state.required = state.timed('essential_scan', () => strategy.essentialDecisions(state.model));
    state.strategy = strategy;
    state.phases.total = elapsed(start);
    return { metrics: metricsOf(runtime, state), phases_ns: state.phases,
      profile_notes: profileNotes(state, { source_head: this.sourceHead, source_patch: null }, true) };
  }

  async handle(request) {
    let action = object(request) && typeof request.action === 'string' ? request.action : null;
    try {
      if (!['version', 'measure', 'capture', 'profile', 'preprocess'].includes(action)) throw new ProtocolError('unknown action');
      const prepared = action === 'version' ? null : prepareCase(request.case);
      if (action === 'measure' && (!Number.isSafeInteger(request.iterations) || request.iterations < 1)) {
        throw new ProtocolError('iterations must be a positive safe integer');
      }
      await this.load();
      let response;
      if (action === 'version') response = this.versionInfo;
      if (action === 'measure') response = await this.measure(prepared, request.iterations);
      if (action === 'capture' || action === 'profile') response = await this.capture(prepared, action === 'profile');
      if (action === 'preprocess') response = this.preprocess(prepared);
      return { ok: true, action, ...response };
    } catch (error) {
      return { ok: false, action, error: { kind: error.name ?? 'Error', message: String(error.message ?? error) } };
    }
  }

  async close() {
    if (this.temp) await rm(this.temp, { recursive: true, force: true });
    this.temp = null;
    this.profileRuntime = null;
  }
}

async function main() {
  let repo;
  let presolve = 'on';
  const args = process.argv.slice(2);
  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--repo') repo = args[++i];
    else if (args[i] === '--presolve') presolve = args[++i];
    else throw new ProtocolError(`unknown argument: ${args[i]}`);
  }
  if (!repo) throw new ProtocolError('usage: js_driver.mjs --repo ABSOLUTE_PATH [--presolve on|off]');
  const driver = new Driver(repo, presolve);
  const lines = createInterface({ input: process.stdin, crlfDelay: Infinity });
  try {
    for await (const line of lines) {
      let response;
      try { response = await driver.handle(JSON.parse(line)); }
      catch (error) { response = { ok: false, action: null, error: { kind: error.name, message: error.message } }; }
      await new Promise((resolveWrite, reject) => process.stdout.write(JSON.stringify(response) + '\n',
        error => error ? reject(error) : resolveWrite()));
    }
  } finally { await driver.close(); }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch(error => { process.stderr.write(`${error.name}: ${error.message}\n`); process.exitCode = 1; });
}
