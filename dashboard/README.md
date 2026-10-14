# cld-reducer browser page

A page that reduces a compact letter display in the browser. It is one self-contained HTML file: the page, the cld-reducer JavaScript package from [`../js`](../js), the HiGHS WebAssembly solver, and two example data sets are all inside it. Open the file in a browser. It needs no server and no network connection, and the data does not leave the computer.

The page shows the letters before reduction, one letter for each maximal clique. Run puts the reduced letters next to them, with the time of each solve. A second view repeats the simulation study of Ennis, Fayle, and Ennis (2012) in the browser.

The page reads significance decisions. It does not run significance tests on measurements. Give it the decisions of your own analysis.

This package is private. It is not part of the R, Python, or npm archives, and it has no version of its own. The page shows the version of the JavaScript package.

## Build

The build uses the JavaScript package in `../js` and its `highs` dependency, so install that first. Node.js 22 or later.

```sh
cd js && npm ci
cd ../dashboard && npm ci && npm run build
open dist/cld-reducer-dashboard.html     # or double-click the file
```

`npm run build` writes `dist/cld-reducer-dashboard.html` (about 1.7 MB). The file can be copied or sent as it is. The build also writes the same page as `dist/site/index.html`, for a static web host. No host is set up. The CI workflow `js.yaml` builds the page and keeps it as the `cld-reducer-dashboard` artifact of each run.

## Input format

**Pairwise decisions**, by paste or by file: one row for each pair of groups. A group is one item or treatment.

```csv
group1,group2,significant
Control,Low dose,false
Control,Mid dose,true
Control,High dose,true
Low dose,Mid dose,false
Low dose,High dose,true
Mid dose,High dose,false
```

- The first row holds the column names `group1`, `group2`, and `significant`. Their case does not matter. Other columns are ignored.
- `significant` is true when the two groups differ significantly. The package reads the values: `true` or `false`, `t` or `f`, `yes` or `no`, `y` or `n`, `1` or `0`, and `significant` or `not significant` or `ns`, in any letter case.
- Every unordered pair of groups needs exactly one row. A missing pair is an error. The page does not read it as a significant difference. A duplicate pair and a row that compares a group with itself are errors too.
- Commas, semicolons, or tabs separate the values. Quoted values and a byte order mark are read. Spaces around a value without quotes are removed. A value in quotes stays as it is.

**Means**, optional: one row for each group.

```csv
group,mean
Control,4.1
Low dose,4.6
Mid dose,5.2
High dose,5.9
```

- The first row holds the column names `group` and `mean`.
- The means set the order of the groups and of the letters: the group with the highest mean takes the first letter. They do not change a decision. Without means, the group order is the order of first appearance in the `group1` column, followed by the labels that appear in the `group2` column only.
- With means, every group of the decisions needs a mean. With semicolons or tabs, a decimal comma is read as a decimal point.

The page gives the rows to `reduceLetters` of the package as text, and the package checks them with the rules of [`docs/algorithm.md`](../docs/algorithm.md), section 1. The page shows the message of the package when it rejects the input. "Download a template" on the page gives the two files above. The page does not read a matrix of non-significant pairs.

## Methods

- **CLD-C** (`letter_minimum`), the default, gives the fewest distinct letters.
- **CLD-sigma** (`assignment_minimum`) gives the fewest assignments of a letter to a group.

Each package method minimizes one quantity. Neither optimizes the other quantity as a second objective. "Compare both methods" runs the two methods on the same input and puts them side by side.

### Second stage (experimental)

"Then minimize the other quantity" is on by default. It adds a second solve after each method:

- **CLD-C then CLD-sigma** gives the fewest assignments among the displays with the minimum letter count of CLD-C.
- **CLD-sigma then CLD-C** gives the fewest letters among the displays with the minimum assignment count of CLD-sigma.

The second stage keeps the minimum of the first stage exactly. It uses the CLD-sigma model of the package with one more binary column for each maximal clique, the canonical solve engine of the package, and the same HiGHS solver. [`../docs/plans/dashboard-staged-solve/plan.md`](../docs/plans/dashboard-staged-solve/plan.md) states the model and why it is exact. The tests compare it with an exhaustive search on more than 1,000 small graphs. The second stage exists in this page only. It is not part of the specification or of the R, Python, and npm packages.

On the graph of Table II of the 2012 paper the two orders differ: no display with the fewest letters has the fewest assignments.

### What the page shows

For the letters before reduction and for each result, the page shows the distinct letters, the assignments, the assignments and letters removed, the relationship check of the package, and the time in this browser. The time of a second stage covers the second solve only. A table gives the letters of each group before and after reduction. A matrix gives the letters that each pair of groups shares in each final result, for up to 30 groups: two groups share a letter exactly when the input says that they are not significantly different.

The page checks that the counts of the letters before reduction equal the statistics of the package. A result does not say whether the essential cover proof or HiGHS produced it. The package does not report that.

## Result files

- "Download JSON" gives the exact labels, the letter tokens, and all statistics of the letters before reduction and of each result, with its stage and time.
- "Download CSV" gives one row for each group before reduction, then one row for each result and group. It puts an apostrophe before a label that starts with `=`, `+`, `-`, or `@`, so that a spreadsheet does not read the label as a formula.

## Run, cancel, and limits

The solver runs in a Web Worker, so the page stays responsive during a solve. Cancel terminates the worker, and the page starts a new one. A change of the input or of the method also stops a solve, and it removes the result that the page shows. If the browser cannot start a worker, the page says so and does not solve.

The page uses the defaults of the package: at most 10,000 maximal cliques, and no time limit. A large or dense input can take long with CLD-sigma or a second stage. Use Cancel to stop it. Each input field reads up to 5,000,000 characters.

The page checks each result before it shows it: the method, one row for each group, the relationship check, and the shared letters against the input decisions. A result that fails the check is not shown.

A content security policy in the page refuses every network connection. The page needs a browser with WebAssembly, `DecompressionStream`, and module scripts.

## Example data

The two data sets come from [`../conformance/data`](../conformance/data). The build reads the files, so the page holds the data that the conformance suite uses.

- **Simple example**: 5 groups with means and 10 pairwise decisions, the teaching example of Ennis, Fayle, and Ennis (2012), <https://doi.org/10.1145/2133803.2275596>.
- **Wheat yield**: 20 wheat treatments and 190 pairwise decisions, from Piepho (2004), <https://doi.org/10.1198/1061860043515>, as tabulated in Table VIII of Ennis, Fayle, and Ennis (2012).
- **Table II graph**: the 8 vertices of the clique membership matrix of Table II of Ennis, Fayle, and Ennis (2012). It is a graph, not measured data.

The triticale data of Table VI of the 2012 paper is not in the page. The data records of [`../js/NOTICE`](../js/NOTICE) have no approval for it.

### Simulated experiments

"Generate" makes a new input from a number of treatments and a seed. The same pair gives the same experiment. Each click uses the seed shown and then adds 1. Section 8 of the 2012 paper generates its graphs with the method of Section 3.2 of Gramm, Guo, Hüffner, Niedermeier, Piepho, and Schmid (2007), Computational Statistics and Data Analysis 52, 725-736. The page uses that model:

- treatment means from a normal distribution with mean 42.6 and variance 12.7;
- variances of the sample means from a gamma distribution with shape 4.12 and scale 0.429;
- correlations tanh(z), with z normal with mean 0.00625 and variance 0.00182; non-positive eigenvalues of the correlation matrix become the smallest positive eigenvalue;
- the covariance matrix D^(1/2) R D^(1/2), and t = (m_i - m_j) / sqrt(s_ii + s_jj - 2 s_ij);
- a pair differs significantly when |t| > 1.96.

The groups are T1 to Tn, from the highest mean down. The means go into the means field with three decimals.

These graphs are denser than the graphs of Table X of the 2012 paper. The mean assignment count of the maximal display is 18.0, 60.3, and 126.9 for 10, 20, and 30 treatments (seeds 1 to 300, 1 to 150, and 1 to 60). Table X reports 14.38, 42.87, and 80.03. No reading of the published parameters (variance or standard deviation, gamma scale or rate) gives the Table X values. The 2012 program can differ from the published text in a detail that the text does not state. The page keeps the published model and says so next to the published figures.

## Simulation study

The second view repeats the experiment of Section 8 of the 2012 paper. It takes a range of treatment counts, a count of instances for each, a first seed, and a time limit for each solve (30 seconds by default, as in 2012). Each instance runs CLD-C, CLD-sigma, and both second stages with the `timeLimit` option of the package. The view shows, for each number of treatments:

- the mean letters and assignments before reduction, after each method, and after each second stage;
- the number of instances in which no display with the fewest letters has the fewest assignments;
- the mean and maximum time of each solve, and the number of instances in which all four solves finished.

Next to these are the published MA, EA, PC, and ET values of Table X and the counts of Table XI. The 2012 study used 1,000 other instances for each size and FIND-AM on 2012 hardware, and its MA and EA cover only the searches that finished. The page computes no speed factor. "Download instances (CSV)" gives every instance with its counts and times. Cancel stops the study and keeps the finished instances.

## Development

```sh
npm run typecheck      # the page and the tests
npm test               # CSV reading, the generator, the second stage, result checks, files, and the worker protocol
npm run build
npm run test:browser   # the built file in headless Chrome, opened as a file, with the network off
```

`test:browser` needs Chrome. It looks in the usual places; set `CHROME_PATH` otherwise. Set `SCREENSHOT_DIR` to keep pictures of the page at a wide and a narrow width.

The sources are in `src/`: `app.ts` (the page), `worker.ts` (the solver side), `staged.ts` (the letters before reduction and the second stage), `simulate.ts` (simulated experiments), `study.ts` (study summaries), `csv.ts` (reading the input), `data.ts` (methods, examples, the published tables, the result check, and the result files), and `index.html` and `styles.css`. `build.mjs` bundles them with esbuild and inlines `highs.wasm`, compressed with gzip.

## License

MIT, as the rest of the repository. The built page holds the license of this repository, the license of the npm package `highs`, and the data source record of [`../js/NOTICE`](../js/NOTICE), under "Licenses and data sources".
