# Package releases

Version 0.2.0 is a release candidate. The repository follows the turfLP layout:
R at the root, Python in `python/`, and JavaScript in `js/`. PR #4 follows PR #3.
Merge PR #3 first. Then update PR #4 against `main` and repeat its required checks.
Neither a green check nor these instructions grant permission to merge or publish.

## Package identity and open conditions

| Package | Name | Public record |
|---|---|---|
| R | `cldreducer` | <https://cran.r-project.org/package=cldreducer> |
| Python distribution | `cld-reducer` | <https://pypi.org/project/cld-reducer/> |
| Python import | `cld_reducer` | Included in the Python distribution |
| npm | `cld-reducer` | <https://www.npmjs.com/package/cld-reducer> |

On 2026-10-09, public metadata for npm, PyPI, and TestPyPI returned 404. The CRAN
index had no `cldreducer`. These checks do not prove that Python was never
published. John recalls an earlier Python submission. Its identity, uploaded
versions, and date remain unconfirmed.

John Ennis owns the following release decisions:

- Confirm the Python project from the maintainer's project record, an upload
  receipt, or the old project URL. Record only the name, versions, date, and
  public evidence. Do not place account details or credentials in this repo.
- If the project exists, retain its identity and use its existing-project
  trusted publisher. If an old upload is confirmed but the project is now
  unavailable, resolve access or restoration before publication. A 404 does not
  authorize name reuse, version reuse, or recreation. A new-project route needs
  explicit maintainer approval. A different historical name also needs a decision.
- John Ennis confirmed that the example data are public and approved their
  inclusion on 2026-10-10. `inst/COPYRIGHTS`, `python/NOTICE`, and `js/NOTICE`
  record the sources, transformations, distribution scope, and that approval.
  This record does not assign a new license to the source publications.
- John Ennis is the sole package author and CRAN maintainer,
  `john.m.ennis@aigora.com`, as directed by the maintainer on 2026-10-09.
  Published-paper citations and existing copyright notices retain their authors
  and holders.

## Python compatibility

Version 0.2.0 moves Python into `python/`. Git installation needs the
`#subdirectory=python` fragment. It also fixes canonical tie handling, which can
change letter displays from 0.1.0 when multiple minimum displays exist.
See the Python section of `NEWS.md` for all API and input changes.

## Validate the candidate

Keep one unused version in `DESCRIPTION`, `CITATION.cff`, `NEWS.md`, both package
manifests and locks, and Python's `__version__`. `scripts/release.py version`
checks agreement. If 0.2.0 has been used, choose the next unused common version,
at least 0.2.1. Never replace an uploaded version.

Run from the repository root unless a block changes directory:

```sh
cd python
uv sync --locked --extra dev --python 3.13
uv run --locked ruff check . ../scripts
uv run --locked ruff format --check . ../scripts
uv run --locked pytest -q
uv run --locked python ../scripts/test_release.py
uv build
uv run --locked twine check dist/*
uv run --locked python ../scripts/check_python_package.py dist
cd ../js
npm ci
npm run typecheck
npm run build
npm test
npm run test:conformance
npm run check:package
cd ..
python3 conformance/generate.py --check
python3 conformance/test_generate.py
Rscript -e 'testthat::test_local(stop_on_failure=TRUE)'
Rscript conformance/run_r.R
```

CI also covers Python 3.10, minimum dependencies, Node 22 and 24, and five R
platforms including R-devel. The Python artifact check installs the wheel and a
wheel rebuilt from the source distribution into separate clean environments.
It runs the API, CLI, exact label cases, and the included simple and wheat
examples outside the checkout. Example scripts and CSV files belong in the
source distribution; the wheel does not need them. Shared conformance files
remain repository tests. Source-distribution tests skip shared cases when those
files are absent. Do not report those skipped tests as source-distribution proof.
The npm check compiles an installed TypeScript consumer and runs the WASM solver.

Build R outside the checkout, with a PDF toolchain, pandoc, and HTML Tidy available:

```r
candidate_dir <- tempfile("cldreducer-candidate-")
dir.create(candidate_dir)
tarball <- pkgbuild::build(path = ".", dest_path = candidate_dir, manual = TRUE)
source("scripts/check_r_package.R")
check_r_package(tarball)
rcmdcheck::rcmdcheck(tarball, args = c("--as-cran", "--timings"),
                    error_on = "warning", check_dir = file.path(candidate_dir, "check"))
```

Record the candidate commit, SHA-256, R version, all NOTEs, example timings, and
check links in `cran-comments.md`. Do not copy older results onto a new candidate.
Generated help uses the roxygen2 version in `DESCRIPTION`. Regenerate data through
`data-raw/datasets.R`; compare data contents with `data-raw/check-datasets.R`.

## Freeze and run the workflows

After explicit merge approval, merge the reviewed PRs. Resolve the open conditions
above. Set the planned release date in `CITATION.cff` in a reviewed commit.
If the date changes, update it before tagging. Recheck all registries for the
selected version. Obtain separate authorization to tag and publish.

Create an immutable `v0.2.0` tag from the checked commit on `main` and push that
tag only after authorization. Both publication workflows are manual. Run each
from `main`, with that tag and `dry_run=true`:

```sh
gh workflow run publish-npm.yaml --ref main -f tag=v0.2.0 -F dry_run=true
gh workflow run publish-python.yaml --ref main -f tag=v0.2.0 -F dry_run=true
```

The workflows reject invalid tags, commits outside `origin/main`, version
mismatches, and dispatches from another branch. Build jobs have read-only
repository access. The final publish job alone has OIDC access and the matching
GitHub environment. Dry runs skip that job. Each registry has its own concurrency
queue with cancellation disabled. An existing version or a registry read error
stops publication. A dry run does not prove account authorization or installation
from the public registry.

Save each workflow run URL and its artifact bundle. `release-manifest.json`
records the tag, full commit, version, filenames, and SHA-256 hashes. The final
job verifies these hashes and uploads those same files without rebuilding them.
Build and check the R archive from the same tag. Freeze that file too.

With authorization to send the package, run win-builder on that frozen R archive
for R-release and R-devel. The maintainer receives the result emails. Record
links, hashes, and results. If any packaged byte changes, rebuild and repeat the
checks. R-devel CI does not replace win-builder evidence.

## Publish each registry

For the first npm release, use an authorized maintainer account and the required
second factor. Download `npm-candidate` from the successful dry run. Verify its
commit and tag, then compare the downloaded tarball's SHA-256 with the saved
manifest. Stop on a mismatch. Publish that exact path:

```sh
shasum -a 256 downloaded/npm-candidate/packages/cld-reducer-0.2.0.tgz
npm publish downloaded/npm-candidate/packages/cld-reducer-0.2.0.tgz --access public
```

Do not repack the source or publish from a directory. Do not run the npm workflow
with `dry_run=false` for that same version afterward. Test a public installation
in an empty project.

For later npm releases, configure trusted publishing for `aigorahub/cld-reducer`,
workflow `publish-npm.yaml`, environment `npm`, with direct publish permission.
Configure it near the next authorized upload. Current [npm guidance](https://docs.npmjs.com/trusted-publishers/) requires a
new trusted publisher configuration to complete its first successful publication
within two days. Recheck that guidance at release time. Saving a configuration
or running `npm whoami` does not test OIDC. Then dispatch only the npm workflow
with the new tag and `dry_run=false`.

For Python, first resolve the historical identity above. Configure the confirmed
project's publisher for `aigorahub/cld-reducer`, `publish-python.yaml`, environment
`pypi`. A pending publisher is an option only after explicit confirmation of a
new-project route. Dispatch only that workflow with the tag and `dry_run=false`.
Check public metadata and install its wheel in a clean environment. TestPyPI is
optional and uses separate publisher settings.

Submit the frozen, checked R archive through CRAN's submission process. The
maintainer handles confirmation and reviewer correspondence. Record submission
and acceptance as separate events. A submitted package is not yet installable
from CRAN.

Create GitHub release notes with the actual registry state, artifact hashes,
commit, URLs, and any pending CRAN result. A GitHub release does not trigger
uploads. A partial release stays partial until each registry is verified. Retry
only the failed registry. Update public install claims after each registry works.

See [submission status](submission-status.md) for the checked files, hashes,
Windows check requests, and remaining account work.

## External setup record

The table distinguishes completed repository setup from open release conditions.
Registry account access has not been configured by this work.

| Action | Owner | Required evidence |
|---|---|---|
| Python history and identity | John Ennis | Confirmed project and uploaded versions |
| Data reuse basis | John Ennis | Source and permission for each data set |
| Authors and maintainer | Confirmed 2026-10-09 | John Ennis is the sole package author and maintainer |
| GitHub `npm` and `pypi` environments | Configured 2026-10-09 | Only the `main` branch is allowed |
| Registry trusted publishers | Registry maintainer | Exact repository, workflow, environment; successful authorized upload |
| Repository description | Updated 2026-10-09 | Describes R, Python, and JavaScript packages |
| Tag and release | Repository maintainer | Separate authorization, checked commit, hashes |
| win-builder | Current archive accepted by both queues on 2026-10-10 | R-release and R-devel results pending |
| CRAN submission | CRAN maintainer | Submission receipt, then separate acceptance |

References: [npm trusted publishers](https://docs.npmjs.com/trusted-publishers/),
[PyPI trusted publishers](https://docs.pypi.org/trusted-publishers/),
[CRAN submission checklist](https://cran.r-project.org/web/packages/submission_checklist.html).
