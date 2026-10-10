# Submission status

Status on 2026-10-10.

Version `v0.2.0` is tagged at package commit
`8a09915a6ad0dcb1fc0ca17bce4ebaa46ddc2b39`.
PRs [#3](https://github.com/aigorahub/cld-reducer/pull/3),
[#4](https://github.com/aigorahub/cld-reducer/pull/4), and
[#5](https://github.com/aigorahub/cld-reducer/pull/5) are merged.
The workflow build fix is merge commit
`be6ad8765077c9bf721758dd57f65f39c9139ec1`. It does not change the tagged package.

| Registry | Package | Status |
|---|---|---|
| PyPI | [`cld-reducer` 0.2.0](https://pypi.org/project/cld-reducer/0.2.0/) | Published and verified |
| npm | [`cld-reducer` 0.2.0](https://www.npmjs.com/package/cld-reducer) | Published and verified |
| CRAN | `cldreducer` 0.2.0 | Submitted and confirmed; manual review pending |

The [GitHub release](https://github.com/aigorahub/cld-reducer/releases/tag/v0.2.0)
records the package files and checksums. CRAN submission does not mean acceptance.
The R package is not yet available through `install.packages("cldreducer")`.

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

## Published files and frozen R candidate

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

## Verification

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

## CRAN review

The maintainer submitted and confirmed `cldreducer` 0.2.0 on 2026-10-10 at
13:27:40 UTC. CRAN's automated pretest email at 13:36:14 UTC reports one NOTE
on both Windows and Debian. The logs contain no errors or warnings:
[Windows pretest](https://win-builder.r-project.org/incoming_pretest/cldreducer_0.2.0_20261010_152740/Windows/00check.log)
and [Debian pretest](https://win-builder.r-project.org/incoming_pretest/cldreducer_0.2.0_20261010_152740/Debian/00check.log).

The NOTE covers a new submission and possible spelling flags for CLD, CLDs,
Ennis, Fayle, and Piepho. The email states that manual inspection is pending
and that a team member typically responds within 10 working days.
No acceptance has been received.

## Remaining steps

- Respond to CRAN reviewer requests, if any. Record acceptance separately.
- After CRAN acceptance, verify public installation and update this record.
- Configure npm trusted publishing near the next authorized release, as described
  in [release instructions](releasing.md). The PyPI trusted publisher is active.
