# Submission status

Status on 2026-10-10.

PR [#3](https://github.com/aigorahub/cld-reducer/pull/3) was merged as
`9dc3f6a47c4fa8390170ad70cebb8e38eedc16d6`.
PR [#4](https://github.com/aigorahub/cld-reducer/pull/4) now targets `main`.
No version tag, registry publication, or CRAN submission has been made.

## Decisions

John Ennis confirmed that the example data are public and approved their
inclusion on 2026-10-10. The three package source notices record this decision
and the source publications. They do not assign a new license to the papers.
John Ennis is the sole package author and maintainer. Published-paper citations
and existing copyright notices retain their authors and holders.

The maintainer approved merging and publication on 2026-10-10, subject to
thorough review. The plan and implementation received independent review.
The final implementation review found no remaining defects. The final CI
checks and exact-commit test record must pass before PR #4 is merged.

## Checked candidates

The R archive was built from `54ec3703ae96fc910aab8d7103c36d4798fc49e5`.
The Python files were built from `2d3472ea0cb88e830a8b0c1548a5f77b8d21eb3a`.
The npm file was built from `40756a986f0b8f69de875abd82d3e28b114583d0`.
Later source changes do not change Python or npm package content. Later changes
to this record and `cran-comments.md` do not enter the R archive.
The final publication workflows must build and check the authorized tag on `main`.

| File | SHA-256 |
|---|---|
| `R/cldreducer_0.2.0.tar.gz` | `11b68758ac001659237998568a8d0d0bf11d27548cf6441851cf07eb7dccbeb0` |
| `python/cld_reducer-0.2.0.tar.gz` | `751136ee865b036bfd2fdc2cb7d37e2163feded9b8615572c0a49d3f1296baad` |
| `python/cld_reducer-0.2.0-py3-none-any.whl` | `352d98ccbc83bdf38afe288311f589126b5f76cb5ce8e1d5c2cd9a2b24db48e8` |
| `npm/cld-reducer-0.2.0.tgz` | `4d85fd6ad5a6836c59a9c64ddfa78ca3bb131f9b4ffde48b5788299e1fcf1937` |

The R archive passes the complete `R CMD check --as-cran --timings` check,
including PDF and HTML manuals. Result: zero errors, zero warnings, one
new-submission NOTE. The longest example takes 0.333 seconds. The source archive
check rejects development caches. See `cran-comments.md`.

Both Python files pass Twine. The wheel and a wheel rebuilt from the source
archive pass API, CLI, label, and example checks in separate clean environments.
The npm archive passes clean installation, WASM execution, and TypeScript use.
Local suites pass: 3,023 Python tests, 88 JavaScript tests, 310 R checks,
1,505 shared cases, and 24 generator tests.

Both win-builder queues accepted the R archive above on 2026-10-10 at 12:57 UTC.
Both FTP transfers returned 226. Results are pending. Earlier Windows results
had zero errors and warnings, but they do not certify this new archive.

## Registry setup

The GitHub `npm` and `pypi` environments exist. Both permit deployments only
from `main`. The repository description names all three languages.
The manual publication workflows and their control tests are in place.

Use turfLP's first npm publication process: sign in as the maintainer, verify
the tarball from the successful workflow dry run, and publish that exact file.
The npm browser account is `john-aigora`, which owns `turflp`. The CLI login
is waiting for the maintainer's security key. Configure trusted publishing for
later releases. See `docs/releasing.md`.

PyPI still needs the maintainer's completed login. Public PyPI and TestPyPI
metadata return 404 for `cld-reducer`. The earlier Python project's identity
and versions remain unconfirmed. Check the account's project list before
creating a pending publisher or choosing a new-project route.
The publisher settings are repository `aigorahub/cld-reducer`, workflow
`publish-python.yaml`, environment `pypi`. No publisher has been created.

## Remaining steps

- Complete registry login and resolve the earlier Python project record.
- Finish CI, merge PR #4, and verify the merged commit.
- Tag the checked release and run both publication workflow dry runs.
- Record final Windows results for the exact R file to submit.
- Publish the checked npm and Python artifacts after registry setup.
- Submit the R archive to CRAN. Record submission and acceptance separately.
