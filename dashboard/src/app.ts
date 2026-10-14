// The page: read the input, show the display before reduction, run cld-reducer
// and the experimental second stage in a worker, and run the simulation study.

import type { CldReduction } from "../../js/src/index.js";
import wasmGzipBase64 from "virtual:highs-wasm";
import repository from "virtual:repository";
import workerSource from "virtual:worker-source";
import { DataError, MAX_CHARS, TEMPLATE_MEANS, TEMPLATE_PAIRS, parseMeans, parsePairs } from "./csv.js";
import {
  EXAMPLES, METHODS, SECOND_STAGE, TABLE_X, TABLE_XI, checkReduction, count, displayOf, duration, explain,
  meanText, methodInfo, resultsCsv, resultsJson, sharedTokens, tokensOf,
  checkBefore, checkInput, checkStage, isTime, type BeforeRows, type Example, type Method, type MethodResult, type ResultMethod, type StagedOrder,
} from "./data.js";
import { MAX_SEED, experimentCsv, seedAfter, simulate } from "./simulate.js";
import { summarize, studyCsv, ALL_METHODS, checkInstance, instanceFacts, planned, slowest } from "./study.js";
import type { Input, Instance, Reply, Request, Study } from "./worker.js";

/** The matrix of shared letters has one cell for each pair, so it is shown for small inputs only. */
const MAX_MATRIX_GROUPS = 30;

// Elements

function $<T extends HTMLElement>(id: string): T {
  const el = document.getElementById(id);
  if (!el) throw new Error(`Missing element #${id}`);
  return el as T;
}

const ui = {
  status: $("solver-status"),
  viewReduce: $<HTMLButtonElement>("view-reduce"),
  viewStudy: $<HTMLButtonElement>("view-study"),
  reduceView: $("reduce-view"),
  studyView: $("study-view"),
  examples: $("examples"),
  exampleNote: $("example-note"),
  simN: $<HTMLInputElement>("sim-n"),
  simSeed: $<HTMLInputElement>("sim-seed"),
  simGenerate: $<HTMLButtonElement>("sim-generate"),
  pairs: $<HTMLTextAreaElement>("pairs"),
  means: $<HTMLTextAreaElement>("means"),
  theme: $<HTMLButtonElement>("theme"),
  run: $<HTMLButtonElement>("run"),
  compare: $<HTMLButtonElement>("compare"),
  reset: $<HTMLButtonElement>("reset"),
  runHint: $("run-hint"),
  results: $("results"),
  studyFrom: $<HTMLInputElement>("study-from"),
  studyTo: $<HTMLInputElement>("study-to"),
  studyStep: $<HTMLInputElement>("study-step"),
  studyCount: $<HTMLInputElement>("study-count"),
  studySeed: $<HTMLInputElement>("study-seed"),
  studyLimit: $<HTMLInputElement>("study-limit"),
  studyRun: $<HTMLButtonElement>("study-run"),
  studyHint: $("study-hint"),
  studyResults: $("study-results"),
};

function el<K extends keyof HTMLElementTagNameMap>(tag: K, className?: string, text?: string,
                                                   parent?: Element): HTMLElementTagNameMap[K] {
  const e = document.createElement(tag);
  if (className) e.className = className;
  if (text !== undefined) e.textContent = text;
  parent?.appendChild(e);
  return e;
}

function button(className: string, text: string, parent: Element, onClick: () => void): HTMLButtonElement {
  const b = el("button", className, text, parent);
  b.type = "button";
  b.addEventListener("click", onClick);
  return b;
}

// State

interface Run {
  id: number;
  methods: Method[];
  /** Every result that the run must return, in order. */
  expected: ResultMethod[];
  input: Input;
  inputVersion: number;
  source: string;
  results: MethodResult[];
  current: ResultMethod;
  stage: 1 | 2;
  currentStart: number;
  /** Every result arrived, and the run waits for its display before reduction. */
  waiting?: boolean;
}

/** A finished run. The page shows it until the input or the method changes. */
interface Shown {
  /** The input version of the run. */
  version: number;
  results: MethodResult[];
  input: Input;
  source: string;
  /** The checked display before reduction: the page shows no result without it. */
  before: BeforeRows;
}

interface Problem {
  title: string;
  message: string;
  detail: string | null;
}

interface StudyRun {
  id: number;
  study: Study;
  total: number;
  instances: Instance[];
  status: "running" | "done" | "cancelled" | "error";
  message: string | null;
  started: number;
  ended: number | null;
}

const state = {
  view: "reduce" as "reduce" | "study",
  solver: "loading" as "loading" | "ready" | "failed",
  solverMessage: "",
  example: null as Example | null,
  /** Name of the input for the result files. */
  source: "Pasted text",
  /** A note under the examples for a simulated experiment. */
  sourceNote: null as string | null,
  /** Each change of the input text gets a new number. */
  inputVersion: 0,
  before: null as (BeforeRows & { version: number }) | null,
  /** Why the page shows no display before reduction. */
  beforeNote: null as string | null,
  run: null as Run | null,
  shown: null as Shown | null,
  problem: null as Problem | null,
  notice: null as string | null,
  study: null as StudyRun | null,
};

const studyFields = [ui.studyFrom, ui.studyTo, ui.studyStep, ui.studyCount, ui.studySeed, ui.studyLimit];

let nextId = 1;
/** The before request in flight, with the input and the input version that it belongs to. */
let beforeRequest: { id: number; version: number; input: Input } | null = null;
/** The last input version for which the page asked for the display before reduction. */
let beforeVersion = -1;
let beforeTimer: ReturnType<typeof setTimeout> | undefined;

// Each change of a field gets a new number. A file read that ends after a
// later change of its field is then out of date, and the page drops it.
const fieldChange = new Map<HTMLTextAreaElement, number>();
function changed(...areas: HTMLTextAreaElement[]): void {
  for (const area of areas) fieldChange.set(area, (fieldChange.get(area) ?? 0) + 1);
}

function selectedMethod(): Method {
  const checked = document.querySelector<HTMLInputElement>('input[name="method"]:checked');
  return checked?.value === "assignment_minimum" ? "assignment_minimum" : "letter_minimum";
}

function currentBefore(): BeforeRows | null {
  return state.before && state.before.version === state.inputVersion ? state.before : null;
}

// Solver

const workerUrl = URL.createObjectURL(new Blob([workerSource], { type: "text/javascript" }));
let wasm: Uint8Array | null = null;
let worker: Worker | null = null;

async function inflate(base64: string): Promise<Uint8Array> {
  const bytes = Uint8Array.from(atob(base64), (c) => c.charCodeAt(0));
  const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream("gzip"));
  return new Uint8Array(await new Response(stream).arrayBuffer());
}

function solverFailed(message: string): void {
  worker = null;
  state.solver = "failed";
  state.solverMessage = message;
  render();
}

/** Start a worker and load the solver in it. Replies of any earlier worker are ignored. */
function startWorker(): void {
  state.solver = "loading";
  // A request to the old worker is lost; ask the new one again.
  beforeVersion = -1;
  beforeRequest = null;
  let w: Worker;
  try {
    w = new Worker(workerUrl, { name: "cld-reducer-solver" });
  } catch (e) {
    solverFailed(e instanceof Error ? e.message : String(e));
    return;
  }
  worker = w;
  let ready = false;
  w.onmessage = (e: MessageEvent<unknown>) => {
    if (w !== worker) return;
    const r = e.data;
    if (ready) { onReply(r); return; }
    // While it loads, the worker sends one ready reply without an id, or an error.
    const record = isRecord(r) ? r : null;
    if (record?.type === "ready" && record.id === undefined) {
      ready = true;
      state.solver = "ready";
      if (!currentBefore()) requestBefore();
      render();
    } else {
      w.terminate();
      // The message of a loading error is used as text only when it is text.
      solverFailed(record?.type !== "error" ? "The worker sent a reply that loading does not have."
        : typeof record.message === "string" ? record.message : "The worker sent an error without a message.");
    }
  };
  w.onerror = (e) => {
    e.preventDefault();
    if (w !== worker) return;
    w.terminate();
    const message = e.message || "The solver worker stopped.";
    if (!ready) { solverFailed(message); return; }
    // The worker failed after it started: end the work and start a new worker.
    if (state.run) fail({ title: "The solver stopped", message, detail: null });
    if (state.study?.status === "running") endStudy("error", message);
    startWorker();
    render();
  };
  const copy = wasm!.slice();
  w.postMessage({ type: "load", wasm: copy } satisfies Request, [copy.buffer]);
}

/** Stop the work in progress: terminate the worker and start a new one. */
function restartWorker(): void {
  worker?.terminate();
  worker = null;
  startWorker();
}

async function startSolver(): Promise<void> {
  try {
    wasm = await inflate(wasmGzipBase64);
  } catch (e) {
    solverFailed(e instanceof Error ? e.message : String(e));
    return;
  }
  startWorker();
  render();
}

function fail(problem: Problem): void {
  state.run = null;
  state.shown = null;
  state.notice = null;
  state.problem = problem;
}

function problemOf(kind: string, message: string): Problem {
  return kind === "input"
    ? { title: "The package rejected the input", message, detail: explain(message) }
    : { title: kind === "solver" ? "The solver stopped with an error" : "The run stopped with an error",
        message, detail: explain(message) };
}

/** A plain object, as the worker sends: not null, an array, a date, a buffer, or another kind of object. */
function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && Object.getPrototypeOf(value) === Object.prototype;
}

/** A reply that the protocol does not have stops the run or the study, and the page starts a new worker. */
function protocolError(message: string): void {
  if (state.study?.status === "running") {
    endStudy("error", `The solver returned an invalid result. ${message}`);
    restartWorker();
  } else if (state.run) {
    fail({ title: "The solver returned an invalid result", message, detail: "The page shows no result." });
    restartWorker();
  } else if (beforeRequest) {
    // The reply can be the one for the display before reduction: end that request, so that a later
    // run does not wait for it. The page does not ask again for this input.
    beforeRequest = null;
    state.before = null;
    state.beforeNote = `The reply failed the check of the page. ${message}`;
  }
  render();
}

function onReply(value: unknown): void {
  if (!isRecord(value)) {
    protocolError("The worker sent a reply that is not a record.");
    return;
  }
  const reply = value as Reply;
  // A worker sends ready once, when it has loaded (startWorker). A second ready without an id stops
  // the work in progress; a ready that names a run or a study goes on to the checks below.
  if (reply.type === "ready" && typeof (reply as { id?: unknown }).id !== "number") {
    protocolError("The worker sent a second ready reply.");
    return;
  }
  // An error reply is used as text: a message that is not text, or an unknown kind, is a solver error.
  const valid = reply.type === "error" && typeof reply.message === "string" &&
    (["input", "solver", "other"] as unknown[]).includes(reply.kind);
  const r: Reply = reply.type !== "error" || valid ? reply : {
    ...reply, kind: "solver" as const,
    message: typeof reply.message === "string" ? reply.message : "The worker sent an error without a message.",
  };
  if (beforeRequest && r.id === beforeRequest.id) {
    const { version, input } = beforeRequest;
    beforeRequest = null;
    const defect = r.type === "error" ? null
      : r.type !== "before" ? "The worker sent a reply that the display before reduction does not have."
      : safely(() => checkBefore(r.before, input.pairs, input.means) ??
                     (isTime(r.milliseconds) ? null : "The time of the reply is not a time."));
    // An error here comes from the input checks or from the clique limit, not from HiGHS, so the
    // worker stays. A new worker would ask for the same display and fail the same way.
    if (defect) {
      state.before = null;
      state.beforeNote = `The reply failed the check of the page. ${defect}`;
    } else if (r.type === "before") {
      state.before = { ...r.before, milliseconds: r.milliseconds, version };
      state.beforeNote = null;
    } else if (r.type === "error") {
      state.before = null;
      state.beforeNote = r.message;
    }
    // A run that ended before this display arrived waits for it: the page checks the run against it now.
    const run = state.run;
    if (run?.waiting && run.inputVersion === version) finishRun(run);
    render();
    return;
  }
  if (state.study && r.id === state.study.id) {
    if (state.study.status === "running") onStudyReply(r);
    return;
  }
  const run = state.run;
  // A reply of a run that was cancelled or replaced has another id.
  if (!run || r.id !== run.id) return;
  if (r.type === "start") {
    const stage = METHODS.some((m) => m.id === r.method) ? 1 : 2;
    if (r.method !== run.expected[run.results.length] || r.stage !== stage) {
      fail({ title: "The solver returned an invalid result", message: "The reply is for another method.",
             detail: "The page shows no result." });
      restartWorker();
    } else {
      run.current = r.method;
      run.stage = r.stage;
      run.currentStart = performance.now();
    }
  } else if (r.type === "result") {
    const expected = run.expected[run.results.length];
    const groups = run.results[0]?.reduction.groups;
    const stage = METHODS.some((m) => m.id === r.method) ? 1 : 2;
    const previous = run.results[run.results.length - 1];
    const defect = safely(() => r.method !== expected || r.stage !== stage ? "The reply is for another method."
      : checkReduction(r.reduction, r.method)
      ?? checkInput(r.reduction, run.input.pairs, run.input.means)
      ?? (isTime(r.milliseconds) ? null : "The time of the reply is not a time.")
      ?? (r.stage === 2 ? checkStage(previous.reduction, r.reduction, r.method as StagedOrder) : null)
      ?? (groups && JSON.stringify(groups) !== JSON.stringify(r.reduction.groups)
        ? "The methods returned different groups." : null)
      ?? beforeDefect(run, r.reduction));
    if (defect) {
      fail({ title: "The solver returned an invalid result", message: defect, detail: "The page shows no result." });
      // The worker can hold more replies of this run. Start again from a clean worker.
      restartWorker();
    } else {
      run.results.push({ method: r.method, stage: r.stage, reduction: r.reduction, milliseconds: r.milliseconds });
    }
  } else if (r.type === "done") {
    finishRun(run);
  } else if (r.type === "error") {
    const problem = problemOf(r.kind, r.message);
    // The first stage finished and passed its checks; the error is in the experimental second stage,
    // whatever kind it names: the first stage accepted the same input. The stage is the one of the
    // next result, not of the last start reply, which can arrive later.
    const pending = run.expected[run.results.length];
    const second = pending !== undefined && !METHODS.some((m) => m.id === pending);
    fail(second
      ? { ...problem, title: "The second stage stopped with an error",
          detail: "The first stage finished. Clear \"Then minimize the other quantity\" to see its result." }
      : problem);
    // After a solver error, or any error of a second stage, the next run starts from a clean worker.
    if (r.kind !== "input" || second) restartWorker();
  } else {
    fail({ title: "The solver returned an invalid result", message: "The worker sent a reply that a run does not have.",
           detail: "The page shows no result." });
    restartWorker();
  }
  render();
}

/** A check that throws on a reply of an unexpected form counts as a failed check. */
function safely(check: () => string | null): string | null {
  try {
    return check();
  } catch {
    return "The reply has a form that the page cannot read.";
  }
}

const BEFORE_MISMATCH = "The display before reduction does not match the statistics of the package.";

/** Each result of a run has the counts before reduction of the first result and of the display before reduction. */
function beforeDefect(run: Run, reduction: CldReduction): string | null {
  const s = reduction.stats;
  const first = run.results[0]?.reduction.stats;
  if (first && (first.numLettersBefore !== s.numLettersBefore || first.assignmentsBefore !== s.assignmentsBefore)) {
    return "The results have different counts before reduction.";
  }
  const before = state.before && state.before.version === run.inputVersion ? state.before : null;
  return before && (before.letters !== s.numLettersBefore || before.assignments !== s.assignmentsBefore)
    ? BEFORE_MISMATCH : null;
}

function finishRun(run: Run): void {
  if (run.results.length !== run.expected.length) {
    fail({ title: "The solver returned an invalid result", message: "A method has no result.", detail: null });
    restartWorker();
    return;
  }
  const before = state.before && state.before.version === run.inputVersion ? state.before : null;
  if (!before) {
    // The page shows a result only with its checked display before reduction. Ask for it now if the
    // page has not asked yet, and wait for it.
    requestBefore();
    if (beforeRequest && beforeRequest.version === run.inputVersion) {
      run.waiting = true;
      return;
    }
    fail({ title: "The page cannot check the result", detail: "The page shows no result.",
           message: "The display before reduction of this input is not available, so the page cannot check the counts before reduction." });
    return;
  }
  const stats = run.results[0].reduction.stats;
  if (before.letters !== stats.numLettersBefore || before.assignments !== stats.assignmentsBefore) {
    // The page checked the display before reduction against the input, so the result is the wrong one.
    fail({ title: "The solver returned an invalid result", detail: "The page shows no result.", message: BEFORE_MISMATCH });
    restartWorker();
    return;
  }
  state.shown = { version: run.inputVersion, results: run.results, input: run.input, source: run.source, before };
  state.run = null;
}

// Input

/** The method or the second stage changed: stop a run and remove the result. */
function invalidate(): void {
  const had = state.run !== null || state.shown !== null;
  if (state.run) {
    state.run = null;
    restartWorker();
  }
  state.shown = null;
  state.problem = null;
  state.notice = had ? "The input or the method changed. Press Run to solve again." : null;
  render();
}

/** The input text changed: also compute the display before reduction again. */
function inputChanged(): void {
  state.inputVersion++;
  state.beforeNote = null;
  // A reply to the request in flight belongs to the earlier input.
  beforeRequest = null;
  clearTimeout(beforeTimer);
  beforeTimer = setTimeout(requestBefore, 250);
  invalidate();
}

function readInput(): Input {
  return { pairs: parsePairs(ui.pairs.value), means: parseMeans(ui.means.value) };
}

/** Ask the worker for the display before reduction of the current input, once for each version. */
function requestBefore(): void {
  clearTimeout(beforeTimer);
  if (state.solver !== "ready" || !worker || beforeVersion === state.inputVersion) return;
  beforeVersion = state.inputVersion;
  // A reply to an earlier request belongs to an earlier input.
  beforeRequest = null;
  let input: Input;
  try {
    input = readInput();
  } catch (e) {
    state.before = null;
    state.beforeNote = e instanceof Error ? e.message : String(e);
    render();
    return;
  }
  beforeRequest = { id: nextId++, version: state.inputVersion, input };
  worker.postMessage({ type: "before", id: beforeRequest.id, input } satisfies Request);
}

function setInput(pairs: string, means: string, source: string, example: Example | null, note: string | null): void {
  changed(ui.pairs, ui.means);
  ui.pairs.value = pairs;
  ui.means.value = means;
  state.example = example;
  state.source = source;
  state.sourceNote = note;
  inputChanged();
  state.notice = null;
  render();
}

function loadExample(example: Example): void {
  const pairs = example.pairsText ?? repository.examples[example.pairsFile!];
  setInput(pairs, example.meansFile ? repository.examples[example.meansFile] : "", example.title, example, null);
}

function wholeNumber(input: HTMLInputElement, min: number, max: number, fallback: number): number {
  const v = Number(input.value);
  const n = input.value.trim() !== "" && Number.isInteger(v) ? Math.min(max, Math.max(min, v)) : fallback;
  input.value = String(n);
  return n;
}

function generate(): void {
  const n = wholeNumber(ui.simN, 2, 80, 20);
  const seed = wholeNumber(ui.simSeed, 1, MAX_SEED, 1);
  const files = experimentCsv(simulate(n, seed));
  const next = seedAfter(seed, 1);
  setInput(files.pairs, files.means, `Simulated, ${n} treatments, seed ${seed}`, null,
           `Simulated experiment with ${n} treatments and seed ${seed}. The next Generate uses seed ${next}.`);
  ui.simSeed.value = String(next);
}

async function loadFile(file: File, target: HTMLTextAreaElement): Promise<void> {
  const what = target === ui.pairs ? "decisions" : "means";
  changed(target);
  const change = fieldChange.get(target);
  const tooLong = (): void => {
    state.problem = { title: `The ${what} could not be read`, detail: null,
                      message: `${file.name} has more characters than the page reads (${MAX_CHARS.toLocaleString("en-US")}).` };
    render();
  };
  // The limit counts characters. A character takes at most 3 bytes in UTF-8 (two for each half of a
  // pair), so a larger file cannot fit, and the page does not read it.
  if (file.size > 3 * MAX_CHARS + 3) {
    tooLong();
    return;
  }
  let text: string;
  try {
    text = await file.text();
  } catch {
    if (fieldChange.get(target) !== change) return;
    state.problem = { title: `The ${what} could not be read`, message: `${file.name} could not be read.`, detail: null };
    render();
    return;
  }
  // The field changed during the read: an example, an edit, Reset, or a later file.
  if (fieldChange.get(target) !== change) return;
  if (text.length > MAX_CHARS) {
    tooLong();
    return;
  }
  target.value = text;
  state.example = null;
  state.sourceNote = null;
  if (target === ui.pairs) state.source = file.name;
  inputChanged();
}

function download(name: string, text: string, type: string): void {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = el("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function slug(text: string): string {
  return text.replace(/\.[^.]+$/, "").replace(/[^\w-]+/g, "-").replace(/^-+|-+$/g, "").toLowerCase() || "result";
}

// Run

function startRun(methods: Method[]): void {
  if (state.solver !== "ready" || state.run || state.study?.status === "running") return;
  state.shown = null;
  state.problem = null;
  state.notice = null;
  let input: Input;
  let reading = "decisions";
  try {
    const pairs = parsePairs(ui.pairs.value);
    reading = "means";
    input = { pairs, means: parseMeans(ui.means.value) };
  } catch (e) {
    state.problem = { title: `The ${reading} could not be read`, detail: null,
                      message: e instanceof DataError || e instanceof Error ? e.message : String(e) };
    render();
    return;
  }
  // The display before reduction goes first, so that it is ready with the result.
  requestBefore();
  // Each method runs with its second stage, and the page shows the second stage under the name of the method.
  const staged = true;
  const expected = methods.flatMap((m): ResultMethod[] => [m, SECOND_STAGE[m]]);
  state.run = { id: nextId++, methods, expected, input, inputVersion: state.inputVersion, source: state.source,
                results: [], current: methods[0], stage: 1, currentStart: performance.now() };
  worker!.postMessage({ type: "run", id: state.run.id, input, methods, staged } satisfies Request);
  render();
}

function cancelRun(): void {
  const run = state.run;
  if (!run) return;
  state.run = null;
  restartWorker();
  // Cancel keeps the results that arrived, as finishRun shows them: checked, and with their checked
  // display before reduction. So a slow second minimization leaves the display of the first.
  const before = state.before && state.before.version === run.inputVersion ? state.before : null;
  const stats = run.results[0]?.reduction.stats;
  if (stats && before && before.letters === stats.numLettersBefore && before.assignments === stats.assignmentsBefore) {
    state.shown = { version: run.inputVersion, results: run.results, input: run.input, source: run.source, before };
    state.notice = run.stage === 2
      ? `Cancel stopped the second minimization of ${shownName(run.current)}. Its column shows the display of the first minimization.`
      : `Cancel stopped ${shownName(run.current)}. The page shows the methods that finished.`;
  } else {
    state.notice = "The run was cancelled.";
  }
  render();
}

function reset(): void {
  if (state.run) {
    state.run = null;
    restartWorker();
  }
  document.querySelector<HTMLInputElement>('input[name="method"][value="letter_minimum"]')!.checked = true;
  loadExample(EXAMPLES[0]);
}

// Study

function studyPlan(): Study | string {
  const from = wholeNumber(ui.studyFrom, 2, 80, 10);
  const to = wholeNumber(ui.studyTo, 2, 80, 45);
  const step = wholeNumber(ui.studyStep, 1, 40, 5);
  const countEach = wholeNumber(ui.studyCount, 1, 1000, 10);
  const firstSeed = wholeNumber(ui.studySeed, 1, MAX_SEED, 1);
  const timeLimit = wholeNumber(ui.studyLimit, 1, 600, 30);
  if (from > to) return "The first number of treatments must not be larger than the last.";
  const sizes: number[] = [];
  for (let n = from; n <= to; n += step) sizes.push(n);
  return { sizes, count: countEach, firstSeed, timeLimit };
}

function startStudy(): void {
  if (state.solver !== "ready" || state.run || state.study?.status === "running") return;
  const study = studyPlan();
  if (typeof study === "string") {
    ui.studyHint.textContent = study;
    return;
  }
  state.study = { id: nextId++, study, total: study.sizes.length * study.count, instances: [], status: "running",
                  message: null, started: performance.now(), ended: null };
  worker!.postMessage({ type: "study", id: state.study.id, study } satisfies Request);
  render();
}

function endStudy(status: StudyRun["status"], message: string | null): void {
  if (!state.study) return;
  state.study.status = status;
  state.study.message = message;
  state.study.ended = performance.now();
}

// A study can have 79,000 instances. The page draws its tables at most every 250 ms, not for each instance.
let studyTimer: ReturnType<typeof setTimeout> | undefined;
function drawStudySoon(): void {
  if (studyTimer === undefined) studyTimer = setTimeout(() => { studyTimer = undefined; render(); }, 250);
}

function onStudyReply(r: Reply): void {
  const run = state.study!;
  let defect: string | null = null;
  if (r.type === "instance") {
    const next = planned(run.study, run.instances.length);
    defect = next ? safely(() => checkInstance(r.instance, next.n, next.seed, instanceFacts(next.n, next.seed), run.study.timeLimit))
      : "The worker sent more instances than the study has.";
    if (!defect) {
      run.instances.push(r.instance);
      drawStudySoon();
      return;
    }
  } else if (r.type === "done") {
    if (run.instances.length === run.total) endStudy("done", null);
    else defect = "The study ended before all its instances were solved.";
  } else if (r.type === "error") {
    endStudy("error", r.message);
    restartWorker();
  } else {
    defect = "The worker sent a reply that a study does not have.";
  }
  if (defect) {
    endStudy("error", `The solver returned an invalid result. ${defect}`);
    // The worker can hold more replies of this study. Start again from a clean worker.
    restartWorker();
  }
  render();
}

function cancelStudy(): void {
  if (state.study?.status !== "running") return;
  endStudy("cancelled", null);
  restartWorker();
  render();
}

function showView(view: "reduce" | "study"): void {
  state.view = view;
  render();
}

// Rendering

function renderStatus(): void {
  ui.status.classList.toggle("is-error", state.solver === "failed");
  ui.status.textContent = state.solver === "failed" ? `The solver could not start: ${state.solverMessage}`
    : state.solver === "loading" ? "Loading the solver…"
    : state.run || state.study?.status === "running" ? "Solving…" : "Solver ready";
  ui.reduceView.hidden = state.view !== "reduce";
  ui.studyView.hidden = state.view !== "study";
  ui.viewReduce.setAttribute("aria-pressed", String(state.view === "reduce"));
  ui.viewStudy.setAttribute("aria-pressed", String(state.view === "study"));
}

const exampleButtons = new Map<string, HTMLButtonElement>();

/** Build the example buttons once, so that focus survives a render. */
function buildExamples(): void {
  for (const example of EXAMPLES) {
    const b = button("example", example.title, ui.examples, () => loadExample(example));
    exampleButtons.set(example.id, b);
  }
}

function renderControls(): void {
  for (const [id, b] of exampleButtons) b.setAttribute("aria-pressed", String(state.example?.id === id));
  const example = state.example;
  ui.exampleNote.hidden = !example && !state.sourceNote;
  ui.exampleNote.replaceChildren();
  if (example) {
    ui.exampleNote.append(`${example.description} Source: `);
    example.sources.forEach((source, k) => {
      if (k > 0) ui.exampleNote.append("; ");
      const a = el("a", undefined, source.text, ui.exampleNote);
      a.href = source.url;
      a.target = "_blank";
      a.rel = "noopener";
    });
    ui.exampleNote.append(".");
  } else if (state.sourceNote) {
    ui.exampleNote.textContent = state.sourceNote;
  }

  const running = state.run !== null;
  const studying = state.study?.status === "running";
  ui.run.textContent = running ? "Cancel" : "Run";
  ui.run.classList.toggle("is-cancel", running);
  ui.run.disabled = !running && (state.solver !== "ready" || studying);
  ui.compare.disabled = running || studying || state.solver !== "ready";
  for (const field of studyFields) field.disabled = studying;
  ui.runHint.textContent = state.solver === "failed" ? "The solver is not available."
    : studying ? "The simulation study is running."
    : running ? (!state.run!.results.length ? "Cancel stops the solver."
      : state.run!.stage === 2 ? "Cancel keeps the display of the first minimization." : "Cancel keeps the methods that finished.")
    : state.solver === "loading" ? "Waiting for the solver…" : "";

  ui.studyRun.textContent = studying ? "Cancel" : "Run the study";
  ui.studyRun.classList.toggle("is-cancel", studying);
  ui.studyRun.disabled = !studying && (state.solver !== "ready" || running);
}

function renderResults(): void {
  const host = ui.results;
  host.replaceChildren();
  if (state.problem) renderProblem(host, state.problem);
  const before = currentBefore();
  if (state.run) {
    renderRunning(host, state.run);
  } else if (state.shown) {
    if (state.notice) el("p", "notice", state.notice, host).setAttribute("role", "status");
    renderShown(host, state.shown);
  } else {
    if (state.notice) el("p", "notice", state.notice, host).setAttribute("role", "status");
    if (!state.problem) renderIntro(host);
    if (before) {
      const head = el("section", "headline is-before", undefined, host);
      el("h2", "headline-title", `Before reduction: ${count(before.letters, "letter", "letters")} and ` +
         `${count(before.assignments, "assignment", "assignments")}`, head);
      el("p", "headline-text", "One letter for each maximal clique. Press Run to reduce it. The reduced letters appear next to these.", head);
      el("p", "muted", `${state.source}. Computed in ${duration(before.milliseconds)} in this browser.`, head);
    } else if (!state.problem) {
      const empty = el("div", "empty", undefined, host);
      el("p", undefined,
         "Give one row for each pair of groups, with the decision of your analysis: significant or not significant. " +
         "Choose a method, then press Run.", empty);
      if (state.beforeNote) el("p", "hint", `The display before reduction is not available: ${state.beforeNote}`, empty);
    }
  }
  const shownBefore = state.shown ? state.shown.before : before;
  const results = state.shown ? finalsOf(state.shown.results) : [];
  const means = state.shown ? state.shown.input.means : state.run ? state.run.input.means : meansForBefore();
  if (shownBefore || results.length) renderLetters(host, shownBefore, results, means);
  if (state.shown) renderMatrices(host, state.shown);
}

/** What the page is for, until the first result. */
function renderIntro(host: HTMLElement): void {
  const intro = el("section", "intro", undefined, host);
  el("h2", "intro-title", "Simpler letter displays, with the same conclusions", intro);
  el("p", undefined,
     "In a compact letter display, groups that are not significantly different share a letter. " +
     "The Before column starts from one letter for each maximal clique, and such a display can hold more letters " +
     "than the decisions need. CLD-C finds the display with the fewest distinct letters. CLD-sigma finds the display " +
     "with the fewest letters in the table. Every pair keeps its decision.", intro);
  el("p", "intro-note", "The solve runs in this browser. Your data does not leave this computer.", intro);
}

/** A row of numbers under a headline: a label, a value, and a note for each. */
function renderStats(host: HTMLElement, stats: readonly (readonly [string, string, string])[]): void {
  const dl = el("dl", "stats", undefined, host);
  for (const [label, value, note] of stats) {
    const stat = el("div", "stat", undefined, dl);
    el("dt", undefined, label, stat);
    el("dd", "stat-value", value, stat);
    el("dd", "stat-note", note, stat);
  }
}

/** The means of the current input for the before column, when they can be read. */
function meansForBefore(): Input["means"] {
  try {
    return parseMeans(ui.means.value);
  } catch {
    return null;
  }
}

function renderProblem(host: HTMLElement, problem: Problem): void {
  const box = el("section", "problem", undefined, host);
  box.setAttribute("role", "alert");
  el("h2", undefined, problem.title, box);
  el("p", "problem-message", problem.message, box);
  if (problem.detail) el("p", undefined, problem.detail, box);
  button("button-secondary", "Clear", box, () => {
    state.problem = null;
    render();
    ui.run.focus();
  });
}

function renderRunning(host: HTMLElement, run: Run): void {
  const head = el("section", "headline", undefined, host);
  if (run.waiting) {
    el("h2", "headline-title", "Waiting for the display before reduction…", head);
    el("p", "muted", "The page checks the result against it before it shows the result.", head);
    return;
  }
  el("h2", "headline-title", `Solving with ${shownName(run.current)}…`, head);
  const step = run.expected.length > 1 ? `Step ${run.results.length + 1} of ${run.expected.length}. ` : "";
  const p = el("p", "muted", `${step}${run.stage === 1 ? "First" : "Second"} minimization. `, head);
  const time = el("span", "live-time", duration(performance.now() - run.currentStart), p);
  time.dataset.start = String(run.currentStart);
}

/** The result of each method after its last stage. */
const finalsOf = (results: readonly MethodResult[]): MethodResult[] =>
  results.filter((r, k) => r.stage === 2 || results[k + 1]?.stage !== 2);

/** The package method of a result: the method itself, or the method that a second stage follows. */
function packageMethod(method: ResultMethod): Method {
  return METHODS.find((m) => m.id === method || SECOND_STAGE[m.id] === method)!.id;
}

/** The page shows a second stage under the name of its method: CLD-C is CLD-C then CLD-sigma. */
const shownName = (method: ResultMethod): string => methodInfo(packageMethod(method)).name;

/** What a method of the page minimizes, with its second stage. */
const MINIMIZES: Record<Method, string> = {
  letter_minimum: "Distinct letters, then assignments",
  assignment_minimum: "Assignments, then distinct letters",
};

/** The time of a final result: both stages when it is a second stage. */
function totalTime(results: readonly MethodResult[], r: MethodResult): number {
  const k = results.indexOf(r);
  return r.stage === 2 && k > 0 ? results[k - 1].milliseconds + r.milliseconds : r.milliseconds;
}

function renderShown(host: HTMLElement, shown: Shown): void {
  const { results } = shown;
  const finals = finalsOf(results);
  const both = (r: MethodResult): string => {
    const s = r.reduction.stats;
    return `${count(s.numLettersAfter, "letter", "letters")} and ${count(s.assignmentsAfter, "assignment", "assignments")}`;
  };
  const s0 = results[0].reduction.stats;
  const removed = (r: MethodResult): string => {
    const s = r.reduction.stats;
    return `${count(s.assignmentsBefore - s.assignmentsAfter, "assignment", "assignments")}, ` +
      `${count(s.numLettersBefore - s.numLettersAfter, "letter", "letters")}`;
  };
  const head = el("section", "headline", undefined, host);
  let times: string;
  if (finals.length === 1) {
    const last = finals[0];
    const s = last.reduction.stats;
    el("h2", "headline-title", `${shownName(last.method)}: ${both(last)}`, head);
    renderStats(head, [
      ["Distinct letters", String(s.numLettersAfter), `${s.numLettersBefore} before`],
      ["Assignments", String(s.assignmentsAfter), `${s.assignmentsBefore} before`],
      ["Removed", `${s.reductionPct.toFixed(1)}%`, removed(last)],
    ]);
    times = last.stage === 2
      ? `${shownName(last.method)} took ${duration(totalTime(results, last))} in this browser: ` +
        `${duration(results[results.indexOf(last) - 1].milliseconds)} for the first minimization and ` +
        `${duration(last.milliseconds)} for the second.`
      : `${shownName(last.method)} took ${duration(last.milliseconds)} in this browser.`;
  } else {
    el("h2", "headline-title", "CLD-C and CLD-sigma", head);
    renderStats(head, [
      ["Before reduction", count(s0.numLettersBefore, "letter", "letters"), count(s0.assignmentsBefore, "assignment", "assignments")],
      ...finals.map((r): [string, string, string] => [shownName(r.method),
        count(r.reduction.stats.numLettersAfter, "letter", "letters"),
        `${count(r.reduction.stats.assignmentsAfter, "assignment", "assignments")}, ${r.reduction.stats.reductionPct.toFixed(1)}% fewer`]),
    ]);
    times = `All solves together took ${duration(results.reduce((t, r) => t + r.milliseconds, 0))} in this browser.`;
  }
  const pairs = s0.numGroups * (s0.numGroups - 1) / 2;
  el("p", "muted",
     `${shown.source}: ${count(s0.numGroups, "group", "groups")} and ${count(pairs, "pair", "pairs")}. ` +
     `${count(s0.numEdges, "pair is", "pairs are")} not significantly different.`, head);
  el("p", "muted", times, head);
  const actions = el("div", "actions", undefined, head);
  const name = slug(shown.source);
  button("button-secondary", "Download CSV", actions,
         () => download(`cld-${name}.csv`, resultsCsv(results, shown.input.means, shown.before), "text/csv"));
  button("button-secondary", "Download JSON", actions, () => download(`cld-${name}.json`,
         resultsJson(results, { source: shown.source, pairs: shown.input.pairs.length, means: shown.input.means },
                     repository.version, shown.before), "application/json"));

  // Summary: one column before reduction and one for each method, so that both quantities are side by side.
  // It opens over the page from its button, so that the letters stay where they are.
  const open = button("button-secondary summary-button", "Summary", actions, () => {});
  const summary = el("section", "summary-pop", undefined, actions);
  summary.id = "summary";
  summary.popover = "auto";
  summary.setAttribute("aria-labelledby", "summary-title");
  open.popoverTargetElement = summary;
  // Before it opens, the panel goes under its button, so it never shows elsewhere; once it is open and
  // has a size, it moves inside the window.
  summary.addEventListener("beforetoggle", (e) => {
    if ((e as ToggleEvent).newState !== "open") return;
    const r = open.getBoundingClientRect();
    summary.style.left = `${Math.max(16, r.left)}px`;
    summary.style.top = `${r.bottom + 8}px`;
    summary.style.bottom = "auto";
  });
  summary.addEventListener("toggle", () => placeSummary());
  const top = el("div", "pop-head", undefined, summary);
  el("h3", undefined, "Summary", top).id = "summary-title";
  const close = button("button-secondary", "Close", top, () => {});
  close.popoverTargetElement = summary;
  close.popoverTargetAction = "hide";
  const table = el("table", "data-table summary-table", undefined, el("div", "table-wrap", undefined, summary));
  const headRow = el("tr", undefined, undefined, el("thead", undefined, undefined, table));
  el("td", undefined, undefined, headRow);
  const before = shown.before;
  if (before) el("th", "num", "Before", headRow).scope = "col";
  for (const r of finals) el("th", "num", shownName(r.method), headRow).scope = "col";
  const body = el("tbody", undefined, undefined, table);
  const line = (label: string, beforeText: string, value: (r: MethodResult) => string, cls = "num"): void => {
    const tr = el("tr", undefined, undefined, body);
    el("th", undefined, label, tr).scope = "row";
    if (before) el("td", cls, beforeText, tr);
    for (const r of finals) el("td", cls, value(r), tr);
  };
  line("Minimizes", "One letter for each maximal clique",
       (r) => (r.stage === 2 ? MINIMIZES[packageMethod(r.method)] : methodInfo(r.method).minimizes), "num wrap");
  line("Distinct letters", before ? String(before.letters) : "", (r) => String(r.reduction.stats.numLettersAfter));
  line("Assignments", before ? String(before.assignments) : "", (r) => String(r.reduction.stats.assignmentsAfter));
  line("Assignments removed", "", (r) => {
    const s = r.reduction.stats;
    return `${s.assignmentsBefore - s.assignmentsAfter} (${s.reductionPct.toFixed(1)}%)`;
  });
  line("Letters removed", "", (r) => String(r.reduction.stats.numLettersBefore - r.reduction.stats.numLettersAfter));
  line("Relationships preserved", "", (r) => (r.reduction.relationshipPreserved ? "Yes" : "No"));
  line("Time in this browser", before ? duration(before.milliseconds) : "", (r) => duration(totalTime(results, r)));
  el("p", "hint",
     "Each method first minimizes its own quantity, then the other quantity among the displays that keep that minimum. " +
     "The R, Python, and npm packages stop after the first minimization; Download JSON has both. " +
     "The time covers both minimizations. The relationship check gives back every input decision from the letters.", summary);
}

/** Place the open summary under its button, inside the window. */
function placeSummary(): void {
  const panel = document.getElementById("summary");
  const anchor = document.querySelector<HTMLElement>(".summary-button");
  if (!panel || !anchor || !panel.matches(":popover-open")) return;
  const r = anchor.getBoundingClientRect();
  const margin = 16;
  const width = Math.min(panel.offsetWidth, innerWidth - 2 * margin);
  panel.style.left = `${Math.max(margin, Math.min(r.left, innerWidth - width - margin))}px`;
  const below = innerHeight - r.bottom - margin - 8;
  const above = r.top - margin - 8;
  if (below >= Math.min(panel.scrollHeight, 320) || below >= above) {
    panel.style.top = `${r.bottom + 8}px`;
    panel.style.bottom = "auto";
    panel.style.maxHeight = `${Math.max(below, 120)}px`;
  } else {
    panel.style.top = "auto";
    panel.style.bottom = `${innerHeight - r.top + 8}px`;
    panel.style.maxHeight = `${above}px`;
  }
}

function renderLetters(host: HTMLElement, before: BeforeRows | null, results: readonly MethodResult[],
                       means: Input["means"]): void {
  const section = el("section", "panel-block", undefined, host);
  el("h3", undefined, results.length ? "Letters before and after reduction" : "Letters before reduction", section);
  const table = el("table", "data-table letters-table", undefined, el("div", "table-wrap", undefined, section));
  const headRow = el("tr", undefined, undefined, el("thead", undefined, undefined, table));
  el("th", undefined, "Group", headRow).scope = "col";
  const meanOf = means === null ? null : new Map(means.map((m) => [m.group, m.mean]));
  if (meanOf) el("th", "num", "Mean", headRow).scope = "col";
  if (before) el("th", undefined, "Before", headRow).scope = "col";
  for (const r of results) el("th", undefined, shownName(r.method), headRow).scope = "col";
  const body = el("tbody", undefined, undefined, table);
  const rows = before?.rows ?? results[0].reduction.rows;
  rows.forEach((row, i) => {
    const tr = el("tr", undefined, undefined, body);
    el("th", "label", row.group, tr).scope = "row";
    if (meanOf) el("td", "num", meanOf.has(row.group) ? meanText(meanOf.get(row.group)!) : "", tr);
    if (before) el("td", "letters before", before.rows[i].letters, tr);
    for (const r of results) el("td", "letters", r.reduction.rows[i].letters, tr);
  });
}

function renderMatrices(host: HTMLElement, shown: Shown): void {
  for (const r of finalsOf(shown.results)) {
    const section = el("section", "panel-block", undefined, host);
    el("h3", undefined, `Shared letters, ${shownName(r.method)}`, section);
    const groups = r.reduction.groups;
    if (groups.length > MAX_MATRIX_GROUPS) {
      el("p", "muted", `The page shows this matrix for up to ${MAX_MATRIX_GROUPS} groups. This input has ${groups.length}.`, section);
      continue;
    }
    el("p", "hint",
       "A cell holds the letters that the row group and the column group share. " +
       "Two groups share a letter exactly when the input says that they are not significantly different. " +
       "An empty cell is a significant difference.", section);
    const tokens = r.reduction.rows.map((row) => tokensOf(row.assignments));
    const matrix = el("table", "data-table matrix", undefined, el("div", "table-wrap", undefined, section));
    const top = el("tr", undefined, undefined, el("thead", undefined, undefined, matrix));
    el("td", undefined, undefined, top);
    // A long label is cut in the matrix, so the full label is also the tooltip.
    const label = (g: string, parent: Element, scope: string): void => {
      const th = el("th", "label", g, parent);
      th.scope = scope;
      th.title = g;
    };
    for (const g of groups) label(g, top, "col");
    const matrixBody = el("tbody", undefined, undefined, matrix);
    groups.forEach((g, i) => {
      const tr = el("tr", undefined, undefined, matrixBody);
      label(g, tr, "row");
      groups.forEach((_, j) => {
        const shared = sharedTokens(tokens, i, j);
        const td = el("td", i === j ? "is-self" : shared.length ? undefined : "is-different", displayOf(shared), tr);
        if (shared.length === 0) el("span", "visually-hidden", "different", td);
      });
    });
  }
}

function studyHint(run: StudyRun): string {
  const done = run.instances.length;
  const elapsed = (run.ended ?? performance.now()) - run.started;
  return run.status === "running" ? `Instance ${done + 1} of ${run.total}. ${duration(elapsed)} so far.`
    : run.status === "cancelled" ? `Cancelled after ${done} of ${run.total} instances.`
    : run.status === "error" ? `The study stopped with an error after ${done} instances: ${run.message}`
    : `Done: ${run.total} instances in ${duration(elapsed)}.`;
}

// The study drawn last. The page draws the study tables again only when the study changes, not on
// each render: a render can come from a key stroke in another field.
let studyDrawn: { run: StudyRun | null; count: number; status: string } = { run: null, count: -1, status: "" };

function renderStudy(): void {
  const run = state.study;
  const host = ui.studyResults;
  if (!run) {
    host.replaceChildren();
    studyDrawn = { run: null, count: -1, status: "" };
    ui.studyHint.textContent = state.solver === "ready" ? "" : "Waiting for the solver…";
    return;
  }
  ui.studyHint.textContent = studyHint(run);
  if (studyDrawn.run === run && studyDrawn.count === run.instances.length && studyDrawn.status === run.status) return;
  studyDrawn = { run, count: run.instances.length, status: run.status };
  host.replaceChildren();
  const done = run.instances.length;
  if (!done) return;

  const rows = summarize(run.instances);
  const slowestTime = slowest(run.instances);
  const finished = rows.reduce((t, r) => t + r.finished, 0);
  const head = el("section", "headline", undefined, host);
  el("p", "headline-text",
     `${finished} of ${count(done, "instance", "instances")} finished all four solves under the limit of ` +
     `${run.study.timeLimit} s. The slowest solve took ${duration(slowestTime ?? 0)}.`, head);
  const actions = el("div", "actions", undefined, head);
  button("button-secondary", "Download instances (CSV)", actions,
         () => download("cld-simulation-study.csv", studyCsv(run.instances), "text/csv"));

  const fixed = (v: number | null): string => (v === null ? "" : v.toFixed(1));
  const table = (title: string, note: string, heads: string[], body: string[][]): void => {
    const section = el("section", "panel-block", undefined, host);
    el("h3", undefined, title, section);
    el("p", "hint", note, section);
    const t = el("table", "data-table study-table", undefined, el("div", "table-wrap", undefined, section));
    const tr = el("tr", undefined, undefined, el("thead", undefined, undefined, t));
    heads.forEach((h, k) => { el("th", k === 0 ? undefined : "num", h, tr).scope = "col"; });
    const tb = el("tbody", undefined, undefined, t);
    for (const row of body) {
      const r = el("tr", undefined, undefined, tb);
      row.forEach((cell, k) => { if (k === 0) el("th", undefined, cell, r).scope = "row"; else el("td", "num", cell, r); });
    }
  };
  table("Letters and assignments", "Means over the instances of each size. A solve that did not finish under the limit is left out of its mean.",
        ["Treatments", "Instances", "Letters before", "Assignments before", "CLD-C letters", "CLD-sigma assignments",
         "Assignments removed by CLD-sigma", "CLD-C then CLD-sigma assignments", "CLD-sigma then CLD-C letters",
         "Letter minimum not assignment minimum"],
        rows.map((r) => [String(r.n), String(r.instances), fixed(r.lettersBefore), fixed(r.assignmentsBefore),
          fixed(r.value.letter_minimum), fixed(r.value.assignment_minimum),
          r.assignmentsRemoved === null ? "" : `${(100 * r.assignmentsRemoved).toFixed(1)}%`,
          fixed(r.value.letter_then_assignment), fixed(r.value.assignment_then_letter), `${r.tradeOff} of ${r.tradeOffKnown}`]));
  table("Time in this browser", "Mean and maximum time of each solve that ran, also of a solve that reached the limit. " +
        "A time covers the whole call, with the enumeration of the maximal cliques. A stage 2 time covers the whole second stage, not stage 1. " +
        "A second stage does not run when its first stage does not finish, and it is not in these times.",
        ["Treatments", "CLD-C mean", "CLD-C max", "CLD-sigma mean", "CLD-sigma max", "Stage 2 after CLD-C mean",
         "Stage 2 after CLD-C max", "Stage 2 after CLD-sigma mean", "Stage 2 after CLD-sigma max",
         "All four solves under the limit"],
        rows.map((r) => [String(r.n), ...ALL_METHODS.flatMap((m) => [r.mean[m], r.max[m]].map((t) => (t === null ? "" : duration(t)))),
                         `${r.finished} of ${r.instances}`]));
  const published = rows.flatMap((r) => {
    const x = TABLE_X.find((t) => t.n === r.n);
    return x ? [[String(r.n), `${(100 * r.sigmaFinished / r.instances).toFixed(1)}%`, `${x.pc.toFixed(1)}%`,
                 fixed(r.sigmaBefore), x.ma.toFixed(1), fixed(r.value.assignment_minimum), x.ea.toFixed(1),
                 r.sigmaTime === null ? "" : duration(r.sigmaTime), `${x.et.toFixed(3)} s`,
                 `${r.tradeOff} of ${r.tradeOffKnown}`, `${TABLE_XI[r.n] ?? 0} of 1,000`]] : [];
  });
  // Table X counts a search as finished in under 30 seconds. Another limit gives other finished sets.
  if (published.length && run.study.timeLimit !== 30) {
    el("p", "hint", "The comparison with Table X of the 2012 paper needs a time limit of 30 seconds, as in 2012.",
       el("section", "panel-block", undefined, host));
  } else if (published.length) {
    table("Compared with 2012",
          "Here: CLD-sigma on the instances above. 2012: FIND-AM in Table X and Table XI of Ennis, Fayle, and Ennis (2012), " +
          "1,000 other instances for each size on 2012 hardware. Both columns of a pair average the assignments and the time over " +
          "the exact solves that finished in under 30 seconds. Here a solve finishes when its whole time, with the enumeration of " +
          "the maximal cliques, is under 30 seconds; the paper does not say whether its limit includes the enumeration. The instances here follow the published model text and have larger maximal displays " +
          "than Table X reports, so read the two as separate studies.",
          ["Treatments", "Finished, here", "Finished, 2012", "Assignments before, here", "MA, 2012",
           "Exact assignments, here", "EA, 2012", "Mean time, here", "ET, 2012",
           "Letter minimum not assignment minimum, here", "Table XI, 2012"], published);
  }
}

function render(): void {
  renderStatus();
  renderControls();
  renderResults();
  renderStudy();
}

// The Run bar stays at the bottom of its side panel. The panel scrolls a focused control above the bar,
// not behind it.
for (const bar of document.querySelectorAll<HTMLElement>(".run-bar")) {
  new ResizeObserver(() => { bar.parentElement!.style.scrollPaddingBottom = `${bar.offsetHeight + 8}px`; }).observe(bar);
}

// Light and dark mode. The page follows the system until the user picks one; the pick is kept in this browser.
const THEME_KEY = "cld-reducer-theme";
const systemDark = matchMedia("(prefers-color-scheme: dark)");
const theme = (): "light" | "dark" => {
  const set = document.documentElement.dataset.theme;
  return set === "light" || set === "dark" ? set : systemDark.matches ? "dark" : "light";
};
function renderTheme(): void {
  const dark = theme() === "dark";
  ui.theme.setAttribute("aria-label", dark ? "Switch to light mode" : "Switch to dark mode");
  ui.theme.title = dark ? "Light mode" : "Dark mode";
  ui.theme.querySelector<SVGElement>(".icon-sun")!.style.display = dark ? "" : "none";
  ui.theme.querySelector<SVGElement>(".icon-moon")!.style.display = dark ? "none" : "";
}
ui.theme.addEventListener("click", () => {
  const next = theme() === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = next;
  try {
    localStorage.setItem(THEME_KEY, next);
  } catch {
    // Without storage, the pick lasts until the page closes.
  }
  renderTheme();
});
systemDark.addEventListener("change", renderTheme);
renderTheme();

// The open summary follows its button when the page scrolls or the window changes size.
for (const target of [window, ui.results.parentElement!]) target.addEventListener("scroll", placeSummary, { passive: true });
window.addEventListener("resize", placeSummary);

// Live time of the running solve and of the study.
setInterval(() => {
  for (const cell of ui.results.querySelectorAll<HTMLElement>(".live-time")) {
    cell.textContent = duration(performance.now() - Number(cell.dataset.start));
  }
  if (state.study?.status === "running") ui.studyHint.textContent = studyHint(state.study);
}, 200);

// Events

ui.viewReduce.addEventListener("click", () => showView("reduce"));
ui.viewStudy.addEventListener("click", () => showView("study"));
ui.run.addEventListener("click", () => {
  if (state.run) cancelRun();
  else startRun([selectedMethod()]);
});
ui.compare.addEventListener("click", () => startRun(METHODS.map((m) => m.id)));
ui.reset.addEventListener("click", reset);
ui.simGenerate.addEventListener("click", generate);
ui.studyRun.addEventListener("click", () => {
  if (state.study?.status === "running") cancelStudy();
  else startStudy();
});
// The fields cannot change during a study. A change after it removes its results, which belong to the old fields.
for (const field of studyFields) {
  field.addEventListener("input", () => {
    if (state.study && state.study.status !== "running") {
      state.study = null;
      render();
    }
  });
}

for (const area of [ui.pairs, ui.means]) {
  area.addEventListener("input", () => {
    changed(area);
    state.example = null;
    state.sourceNote = null;
    if (area === ui.pairs) state.source = "Pasted text";
    inputChanged();
  });
}
for (const radio of document.querySelectorAll<HTMLInputElement>('input[name="method"]')) {
  radio.addEventListener("change", invalidate);
}

for (const [name, area, template] of [["pairs", ui.pairs, TEMPLATE_PAIRS], ["means", ui.means, TEMPLATE_MEANS]] as const) {
  const file = $<HTMLInputElement>(`${name}-file`);
  $(`${name}-choose`).addEventListener("click", () => file.click());
  file.addEventListener("change", () => {
    const f = file.files?.[0];
    if (f) void loadFile(f, area);
    file.value = "";
  });
  $(`${name}-template`).addEventListener("click", () => download(`cld-${name}-template.csv`, template, "text/csv"));

  // Only a file drag is taken here. A drag of text goes into the field as usual.
  const zone = $(`${name}-field`);
  let depth = 0;
  zone.addEventListener("dragenter", (e) => {
    if (!hasFile(e)) return;
    e.preventDefault();
    depth++;
    zone.classList.add("is-over");
  });
  zone.addEventListener("dragleave", (e) => {
    if (hasFile(e) && --depth <= 0) { depth = 0; zone.classList.remove("is-over"); }
  });
  zone.addEventListener("drop", (e) => {
    depth = 0;
    zone.classList.remove("is-over");
    const f = e.dataTransfer?.files?.[0];
    if (f) void loadFile(f, area);
  });
}
// A dropped file must not open in the tab, in a field or outside it.
function hasFile(e: DragEvent): boolean {
  return e.dataTransfer?.types.includes("Files") ?? false;
}
for (const type of ["dragover", "drop"] as const) {
  window.addEventListener(type, (e) => { if (hasFile(e)) e.preventDefault(); });
}

buildExamples();
loadExample(EXAMPLES[0]);
void startSolver();
