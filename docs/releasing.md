# Package releases

The repository follows the turfLP layout: R at the root, Python in `python/`,
and JavaScript in `js/`. Version 0.2.0 is tagged and published on PyPI and npm.
CRAN review is pending.
See [submission status](submission-status.md) for the current evidence.
These instructions describe future releases. Checks do not grant permission
to merge or publish.

## Package identity and release decisions

| Package | Name | Public record |
|---|---|---|
| R | `cldreducer` | <https://cran.r-project.org/package=cldreducer> |
| Python distribution | `cld-reducer` | <https://pypi.org/project/cld-reducer/> |
| Python import | `cld_reducer` | Included in the Python distribution |
| npm | `cld-reducer` | <https://www.npmjs.com/package/cld-reducer> |

The earlier Python publication was sensPy, a separate project.
Version 0.2.0 is the first verified `cld-reducer` PyPI release.
Its trusted publisher is configured for this repository. Do not create a new
pending publisher or change the package name for later releases.

John Ennis owns the following release decisions:

- Keep the existing package names and publisher settings. Check the current
  registry versions before choosing a new release version. Never replace a
  published version.
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

Version 0.2.0 is already used. Choose the next unused common version for a
future release, at least 0.2.1. Keep that version in `DESCRIPTION`,
`CITATION.cff`, `NEWS.md`, both package manifests and locks, and Python's
`__version__`. `scripts/release.py version` checks agreement. Never replace an
uploaded version.

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

Create an immutable tag for the new version from the checked commit on `main`.
Push it only after authorization. Both publication workflows are manual.
The examples below use `v0.2.1`; confirm it is unused and substitute the selected
version where needed. Run each workflow from `main`, with that tag and
`dry_run=true`:

```sh
gh workflow run publish-npm.yaml --ref main -f tag=v0.2.1 -F dry_run=true
gh workflow run publish-python.yaml --ref main -f tag=v0.2.1 -F dry_run=true
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

The first npm release, 0.2.0, used the maintainer account and a second factor.
For an authorized manual upload of a future version, use the same process. Download `npm-candidate` from the successful dry run. Verify its
commit and tag, then compare the downloaded tarball's SHA-256 with the saved
manifest. Stop on a mismatch. Publish that exact path:

```sh
shasum -a 256 downloaded/npm-candidate/packages/cld-reducer-0.2.1.tgz
npm publish downloaded/npm-candidate/packages/cld-reducer-0.2.1.tgz --access public
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

For Python, retain the existing trusted publisher for `aigorahub/cld-reducer`,
workflow `publish-python.yaml`, environment `pypi`. Dispatch only that workflow
with the new tag and `dry_run=false`.
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
Windows checks, registry verification, and remaining CRAN work.

## External setup record

The table distinguishes completed repository setup from open release conditions.
PyPI access is configured. The first npm upload uses the maintainer account.
Configure npm trusted publishing near the next authorized release.

| Action | Owner | Required evidence |
|---|---|---|
| Python history and identity | Resolved 2026-10-10 | Earlier publication was sensPy; `cld-reducer` 0.2.0 is live |
| Data reuse basis | John Ennis | Source and permission for each data set |
| Authors and maintainer | Confirmed 2026-10-09 | John Ennis is the sole package author and maintainer |
| GitHub `npm` and `pypi` environments | Configured 2026-10-09 | Only the `main` branch is allowed |
| PyPI trusted publisher | Configured and verified 2026-10-10 | `publish-python.yaml`, environment `pypi`; release workflow succeeded |
| npm trusted publisher | Registry maintainer, next release | Configure near the next authorized upload and verify it with that release |
| Repository description | Updated 2026-10-09 | Describes R, Python, and JavaScript packages |
| Tag and release | `v0.2.0` created 2026-10-10 | Immutable package commit `8a09915a6ad0dcb1fc0ca17bce4ebaa46ddc2b39`; see submission status for release notes |
| win-builder | Both passed 2026-10-10 | Zero errors, zero warnings, one NOTE on the frozen R archive |
| CRAN submission | Submitted and confirmed 2026-10-10 | Automated Windows and Debian pretests: one NOTE each; manual review pending |

References: [npm trusted publishers](https://docs.npmjs.com/trusted-publishers/),
[PyPI trusted publishers](https://docs.pypi.org/trusted-publishers/),
[CRAN submission checklist](https://cran.r-project.org/web/packages/submission_checklist.html).
