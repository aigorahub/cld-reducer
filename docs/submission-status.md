# Submission status

Status on 2026-10-09 in America/New_York (2026-10-10 UTC).

PR [#4](https://github.com/aigorahub/cld-reducer/pull/4) contains the preparation
work and follows PR [#3](https://github.com/aigorahub/cld-reducer/pull/3).
Neither PR has been merged. No version tag or registry upload has been made.

## Checked candidate

These files were built from `df5fa97bb78a5834eea66df6ce9bbab5f71dca1b`.
Later changes to this record and `cran-comments.md` do not change the package
contents. These are review candidates. Final publication workflows must build
and check the authorized tag on `main`.

| File | SHA-256 |
|---|---|
| `cldreducer_0.2.0.tar.gz` | `31c79adf99a063320dc9343bfd481ae8d3a380d34fa3549694573efc981acb00` |
| `cld_reducer-0.2.0.tar.gz` | `451c504672975a3ed8a848b79275b1324f3e9acf509364e65db1a9469c35a19b` |
| `cld_reducer-0.2.0-py3-none-any.whl` | `8fb63311a62c72e1c388f7753fdb49501c209c63daf865990824b98afeed09b9` |
| `cld-reducer-0.2.0.tgz` | `294176e28768843c8cf518c2e918b433c0856e0f45c3fe94e94e99ff30827ccd` |

The R archive passes `R CMD check --as-cran --timings` with its PDF manual and
HTML validation. Result: zero errors, zero warnings, one new-submission NOTE.
The longest example takes 0.339 seconds. See `cran-comments.md`.

Both Python files pass Twine. The wheel and a wheel rebuilt from the source
archive pass API, CLI, label, and example checks in separate clean environments
outside the checkout. The retained npm archive passes clean installation,
WASM execution, and TypeScript consumer checks.

The R archive above was sent to win-builder's `R-release` and `R-devel` queues
on 2026-10-10 at 02:25 UTC. Both FTP transfers returned 226. Results are pending.
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
- Confirm the authors and maintainer carried forward from PR #3.
- Record the two win-builder results for the file above.
- Obtain explicit approval to merge the PRs. Recheck the resulting commit.
- Configure the confirmed PyPI project's publisher and authorize the version
  tag. Run the final workflow dry runs and preserve their checked artifacts.
- Obtain publication approval. Publish those exact artifacts. Record CRAN
  submission and acceptance separately.

Code checks do not verify registry access. Dry runs do not prove publication
rights. A changed package needs new artifact checks and Windows check results.
