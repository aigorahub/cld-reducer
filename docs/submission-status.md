# Submission status

Status on 2026-10-09 in America/New_York (2026-10-10 UTC).

PR [#4](https://github.com/aigorahub/cld-reducer/pull/4) contains the preparation
work and follows PR [#3](https://github.com/aigorahub/cld-reducer/pull/3).
Neither PR has been merged. No version tag or registry upload has been made.

## Checked candidate

These archives precede the sole-author metadata change and are superseded.
Do not publish them. Fresh archives must pass the checks below.

These files were built from `ad2c03f65541c9f0b10af21efcd0048c95fc9dc0`.
Later changes to this record and `cran-comments.md` do not change the package
contents. These are review candidates. Final publication workflows must build
and check the authorized tag on `main`.

| File | SHA-256 |
|---|---|
| `cldreducer_0.2.0.tar.gz` | `6a6fa55164199b90de39272935c23f2de1cb0028480cbbc6f96e2bc8d19332ff` |
| `cld_reducer-0.2.0.tar.gz` | `d5bbe0569cf6811a918098abbef53dfbe388237f52a91eac11ce2b4b98d1c4e2` |
| `cld_reducer-0.2.0-py3-none-any.whl` | `78371df5daaba7807df602305bade78a833b26f80ceda0ea31e0e4d83bea2a60` |
| `cld-reducer-0.2.0.tgz` | `d61759316082ebebdc696f61fdc85dacf51d9809aea3989b877e07f67b5ccabc` |

The R archive passes `R CMD check --as-cran --timings` with its PDF manual and
HTML validation. Result: zero errors, zero warnings, one new-submission NOTE.
The longest example takes 0.350 seconds. See `cran-comments.md`.

Both Python files pass Twine. The wheel and a wheel rebuilt from the source
archive pass API, CLI, label, and example checks in separate clean environments
outside the checkout. The retained npm archive passes clean installation,
WASM execution, and TypeScript consumer checks.

The R archive above was sent to win-builder's `R-release` queue on 2026-10-10
at 02:27 UTC. The FTP transfer returned 226. The `R-devel` transfer returned
550 and must be retried. Results are pending. An earlier archive was sent to
both queues at 02:25 UTC; those requests do not certify this candidate.
This is a test request. It is not a CRAN submission.

## Repository and registry setup

The GitHub `npm` and `pypi` environments exist. Each permits deployments only
from the `main` branch. The repository description names all three languages.
The manual publication workflows and their local control tests are in place.

The npm website session identifies the maintainer as `john-aigora`, who owns
`turflp`. The npm CLI has no valid login. The first `cld-reducer` publication
needs an authorized maintainer login and second factor. Configure npm trusted
publishing after that first publication. See `docs/releasing.md`.

PyPI account access is pending. Public PyPI and TestPyPI metadata return 404 for
`cld-reducer`. A targeted search of the maintainer's mail found no upload receipt
for `cld-reducer`, `cld_reducer`, or `cldreducer`. This does not establish that an
earlier upload never existed. Confirm the project in the maintainer's PyPI
account before creating a pending publisher or selecting a release version.

The required Python publisher settings are repository `aigorahub/cld-reducer`,
workflow `publish-python.yaml`, environment `pypi`. No registry publisher has
been created by this work.

## Decisions and checks still required

- Confirm the earlier Python project's identity and used versions.
- Confirm the reuse basis for the example data in `inst/COPYRIGHTS`. The simple
  example and its means come from the 2012 paper. The wheat decisions come from
  Piepho (2004), reproduced in the 2012 paper. No explicit reuse license was
  found. R and the Python source archive include both. The npm README includes
  the simple example. The Python wheel omits the CSV files but includes
  simple-example output in its metadata.
- The maintainer directed sole package authorship by John Ennis on 2026-10-09.
  Package metadata and the software citation now use that name. Published work
  citations and existing copyright notices retain their authors and holders.
- Record the two win-builder results for the file above.
- Obtain explicit approval to merge the PRs. Recheck the resulting commit.
- Configure the confirmed PyPI project's publisher and authorize the version
  tag. Run the final workflow dry runs and preserve their checked artifacts.
- Obtain publication approval. Publish those exact artifacts. Record CRAN
  submission and acceptance separately.

Code checks do not verify registry access. Dry runs do not prove publication
rights. A changed package needs new artifact checks and Windows check results.
