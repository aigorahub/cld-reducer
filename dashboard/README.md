# cld-reducer browser page

A page that reduces a compact letter display in the browser. It is one self-contained HTML file: the page, the cld-reducer JavaScript package from [`../js`](../js), the HiGHS WebAssembly solver, and two example data sets are all inside it. Open the file in a browser. It needs no server and no network connection, and the data does not leave the computer.

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
- The means set the order of the groups and of the letters: the group with the highest mean takes the first letter. They do not change a decision. Without means, the groups keep their order of first appearance.
- With means, every group of the decisions needs a mean. With semicolons or tabs, a decimal comma is read as a decimal point.

The page gives the rows to `reduceLetters` of the package as text, and the package checks them with the rules of [`docs/algorithm.md`](../docs/algorithm.md), section 1. The page shows the message of the package when it rejects the input. "Download a template" on the page gives the two files above. The page does not read a matrix of non-significant pairs.

## Methods

- **CLD-C** (`letter_minimum`), the default, gives the fewest distinct letters.
- **CLD-sigma** (`assignment_minimum`) gives the fewest assignments of a letter to a group.

Each method minimizes one quantity. Neither method optimizes the other quantity as a second objective. The results show both quantities for each method, so that you can compare them. "Compare both methods" runs the two methods on the same input and puts them side by side.

For each method the page shows the distinct letters, the assignments, the objective value, the counts before reduction (one letter for each maximal clique), the relationship check of the package, and the time of the package call in this browser. A table gives the letters of each group. A matrix gives the letters that each pair of groups shares, for up to 30 groups: two groups share a letter exactly when the input says that they are not significantly different.

The result does not say whether the essential cover proof or HiGHS produced it. The package does not report that.

## Result files

- "Download JSON" gives the exact labels, the letter tokens, and all statistics of each method.
- "Download CSV" gives one row for each method and group. It puts an apostrophe before a label that starts with `=`, `+`, `-`, or `@`, so that a spreadsheet does not read the label as a formula.

## Run, cancel, and limits

The solver runs in a Web Worker, so the page stays responsive during a solve. Cancel terminates the worker, and the page starts a new one. A change of the input or of the method also stops a solve, and it removes the result that the page shows. If the browser cannot start a worker, the page says so and does not solve.

The page uses the defaults of the package: at most 10,000 maximal cliques, and no time limit. A large or dense input can take long with CLD-sigma. Use Cancel to stop it. Each input field reads up to 5,000,000 characters.

The page checks each result before it shows it: the method, one row for each group, the relationship check, and the shared letters against the input decisions. A result that fails the check is not shown.

A content security policy in the page refuses every network connection. The page needs a browser with WebAssembly, `DecompressionStream`, and module scripts.

## Example data

Both example data sets come from [`../conformance/data`](../conformance/data). The build reads the files, so the page holds the data that the conformance suite uses.

- **Simple example**: 5 groups with means and 10 pairwise decisions, the teaching example of Ennis, Fayle, and Ennis (2012), <https://doi.org/10.1145/2133803.2275596>.
- **Wheat yield**: 20 wheat treatments and 190 pairwise decisions, from Piepho (2004), <https://doi.org/10.1198/1061860043515>, as tabulated in Table VIII of Ennis, Fayle, and Ennis (2012).

## Development

```sh
npm run typecheck      # the page and the tests
npm test               # CSV reading, result checks, result files, and the worker protocol (Vitest)
npm run build
npm run test:browser   # the built file in headless Chrome, opened as a file, with the network off
```

`test:browser` needs Chrome. It looks in the usual places; set `CHROME_PATH` otherwise. Set `SCREENSHOT_DIR` to keep pictures of the page at a wide and a narrow width.

The sources are in `src/`: `app.ts` (the page), `worker.ts` (the solver side), `csv.ts` (reading the input), `data.ts` (methods, examples, the result check, and the result files), and `index.html` and `styles.css`. `build.mjs` bundles them with esbuild and inlines `highs.wasm`, compressed with gzip.

## License

MIT, as the rest of the repository. The built page holds the license of this repository, the license of the npm package `highs`, and the data source record of [`../js/NOTICE`](../js/NOTICE), under "Licenses and data sources".
