# Staged solve, simulated examples, and before and after letters in the browser page

Status: implemented on branch `feat/dashboard-staged-solve`. The pull request holds the verification record.

Workspace: `/Users/john/aigora/dev/cld-reducer-pre-model-certificate`.
Branch: `feat/dashboard-staged-solve`.
Base: `4474ea6114d4068acb915e549ccedd97cc63ea14` (`main`, development version 0.3.2).

## Goal

The browser page must show how much the reduction removes and how fast it runs.
The user asked for four changes:

1. Many more examples, generated as in the 2012 paper.
2. The letters before reduction, and the letters after reduction next to them,
   with the time of each solve.
3. A staged solve: CLD-C, then CLD-sigma subject to the CLD-C result, and the
   reverse order. Both stages are timed.
4. A presentation that shows effect and speed with measured numbers.

## Scope

All changes are in `dashboard/` and the documents. The R, Python, and npm
packages do not change. The change is version 0.3.2, the development version
of `main`; the documents describe 0.3.2 as this change.

### Simulated examples

Section 8 of Ennis, Fayle, and Ennis (2012) generates graphs with the method of
Gramm et al. Section 3.2 of Gramm, Guo, Hüffner, Niedermeier, Piepho, and Schmid
(2007), Computational Statistics and Data Analysis 52, 725-736, gives the model:

- n treatment means from a normal distribution with mean 42.6 and variance 12.7;
- variances of the sample means from a gamma distribution with shape 4.12 and
  scale 0.429;
- correlations tanh(z) with z normal, mean 0.00625 and variance 0.00182;
  non-positive eigenvalues of the correlation matrix are set to the smallest
  positive eigenvalue;
- the covariance matrix D^(1/2) R D^(1/2);
- a pair differs significantly when |t| > 1.96, with
  t = (m_i - m_j) / sqrt(s_ii + s_jj - 2 s_ij).

The page generates such an experiment for a chosen n and seed. A seeded
generator makes each example reproducible.

Result of the implementation: the graphs of this model have larger maximal
displays than Table X of the 2012 paper reports. The mean assignment count of the maximal display is
18.0, 60.3, and 126.9 for n = 10, 20, and 30, against 14.38, 42.87, and 80.03 in
Table X. Table X averages over the searches that finished: all of them at
n = 10, so that comparison is direct. None of the eight readings of the
ambiguous parameters that we tried (variance or standard deviation, gamma scale
or rate, gamma value as variance or standard deviation) matches.
The page keeps the published model and states the difference. It does not fit
parameters to Table X.

The page also gets the graph of Table II of the 2012 paper. In that graph no
letter-minimum display is assignment-minimum. The triticale data of Table VI
stays out: the data records of `js/NOTICE` have no approval for it.

### Before and after

The display before reduction has one letter for each maximal clique. The page
computes it in the worker with the package's own modules: input checks
(`pairsToGraph`), maximal cliques, and letter assignment. The page shows it when
the input changes. Run puts the reduced letters next to it. The page checks that
the counts of the before display equal `assignmentsBefore` and
`numLettersBefore` of the package result.

### Staged solve

The staged solve is lexicographic:

- CLD-C, then CLD-sigma: the fewest assignments among displays with the minimum
  letter count L of CLD-C.
- CLD-sigma, then CLD-C: the fewest letters among displays with the minimum
  assignment count A of CLD-sigma.

The model is the CLD-sigma model with one binary column u for each maximal
clique and the rows x(c, g) <= u(c). One column for each maximal clique loses no
display: two letters inside one maximal clique merge into their union, with
fewer letters and no more assignments. The weighted vertex reduction stays
exact: a vertex can take the pattern of a twin with fewer memberships, and
neither count increases.

- CLD-C, then CLD-sigma adds the row sum(u) <= L and minimizes the weighted
  memberships. The decisions are the memberships, so the canonical engine and
  the essential cover proof of the package apply unchanged.
- CLD-sigma, then CLD-C adds the row sum(w x) <= A and minimizes sum(u). The
  decisions are the clique columns, and the proof is off. A third solve on the
  chosen cliques gives the canonical memberships. Its minimum must equal A.

The staged solve is experimental and exists in the page only. It reuses the
package model, the canonical engine, and the HiGHS loader. It is not part of the
specification or the R, Python, and npm packages.

Each stage is timed in the worker. Stage 1 is the package call. Stage 2 is the
staged solve.

### Simulation study

A second view repeats the experiment of Section 8 of the 2012 paper in the
browser: a range of n, a count of instances for each n, and a time limit of 30
seconds for each solve. For each n it shows the mean assignments before and after,
the letters before and after, the share solved within the limit, and the mean
and maximum time. Next to these are the published PC, ET, MA, and EA values of
Table X. The page states the source and date of those values and computes no
speed factor.

## Verification

- Unit tests: the generator (reproducible seeds, the normal and gamma moments,
  the eigenvalue repair, the order of the groups), the staged solve against an
  exhaustive search on small graphs (the exhaustive inputs of the conformance
  suite), the before display against the package statistics, and the extended
  reply check.
- Browser test of the built file: the new examples, the before and after
  columns, both staged orders with two timings, the simulation view with
  cancellation, and the existing checks.
- Existing gates of PR #13.

## Out of scope

A change to the specification or the R, Python, and npm packages, a public API
for the staged solve, and hosting.
