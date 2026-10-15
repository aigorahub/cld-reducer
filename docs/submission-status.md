# Submission status

Status verified on 2026-10-15. Version 0.3.3 is published on npm and PyPI.
The release tag `v0.3.3` points to merged commit
`01d89dee3474fe1e11ab03dc5b9ca6d47f1dac24`. The development version is 0.3.4.

| Registry | Package | Status |
|---|---|---|
| PyPI | [`cld-reducer` 0.3.3](https://pypi.org/project/cld-reducer/0.3.3/) | Published and verified |
| npm | [`cld-reducer` 0.3.3](https://www.npmjs.com/package/cld-reducer/v/0.3.3) | Published and verified |
| CRAN | `cldreducer` 0.2.0 | Submitted and confirmed; manual review pending |

CRAN does not yet list the package. The R 0.3.3 archive is a checked candidate,
not a new submission. The [CRAN policy](https://cran.r-project.org/web/packages/policies.html)
prohibits another submission while an earlier version is pending without a
response from a CRAN maintainer. No such response was found in the maintainer's
email on 2026-10-15. The Windows R-release result passed; the R-devel result
was still pending at that check.

## Version 0.3.3 files and checks

The [GitHub release](https://github.com/aigorahub/cld-reducer/releases/tag/v0.3.3)
holds the exact files and separate registry manifests. Public npm and PyPI files
match their workflow SHA-256 hashes. Fresh public installs passed the CLD-C,
CLD-sigma, and pair API checks. The Python check verified the installed version
as 0.3.3. The npm check loaded the WASM solver. A separate registry check
confirmed that the npm `latest` tag points to 0.3.3.

| File | SHA-256 |
|---|---|
| `cld-reducer-0.3.3.tgz` | `48225200aee9e7ad8b1a48c29f66c9c93a3fdb905ad0a77edf39d53bf5aa9f53` |
| `cld_reducer-0.3.3-py3-none-any.whl` | `807c7680ea63cdb9365d15b105470b1bc75b976de9f42955e00d5387d91d2485` |
| `cld_reducer-0.3.3.tar.gz` | `edf004b08c6638d79f51f4963cbb637b6f3dc8c0eae5500da26b96a9d9812f3e` |
| `cldreducer_0.3.3.tar.gz` (candidate) | `bbeb2b822e805b5a2dced15166364c02d4a053e6d2f16c65f184df58189cafd4` |

The [npm build](https://github.com/aigorahub/cld-reducer/actions/runs/38791399051)
passed its tests, conformance cases, and installed-package checks. The maintainer
published its exact tarball with lifecycle scripts disabled.
The [Python publication](https://github.com/aigorahub/cld-reducer/actions/runs/38794901991)
passed 14,110 tests, release checks, metadata checks, and clean installs from
both the wheel and the source archive. It used the existing trusted publisher.

The R 0.3.3 archive passed `R CMD check --as-cran --timings` on macOS with
R 4.6.1: zero errors, zero warnings, and one New submission NOTE. All 631 tests
passed. PDF and HTML manuals passed. The longest example took 0.315 seconds.
The archive passed the package-content check. The same file was uploaded to
win-builder R-release and R-devel. The [R-release log](https://win-builder.r-project.org/bmqR3hnotkU3/00check.log)
reports zero errors, zero warnings, and one NOTE on R 4.6.1 for Windows.
The NOTE covers a new submission and the spelling flags CLD, CLDs, Ennis,
Fayle, and Piepho. PDF and HTML manuals passed. The R-devel result is pending.

## Earlier 0.2.0 release

The following sections retain the original 0.2.0 evidence. Version `v0.2.0`
is tagged at `8a09915a6ad0dcb1fc0ca17bce4ebaa46ddc2b39`.
PRs #3, #4, and #5 are merged. The workflow build fix is merge commit
`be6ad8765077c9bf721758dd57f65f39c9139ec1`; it did not change the tagged package.
The [0.2.0 release](https://github.com/aigorahub/cld-reducer/releases/tag/v0.2.0)
retains its files. The frozen CRAN submission is unchanged.

## Decisions and review

John Ennis confirmed that the example data are public and approved their
inclusion on 2026-10-10. The package source notices record the source
publications and this decision. They do not assign a new license to the papers.
John Ennis is the sole package author and maintainer. Published-paper citations
and existing copyright notices retain their authors and holders.

The maintainer approved merging and publication on 2026-10-10 after thorough
review. The plan and implementation received independent review. Local gates
and CI passed before the package changes were merged. The workflow build fix
received a separate review and passed its local gates and CI.

The earlier Python publication was sensPy, a separate project. The maintainer
approved a new-project trusted publisher for `cld-reducer`. Version 0.2.0 is
its first verified PyPI release.

## Version 0.2.0 files and frozen R candidate

Python and npm workflows built package commit
`8a09915a6ad0dcb1fc0ca17bce4ebaa46ddc2b39` from the immutable tag.
Their manifests record that commit and the uploaded file hashes.
The public registry files match those hashes.

The R archive was built from `54ec3703ae96fc910aab8d7103c36d4798fc49e5`.
Later changes do not change the contents of that archive. The exact file below
was checked and submitted. It remains frozen while CRAN reviews it.

| File | SHA-256 |
|---|---|
| `cldreducer_0.2.0.tar.gz` | `11b68758ac001659237998568a8d0d0bf11d27548cf6441851cf07eb7dccbeb0` |
| `cld_reducer-0.2.0.tar.gz` | `625a957c19532eabbb82c438728cfe5c66ecb3b08e72758145b90de600e8b7f3` |
| `cld_reducer-0.2.0-py3-none-any.whl` | `48a5c3ea00d281227e7cabbdcaced47b0b1057440b83932885595aa702cd297d` |
| `cld-reducer-0.2.0.tgz` | `4e6b190c417a926a0e7cf8117c8058544688f26958f0c1f9bc58cbd284ccff0f` |

## Version 0.2.0 verification

The R archive passed `R CMD check --as-cran --timings`, including PDF and HTML
manuals: zero errors, zero warnings, one new-submission NOTE. Both win-builder
checks passed on this frozen file:
[R-release](https://win-builder.r-project.org/9jgT66qYVvWj/00check.log) and
[R-devel](https://win-builder.r-project.org/A2g07e6zSost/00check.log).

Python publication [run 38065890470](https://github.com/aigorahub/cld-reducer/actions/runs/38065890470)
succeeded. Its wheel and source archive passed the workflow checks. A fresh
installation from public PyPI passed the API and canonical label check.
The public metadata names John Ennis as author.

The npm candidate [run 38054826758](https://github.com/aigorahub/cld-reducer/actions/runs/38054826758)
succeeded. The maintainer published that exact tarball after security key
verification. A fresh installation from public npm passed WASM solver execution,
the canonical label check, and TypeScript compilation.

The reviewed local suites passed: 3,023 Python tests, 88 JavaScript tests,
310 R checks, 1,505 shared cases, and 24 generator tests.

## Version 0.2.0 CRAN review

The maintainer submitted and confirmed `cldreducer` 0.2.0 on 2026-10-10 at
13:27:40 UTC. CRAN's automated pretest email at 13:36:14 UTC reports one NOTE
on both Windows and Debian. The logs contain no errors or warnings:
[Windows pretest](https://win-builder.r-project.org/incoming_pretest/cldreducer_0.2.0_20261010_152740/Windows/00check.log)
and [Debian pretest](https://win-builder.r-project.org/incoming_pretest/cldreducer_0.2.0_20261010_152740/Debian/00check.log).

The NOTE covers a new submission and possible spelling flags for CLD, CLDs,
Ennis, Fayle, and Piepho. The email states that manual inspection is pending
and that a team member typically responds within 10 working days.
No acceptance is recorded in this repository. The public CRAN index check on
2026-10-13 found no package entry. The last recorded correspondence remains
the automated pretest described above.

## Remaining steps

- Collect and record the 0.3.3 Windows R-devel result.
- Respond to CRAN reviewer requests before submitting the checked 0.3.3 candidate.
  Record acceptance separately.
- After CRAN acceptance, verify public installation and update this record.
- Configure npm trusted publishing near the next authorized release, as described
  in [release instructions](releasing.md). The PyPI trusted publisher is active.
