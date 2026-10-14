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
  window.__heldBefore = [];
  window.__holdBefore = false;
  window.__alter = null;
  window.__alterBefore = null;
  window.__alterInstance = null;
  window.__alterStart = null;
  window.__seen = [];
  window.__alterLoad = null;
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
        window.__seen.push(e.data?.type);
        if (window.__hold && ["start", "result", "done"].includes(e.data?.type)) { window.__held.push(e.data); return; }
        if (window.__holdBefore && ["before", "error"].includes(e.data?.type)) { window.__heldBefore.push([this, e.data]); return; }
        if (window.__alter && e.data?.type === "result") { this.deliver(window.__alter(structuredClone(e.data))); return; }
        if (window.__alterBefore && e.data?.type === "before") { this.deliver(window.__alterBefore(structuredClone(e.data))); return; }
        if (window.__alterStart && e.data?.type === "start") { this.deliver(window.__alterStart(structuredClone(e.data))); return; }
        if (window.__alterLoad && e.data?.type === "ready") { this.deliver(window.__alterLoad(e.data)); return; }
        if (window.__alterInstance && e.data?.type === "instance") {
          this.deliver(window.__alterInstance(structuredClone(e.data)));
          return;
        }
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

    // A timeout names the condition, so that a failure says where the test stopped.
    const wait = (fn, arg) => page.waitForFunction(fn, arg, { timeout: 60_000 }).catch(async (e) => {
      const shown = await page.evaluate(() => [document.getElementById("solver-status").textContent,
        document.getElementById("run").textContent, document.querySelector(".results")?.innerText.slice(0, 400)])
        .catch(() => null);
      throw new Error(`${e.message.split("\n")[0]} Waiting for: ${fn.toString().slice(0, 300)} Page: ${JSON.stringify(shown)}`);
    });
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
    // No result: no summary and no matrix, and at most the display before reduction.
    const noResult = (state, what) => check(state.summary === null && state.matrices.length === 0 &&
      (state.letters === null || state.letters[0].every((h) => ["Group", "Mean", "Before"].includes(h))) &&
      (state.title === null || state.title.startsWith("Before reduction")), `${what}: a result is shown`);

    // The page starts with the solver loading and the simple example in the fields.
    await ready();
    let state = await read();
    check(await page.$eval(".brand-version", (e) => e.textContent) === version, "the version is not the one of js/package.json");
    check(state.pairs === SIMPLE_PAIRS && state.means === SIMPLE_MEANS, "the fields do not hold the simple example");
    check(same(state.pressed, ["Simple example"]) && state.checked === "letter_minimum", "the default example or method");
    // The display before reduction appears without a run: one letter for each maximal clique.
    await wait(() => document.querySelector(".letters-table") !== null);
    state = await read();
    check(state.title === "Before reduction: 3 letters and 9 assignments", `before title: ${state.title}`);
    check(same(state.letters, [["Group", "Mean", "Before"], ["1", "3.73", "A"], ["2", "3.57", "AB"], ["3", "3.46", "ABC"],
                               ["4", "3.33", "BC"], ["5", "3.3", "C"]]), `before letters: ${JSON.stringify(state.letters)}`);
    noResult(state, "start");
    check(await page.evaluate(() => window.__workers.length) === 1, "the page did not start one worker");
    // The start says what the page is for, and the Aigora fonts and mark are inside the file.
    check(await page.$eval("#results .intro-title", (e) => e.textContent) === "Simpler letter displays, with the same conclusions",
          "the start has no intro");
    check(await page.evaluate(async () => { await document.fonts.ready;
      return document.fonts.check("15px Manrope") && document.fonts.check("italic 24px 'Instrument Serif'") &&
        [...document.fonts].filter((f) => f.status === "loaded").length === 2; }), "the Aigora fonts did not load");
    check(await page.$eval(".brand-mark", (e) => e.src.startsWith("data:image/svg+xml,") && e.complete && e.naturalWidth > 0),
          "the Aigora mark is not in the file");
    // The theme button switches light and dark mode, and the page keeps the choice in this browser.
    const look = () => page.evaluate(() => ({ theme: document.documentElement.dataset.theme ?? null,
      label: document.getElementById("theme").getAttribute("aria-label"), background: getComputedStyle(document.body).backgroundColor }));
    const light = await look();
    check(light.theme === null && light.label === "Switch to dark mode", `system theme: ${JSON.stringify(light)}`);
    await page.click("#theme");
    const dark = await look();
    check(dark.theme === "dark" && dark.label === "Switch to light mode" && dark.background !== light.background,
          `dark mode: ${JSON.stringify(dark)}`);
    await page.reload();
    await ready();
    check((await look()).theme === "dark", "the page does not keep the theme");
    await page.click("#theme");
    check((await look()).theme === "light" && (await look()).background === light.background, "light mode");
    await page.evaluate(() => { localStorage.removeItem("cld-reducer-theme"); delete document.documentElement.dataset.theme; });
    await page.emulateMedia({ colorScheme: "dark" });
    await page.waitForTimeout(50);
    check((await look()).label === "Switch to light mode", "the button does not follow the system theme");
    await page.emulateMedia({ colorScheme: "light" });
    await page.waitForTimeout(50);
    await wait(() => document.querySelector(".letters-table") !== null);

    // Tab from the decisions reaches "Choose a file", and the side panel shows it above the sticky Run bar.
    await page.focus("#pairs");
    await page.keyboard.press("Tab");
    await page.waitForTimeout(100);
    const tabbed = await page.evaluate(() => ({ id: document.activeElement.id,
      bottom: document.activeElement.getBoundingClientRect().bottom,
      bar: document.querySelector("#reduce-view .run-bar").getBoundingClientRect().top }));
    check(tabbed.id === "pairs-choose" && tabbed.bottom <= tabbed.bar, `focus behind the Run bar: ${JSON.stringify(tabbed)}`);
    await page.evaluate(() => { document.activeElement.blur(); document.querySelector("#reduce-view .side").scrollTop = 0; });
    if (shots) await page.screenshot({ path: join(shots, "wide-start.png") });

    // CLD-C is the default. It runs with its second minimization, and the page shows the result under the
    // name CLD-C: the fewest letters, then the fewest assignments among them. The letters stay in place.
    const lettersTop = await page.$eval(".letters-table", (e) => e.getBoundingClientRect().top);
    await page.click("#run");
    await solved();
    state = await read();
    check(state.title === "CLD-C: 3 letters and 8 assignments", `simple CLD-C title: ${state.title}`);
    check(await page.$eval(".letters-table", (e) => e.getBoundingClientRect().top) <= lettersTop,
          "the letters moved down when the result came");
    check(same(state.summary[0], ["", "Before", "CLD-C"]), "simple CLD-C summary head");
    check(same(summaryRow(state, "Minimizes"), ["One letter for each maximal clique", "Distinct letters, then assignments"]),
          "CLD-C does not state its objective");
    check(same(summaryRow(state, "Distinct letters"), ["3", "3"]) && same(summaryRow(state, "Assignments"), ["9", "8"]) &&
          same(summaryRow(state, "Assignments removed"), ["", "1 (11.1%)"]) &&
          same(summaryRow(state, "Relationships preserved"), ["", "Yes"]),
          `simple CLD-C summary: ${JSON.stringify(state.summary)}`);
    check(summaryRow(state, "Time in this browser").every((t) => /^(<1|\d+) ms$|^\d+\.\d+ s$/.test(t)), "no browser time");
    check(same(state.letters, [["Group", "Mean", "Before", "CLD-C"], ["1", "3.73", "A", "A"], ["2", "3.57", "AB", "AB"],
                               ["3", "3.46", "ABC", "AC"], ["4", "3.33", "BC", "BC"], ["5", "3.3", "C", "C"]]),
          `simple CLD-C letters: ${JSON.stringify(state.letters)}`);
    check(state.matrices.length === 1 && same(state.matrices[0][1], ["1", "A", "A", "A", "different", "different"]) &&
          same(state.matrices[0][3], ["3", "A", "A", "AC", "C", "C"]), `simple matrix: ${JSON.stringify(state.matrices[0])}`);
    // The summary opens over the page from its button, and Escape closes it.
    check(!(await page.$eval("#summary", (e) => e.matches(":popover-open"))), "the summary starts open");
    // It is under its button from the first frame, and inside the window once it has its size.
    const where = () => {
      const panel = document.getElementById("summary").getBoundingClientRect();
      const anchor = document.querySelector(".summary-button").getBoundingClientRect();
      return { open: document.getElementById("summary").matches(":popover-open"), below: panel.top >= anchor.bottom,
               inside: panel.left >= 0 && panel.right <= innerWidth };
    };
    // The page does not allow eval, so the first-frame check repeats the measure of where().
    const first = await page.evaluate(() => new Promise((resolve) => {
      document.querySelector(".summary-button").click();
      requestAnimationFrame(() => {
        const panel = document.getElementById("summary").getBoundingClientRect();
        const anchor = document.querySelector(".summary-button").getBoundingClientRect();
        resolve({ open: document.getElementById("summary").matches(":popover-open"), below: panel.top >= anchor.bottom });
      });
    }));
    await page.waitForTimeout(100);
    const pop = await page.evaluate(where);
    check(first.open && first.below && pop.open && pop.below && pop.inside, `summary panel: ${JSON.stringify([first, pop])}`);
    await page.keyboard.press("Escape");
    check(!(await page.$eval("#summary", (e) => e.matches(":popover-open"))), "Escape does not close the summary");
    let json = await save("Download JSON");
    check(json.name === "cld-simple-example.json", `JSON name: ${json.name}`);
    let saved = JSON.parse(json.text);
    check(saved.package === "cld-reducer" && saved.version === version && saved.input.source === "Simple example" &&
          saved.input.pairs === 10 && saved.input.means.length === 5 && saved.results.length === 2 &&
          saved.before.letters === 3 && saved.before.assignments === 9, "JSON head");
    // The file keeps the result of the package method and the second stage under their own names.
    checkAgainst(saved.results[0], EXPECTED.simple.letter_minimum, "simple CLD-C");
    check(saved.results[1].method === "letter_then_assignment" && saved.results[1].stats.assignmentsAfter === 8, "JSON second stage");

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
    check(same(summaryRow(state, "Minimizes"), ["One letter for each maximal clique", "Assignments, then distinct letters"]) &&
          same(summaryRow(state, "Assignments"), ["9", "8"]), "CLD-sigma does not state its objective");
    check(state.letters[3][3] === "AC", "simple CLD-sigma does not give group 3 the letters AC");
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
    check(same(state.summary[0], ["", "Before", "CLD-C", "CLD-sigma"]) &&
          same(summaryRow(state, "Minimizes"), ["One letter for each maximal clique", "Distinct letters, then assignments",
                                                "Assignments, then distinct letters"]) &&
          same(summaryRow(state, "Distinct letters"), ["4", "4", "4"]) &&
          same(summaryRow(state, "Assignments"), ["56", "44", "44"]) &&
          same(summaryRow(state, "Assignments removed"), ["", "12 (21.4%)", "12 (21.4%)"]),
          `wheat summary: ${JSON.stringify(state.summary)}`);
    check(state.letters.length === 21 && same(state.letters[0], ["Group", "Before", "CLD-C", "CLD-sigma"]), "wheat letters table");
    json = await save("Download JSON");
    saved = JSON.parse(json.text);
    check(json.name === "cld-wheat-yield.json" && saved.input.means === null && saved.input.pairs === 190, "wheat JSON head");
    checkAgainst(saved.results[0], EXPECTED.wheat.letter_minimum, "wheat CLD-C");
    checkAgainst(saved.results[2], EXPECTED.wheat.assignment_minimum, "wheat CLD-sigma");
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
    check(csv.name === "cld-wheat-yield.csv" && csvLines.length === 101 && csvLines[0] === "method,group,letters,assignments" &&
          csvLines[1] === "before,1,ABCD,A B C D" && csvLines[21] === "letter_minimum,1,ABCD,A B C D" &&
          csvLines[41].startsWith("letter_then_assignment,1,") && csvLines[80] === "assignment_minimum,20,C,C" &&
          csvLines[100].startsWith("assignment_then_letter,20,"), `CSV: ${csvLines[1]}`);
    if (shots) await page.screenshot({ path: join(shots, "wide-wheat.png") });
    // An open summary whose button scrolls out of the window closes; it never hangs outside the window.
    const summaryAfterScroll = async (scroll) => {
      await page.click(".summary-button");
      await page.waitForTimeout(100);
      await page.evaluate(scroll);
      await page.waitForTimeout(100);
      return page.evaluate(() => {
        const panel = document.getElementById("summary");
        const r = panel.getBoundingClientRect();
        return { open: panel.matches(":popover-open"), top: r.top, bottom: r.bottom, height: innerHeight };
      });
    };
    let scrolled = await summaryAfterScroll(() => { document.querySelector("#reduce-view .results-pane").scrollTop += 700; });
    check(!scrolled.open, `the summary stays open after its button left the window: ${JSON.stringify(scrolled)}`);
    scrolled = await summaryAfterScroll(() => { document.querySelector("#reduce-view .results-pane").scrollTop -= 690; });
    check(!scrolled.open || (scrolled.top >= 0 && scrolled.bottom <= scrolled.height), `summary after a short scroll: ${JSON.stringify(scrolled)}`);
    await page.keyboard.press("Escape");
    await page.evaluate(() => { document.querySelector("#reduce-view .results-pane").scrollTop = 0; });

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
    check(same(state.letters.slice(1).map((row) => row[2]), ["A", "AB", "BC", "C"]), "letters of the pasted input");
    check(same(state.matrices[0][0].slice(1), LABELS), "matrix labels");
    check(await page.evaluate(() => document.querySelector("#results img, #results b") === null && window.__xss === undefined),
          "a label was read as markup");
    saved = JSON.parse((await save("Download JSON")).text);
    check(saved.input.source === "Pasted text" && same(saved.results[0].rows.map((r) => r.group), LABELS), "JSON labels");
    const labelCsv = (await save("Download CSV")).text.split("\n");
    check(labelCsv[1] === 'before,"<img src=x onerror=""window.__xss=1"">",A,A' &&
          labelCsv[5] === 'letter_minimum,"<img src=x onerror=""window.__xss=1"">",A,A' &&
          labelCsv[7] === "letter_minimum,'=1+1,BC,B C" && labelCsv[8] === 'letter_minimum,"a,b",C,C', `CSV labels: ${labelCsv}`);

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
    check(same(state.letters, [["Group", "Mean", "Before", "CLD-C"], ["high", "9.5", "A", "A"], ["mid", "5", "AB", "AB"],
                               ["low", "1.25", "B", "B"]]),
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
    // The limit counts characters, not bytes: 2,600,000 two-byte characters are read, and a file with
    // more than 5,000,000 characters is not.
    const wide = "group1,group2,significant\n" + "é".repeat(2_600_000) + ",b,false\n";
    await page.setInputFiles("#pairs-file", { name: "wide.csv", mimeType: "text/csv", buffer: Buffer.from(wide) });
    await wait((n) => document.getElementById("pairs").value.length === n, wide.length);
    await page.setInputFiles("#pairs-file", { name: "long.csv", mimeType: "text/csv", buffer: Buffer.from("x".repeat(5_000_001)) });
    await wait(() => document.querySelector(".problem > p")?.textContent ===
      "long.csv has more characters than the page reads (5,000,000).");
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
    check(same(state.letters.slice(1), [["low", "1", "B", "B"], ["mid", "2", "AB", "AB"], ["high", "3", "A", "A"]]),
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
    // The live time changes every 200 ms: the timers run for more than two of these changes.
    const during = await page.evaluate(() => new Promise((resolve) => {
      const first = document.querySelector(".live-time").textContent;
      const start = performance.now();
      let ticks = 0;
      const tick = () => {
        if (++ticks < 20 || performance.now() - start < 450) { setTimeout(tick, 10); return; }
        requestAnimationFrame(() => resolve({
          first, last: document.querySelector(".live-time").textContent, elapsed: performance.now() - start, ticks,
          title: document.querySelector(".headline-title").textContent, workers: window.__workers.length,
        }));
      };
      tick();
    }));
    check(during.title === "Solving with CLD-sigma…" && during.workers === 1, `busy state: ${JSON.stringify(during)}`);
    check(during.elapsed < 1500, `the page was slow during the solve: ${during.elapsed} ms for ${during.ticks} timers`);
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
    // CLD-C finds the letters of this input at once, but its second minimization takes long. Cancel in the
    // second minimization keeps the checked display of the first, and says so.
    await method("letter_minimum");
    await page.click("#run");
    await wait(() => document.querySelector(".headline .muted")?.textContent.startsWith("Step 2 of 2. Second minimization."));
    check((await read()).hint === "Cancel keeps the display of the first minimization.", "the hint of a second minimization");
    await page.click("#run");
    state = await read();
    check(state.title === "CLD-C: 6 letters and 30 assignments" &&
          same(state.letters.slice(1).map((row) => row[2]), BUSY_C_LETTERS), `run after cancel: ${state.title}`);
    check(state.notice === "Cancel stopped the second minimization of CLD-C. Its column shows the display of the first minimization.",
          `notice of a cancelled second minimization: ${state.notice}`);
    check(same(summaryRow(state, "Minimizes"), ["One letter for each maximal clique", "Distinct letters"]),
          "a first minimization is named as the second");
    saved = JSON.parse((await save("Download JSON")).text);
    check(same(saved.results.map((r) => r.method), ["letter_minimum"]), "the JSON of a cancelled second minimization");
    await ready();

    // A change of the method during a solve stops it too.
    await method("assignment_minimum");
    await page.click("#run");
    await busy();
    await method("letter_minimum");
    state = await read();
    check(state.run === "Run" && state.notice.startsWith("The input or the method changed."), "a method change did not stop the run");
    check(same(await page.evaluate(() => window.__workers.map((w) => w.terminated)), [true, true, true, false]),
          "the method change did not terminate the busy worker");
    await ready();
    await page.click("#reset");
    state = await read();
    check(state.pairs === SIMPLE_PAIRS && state.means === SIMPLE_MEANS && state.checked === "letter_minimum" &&
          state.notice === null && state.problem === null && same(state.pressed, ["Simple example"]), "Reset");
    noResult(state, "reset");

    // Cancel after CLD-C and its second minimization, before CLD-sigma: CLD-C keeps its second-stage display.
    await wait(() => document.querySelector(".headline-title")?.textContent === "Before reduction: 3 letters and 9 assignments");
    await page.evaluate(() => { window.__hold = true; });
    await page.click("#compare");
    await wait(() => window.__held.length >= 4);
    await page.evaluate(() => { for (const reply of window.__held.slice(0, 4)) window.__workers.at(-1).deliver(reply); });
    check((await read()).hint === "Cancel keeps the methods that finished.", "the hint between two methods");
    await page.click("#run");
    await page.evaluate(() => { window.__hold = false; window.__held = []; });
    state = await read();
    check(state.notice === "Cancel stopped CLD-sigma. The page shows the methods that finished." &&
          same(state.summary[0], ["", "Before", "CLD-C"]) &&
          same(summaryRow(state, "Minimizes"), ["One letter for each maximal clique", "Distinct letters, then assignments"]) &&
          state.letters[3][3] === "AC", `cancel between two methods: ${JSON.stringify([state.notice, state.summary, state.letters])}`);
    await ready();

    // Replies of a cancelled run arrive late: the page ignores them, from the old worker and with the old id.
    await page.evaluate(() => { window.__hold = true; });
    await page.click("#run");
    await wait(() => window.__held.some((r) => r.type === "done"));
    check((await read()).run === "Cancel", "a held run is not in progress");
    await page.click("#run");
    await page.evaluate(() => { window.__hold = false; });
    await ready();
    const held = await page.evaluate(() => window.__held.map((r) => r.type));
    check(same(held, ["start", "result", "start", "result", "done"]), `held replies: ${held}`);
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
      const [old, current] = window.__workers.slice(-2);
      const [stale, fresh] = [window.__held.slice(0, 5), window.__held.slice(5)];
      window.__hold = false;
      for (const reply of stale) current.deliver(reply);
      // The old worker's replies with the id of the current run: the page takes no reply of an old worker.
      for (const reply of stale) old.deliver({ ...reply, id: fresh[0].id });
      window.__afterStale = document.getElementById("run").textContent;
      for (const reply of fresh) current.deliver(reply);
    });
    await solved();
    state = await read();
    check(await page.evaluate(() => window.__afterStale) === "Cancel", "a late reply ended the next run");
    check(state.title === "CLD-C: 4 letters and 44 assignments" && state.letters.length === 21, `run after late replies: ${state.title}`);

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
    // A reply that is consistent in itself but has other decisions than the input: one letter for all groups.
    await page.evaluate(() => {
      window.__alter = (reply) => {
        const r = reply.reduction;
        for (const row of r.rows) row.letters = row.assignments = "a";
        r.adjacency = r.adjacency.map((line) => line.map(() => true));
        r.stats.numLettersAfter = r.stats.objective = 1;
        r.stats.assignmentsAfter = r.rows.length;
        r.stats.reductionPct = (r.stats.assignmentsBefore - r.rows.length) / r.stats.assignmentsBefore * 100;
        return reply;
      };
    });
    await ready();
    await page.click("#run");
    await wait(() => /^The reply changes the decision for \d+ and \d+\.$/.test(document.querySelector(".problem > p")?.textContent ?? ""));
    noResult(await read(), "reply with other decisions than the input");
    await page.evaluate(() => { window.__alter = (reply) => { reply.milliseconds = NaN; return reply; }; });
    await ready();
    await page.click("#run");
    await wait(() => document.querySelector(".problem > p")?.textContent === "The time of the reply is not a time.");
    noResult(await read(), "reply with a time that is not a number");
    await page.evaluate(() => { window.__alter = null; });
    await ready();
    await page.click("#compare");
    await solved();
    check((await read()).problem === null, "the error stays after a good run");

    // The second stage: CLD-C, then CLD-sigma at the minimum letter count, and the reverse order.
    await page.click('button.example:has-text("Simple example")');
    await page.click("#run");
    await solved();
    state = await read();
    check(state.title === "CLD-C: 3 letters and 8 assignments", `staged title: ${state.title}`);
    const stats = await page.$$eval(".stats .stat", (list) => list.map((s) => [...s.children].map((c) => c.textContent)));
    check(same(stats, [["Distinct letters", "3", "3 before"], ["Assignments", "8", "9 before"],
                       ["Removed", "11.1%", "1 assignment, 0 letters"]]), `staged stats: ${JSON.stringify(stats)}`);
    check(await page.$("#results .intro") === null, "the intro stays with a result");
    check(same(state.summary[0], ["", "Before", "CLD-C"]), "staged summary head");
    const stagedText = await page.$eval(".headline", (e) => e.textContent);
    check(/CLD-C took (<1|\d+) ms in this browser: (<1|\d+) ms for the first minimization and (<1|\d+) ms for the second\./
      .test(stagedText), `stage times: ${stagedText}`);
    // The graph of Table II of the 2012 paper: no letter-minimum display is assignment-minimum.
    await page.click('button.example:has-text("Table II graph")');
    await wait(() => document.querySelector(".headline-title")?.textContent === "Before reduction: 7 letters and 26 assignments");
    await page.click("#compare");
    await solved();
    state = await read();
    check(state.title === "CLD-C and CLD-sigma", `Table II title: ${state.title}`);
    check(same(state.summary[0], ["", "Before", "CLD-C", "CLD-sigma"]), "Table II summary head");
    saved = JSON.parse((await save("Download JSON")).text);
    const [c, cs, sigma, sc] = saved.results;
    check(same(saved.results.map((r) => [r.method, r.stage]), [["letter_minimum", 1], ["letter_then_assignment", 2],
          ["assignment_minimum", 1], ["assignment_then_letter", 2]]), "Table II stages");
    check(cs.stats.numLettersAfter === c.stats.numLettersAfter && sc.stats.assignmentsAfter === sigma.stats.assignmentsAfter &&
          cs.stats.assignmentsAfter > sigma.stats.assignmentsAfter && sc.stats.numLettersAfter > c.stats.numLettersAfter,
          `Table II results: ${JSON.stringify(saved.results.map((r) => r.stats))}`);
    check(saved.before.letters === 7 && saved.before.assignments === 26 && state.matrices.length === 2, "Table II before and matrices");
    // A second stage that does not keep the minimum of its first stage is not shown. Here an extra
    // letter copies the column of A: the display stays valid but has one letter too many. On the
    // Table II graph it still has fewer letters and assignments than the display before reduction.
    await page.evaluate(() => {
      window.__alter = (reply) => {
        if (reply.method !== "letter_then_assignment") return reply;
        const r = reply.reduction;
        for (const row of r.rows) {
          if (row.assignments.split(" ").includes("A")) { row.assignments += " Z"; row.letters += "Z"; }
        }
        r.stats.numLettersAfter += 1;
        r.stats.assignmentsAfter = r.rows.reduce((t, row) => t + row.assignments.split(" ").length, 0);
        r.stats.objective = r.stats.assignmentsAfter;
        r.stats.reductionPct = (r.stats.assignmentsBefore - r.stats.assignmentsAfter) / r.stats.assignmentsBefore * 100;
        return reply;
      };
    });
    await page.click("#run");
    await wait(() => document.querySelector(".problem > p")?.textContent === "The second stage does not keep the minimum of the first stage.");
    noResult(await read(), "second stage without the minimum");
    await page.evaluate(() => { window.__alter = null; });
    await ready();

    // A simulated experiment as input. Generate moves the seed on by one.
    await page.fill("#sim-n", "12");
    await page.fill("#sim-seed", "4");
    await page.click("#sim-generate");
    state = await read();
    check(state.pairs.trim().split("\n").length === 67 && state.means.trim().split("\n").length === 13, "simulated input size");
    check(await page.$eval("#sim-seed", (e) => e.value) === "5", "the seed does not move on");
    check((await page.$eval("#example-note", (e) => e.textContent)).startsWith("Simulated experiment with 12 treatments and seed 4."),
          "simulated note");
    await wait(() => document.querySelector(".headline-title")?.textContent.startsWith("Before reduction"));
    await page.click("#run");
    await solved();
    state = await read();
    check(state.title.startsWith("CLD-C: "), `simulated title: ${state.title}`);
    json = await save("Download JSON");
    check(json.name === "cld-simulated-12-treatments-seed-4.json" &&
          JSON.parse(json.text).input.source === "Simulated, 12 treatments, seed 4", `simulated file: ${json.name}`);
    // After the largest seed, the next one is 1 again.
    await page.fill("#sim-seed", "2147483647");
    await page.click("#sim-generate");
    check(await page.$eval("#sim-seed", (e) => e.value) === "1", "the seed does not start again at 1");

    // A late display before reduction for an earlier input is not shown for a later input.
    await page.evaluate(() => { window.__holdBefore = true; });
    await page.fill("#means", "");
    await page.fill("#pairs", "group1,group2,significant\nA,B,false\n");
    await wait(() => window.__heldBefore.length === 1);
    await page.fill("#pairs", "x,y\n1,2\n");
    await wait(() => document.querySelector(".empty .hint")?.textContent.startsWith("The display before reduction is not available"));
    await page.evaluate(() => {
      window.__holdBefore = false;
      for (const [w, reply] of window.__heldBefore) w.deliver(reply);
    });
    await page.waitForTimeout(200);
    state = await read();
    check(state.title === null && state.letters === null, `a late display before reduction is shown: ${state.title}`);
    // The same for a late reply that arrives before the page asks again for a later, valid input.
    await page.evaluate(() => { window.__heldBefore = []; window.__holdBefore = true; });
    await page.fill("#pairs", "group1,group2,significant\nA,B,false\nA,C,true\n");
    await wait(() => window.__heldBefore.length === 1);
    await page.fill("#pairs", "group1,group2,significant\nA,B,false\n");
    await page.evaluate(() => {
      window.__holdBefore = false;
      for (const [w, reply] of window.__heldBefore) w.deliver(reply);
    });
    const early = await page.evaluate(() => document.querySelector(".empty .hint")?.textContent ?? "");
    check(!early.includes("missing"), `a late reply for an earlier input is shown: ${early}`);
    await wait(() => document.querySelector(".headline-title")?.textContent === "Before reduction: 1 letter and 2 assignments");
    // A display before reduction that does not match the input is not shown.
    await page.evaluate(() => {
      window.__alterBefore = (reply) => {
        reply.before.rows[0].letters = reply.before.rows[0].assignments = "Z";
        return reply;
      };
    });
    await page.click('button.example:has-text("Simple example")');
    await wait(() => document.querySelector(".empty .hint")?.textContent
      .startsWith("The display before reduction is not available: The reply failed the check of the page."));
    state = await read();
    check(state.title === null && state.letters === null, `an altered display before reduction is shown: ${state.title}`);
    // A display before reduction can match every decision and still miss a maximal clique. Here the
    // triangle a, b, c is a maximal clique, but the three other cliques cover its pairs.
    await page.evaluate(() => {
      window.__alterBefore = (reply) => {
        const b = reply.before;
        const members = (t) => b.rows.filter((r) => r.assignments.split(" ").includes(t)).map((r) => r.group).join("");
        const drop = [...new Set(b.rows.flatMap((r) => r.assignments.split(" ")))].find((t) => members(t) === "abc");
        for (const r of b.rows) {
          const tokens = r.assignments.split(" ").filter((t) => t !== drop);
          r.assignments = tokens.join(" ");
          r.letters = tokens.every((t) => t.length === 1) ? tokens.join("") : tokens.join(" ");
        }
        b.letters -= 1;
        b.assignments -= 3;
        return reply;
      };
    });
    const joined = new Set(["a,b", "b,c", "a,c", "a,x", "b,x", "b,y", "c,y", "a,z", "c,z"]);
    const sun = ["a", "b", "c", "x", "y", "z"].flatMap((g, i, all) => all.slice(i + 1).map((h) => `${g},${h},${!joined.has(`${g},${h}`)}`));
    await page.fill("#means", "");
    await page.fill("#pairs", ["group1,group2,significant", ...sun].join("\n") + "\n");
    await wait(() => document.querySelector(".empty .hint")?.textContent === "The display before reduction is not available: " +
      "The reply failed the check of the page. The display before reduction misses a maximal clique of the input.");
    check((await read()).title === null, "a display before reduction without a maximal clique is shown");
    await page.evaluate(() => { window.__alterBefore = null; });

    // A result with other counts before reduction than the display before reduction is not shown,
    // also when the display before reduction arrives after the run.
    const BEFORE_MISMATCH = "The display before reduction does not match the statistics of the package.";
    await page.evaluate(() => {
      window.__alter = (reply) => {
        const s = reply.reduction.stats;
        s.assignmentsBefore += 1;
        s.reductionPct = (s.assignmentsBefore - s.assignmentsAfter) / s.assignmentsBefore * 100;
        return reply;
      };
    });
    await page.click('button.example:has-text("Simple example")');
    await wait(() => document.querySelector(".headline-title")?.textContent === "Before reduction: 3 letters and 9 assignments");
    await page.click("#run");
    await wait(() => document.querySelector(".problem > p")?.textContent === "The display before reduction does not match the statistics of the package.");
    noResult(await read(), "result with other counts before reduction");
    // The same for a second stage with other counts before reduction than its first stage.
    await page.evaluate(() => {
      window.__alter = (reply) => {
        if (reply.method !== "letter_then_assignment") return reply;
        const s = reply.reduction.stats;
        s.assignmentsBefore -= 1;
        s.reductionPct = (s.assignmentsBefore - s.assignmentsAfter) / s.assignmentsBefore * 100;
        return reply;
      };
    });
    await ready();
    await page.click("#run");
    await wait(() => document.querySelector(".problem > p")?.textContent === "The results have different counts before reduction.");
    noResult(await read(), "second stage with other counts before reduction");
    await page.evaluate(() => {
      window.__alter = (reply) => {
        const s = reply.reduction.stats;
        s.assignmentsBefore += 1;
        s.reductionPct = (s.assignmentsBefore - s.assignmentsAfter) / s.assignmentsBefore * 100;
        return reply;
      };
    });
    await ready();
    // A run that ends before its display before reduction arrives waits for it: no result is shown or
    // exported before the page has checked it.
    const heldRun = async (example) => {
      await page.evaluate(() => { window.__heldBefore = []; window.__holdBefore = true; });
      await page.click(`button.example:has-text("${example}")`);
      await wait(() => window.__heldBefore.length === 1);
      await page.evaluate(() => { window.__seen = []; });
      await page.click("#run");
      await wait(() => window.__seen.includes("done"));
      await page.waitForTimeout(100);
      const waiting = await read();
      check(waiting.summary === null && waiting.matrices.length === 0 && waiting.run === "Cancel" &&
            waiting.title === "Waiting for the display before reduction…", `a run waiting for its display before reduction: ${waiting.title}`);
      await page.evaluate(() => {
        window.__holdBefore = false;
        for (const [w, reply] of window.__heldBefore) w.deliver(reply);
      });
    };
    const workersBeforeLate = await page.evaluate(() => window.__workers.length);
    await heldRun("Wheat yield");
    await wait((m) => document.querySelector(".problem > p")?.textContent === m, BEFORE_MISMATCH);
    noResult(await read(), "result with other counts before reduction than a late display before reduction");
    check(await page.evaluate((n) => window.__workers.length === n + 1 && window.__workers[n - 1].terminated, workersBeforeLate),
          "the worker runs on after a result with other counts before reduction");
    await page.evaluate(() => { window.__alter = null; });
    await ready();
    await heldRun("Simple example");
    await solved();
    state = await read();
    check(state.title.startsWith("CLD-C: ") && state.summary[0][1] === "Before",
          `a run after a late display before reduction: ${state.title}`);
    // A start reply for a method that the run does not expect stops the run.
    await page.evaluate(() => {
      window.__alterStart = (reply) => { reply.method = "bogus"; return reply; };
    });
    await ready();
    await page.click("#run");
    await wait(() => document.querySelector(".problem > p")?.textContent === "The reply is for another method.");
    noResult(await read(), "run after a start reply for another method");
    await page.evaluate(() => { window.__alterStart = null; });
    await ready();
    // A ready or before reply with the id of the run stops it.
    // So do a second ready reply without an id and a reply that is not a record.
    for (const [type, message] of [["ready", "The worker sent a reply that a run does not have."],
                                   ["before", "The worker sent a reply that a run does not have."],
                                   ["second ready", "The worker sent a second ready reply."],
                                   ["ready with id null", "The worker sent a second ready reply."],
                                   ["null", "The worker sent a reply that is not a record."],
                                   ["array", "The worker sent a reply that is not a record."],
                                   ["date", "The worker sent a reply that is not a record."]]) {
      await page.evaluate((type) => {
        window.__alter = (reply) => (type === "null" ? null : type === "array" ? [] : type === "date" ? new Date(0)
          : type === "second ready" ? { type: "ready" } : type === "ready with id null" ? { type: "ready", id: null }
          : { type, id: reply.id });
      }, type);
      await ready();
      const workersBefore = await page.evaluate(() => window.__workers.length);
      await page.click("#run");
      await wait((m) => document.querySelector(".problem > p")?.textContent === m, message);
      check(await page.evaluate((n) => window.__workers.length === n + 1, workersBefore), `the worker runs on after a ${type} reply`);
      await page.evaluate(() => { window.__alter = null; });
    }
    // A done before the last result stops the run and starts a new worker.
    await page.evaluate(() => { window.__alterStart = (reply) => ({ type: "done", id: reply.id }); });
    await ready();
    const workersBeforeDone = await page.evaluate(() => window.__workers.length);
    await page.click("#run");
    await wait(() => document.querySelector(".problem > p")?.textContent === "A method has no result.");
    check(await page.evaluate((n) => window.__workers.length === n + 1, workersBeforeDone), "the worker runs on after an early done");
    await page.evaluate(() => { window.__alterStart = null; });
    // A reply of another type for the display before reduction is not shown, and its request ends.
    await page.evaluate(() => { window.__alterBefore = (reply) => ({ type: "start", id: reply.id, method: "letter_minimum", stage: 1 }); });
    await ready();
    await page.click('button.example:has-text("Table II graph")');
    await wait(() => document.querySelector(".empty .hint")?.textContent === "The display before reduction is not available: " +
      "The reply failed the check of the page. The worker sent a reply that the display before reduction does not have.");
    await page.evaluate(() => { window.__alterBefore = null; });
    // That request ended: a run on the same input does not wait for it.
    await page.click("#run");
    await wait(() => document.querySelector(".problem > h2")?.textContent === "The page cannot check the result");
    // A reply that is not a record while only the display before reduction is pending ends that
    // request: a later run says that it cannot check its result, and does not wait.
    await page.evaluate(() => { window.__alterBefore = () => null; });
    await ready();
    await page.click('button.example:has-text("Wheat yield")');
    await wait(() => document.querySelector(".empty .hint")?.textContent === "The display before reduction is not available: " +
      "The reply failed the check of the page. The worker sent a reply that is not a record.");
    await page.evaluate(() => { window.__alterBefore = null; });
    await page.click("#run");
    await wait(() => document.querySelector(".problem > h2")?.textContent === "The page cannot check the result");
    // A display before reduction of an earlier input is not shown for a later input.
    await page.click('button.example:has-text("Simple example")');
    await wait(() => document.querySelector(".headline-title")?.textContent === "Before reduction: 3 letters and 9 assignments");
    await page.fill("#means", "");
    const staleTitle = await page.evaluate(() => document.querySelector(".headline-title")?.textContent ?? null);
    check(staleTitle === null, `the display before reduction of an earlier input is shown: ${staleTitle}`);
    await page.click('button.example:has-text("Simple example")');
    await wait(() => document.querySelector(".headline-title")?.textContent === "Before reduction: 3 letters and 9 assignments");
    // A start or result reply with the right method but another stage stops the run.
    for (const which of ["start", "result"]) {
      await page.evaluate((which) => {
        const another = (reply) => { reply.stage = 2; return reply; };
        if (which === "start") window.__alterStart = another; else window.__alter = another;
      }, which);
      await ready();
      await page.click("#run");
      await wait(() => document.querySelector(".problem > p")?.textContent === "The reply is for another method.");
      noResult(await read(), `run after a ${which} reply for another stage`);
      await page.evaluate(() => { window.__alterStart = null; window.__alter = null; });
    }
    // An error in the second stage says so. An error reply without a text message is a solver error.
    for (const [message, title, text] of [
      ["staged solve failed: Solve error", "The second stage stopped with an error", "staged solve failed: Solve error"],
      [42, "The second stage stopped with an error", "The worker sent an error without a message."],
    ]) {
      await page.evaluate((message) => {
        window.__alter = (reply) => (reply.stage === 2 ? { type: "error", id: reply.id, kind: "bogus", message } : reply);
      }, message);
      await ready();
      await page.click("#run");
      await wait((t) => document.querySelector(".problem > h2")?.textContent === t, title);
      state = await read();
      const problem = state.problem;
      check(problem[1] === text && problem[2] === "The first minimization of CLD-C finished. Its column shows that display." &&
            same(summaryRow(state, "Minimizes").slice(1), ["Distinct letters"]), `second stage error: ${problem}`);
      await page.evaluate(() => { window.__alter = null; });
    }
    // An error that arrives before the start reply of the second stage is still a second stage error.
    await page.evaluate(() => {
      window.__alterStart = (reply) => (reply.stage === 2
        ? { type: "error", id: reply.id, kind: "input", message: "post_hoc_results must not contain self-comparisons" } : reply);
    });
    await ready();
    const workersBeforeEarly = await page.evaluate(() => window.__workers.length);
    await page.click("#run");
    await wait(() => document.querySelector(".problem > h2")?.textContent === "The second stage stopped with an error");
    check(await page.evaluate((n) => window.__workers.length === n + 1, workersBeforeEarly),
          "the worker runs on after an early second stage error");
    await page.evaluate(() => { window.__alterStart = null; });
    // A known kind with a message that is not text is a solver error too, and the page starts a new
    // worker. So is an input error in a second stage, whose first stage accepted the same input.
    for (const [stage, message] of [[1, 42], [2, 42], [2, "post_hoc_results must not contain self-comparisons"]]) {
      await page.evaluate(([stage, message]) => {
        window.__alter = (reply) => (reply.stage === stage ? { type: "error", id: reply.id, kind: "input", message } : reply);
      }, [stage, message]);
      await ready();
      const before = await page.evaluate(() => window.__workers.length);
      await page.click("#run");
      await wait((t) => document.querySelector(".problem > h2")?.textContent === t,
                 stage === 1 ? "The solver stopped with an error" : "The second stage stopped with an error");
      check(await page.evaluate((n) => window.__workers.length === n + 1 && window.__workers[n - 1].terminated, before),
            `the worker runs on after an error reply without text in stage ${stage}`);
      await page.evaluate(() => { window.__alter = null; });
    }
    await ready();
    // A solver error in a run ends it, and the next run starts from a new worker.
    await page.evaluate(() => {
      window.__alter = (reply) => ({ type: "error", id: reply.id, kind: "solver", message: "assignment-minimum MILP failed: Error" });
    });
    let workers = await page.evaluate(() => window.__workers.length);
    await page.click("#run");
    await wait(() => document.querySelector(".problem > h2")?.textContent === "The solver stopped with an error");
    check(await page.evaluate((n) => window.__workers.length === n + 1 && window.__workers[n - 1].terminated, workers),
          "the worker runs on after a solver error");
    await page.evaluate(() => { window.__alter = null; });
    await ready();
    // 26 groups in 13 significant pairs have 8,192 maximal cliques. The check of that display before
    // reduction must not block the page.
    await page.evaluate(() => {
      window.__longest = 0;
      new PerformanceObserver((list) => {
        for (const e of list.getEntries()) window.__longest = Math.max(window.__longest, e.duration);
      }).observe({ type: "longtask" });
    });
    const pairsOf26 = ["group1,group2,significant"];
    for (let i = 0; i < 26; i++) for (let j = i + 1; j < 26; j++) pairsOf26.push(`g${i},g${j},${j === i + 1 && i % 2 === 0}`);
    await page.fill("#means", "");
    await page.fill("#pairs", pairsOf26.join("\n") + "\n");
    await wait(() => document.querySelector(".headline-title")?.textContent === "Before reduction: 8,192 letters and 106,496 assignments");
    await page.waitForTimeout(300);
    const longest = await page.evaluate(() => window.__longest);
    check(longest < 1500, `the display before reduction with 8,192 letters blocked the page for ${Math.round(longest)} ms`);
    // A display before reduction with holes in its rows fails the check; it does not break the page.
    await page.evaluate(() => {
      window.__alterBefore = (reply) => ({ ...reply, before: { ...reply.before, rows: new Array(reply.before.rows.length) } });
    });
    await page.click('button.example:has-text("Wheat yield")');
    await wait(() => document.querySelector(".empty .hint")?.textContent === "The display before reduction is not available: " +
      "The reply failed the check of the page. The display before reduction does not have one row for each group of the input.");
    await page.evaluate(() => { window.__alterBefore = null; });
    // A simulated input again, for the study and the narrow layout below.
    await page.fill("#sim-n", "12");
    await page.fill("#sim-seed", "4");
    await page.click("#sim-generate");
    await wait(() => document.querySelector(".headline-title")?.textContent.startsWith("Before reduction"));
    await page.click("#run");
    await solved();

    // The simulation study, its tables and file, and Cancel.
    await page.click("#view-study");
    check(await page.evaluate(() => document.getElementById("reduce-view").hidden && !document.getElementById("study-view").hidden),
          "the study view does not show");
    for (const [id, value] of [["study-from", "8"], ["study-to", "12"], ["study-step", "4"], ["study-count", "2"]]) {
      await page.fill(`#${id}`, value);
    }
    await page.click("#study-run");
    await wait(() => document.getElementById("study-hint").textContent.startsWith("Done: 4 instances"));
    const study = await page.evaluate(() => [...document.querySelectorAll(".study-table")]
      .map((t) => [...t.querySelectorAll("tr")].map((tr) => [...tr.children].map((cell) => cell.textContent))));
    check(study.length === 3 && same(study[0].slice(1).map((r) => [r[0], r[1]]), [["8", "2"], ["12", "2"]]),
          `study tables: ${JSON.stringify(study)}`);
    check(same(study[1].slice(1).map((r) => r[r.length - 1]), ["2 of 2", "2 of 2"]), "study solves within the limit");
    check(same(study[2].slice(1).map((r) => [r[0], r[1], r[2], r[4], r[6]]), [["12", "100.0%", "100.0%", "18.8", "17.9"]]),
          `comparison row for 12 treatments: ${JSON.stringify(study[2])}`);
    const studyFile = await save("Download instances (CSV)");
    check(studyFile.name === "cld-simulation-study.csv" && studyFile.text.trimEnd().split("\n").length === 5, "study file");
    // A study reply that breaks the order of the minimums, or is for another seed, stops the study.
    for (const [id, value] of [["study-from", "10"], ["study-to", "10"], ["study-count", "2"]]) await page.fill(`#${id}`, value);
    // A solver error in a study ends it, and the page starts a new worker.
    await page.evaluate(() => {
      window.__alterInstance = (reply) => ({ type: "error", id: reply.id, kind: "solver", message: "letter-minimum MILP failed: Error" });
    });
    const studyWorkers = await page.evaluate(() => window.__workers.length);
    await page.click("#study-run");
    await wait(() => document.getElementById("study-hint").textContent ===
      "The study stopped with an error after 0 instances: letter-minimum MILP failed: Error");
    check(await page.evaluate((n) => window.__workers.length === n + 1 && window.__workers[n - 1].terminated, studyWorkers),
          "the study worker runs on after a solver error");
    await page.evaluate(() => { window.__alterInstance = null; });
    await ready();
    for (const [alter, message] of [
      ["order", "The solves of the instance do not keep the order of the minimums."],
      ["seed", "The reply is not for the instance with 10 treatments and seed 1."],
      ["type", "The worker sent a reply that a study does not have."],
      ["ready", "The worker sent a reply that a study does not have."],
      ["null", "The worker sent a reply that is not a record."],
      ["array", "The worker sent a reply that is not a record."],
    ]) {
      await page.evaluate((alter) => {
        window.__alterInstance = (reply) => {
          if (alter === "type") return { type: "start", id: reply.id, method: "letter_minimum", stage: 1 };
          if (alter === "ready") return { type: "ready", id: reply.id };
          if (alter === "null") return null;
          if (alter === "array") return new Array(3);
          if (alter === "order") reply.instance.solves.letter_then_assignment = { letters: 999, assignments: 999, milliseconds: 1 };
          else reply.instance.seed = 999;
          return reply;
        };
      }, alter);
      const workers = await page.evaluate(() => window.__workers.length);
      await page.click("#study-run");
      await wait(() => document.getElementById("study-hint").textContent.startsWith("The study stopped with an error"));
      const hint = await page.$eval("#study-hint", (e) => e.textContent);
      check(hint === `The study stopped with an error after 0 instances: The solver returned an invalid result. ${message}`,
            `altered study reply (${alter}): ${hint}`);
      check(await page.evaluate((n) => window.__workers[n - 1].terminated, workers), "the study worker runs on after an invalid reply");
      await page.evaluate(() => { window.__alterInstance = null; });
      await ready();
    }
    // With another limit than 30 seconds, the page compares nothing with Table X.
    for (const [id, value] of [["study-from", "10"], ["study-to", "10"], ["study-count", "1"], ["study-limit", "10"]]) {
      await page.fill(`#${id}`, value);
    }
    await page.click("#study-run");
    await wait(() => document.getElementById("study-hint").textContent.startsWith("Done: 1 instances"));
    check(await page.evaluate(() => document.querySelectorAll(".study-table").length === 2 &&
      [...document.querySelectorAll("#study-results .hint")].some((e) => e.textContent.startsWith("The comparison with Table X"))),
          "a study with a limit of 10 seconds is compared with Table X");
    await page.fill("#study-limit", "30");
    for (const [id, value] of [["study-from", "45"], ["study-to", "45"], ["study-count", "5"]]) await page.fill(`#${id}`, value);
    const workersBefore = await page.evaluate(() => window.__workers.length);
    await page.click("#study-run");
    await wait(() => document.getElementById("study-run").textContent === "Cancel");
    check(await page.$eval("#run", (e) => e.disabled) && await page.$eval("#compare", (e) => e.disabled),
          "Run is open during the study");
    check(await page.evaluate(() => ["from", "to", "step", "count", "seed", "limit"]
      .every((f) => document.getElementById(`study-${f}`).disabled)), "a study field is open during the study");
    await page.waitForTimeout(300);
    await page.click("#study-run");
    const studyHint = await page.$eval("#study-hint", (e) => e.textContent);
    check(/^Cancelled after \d of 5 instances\.$/.test(studyHint), `study cancel: ${studyHint}`);
    check(await page.evaluate((n) => window.__workers.length === n + 1 && window.__workers[n - 1].terminated, workersBefore),
          "Cancel did not stop the study worker");
    await ready();
    // A change of a field after the study removes its results, which belong to the old fields.
    await page.fill("#study-seed", "2");
    check(await page.$eval("#study-results", (e) => e.children.length === 0) &&
          await page.$eval("#study-hint", (e) => e.textContent === ""), "study results stay after a change of a field");
    // Many short instances: the page draws the study tables a few times, not once for each instance.
    for (const [id, value] of [["study-from", "2"], ["study-to", "3"], ["study-step", "1"], ["study-count", "300"]]) {
      await page.fill(`#${id}`, value);
    }
    await page.evaluate(() => {
      window.__draws = 0;
      new MutationObserver((records) => {
        window.__draws += records.filter((r) => r.removedNodes.length > 0).length;
      }).observe(document.getElementById("study-results"), { childList: true });
    });
    await page.click("#study-run");
    await wait(() => document.getElementById("study-hint").textContent.startsWith("Done: 600 instances"));
    const draws = await page.evaluate(() => window.__draws);
    check(draws < 100, `the study tables were drawn ${draws} times for 600 instances`);
    // A render that does not change the study does not draw its tables again.
    await page.evaluate(() => { window.__draws = 0; });
    for (let k = 0; k < 3; k++) await page.click("#view-study");
    check(await page.evaluate(() => window.__draws) === 0, "the study tables were drawn again without a change of the study");
    await page.click("#view-reduce");

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
    await page.$eval(".summary-button", (e) => e.scrollIntoView({ block: "center" }));
    const narrowScrolled = await summaryAfterScroll(() => window.scrollBy(0, 1500));
    check(!narrowScrolled.open || (narrowScrolled.top >= 0 && narrowScrolled.bottom <= narrowScrolled.height),
          `narrow summary after a scroll: ${JSON.stringify(narrowScrolled)}`);
    await page.keyboard.press("Escape");
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.click("#view-study");
    const narrowStudy = await page.evaluate(() => [document.documentElement.scrollWidth, innerWidth]);
    check(narrowStudy[0] <= narrowStudy[1], `narrow study view: ${narrowStudy}`);
    if (shots) await page.screenshot({ path: join(shots, "narrow-study.png") });
    await page.click("#view-reduce");
    if (shots) {
      await page.screenshot({ path: join(shots, "narrow-top.png") });
      await page.evaluate(() => document.querySelector(".headline").scrollIntoView());
      await page.screenshot({ path: join(shots, "narrow-wheat.png") });
    }

    // A long file name wraps in the result and does not widen the page.
    const longName = `${"x".repeat(200)}.csv`;
    await page.fill("#means", "");
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

    // A loading error of a new worker with a message that is not text: the page says so and does not break.
    const errorsBefore = errors.length;
    await page.evaluate(() => { window.__hold = true; window.__held = []; });
    await page.click("#run");
    await wait(() => window.__held.some((r) => r.type === "start"));
    await page.evaluate(() => { window.__alterLoad = () => ({ type: "error", message: { toString: null } }); });
    await page.click("#run");
    await wait(() => document.getElementById("solver-status").textContent ===
      "The solver could not start: The worker sent an error without a message.");
    check(errors.length === errorsBefore, `console messages after a loading error: ${errors.slice(errorsBefore).join(" | ")}`);

    // While a worker loads, a ready reply with an id, or a reply that is not a record, means that the
    // solver could not start. Each case needs a page of its own, because the solver stays failed.
    for (const [load, message] of [["ready with id", "The worker sent a reply that loading does not have."],
                                   ["null", "The worker sent a reply that loading does not have."]]) {
      const other = await context.newPage();
      await other.addInitScript(instrument);
      await other.goto(file);
      await other.waitForFunction(() => document.getElementById("solver-status").textContent === "Solver ready");
      await other.evaluate((load) => {
        window.__hold = true;
        window.__alterLoad = () => (load === "null" ? null : { type: "ready", id: 7 });
      }, load);
      await other.click("#run");
      await other.waitForFunction(() => window.__held.some((r) => r.type === "start"));
      await other.click("#run");
      await other.waitForFunction((m) => document.getElementById("solver-status").textContent === `The solver could not start: ${m}`,
                                  message, { timeout: 60_000 });
      await other.close();
    }

    check(readFileSync(join(here, "..", "dist", "site", "index.html")).equals(readFileSync(built)),
          "dist/site/index.html is not the built page");
    console.log(`ok: ${built}`);
  } finally {
    await browser.close();
  }
}

await main();
