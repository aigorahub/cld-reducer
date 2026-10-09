# Package submission readiness

Prepare the R, Python, and JavaScript packages for submission. Fix the four
confirmed Python input defects. Keep the package layout introduced in PR #3.
Test the built packages and define a release process that works for both a first
publication and an update.

This PR starts with the plan and its independent review. Implementation follows
in the same PR after plan approval. Publication is a separate action.

## Branch and scope

- Repository: `aigorahub/cld-reducer`.
- Branch: `fix/submission-readiness`.
- Initial base: `feat/r-js-packages` at
  `5ff162eb902985ed789bef768a813ab7b28b1ab7`, the head of PR #3.
- PR #3 is open. This PR is stacked on it to keep the review diff small.
- After PR #3 merges, merge `origin/main` into this branch if needed, then change
  this PR's base to `main`. Do not rewrite the shared branch or merge either PR
  without approval in the current session.
- Template: `aigorahub/turfLP` at
  `c6e6b864f0d313aad3acd16aaa2454d23a576b8c`. Its local checkout and remote main
  matched when checked on 2026-10-09. Use it as read-only reference material.

The implementation covers package code, tests, metadata, CI, release workflows,
and release instructions. It does not submit a package, send email, create a
release tag, publish a GitHub release, or change registry account settings.
Those actions need a separate release instruction. Account access must not be
copied into repository files or logs.

## Current evidence

Checks on 2026-10-09 at the PR #3 head:

| Area | Evidence |
|---|---|
| Python | 2,996 tests passed with Python 3.13.14 and the committed lock file. Ruff lint and format checks passed. |
| JavaScript | 88 tests passed. Type checks, build, tarball contents, and clean installation passed. Local Node was 26.3.0; CI also covers Node 22 and 24. |
| R | 310 test checks passed, with no failures, warnings, or skips. Local R was 4.6.1. |
| Shared cases | All three languages passed 1,422 reduction, 65 error, and 18 label cases. Python and JavaScript repeated reduction cases with presolve off. |
| Generator | 24 tests passed. Generated fixtures matched the committed files. |
| GitHub | PR #3 had passing checks and no merge conflicts. No GitHub releases or tags were present. |
| Registries | PyPI and TestPyPI returned 404 for `cld-reducer`. npm returned 404 for `cld-reducer`. The CRAN package index had no `cldreducer`. |
| Release setup | GitHub had no `npm` or `pypi` environment. The repository description still named Python only. |

Fugu reviewed the current code through the Elves read-only runner. The host then
reproduced all four findings. The affected Python code paths also exist on
`main`; these are not all new regressions from PR #3.

John recalls an earlier Python submission. A current 404 does not prove that a
package was never published. The release record must preserve this uncertainty.
The previous plan's claim that Python was never on PyPI is not sufficient proof.

## Comparison with turfLP

| Surface | Current match | Work in this PR |
|---|---|---|
| R package at root | `DESCRIPTION`, `R/`, `man/`, `tests/`, `data/`, `inst/` exist. | Verify the built tarball, metadata, examples, and submission notes. |
| Python in `python/` | Package, lock file, examples, and CI exist. | Fix inputs. Check wheel and source distribution independently. |
| npm in `js/` | TypeScript, ESM exports, HiGHS WASM, and package checks exist. | Keep this layout. Extend installed-package checks for repaired behavior where relevant. |
| Shared solver contract | Specification and exact-search fixtures exist. | Keep the algorithm and canonical output rule. Add focused regression coverage. |
| Versions and citations | All packages say 0.2.0. `CITATION.cff` has a release date although no tag exists. | Check version agreement and set release facts only from an actual release decision. |
| Publishing | Separate npm and PyPI workflows use OIDC. | Require an explicit tag and a verified artifact before publication. |
| Data attribution | Help pages cite the papers. turfLP also carries explicit data rights notes. | Record the source and confirmed rights for every distributed data set. |

Do not copy turfLP's unrelated application code, data licenses, dependency floors,
or historical submission results. Keep the existing API names, solver bounds,
Python 3.10 floor, Node 22 floor, and R 4.0 floor unless validation proves a change
is required.

## Work packages

### 1. Establish package identity and version

Record the current names and registry URLs in `docs/releasing.md`:
R `cldreducer`, npm `cld-reducer`, Python distribution `cld-reducer`, and Python
import `cld_reducer`.

Before publication, inspect the maintainer's PyPI and TestPyPI project records,
an old upload receipt, or the actual old project URL. Record only public package
identity, version, and upload date. Do not search unrelated private records.

- If an existing project with these names is confirmed, retain its identity and
  configure an existing-project trusted publisher.
- If another name is confirmed, stop the name-dependent release steps for a
  maintainer decision. Do not silently rename the distribution or create a second
  project. The code and test work can proceed.
- If no history is available, mark history as unresolved. A pending publisher is
  an option only after the maintainer confirms the intended project identity.

Keep 0.2.0 while it remains an unused release candidate. Recheck tags and all
registries before implementation closes. If 0.2.0 has been released meanwhile,
select the next unused common version, at least 0.2.1. Apply it to `DESCRIPTION`,
`js/package.json`, its lock file, `python/pyproject.toml`, its lock file,
`python/src/cld_reducer/__init__.py`, `CITATION.cff`, and `NEWS.md` as needed.
Never replace an uploaded version.

Acceptance: names and uncertainty are recorded. A version check compares all
package metadata and the proposed tag. It runs in ordinary CI without secrets.

### 2. Fix the four Python input defects

Files: `python/src/cld_reducer/validation.py`, `python/src/cld_reducer/cli.py`,
their existing tests, and the Python section of `NEWS.md`.

| Defect | Required behavior | Regression tests |
|---|---|---|
| CSV inference changes labels. | Preserve exact group text in pair and means CSV columns. Disable pandas NA-token conversion for labels. Keep numeric parsing for means. Use the same means-column rule as the API. | CLI round trips for `001`, `002`, `NA`, `NaN`, and an empty-string label. Include custom pair column names and a means CSV. Read output as text in assertions. Invalid significance and missing/non-finite means still fail. |
| pandas promotes numeric labels in a list of rows. | Preserve each original label before string conversion. Do not infer a shared numeric type across a label column. Keep existing behavior for DataFrame inputs and explicit missing values. | Complete comparisons with labels `1`, `2`, and `3.5` return `"1"`, `"2"`, and `"3.5"`. Include a means mapping and a mixed numeric/string collision case. Check that missing labels remain errors. |
| Means functions select different columns. | Use `group` and `mean` only when both exist. Otherwise use the first two columns in both normalization and group ordering. Reuse one small helper if needed. | A means frame `{"treatment": ["a", "b"], "group": [2, 1]}` succeeds for the `a`/`b` pair. Cover normal names, reversed named columns, fallback columns, and too few columns. |
| Ragged adjacency leaks NumPy errors. | Translate the array-conversion failure for uneven rows into `InvalidInputError` with the square-matrix message. Catch the relevant conversion failure, not arbitrary solver errors. | `[[1, 0], [0]]` raises the package error. Keep existing checks for rectangular arrays, missing values, invalid elements, empty input, and valid matrices. |

Add each test first and confirm that it fails for the intended reason on the
starting head. Then make the smallest repair. Do not change the MILP, canonical
tie rule, solver settings, or accepted significance forms.

Keep Python-specific representation tests in Python. Add a shared fixture only
when the input and expected behavior are portable to all three languages.
Change shared fixtures through `conformance/generate.py`, never by hand.

Acceptance: all four failures have regression tests. Exact label round trips and
exception classes pass on Python 3.10 and 3.13. Existing canonical results remain
unchanged. Document the repaired behavior for Python users.

### 3. Verify package artifacts and metadata

Extend the existing package CI jobs rather than add a second build system.

Python:

- Build both wheel and source distribution with `uv build`.
- Run `twine check` on both. Add Twine to development tooling and refresh the
  existing lock file if required.
- Inspect archive contents and metadata. Require package modules, license, and
  expected examples. Reject repository run notes, secrets, and build debris.
- Install the wheel into a fresh environment outside the checkout. Exercise the
  API and CLI, including exact CSV labels and the simple and wheat examples.
- Unpack the source distribution outside the checkout, build a wheel from it,
  install that wheel into another clean environment, and repeat the smoke tests.
- Assert the imported module path belongs to the clean environment. Do not allow
  an editable install or `PYTHONPATH` to hide missing files.
- Shared conformance remains a repository test. The source distribution currently
  omits `conformance/`; document its test skip rather than claim those cases ran
  inside the source distribution.

JavaScript:

- Retain type checks, build, unit tests, and both presolve conformance runs.
- Retain `js/scripts/check-package.mjs` as the tarball check. Exercise installed
  ESM exports and the WASM solver from an empty consumer folder.
- Verify published TypeScript declarations with a small consumer compilation.
  Do not rely only on a text search for exported names.
- Keep the documented browser WASM loading contract. Use a focused smoke test
  if the loader or public exports change; do not add an application to prove it.

R:

- Build and check the tarball outside the checkout. Assert that Python, JS,
  planning files, and local build files are excluded by `.Rbuildignore`.
- Keep generated help, namespace, and data comparisons. Regenerate only with
  the pinned roxygen version and the existing data scripts.
- Run `R CMD check --as-cran` with the PDF manual and inspect example timings.
  Preserve the five-platform R matrix and the separate conformance job.

Acceptance: both Python distribution routes and the npm tarball work outside
the repository. R checks have zero errors and warnings. Every remaining R NOTE
has an exact explanation in `cran-comments.md`. Package metadata has one agreed
version and the correct repository links and license files.

### 4. Make publication explicit and testable

Keep `publish-npm.yaml` and `publish-python.yaml` as separate workflows with
the existing OIDC environments. For this first release cycle, make publication
manual through `workflow_dispatch`. Remove publication on `release: published`.
Creating release notes must not upload both packages. This differs from turfLP's
automatic trigger because npm needs a first manual upload and Python history is
not yet resolved. The structure and authentication remain the same as turfLP.

Each workflow gets a required `tag` input and a `dry_run` input that defaults to
true. Both paths validate the same tag, version, package, and artifact. The dry
path has no publish step and does not need a registry credential. Do not use
`npm publish --dry-run` as proof of registry authorization.

Requirements:

- Accept only the repository's version-tag format, such as `v0.2.0`. Pass the
  input as data through an environment variable; do not interpolate it into shell
  source. Resolve the exact remote tag commit.
- Require the commit to be reachable from `origin/main`. Check out that exact
  commit, not the workflow dispatch branch. Compare its R, Python, JS, and Python
  runtime versions with the tag.
- Run the relevant tests and artifact checks before upload. Python publication
  currently builds without running tests; repair that gap.
- Upload only the artifact built and verified in that run. Give build/test jobs
  read access only. Give only the final publish job `id-token: write` and the
  matching `npm` or `pypi` environment.
- Use a per-registry concurrency group with `cancel-in-progress: false` so two
  publishes cannot race. Recheck whether the version already exists immediately
  before upload. Fail clearly on an existing version; do not silently skip it.
- A retry of one registry does not run the other registry. A partial release
  stays recorded as partial until both registry checks finish.
- Use the exact workflow file as the OIDC identity. Avoid reusable publish
  workflow indirection. Keep logs free of tokens.
- Record artifact filenames, commit, version, and SHA-256 hashes in the workflow
  summary and uploaded build evidence. Report dry-run success separately from
  successful public installation.

Reuse a small version/ref check only if it removes real duplication. Give it
focused tests for invalid tag text, mismatched versions, a missing tag, a tag
outside main, dry-run behavior, and an already published version. Mock registry
reads in tests. Do not add a general release framework.

Acceptance: a dry run cannot publish. An arbitrary branch cannot be published.
Invalid or mismatched tags fail before any upload. The final publish job uses the
verified artifact. Publication is independent for npm and PyPI. Normal PR and
push CI never publish.

### 5. Prepare CRAN evidence and data attribution

Files: `cran-comments.md`, `DESCRIPTION`, `R/data.R`, generated help,
`inst/`, `python/README.md`, `js/README.md`, and package file lists as needed.

- Retain John Ennis and `john.m.ennis@aigora.com` as the proposed CRAN maintainer.
  Retain the six listed authors and Aigora's recorded roles until confirmed.
  Do not invent ORCID identifiers or change authorship from memory.
- Record each data set's source, transformation, and confirmed reuse basis.
  A paper citation is not evidence of a data license. Do not copy turfLP's
  unrelated CC licenses or label this data MIT without evidence.
- Use `inst/COPYRIGHTS` if a separate data-rights notice is needed, following
  turfLP's pattern. Include the applicable notice in every artifact that ships
  the data. Add a `Copyright` pointer only when its target exists in the package.
- Data rights are a release condition for every affected distribution, not only
  R. If rights cannot be confirmed, record the block. Do not remove example data
  or redesign tests without a maintainer decision.
- Update `cran-comments.md` with actual results, dates, versions, and commit.
  Keep any expected incoming NOTE separate from infrastructure-only notes.
- Try HTML validation with Tidy installed. Do not promise that installing it
  removes every NOTE. Record the actual output.
- Require R-devel evidence from the current CI check and win-builder. Record
  R-release win-builder evidence too. Use one frozen tarball for these external
  checks and submission. Rebuild and recheck if packaged bytes change.

Acceptance: every included data set has a confirmed attribution record or a
clearly stated publication block. CRAN notes contain no fabricated results.
Examples stay short. External check links identify the actual candidate tarball.

### 6. Write the release instructions

Create `docs/releasing.md`. Link it from the root README. Correct claims about
publication status without claiming that a 404 proves no historical release.
Explain the new tag-based manual workflows and the existing API changes from
Python 0.1.0. Keep the algorithm document as the single technical contract.

The instructions must give this order:

1. Finish PR #3 and this PR. Obtain explicit merge approval. Wait for all final
   checks on the candidate commit. Resolve the Python project identity, data
   rights, maintainer, and author roles.
2. Confirm one unused version across registries. Set the citation release date
   to the planned release date in a reviewed commit. If that date changes before
   release, update it before creating the tag. Do not publish unreleased dates as
   facts in README text.
3. With separate release authorization, create the immutable version tag from
   merged main. Run dry runs for both publishing workflows. Preserve their
   artifacts and hashes. Build and check the R tarball from that same tag.
4. With authorization to send the package, run win-builder checks and record
   results for the exact R tarball. The maintainer must receive the result emails.
5. For npm's first release, publish the verified tarball through an authorized
   maintainer account with the required second factor. Do not dispatch the npm
   publishing workflow for that same version afterward. Verify an installation
   from the public registry in an empty project.
6. For later npm versions, configure the trusted publisher with repository
   `aigorahub/cld-reducer`, file `publish-npm.yaml`, environment `npm`, and direct
   publish permission. Configure it near the next authorized upload: current npm
   guidance gives a new configuration two days to complete its first successful
   publication. A saved configuration or `npm whoami` is not an OIDC test.
7. For Python, use the confirmed existing project or an explicitly confirmed new
   project. Configure `publish-python.yaml`, environment `pypi`, and repository
   `aigorahub/cld-reducer` as the trusted publisher. Dispatch only the Python
   workflow for the tag. Verify metadata and a clean public wheel installation.
   TestPyPI is optional and has separate publisher settings.
8. Submit the checked R tarball through CRAN's submission process. The maintainer
   handles confirmation and reviewer correspondence. Record submission separately
   from acceptance. Submission does not make a CRAN install command work yet.
9. Create GitHub release notes with the actual registry state. This does not
   upload packages under the new workflow contract. Record package URLs, commit,
   hashes, and pending CRAN status. Update README install claims only as each
   registry becomes available.

GitHub environment creation, registry publisher setup, repository description
and topic updates, tagging, and publication are outside the implementation PR.
The release checklist names the owner and records done/pending evidence for each.
The proposed description covers R, Python, and JavaScript. Do not mark these
external steps complete from a passing code test.

## Validation and completion

Run focused regression tests during each repair. At the final implementation
head, run the full existing Python, JS, R, and generator suites, plus the new
artifact and workflow checks. Preserve CI coverage of Python 3.10 and 3.13,
Node 22 and 24, and the existing R platforms. Re-run only affected checks after
small review fixes, then confirm final CI is green at the exact head.

| Gate | Required result |
|---|---|
| Python input fixes | Four original failures reproduced, then repaired with tests. No weakened tests. |
| Canonical behavior | All shared fixtures pass in R, Python, and JS. Both Python and JS presolve settings pass. |
| Artifacts | Wheel, sdist-built wheel, npm tarball, and R tarball pass the checks above outside the checkout. |
| Metadata | Package names, versions, licenses, links, and citation fields agree with the release decision. |
| Publishing | Tests prove tag/ref checks and dry-run behavior. No live upload is required to pass this PR. |
| CRAN | Zero errors and warnings in the automated checks. Exact NOTEs are explained. External checks stay pending until actually run. |
| Documentation | Release instructions state package identity uncertainty, first-upload steps, external owners, and the four Python fixes. |
| Review | Fugu plan findings are resolved or explained. An independent implementation review is complete. |

The code PR can be ready to merge while account setup or external submission is
pending. It is not ready to publish until the identity, data, maintainer, artifact,
and external-check conditions are met. No passing test grants merge or publish
authority.

## Sources

- [PR #3](https://github.com/aigorahub/cld-reducer/pull/3), its files and CI at the
  starting commit above.
- [turfLP PR #9](https://github.com/aigorahub/turfLP/pull/9), publishing setup.
- [turfLP PR #10](https://github.com/aigorahub/turfLP/pull/10), CRAN resubmission
  notes and example timing fixes.
- [PyPI project metadata](https://pypi.org/pypi/cld-reducer/json) and
  [TestPyPI project metadata](https://test.pypi.org/pypi/cld-reducer/json), both
  returned 404 on 2026-10-09.
- [PyPI pending publishers](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/)
  and [publishing with OIDC](https://docs.pypi.org/trusted-publishers/using-a-publisher/).
- [npm trusted publishing](https://docs.npmjs.com/trusted-publishers/), including
  provider identity, direct publish permission, and configuration expiry.
- [CRAN submission checklist](https://cran.r-project.org/web/packages/submission_checklist.html).

## Plan review

Pending Fugu review of this plan. Record the review result and any revisions here.
