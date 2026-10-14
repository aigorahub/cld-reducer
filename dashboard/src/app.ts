// The page: read the input, run cld-reducer in a worker, and show the result.

import wasmGzipBase64 from "virtual:highs-wasm";
import repository from "virtual:repository";
import workerSource from "virtual:worker-source";
import { DataError, MAX_CHARS, TEMPLATE_MEANS, TEMPLATE_PAIRS, parseMeans, parsePairs } from "./csv.js";
import { EXAMPLES, METHODS, checkReduction, count, displayOf, duration, explain, meanText, methodInfo, resultsCsv,
         resultsJson, sharedTokens, tokensOf, type Example, type Method, type MethodResult } from "./data.js";
import type { Input, Reply, Request } from "./worker.js";

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
  examples: $("examples"),
  exampleNote: $("example-note"),
  pairs: $<HTMLTextAreaElement>("pairs"),
  means: $<HTMLTextAreaElement>("means"),
  run: $<HTMLButtonElement>("run"),
  compare: $<HTMLButtonElement>("compare"),
  reset: $<HTMLButtonElement>("reset"),
  runHint: $("run-hint"),
  results: $("results"),
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
  input: Input;
  source: string;
  results: MethodResult[];
  current: Method;
  currentStart: number;
}

/** A finished run. The page shows it until the input or the method changes. */
interface Shown {
  results: MethodResult[];
  input: Input;
  source: string;
}

interface Problem {
  title: string;
  message: string;
  detail: string | null;
}

const state = {
  solver: "loading" as "loading" | "ready" | "failed",
  solverMessage: "",
  example: null as Example | null,
  /** Name of the input for the result files: an example, a file, or pasted text. */
  source: "Pasted text",
  run: null as Run | null,
  shown: null as Shown | null,
  problem: null as Problem | null,
  notice: null as string | null,
};

let nextId = 1;

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
  let w: Worker;
  try {
    w = new Worker(workerUrl, { name: "cld-reducer-solver" });
  } catch (e) {
    solverFailed(e instanceof Error ? e.message : String(e));
    return;
  }
  worker = w;
  let ready = false;
  w.onmessage = (e: MessageEvent<Reply>) => {
    if (w !== worker) return;
    const r = e.data;
    if (ready) { onReply(r); return; }
    if (r.type === "ready") {
      ready = true;
      state.solver = "ready";
      render();
    } else if (r.type === "error") {
      w.terminate();
      solverFailed(r.message);
    }
  };
  w.onerror = (e) => {
    e.preventDefault();
    if (w !== worker) return;
    w.terminate();
    const message = e.message || "The solver worker stopped.";
    if (!ready) { solverFailed(message); return; }
    // The worker failed after it started: end the run and start a new worker.
    if (state.run) fail({ title: "The solver stopped", message, detail: null });
    startWorker();
    render();
  };
  const copy = wasm!.slice();
  w.postMessage({ type: "load", wasm: copy } satisfies Request, [copy.buffer]);
}

/** Stop the solve in progress: terminate the worker and start a new one. */
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

function onReply(r: Reply): void {
  const run = state.run;
  // A reply of a run that was cancelled or replaced has another id.
  if (!run || r.type === "ready" || (r.id !== null && r.id !== run.id)) return;
  if (r.type === "start") {
    run.current = r.method;
    run.currentStart = performance.now();
  } else if (r.type === "result") {
    const expected = run.methods[run.results.length];
    const groups = run.results[0]?.reduction.groups;
    const defect = r.method !== expected ? "The reply is for another method."
      : checkReduction(r.reduction, r.method)
      ?? (groups && JSON.stringify(groups) !== JSON.stringify(r.reduction.groups)
        ? "The methods returned different groups." : null);
    if (defect) {
      fail({ title: "The solver returned an invalid result", message: defect, detail: "The page shows no result." });
      // The worker can hold more replies of this run. Start again from a clean worker.
      restartWorker();
    } else {
      run.results.push({ method: r.method, reduction: r.reduction, milliseconds: r.milliseconds });
    }
  } else if (r.type === "done") {
    if (run.results.length === run.methods.length) {
      state.shown = { results: run.results, input: run.input, source: run.source };
      state.run = null;
    } else {
      fail({ title: "The solver returned an invalid result", message: "A method has no result.", detail: null });
    }
  } else {
    fail(r.kind === "input"
      ? { title: "The package rejected the input", message: r.message, detail: explain(r.message) }
      : { title: r.kind === "solver" ? "The solver stopped with an error" : "The run stopped with an error",
          message: r.message, detail: explain(r.message) });
  }
  render();
}

// Input

/** The input or the method changed: stop a run and remove what the page shows. */
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

function loadExample(example: Example): void {
  changed(ui.pairs, ui.means);
  ui.pairs.value = repository.examples[example.pairsFile];
  ui.means.value = example.meansFile ? repository.examples[example.meansFile] : "";
  state.example = example;
  state.source = example.title;
  invalidate();
  state.notice = null;
  render();
}

async function loadFile(file: File, target: HTMLTextAreaElement): Promise<void> {
  const what = target === ui.pairs ? "decisions" : "means";
  changed(target);
  const change = fieldChange.get(target);
  if (file.size > MAX_CHARS) {
    state.problem = { title: `The ${what} could not be read`, detail: null,
                      message: `${file.name} is larger than the page reads (${MAX_CHARS.toLocaleString("en-US")} characters).` };
    render();
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
  target.value = text;
  state.example = null;
  if (target === ui.pairs) state.source = file.name;
  invalidate();
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

// Run

function startRun(methods: Method[]): void {
  if (state.solver !== "ready" || state.run) return;
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
  state.run = { id: nextId++, methods, input, source: state.source, results: [], current: methods[0],
                currentStart: performance.now() };
  worker!.postMessage({ type: "run", id: state.run.id, input, methods } satisfies Request);
  render();
}

function cancelRun(): void {
  if (!state.run) return;
  state.run = null;
  state.notice = "The run was cancelled.";
  restartWorker();
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

// Rendering

function renderStatus(): void {
  ui.status.classList.toggle("is-error", state.solver === "failed");
  ui.status.textContent = state.solver === "failed" ? `The solver could not start: ${state.solverMessage}`
    : state.solver === "loading" ? "Loading the solver…"
    : state.run ? "Solving…" : "Solver ready";
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
  ui.exampleNote.hidden = !example;
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
  }

  const running = state.run !== null;
  ui.run.textContent = running ? "Cancel" : "Run";
  ui.run.classList.toggle("is-cancel", running);
  ui.run.disabled = !running && state.solver !== "ready";
  ui.compare.disabled = running || state.solver !== "ready";
  ui.runHint.textContent = state.solver === "failed" ? "The solver is not available."
    : running ? "Cancel stops the solver." : state.solver === "loading" ? "Waiting for the solver…" : "";
}

function renderResults(): void {
  const host = ui.results;
  host.replaceChildren();
  if (state.problem) renderProblem(host, state.problem);
  if (state.run) {
    renderRunning(host, state.run);
  } else if (state.shown) {
    renderShown(host, state.shown);
  } else if (!state.problem) {
    if (state.notice) el("p", "notice", state.notice, host).setAttribute("role", "status");
    const empty = el("div", "empty", undefined, host);
    el("h2", undefined, "Reduce a compact letter display", empty);
    el("p", undefined,
       "Give one row for each pair of groups, with the decision of your analysis: significant or not significant. " +
       "Choose a method, then press Run.", empty);
    el("p", undefined,
       "Two groups share a letter exactly when they are not significantly different. " +
       "The solve runs in this browser. The data does not leave this computer.", empty);
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
  el("h2", "headline-title", `Solving with ${methodInfo(run.current).name}…`, head);
  const step = run.methods.length > 1 ? `Method ${run.results.length + 1} of ${run.methods.length}. ` : "";
  const p = el("p", "muted", step, head);
  const time = el("span", "live-time", duration(performance.now() - run.currentStart), p);
  time.dataset.start = String(run.currentStart);
}

function renderShown(host: HTMLElement, shown: Shown): void {
  const { results } = shown;
  const first = results[0].reduction;
  const names = results.map((r) => methodInfo(r.method).name);
  const sentence = (r: MethodResult): string => {
    const s = r.reduction.stats;
    return `${count(s.numLettersAfter, "letter", "letters")} and ${count(s.assignmentsAfter, "assignment", "assignments")}`;
  };

  const head = el("section", "headline", undefined, host);
  if (results.length === 1) {
    el("h2", "headline-title", `${names[0]}: ${sentence(results[0])}`, head);
  } else {
    el("h2", "headline-title", `${names[0]} and ${names[1]}`, head);
    el("p", "headline-text", results.map((r, k) => `${names[k]} uses ${sentence(r)}.`).join(" "), head);
  }
  const s = first.stats;
  const pairs = s.numGroups * (s.numGroups - 1) / 2;
  el("p", "muted",
     `${shown.source}: ${count(s.numGroups, "group", "groups")} and ${count(pairs, "pair", "pairs")}. ` +
     `${count(s.numEdges, "pair is", "pairs are")} not significantly different.`, head);
  const actions = el("div", "actions", undefined, head);
  const slug = shown.source.replace(/\.[^.]+$/, "").replace(/[^\w-]+/g, "-").replace(/^-+|-+$/g, "").toLowerCase() || "result";
  button("button-secondary", "Download CSV", actions,
         () => download(`cld-${slug}.csv`, resultsCsv(results, shown.input.means), "text/csv"));
  button("button-secondary", "Download JSON", actions, () => download(`cld-${slug}.json`,
         resultsJson(results, { source: shown.source, pairs: shown.input.pairs.length, means: shown.input.means },
                     repository.version), "application/json"));

  // Summary: one column for each method, so that both quantities are side by side.
  const summary = el("section", "panel-block", undefined, host);
  el("h3", undefined, "Summary", summary);
  const table = el("table", "data-table summary-table", undefined, el("div", "table-wrap", undefined, summary));
  const headRow = el("tr", undefined, undefined, el("thead", undefined, undefined, table));
  el("td", undefined, undefined, headRow);
  for (const name of names) el("th", "num", name, headRow).scope = "col";
  const body = el("tbody", undefined, undefined, table);
  const line = (label: string, value: (r: MethodResult) => string): void => {
    const tr = el("tr", undefined, undefined, body);
    el("th", undefined, label, tr).scope = "row";
    for (const r of results) el("td", "num", value(r), tr);
  };
  line("Minimizes", (r) => methodInfo(r.method).minimizes);
  line("Objective value", (r) => String(r.reduction.stats.objective));
  line("Distinct letters", (r) => String(r.reduction.stats.numLettersAfter));
  line("Assignments", (r) => String(r.reduction.stats.assignmentsAfter));
  line("Letters before reduction", (r) => String(r.reduction.stats.numLettersBefore));
  line("Assignments before reduction", (r) => String(r.reduction.stats.assignmentsBefore));
  line("Relationships preserved", (r) => r.reduction.relationshipPreserved ? "Yes" : "No");
  line("Time in this browser", (r) => duration(r.milliseconds));
  el("p", "hint",
     "\"Before reduction\" is the display with one letter for each maximal clique. " +
     "The package checks that the letters give back every input decision.", summary);

  // Letters of each group.
  const letters = el("section", "panel-block", undefined, host);
  el("h3", undefined, "Letters", letters);
  const lettersTable = el("table", "data-table letters-table", undefined, el("div", "table-wrap", undefined, letters));
  const lettersHead = el("tr", undefined, undefined, el("thead", undefined, undefined, lettersTable));
  el("th", undefined, "Group", lettersHead).scope = "col";
  const means = shown.input.means === null ? null : new Map(shown.input.means.map((m) => [m.group, m.mean]));
  if (means) el("th", "num", "Mean", lettersHead).scope = "col";
  for (const name of names) el("th", undefined, name, lettersHead).scope = "col";
  const lettersBody = el("tbody", undefined, undefined, lettersTable);
  first.rows.forEach((row, i) => {
    const tr = el("tr", undefined, undefined, lettersBody);
    el("th", "label", row.group, tr).scope = "row";
    if (means) el("td", "num", meanText(means.get(row.group)!), tr);
    for (const r of results) el("td", "letters", r.reduction.rows[i].letters, tr);
  });

  // Letters that each pair shares.
  for (const [k, r] of results.entries()) {
    const section = el("section", "panel-block", undefined, host);
    el("h3", undefined, `Shared letters, ${names[k]}`, section);
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

function render(): void {
  renderStatus();
  renderControls();
  renderResults();
}

// Time of the running solve.
setInterval(() => {
  for (const cell of ui.results.querySelectorAll<HTMLElement>(".live-time")) {
    cell.textContent = duration(performance.now() - Number(cell.dataset.start));
  }
}, 200);

// Events

ui.run.addEventListener("click", () => {
  if (state.run) cancelRun();
  else startRun([selectedMethod()]);
});
ui.compare.addEventListener("click", () => startRun(METHODS.map((m) => m.id)));
ui.reset.addEventListener("click", reset);

for (const area of [ui.pairs, ui.means]) {
  area.addEventListener("input", () => {
    changed(area);
    state.example = null;
    if (area === ui.pairs) state.source = "Pasted text";
    invalidate();
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
