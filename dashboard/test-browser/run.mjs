// Browser test of the built page, opened as a file as a user opens it, with
// the network switched off. Needs Chrome: set CHROME_PATH, or install it in
// the usual place. Set SCREENSHOT_DIR to keep pictures of the page.
//
//   npm run build && npm run test:browser

import { mkdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { chromium } from "playwright-core";
import { findChrome } from "../chrome.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, "..", "..");
const built = join(here, "..", "dist", "cld-reducer-dashboard.html");
const file = pathToFileURL(built).href;
const chrome = findChrome();
const shots = process.env.SCREENSHOT_DIR;
if (shots) mkdirSync(shots, { recursive: true });

const text = (...path) => readFileSync(join(root, ...path), "utf8");
const lf = (s) => s.replace(/\r\n/g, "\n");
const version = JSON.parse(text("js", "package.json")).version;
const SIMPLE_PAIRS = lf(text("conformance", "data", "simple_abc_to_ac_pairs.csv"));
const SIMPLE_MEANS = lf(text("conformance", "data", "simple_abc_to_ac_means.csv"));
const WHEAT_PAIRS = lf(text("conformance", "data", "piepho2004_wheat_pairs.csv"));

// Expected results come from the shared conformance fixtures. dashboard/test/worker.test.ts
// shows that wheat with CLD-sigma calls HiGHS and that the other three are essential cover results.
function fixture(name, id) {
  const found = JSON.parse(text("conformance", "fixtures", `${name}.json`)).cases.find((c) => c.id === id);
  if (!found) throw new Error(`no fixture ${id}`);
  return found.expected;
}
const EXPECTED = {
  simple: { letter_minimum: fixture("reduce_letter_minimum", "c/hand/simple-abc-pairs-means"),
            assignment_minimum: fixture("reduce", "hand/simple-abc-pairs-means") },
  wheat: { letter_minimum: fixture("reduce_letter_minimum", "c/hand/wheat"),
           assignment_minimum: fixture("reduce", "hand/wheat") },
};

// Ten groups: each group differs from one partner and equals the eight others.
// CLD-sigma on this input keeps HiGHS busy for much longer than the test waits,
// so it is the solve that the test cancels. CLD-C solves it at once.
const BUSY_PAIRS = (() => {
  const rows = ["group1,group2,significant"];
  for (let i = 0; i < 10; i++) for (let j = i + 1; j < 10; j++) rows.push(`g${i},g${j},${j === i + 1 && i % 2 === 0}`);
  return rows.join("\n") + "\n";
})();
const BUSY_C_LETTERS = ["ABC", "DEF", "ABD", "CEF", "ABE", "CDF", "ABF", "CDE", "ACD", "BEF"];

const LABELS = ['<img src=x onerror="window.__xss=1">', "<b>bold</b>", "=1+1", "a,b"];
const LABEL_PAIRS = [
  "group1;group2;significant",
  `"${LABELS[0].replace(/"/g, '""')}";${LABELS[1]};no`,
  `"${LABELS[0].replace(/"/g, '""')}";${LABELS[2]};yes`,
  `"${LABELS[0].replace(/"/g, '""')}";${LABELS[3]};yes`,
  `${LABELS[1]};${LABELS[2]};ns`,
  `${LABELS[1]};${LABELS[3]};significant`,
  `${LABELS[2]};${LABELS[3]};0`,
].join("\n");

function check(ok, message) {
  if (!ok) throw new Error(message);
}
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

/** One result of the JSON file against a fixture. */
function checkAgainst(result, expected, what) {
  check(result.method === expected.method, `${what}: method ${result.method}`);
  check(result.relationshipPreserved === true, `${what}: relationships`);
  check(same(result.rows.map((r) => r.group), expected.groups), `${what}: groups`);
  check(same(result.rows.map((r) => r.letters), expected.groups.map((g) => expected.letters[g])), `${what}: letters`);
  check(same(result.rows.map((r) => r.assignments), expected.groups.map((g) => expected.assignments[g])), `${what}: tokens`);
  const s = result.stats;
  const stats = { assignments_before: s.assignmentsBefore, assignments_after: s.assignmentsAfter,
                  num_letters_before: s.numLettersBefore, num_letters_after: s.numLettersAfter,
                  num_groups: s.numGroups, num_edges: s.numEdges };
  check(same(stats, expected.stats), `${what}: statistics ${JSON.stringify(stats)}`);
  check(s.objective === expected.objective, `${what}: objective ${s.objective}`);
}

// Runs in the page before its script. It keeps each worker, records terminate(),
// and lets the test hold or change replies on their way to the page.
function instrument() {
  const Native = window.Worker;
  window.__workers = [];
  window.__held = [];
  window.__hold = false;
  window.__alter = null;
  window.Worker = class extends Native {
    constructor(...args) {
      super(...args);
      this.terminated = false;
      window.__workers.push(this);
    }
    terminate() {
      this.terminated = true;
      super.terminate();
    }
    get onmessage() { return super.onmessage; }
    set onmessage(fn) {
      this.deliver = (data) => fn.call(this, new MessageEvent("message", { data }));
      super.onmessage = (e) => {
        if (window.__hold && e.data?.type !== "ready") { window.__held.push(e.data); return; }
        if (window.__alter && e.data?.type === "result") { this.deliver(window.__alter(structuredClone(e.data))); return; }
        fn.call(this, e);
      };
    }
  };
}

async function main() {
  // No host name resolves, and the context is offline: a request to the network cannot succeed.
  const browser = await chromium.launch({ executablePath: chrome, headless: true,
                                          args: ["--host-resolver-rules=MAP * ~NOTFOUND"] });
  try {
    const context = await browser.newContext({ viewport: { width: 1280, height: 900 }, acceptDownloads: true });
    await context.setOffline(true);
    const page = await context.newPage();
    const errors = [];
    const requests = [];
    page.on("pageerror", (e) => errors.push(e.message));
    page.on("console", (m) => { if (m.type() === "error" || m.type() === "warning") errors.push(m.text()); });
    page.on("request", (r) => { if (!/^(file|blob|data):/.test(r.url())) requests.push(r.url()); });
    await page.addInitScript(instrument);
    await page.goto(file);

    const wait = (fn, arg) => page.waitForFunction(fn, arg, { timeout: 60_000 });
    const ready = () => wait(() => document.getElementById("solver-status").textContent === "Solver ready" &&
                                   document.getElementById("run").textContent === "Run" &&
                                   !document.getElementById("run").disabled);
    const solved = () => wait(() => document.querySelector(".summary-table") !== null &&
                                    document.getElementById("run").textContent === "Run");
    const busy = () => wait(() => document.getElementById("run").textContent === "Cancel" &&
                                  document.getElementById("solver-status").textContent === "Solving…");
    const method = (value) => page.check(`input[name="method"][value="${value}"]`);
    const read = () => page.evaluate(() => {
      const one = (selector) => document.querySelector(selector)?.textContent ?? null;
      const table = (t) => [...t.querySelectorAll("tr")].map((tr) => [...tr.children].map((c) => c.textContent));
      const tables = (selector) => [...document.querySelectorAll(selector)].map(table);
      return {
        status: one("#solver-status"), run: one("#run"), hint: one("#run-hint"),
        title: one(".headline-title"), notice: one(".notice"), empty: one(".empty h2"),
        problem: document.querySelector(".problem") &&
          [...document.querySelectorAll(".problem > h2, .problem > p")].map((e) => e.textContent),
        summary: tables(".summary-table")[0] ?? null, letters: tables(".letters-table")[0] ?? null,
        matrices: tables(".matrix"),
        pairs: document.getElementById("pairs").value, means: document.getElementById("means").value,
        checked: document.querySelector('input[name="method"]:checked').value,
        pressed: [...document.querySelectorAll('.example[aria-pressed="true"]')].map((b) => b.textContent),
      };
    });
    const summaryRow = (state, label) => state.summary.find((row) => row[0] === label)?.slice(1);
    const save = async (label) => {
      const [download] = await Promise.all([page.waitForEvent("download"), page.click(`text=${label}`)]);
      return { name: download.suggestedFilename(), text: readFileSync(await download.path(), "utf8") };
    };
    const noResult = (state, what) => check(state.summary === null && state.letters === null &&
                                            state.matrices.length === 0 && state.title === null, `${what}: a result is shown`);

    // The page starts with the solver loading and the simple example in the fields.
    await ready();
    let state = await read();
    check(await page.$eval(".brand-version", (e) => e.textContent) === version, "the version is not the one of js/package.json");
    check(state.pairs === SIMPLE_PAIRS && state.means === SIMPLE_MEANS, "the fields do not hold the simple example");
    check(same(state.pressed, ["Simple example"]) && state.checked === "letter_minimum", "the default example or method");
    check(state.empty === "Reduce a compact letter display", "the page does not start empty");
    noResult(state, "start");
    check(await page.evaluate(() => window.__workers.length) === 1, "the page did not start one worker");
    if (shots) await page.screenshot({ path: join(shots, "wide-start.png") });

    // CLD-C is the default. The simple example with it is an essential cover result.
    await page.click("#run");
    await solved();
    state = await read();
    check(state.title === "CLD-C: 3 letters and 9 assignments", `simple CLD-C title: ${state.title}`);
    check(same(state.summary[0], ["", "CLD-C"]), "simple CLD-C summary head");
    check(same(summaryRow(state, "Minimizes"), ["Distinct letters"]), "CLD-C does not state its objective");
    check(same(summaryRow(state, "Objective value"), ["3"]) && same(summaryRow(state, "Distinct letters"), ["3"]) &&
          same(summaryRow(state, "Assignments"), ["9"]) && same(summaryRow(state, "Relationships preserved"), ["Yes"]),
          `simple CLD-C summary: ${JSON.stringify(state.summary)}`);
    check(/^(<1|\d+) ms$|^\d+\.\d+ s$/.test(summaryRow(state, "Time in this browser")[0]), "no browser time");
    check(same(state.letters, [["Group", "Mean", "CLD-C"], ["1", "3.73", "A"], ["2", "3.57", "AB"],
                               ["3", "3.46", "ABC"], ["4", "3.33", "BC"], ["5", "3.3", "C"]]),
          `simple CLD-C letters: ${JSON.stringify(state.letters)}`);
    check(state.matrices.length === 1 && same(state.matrices[0][1], ["1", "A", "A", "A", "different", "different"]) &&
          same(state.matrices[0][3], ["3", "A", "AB", "ABC", "BC", "C"]), `simple matrix: ${JSON.stringify(state.matrices[0])}`);
    let json = await save("Download JSON");
    check(json.name === "cld-simple-example.json", `JSON name: ${json.name}`);
    let saved = JSON.parse(json.text);
    check(saved.package === "cld-reducer" && saved.version === version && saved.input.source === "Simple example" &&
          saved.input.pairs === 10 && saved.input.means.length === 5 && saved.results.length === 1, "JSON head");
    checkAgainst(saved.results[0], EXPECTED.simple.letter_minimum, "simple CLD-C");

    // A method change removes the result. Keyboard: the arrow key moves the choice.
    await page.focus('input[name="method"]:checked');
    await page.keyboard.press("ArrowDown");
    state = await read();
    check(state.checked === "assignment_minimum", "the arrow key did not change the method");
    noResult(state, "method change");
    check(state.notice === "The input or the method changed. Press Run to solve again.", `notice: ${state.notice}`);
    await page.focus("#run");
    await page.keyboard.press("Enter");
    await solved();
    state = await read();
    check(state.title === "CLD-sigma: 3 letters and 8 assignments", `simple CLD-sigma title: ${state.title}`);
    check(same(summaryRow(state, "Minimizes"), ["Assignments"]) && same(summaryRow(state, "Objective value"), ["8"]),
          "CLD-sigma does not state its objective");
    check(state.letters[3][2] === "AC", "simple CLD-sigma does not give group 3 the letters AC");
    checkAgainst(JSON.parse((await save("Download JSON")).text).results[0], EXPECTED.simple.assignment_minimum, "simple CLD-sigma");

    // Wheat, both methods. CLD-sigma needs HiGHS here.
    await page.click('button.example:has-text("Wheat yield")');
    state = await read();
    noResult(state, "example change");
    check(state.pairs === WHEAT_PAIRS && state.means === "" && same(state.pressed, ["Wheat yield"]), "the wheat example");
    await page.click("#compare");
    await solved();
    state = await read();
    check(state.title === "CLD-C and CLD-sigma", `compare title: ${state.title}`);
    check(same(state.summary[0], ["", "CLD-C", "CLD-sigma"]) &&
          same(summaryRow(state, "Minimizes"), ["Distinct letters", "Assignments"]) &&
          same(summaryRow(state, "Distinct letters"), ["4", "4"]) && same(summaryRow(state, "Assignments"), ["56", "44"]) &&
          same(summaryRow(state, "Objective value"), ["4", "44"]) &&
          same(summaryRow(state, "Assignments before reduction"), ["56", "56"]),
          `wheat summary: ${JSON.stringify(state.summary)}`);
    check(state.letters.length === 21 && same(state.letters[0], ["Group", "CLD-C", "CLD-sigma"]), "wheat letters table");
    json = await save("Download JSON");
    saved = JSON.parse(json.text);
    check(json.name === "cld-wheat-yield.json" && saved.input.means === null && saved.input.pairs === 190, "wheat JSON head");
    checkAgainst(saved.results[0], EXPECTED.wheat.letter_minimum, "wheat CLD-C");
    checkAgainst(saved.results[1], EXPECTED.wheat.assignment_minimum, "wheat CLD-sigma");
    // Each matrix has letters exactly where the input says "not significant".
    const equal = new Set(WHEAT_PAIRS.trim().split("\n").slice(1).map((line) => line.split(","))
      .filter(([, , significant]) => significant === "false").flatMap(([a, b]) => [`${a},${b}`, `${b},${a}`]));
    check(state.matrices.length === 2, "wheat matrices");
    for (const matrix of state.matrices) {
      const groups = matrix[0].slice(1);
      check(groups.length === 20, "wheat matrix size");
      for (const row of matrix.slice(1)) {
        row.slice(1).forEach((cell, j) => {
          const expected = row[0] === groups[j] || equal.has(`${row[0]},${groups[j]}`);
          check((cell !== "different" && cell !== "") === expected, `wheat matrix cell ${row[0]},${groups[j]}: ${cell}`);
        });
      }
    }
    const csv = await save("Download CSV");
    const csvLines = csv.text.trimEnd().split("\n");
    check(csv.name === "cld-wheat-yield.csv" && csvLines.length === 41 && csvLines[0] === "method,group,letters,assignments" &&
          csvLines[1] === "letter_minimum,1,ABCD,A B C D" && csvLines[40] === "assignment_minimum,20,C,C", `CSV: ${csvLines[1]}`);
    if (shots) await page.screenshot({ path: join(shots, "wide-wheat.png") });

    // Paste: semicolons, quotes, decision words, and labels that look like markup or a formula.
    await page.fill("#pairs", LABEL_PAIRS);
    state = await read();
    noResult(state, "paste");
    check(state.pressed.length === 0, "a pasted input still shows an example as chosen");
    await method("letter_minimum");
    await page.click("#run");
    await solved();
    state = await read();
    check(same(state.letters.slice(1).map((row) => row[0]), LABELS), `labels: ${JSON.stringify(state.letters)}`);
    check(same(state.letters.slice(1).map((row) => row[1]), ["A", "AB", "BC", "C"]), "letters of the pasted input");
    check(same(state.matrices[0][0].slice(1), LABELS), "matrix labels");
    check(await page.evaluate(() => document.querySelector("#results img, #results b") === null && window.__xss === undefined),
          "a label was read as markup");
    saved = JSON.parse((await save("Download JSON")).text);
    check(saved.input.source === "Pasted text" && same(saved.results[0].rows.map((r) => r.group), LABELS), "JSON labels");
    const labelCsv = (await save("Download CSV")).text.split("\n");
    check(labelCsv[1] === 'letter_minimum,"<img src=x onerror=""window.__xss=1"">",A,A' &&
          labelCsv[3] === "letter_minimum,'=1+1,BC,B C" && labelCsv[4] === 'letter_minimum,"a,b",C,C', `CSV labels: ${labelCsv}`);

    // Files: decisions with tabs, and means that set the group order.
    await page.setInputFiles("#pairs-file", { name: "trial 1.tsv", mimeType: "text/tab-separated-values",
      buffer: Buffer.from("﻿group1\tgroup2\tsignificant\r\nlow\tmid\tFALSE\r\nlow\thigh\tTRUE\r\nmid\thigh\tFALSE\r\n") });
    await wait(() => document.getElementById("pairs").value.includes("low\tmid"));
    await page.setInputFiles("#means-file", { name: "means.csv", mimeType: "text/csv",
      buffer: Buffer.from("group;mean\nhigh;9,5\nmid;5\nlow;1,25\n") });
    await wait(() => document.getElementById("means").value.includes("high;9,5"));
    noResult(await read(), "file");
    await page.click("#run");
    await solved();
    state = await read();
    check(same(state.letters, [["Group", "Mean", "CLD-C"], ["high", "9.5", "A"], ["mid", "5", "AB"], ["low", "1.25", "B"]]),
          `file letters: ${JSON.stringify(state.letters)}`);
    json = await save("Download JSON");
    check(json.name === "cld-trial-1.json" && JSON.parse(json.text).input.source === "trial 1.tsv", `file source: ${json.name}`);

    // A file read that ends after a later change of the field does not replace the newer input.
    await page.evaluate(() => {
      const read = Blob.prototype.text;
      window.__release = null;
      Blob.prototype.text = function () {
        return new Promise((resolve) => {
          window.__release = () => { Blob.prototype.text = read; resolve(read.call(this)); };
        });
      };
    });
    await page.setInputFiles("#pairs-file", { name: "slow.csv", mimeType: "text/csv",
      buffer: Buffer.from("group1,group2,significant\nold,file,false\n") });
    await wait(() => typeof window.__release === "function");
    await page.click('button.example:has-text("Wheat yield")');
    await page.evaluate(() => window.__release());
    await page.waitForTimeout(200);
    state = await read();
    check(state.pairs === WHEAT_PAIRS && same(state.pressed, ["Wheat yield"]), "a late file read replaced the newer input");
    // The next file is read as usual.
    await page.setInputFiles("#pairs-file", { name: "trial 1.tsv", mimeType: "text/tab-separated-values",
      buffer: Buffer.from("group1\tgroup2\tsignificant\nlow\tmid\tFALSE\nlow\thigh\tTRUE\nmid\thigh\tFALSE\n") });
    await wait(() => document.getElementById("pairs").value.includes("low\tmid"));

    // A file dropped on a field goes into that field, and the tab does not open it.
    const taken = await page.evaluate(() => {
      const data = new DataTransfer();
      data.items.add(new File(["group,mean\nlow,1\nmid,2\nhigh,3\n"], "dropped.csv", { type: "text/csv" }));
      const drop = new DragEvent("drop", { dataTransfer: data, bubbles: true, cancelable: true });
      document.getElementById("means").dispatchEvent(drop);
      return drop.defaultPrevented;
    });
    check(taken, "a dropped file is not taken");
    await wait(() => document.getElementById("means").value.startsWith("group,mean\nlow,1"));
    noResult(await read(), "drop");
    await page.click("#run");
    await solved();
    state = await read();
    check(same(state.letters.slice(1), [["low", "1", "B"], ["mid", "2", "AB"], ["high", "3", "A"]]),
          `letters after a dropped file: ${JSON.stringify(state.letters)}`);

    // Invalid input shows an error and no result.
    const problemOf = async (pairs, means = "") => {
      await page.fill("#pairs", pairs);
      await page.fill("#means", means);
      await page.click("#run");
      await wait(() => document.querySelector(".problem") !== null);
      const s = await read();
      noResult(s, "invalid input");
      check(s.run === "Run" && s.status === "Solver ready", "the page is not ready after an input error");
      return s.problem;
    };
    let problem = await problemOf("group1,group2,significant\nA,B,false\nA,C,true\n");
    check(problem[0] === "The package rejected the input" &&
          problem[1] === 'post_hoc_results missing unordered pairwise comparisons: ["B|C"]' &&
          problem[2].includes("A missing pair is an error."), `missing pair: ${JSON.stringify(problem)}`);
    problem = await problemOf("group1,group2,significant\nA,B,perhaps\n");
    check(problem[1].startsWith("cannot coerce significance value to bool: "), `decision word: ${problem[1]}`);
    problem = await problemOf('group1,group2,significant\nA,"B,false\n');
    check(same(problem, ["The decisions could not be read", "Line 2: a quoted value has no closing quote."]), `quote: ${problem}`);
    problem = await problemOf("A,B,false\n");
    check(problem[1].startsWith("The first row of the decisions must name the columns"), `header: ${problem[1]}`);
    problem = await problemOf("group1,group2,significant\nA,B,false\n", "group,mean\nA,1\nB,tall\n");
    check(same(problem, ["The means could not be read", 'Line 3: the mean "tall" of group "B" is not a number.']), `mean: ${problem}`);
    await page.click(".problem button");
    state = await read();
    check(state.problem === null && await page.evaluate(() => document.activeElement.id) === "run", "Clear did not clear the error");

    // Cancel stops a busy worker. The page answers while the worker solves.
    await page.fill("#means", "");
    await page.fill("#pairs", BUSY_PAIRS);
    await method("assignment_minimum");
    await page.click("#run");
    await busy();
    await page.waitForTimeout(500);
    const during = await page.evaluate(() => new Promise((resolve) => {
      const first = document.querySelector(".live-time").textContent;
      const start = performance.now();
      let ticks = 0;
      const tick = () => {
        if (++ticks < 20) { setTimeout(tick, 10); return; }
        requestAnimationFrame(() => resolve({
          first, last: document.querySelector(".live-time").textContent, elapsed: performance.now() - start,
          title: document.querySelector(".headline-title").textContent, workers: window.__workers.length,
        }));
      };
      tick();
    }));
    check(during.title === "Solving with CLD-sigma…" && during.workers === 1, `busy state: ${JSON.stringify(during)}`);
    check(during.elapsed < 1500, `the page was slow during the solve: ${during.elapsed} ms for 20 timers`);
    check(during.first !== during.last, "the time of the solve does not advance");
    await page.click("#run");
    state = await read();
    check(state.notice === "The run was cancelled." && state.run === "Run", `cancel: ${JSON.stringify(state)}`);
    noResult(state, "cancel");
    check(same(await page.evaluate(() => window.__workers.map((w) => w.terminated)), [true, false]),
          "Cancel did not terminate the busy worker and start one new worker");
    await ready();
    await page.waitForTimeout(1000);
    noResult(await read(), "after cancel");
    // A new run on the same input, with the method that solves it at once.
    await method("letter_minimum");
    await page.click("#run");
    await solved();
    state = await read();
    check(state.title === "CLD-C: 6 letters and 30 assignments" &&
          same(state.letters.slice(1).map((row) => row[1]), BUSY_C_LETTERS), `run after cancel: ${state.title}`);

    // A change of the method during a solve stops it too.
    await method("assignment_minimum");
    await page.click("#run");
    await busy();
    await method("letter_minimum");
    state = await read();
    check(state.run === "Run" && state.notice.startsWith("The input or the method changed."), "a method change did not stop the run");
    check(same(await page.evaluate(() => window.__workers.map((w) => w.terminated)), [true, true, false]),
          "the method change did not terminate the busy worker");
    await ready();
    await page.click("#reset");
    state = await read();
    check(state.pairs === SIMPLE_PAIRS && state.means === SIMPLE_MEANS && state.checked === "letter_minimum" &&
          state.notice === null && state.problem === null && same(state.pressed, ["Simple example"]), "Reset");
    noResult(state, "reset");

    // Replies of a cancelled run arrive late: the page ignores them, from the old worker and with the old id.
    await page.evaluate(() => { window.__hold = true; });
    await page.click("#run");
    await wait(() => window.__held.some((r) => r.type === "done"));
    check((await read()).run === "Cancel", "a held run is not in progress");
    await page.click("#run");
    await page.evaluate(() => { window.__hold = false; });
    await ready();
    const held = await page.evaluate(() => window.__held.map((r) => r.type));
    check(same(held, ["start", "result", "done"]), `held replies: ${held}`);
    await page.evaluate(() => {
      const [old, current] = window.__workers.slice(-2);
      for (const reply of window.__held) old.deliver(reply);
      for (const reply of window.__held) current.deliver(reply);
    });
    state = await read();
    noResult(state, "late replies");
    check(state.notice === "The run was cancelled.", "late replies changed the page");
    // The same late replies during the next run do not end it or enter its result.
    await page.click('button.example:has-text("Wheat yield")');
    await page.evaluate(() => { window.__hold = true; });
    await page.click("#run");
    await wait(() => window.__held.filter((r) => r.type === "done").length === 2);
    await page.evaluate(() => {
      const current = window.__workers.at(-1);
      const [stale, fresh] = [window.__held.slice(0, 3), window.__held.slice(3)];
      window.__hold = false;
      for (const reply of stale) current.deliver(reply);
      window.__afterStale = document.getElementById("run").textContent;
      for (const reply of fresh) current.deliver(reply);
    });
    await solved();
    state = await read();
    check(await page.evaluate(() => window.__afterStale) === "Cancel", "a late reply ended the next run");
    check(state.title === "CLD-C: 4 letters and 56 assignments" && state.letters.length === 21, `run after late replies: ${state.title}`);

    // A reply that does not match the input decisions is not shown, and the old result goes away.
    await page.evaluate(() => {
      window.__alter = (reply) => {
        const row = reply.reduction.rows[17];
        row.letters = row.assignments = "D";
        return reply;
      };
    });
    await page.click("#run");
    await wait(() => document.querySelector(".problem") !== null);
    state = await read();
    noResult(state, "altered reply");
    check(state.problem[0] === "The solver returned an invalid result" &&
          /^The letters of \d+ and \d+ do not match the input decision\.$/.test(state.problem[1]), `altered reply: ${state.problem}`);
    await page.evaluate(() => { window.__alter = (reply) => { reply.reduction.rows[0].letters = "WRONG"; return reply; }; });
    await ready();
    await page.click("#run");
    await wait(() => document.querySelector(".problem > p")?.textContent === "The display of 1 does not match its letter tokens.");
    noResult(await read(), "reply with an altered display string");
    await page.evaluate(() => { window.__alter = (reply) => { reply.reduction.relationshipPreserved = false; return reply; }; });
    await ready();
    await page.click("#run");
    await wait(() => document.querySelector(".problem > p")?.textContent === "The reply does not confirm the relationship check.");
    noResult(await read(), "reply without the relationship check");
    await page.evaluate(() => { window.__alter = null; });
    await ready();
    await page.click("#compare");
    await solved();
    check((await read()).problem === null, "the error stays after a good run");

    // The licenses and the data sources are in the file.
    const notices = await page.$eval(".foot", (e) => e.textContent);
    for (const part of ["Copyright (c) 2026 Aigora", "Copyright (c) 2023 highs-js", "Copyright (c) 2026 HiGHS",
                        "doi:10.1198/1061860043515", "doi:10.1145/2133803.2275596"]) {
      check(notices.includes(part), `the page does not hold: ${part}`);
    }

    // Narrow screen: one column, and the page is not wider than the screen.
    await page.setViewportSize({ width: 390, height: 844 });
    const narrow = await page.evaluate(() => {
      const side = document.querySelector(".side").getBoundingClientRect();
      const results = document.querySelector(".results-pane").getBoundingClientRect();
      const wrap = document.querySelector(".matrix").parentElement;
      return { page: document.documentElement.scrollWidth, screen: innerWidth, below: results.top >= side.bottom,
               matrixScrolls: wrap.scrollWidth > wrap.clientWidth && wrap.getBoundingClientRect().right <= innerWidth };
    });
    check(narrow.page <= narrow.screen && narrow.below && narrow.matrixScrolls, `narrow layout: ${JSON.stringify(narrow)}`);
    if (shots) {
      await page.screenshot({ path: join(shots, "narrow-top.png") });
      await page.evaluate(() => document.querySelector(".headline").scrollIntoView());
      await page.screenshot({ path: join(shots, "narrow-wheat.png") });
    }

    // A long file name wraps in the result and does not widen the page.
    const longName = `${"x".repeat(200)}.csv`;
    await page.setInputFiles("#pairs-file", { name: longName, mimeType: "text/csv",
      buffer: Buffer.from("group1,group2,significant\nB,C,true\nA,B,true\nA,C,true\n") });
    await wait(() => document.getElementById("pairs").value.startsWith("group1,group2,significant\nB,C"));
    await page.click("#run");
    await solved();
    state = await read();
    const long = await page.evaluate(() => ({
      page: document.documentElement.scrollWidth, screen: innerWidth,
      source: document.querySelector(".headline .muted").textContent,
    }));
    check(long.source.startsWith(longName) && long.page <= long.screen, `long file name: ${long.page} > ${long.screen}`);
    // Without means, the groups keep the order of the group1 column, then new labels of group2.
    check(same(state.letters.slice(1).map((row) => row[0]), ["B", "A", "C"]), `group order: ${JSON.stringify(state.letters)}`);

    check(errors.length === 0, `console messages: ${errors.join(" | ")}`);
    check(requests.length === 0, `requests to the network: ${requests.join(" | ")}`);

    // The page's own policy refuses a connection, even when the code asks for one.
    const refused = await page.evaluate(() => new Promise((resolve) => {
      document.addEventListener("securitypolicyviolation", (e) => resolve(e.effectiveDirective), { once: true });
      fetch("https://example.invalid/").then(() => resolve("fetched"), () => setTimeout(() => resolve("failed without the policy"), 2000));
    }));
    check(refused === "connect-src", `content security policy: ${refused}`);

    check(readFileSync(join(here, "..", "dist", "site", "index.html")).equals(readFileSync(built)),
          "dist/site/index.html is not the built page");
    console.log(`ok: ${built}`);
  } finally {
    await browser.close();
  }
}

await main();
