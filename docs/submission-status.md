# Submission status

Status on 2026-10-10.

PR [#4](https://github.com/aigorahub/cld-reducer/pull/4) contains the preparation
work and follows PR [#3](https://github.com/aigorahub/cld-reducer/pull/3).
Neither PR has been merged. No version tag or registry upload has been made.

## Checked candidate

The R and npm files were built from `eaee0e55243577ed3f36cb5c55f3e5ebcb5d22c5`.
The Python files were built from `deb5db2604f85842af7385a9dca82cdca49c77f5` after
the README quickstart was made self-contained. Later changes to this record
and `cran-comments.md` do not change package contents. These are review candidates. Final publication workflows must build
and check the authorized tag on `main`.

| File | SHA-256 |
|---|---|
| `cldreducer_0.2.0.tar.gz` | `3f50237fc8400cd1504590e93d4082b738cbbedb8a5a51d1663b4bcc330a4c73` |
| `cld_reducer-0.2.0.tar.gz` | `94a185b9102c49ca12a080305bf39b760e4c02ffcb4214d37b52e9938a30fc6f` |
| `cld_reducer-0.2.0-py3-none-any.whl` | `d4abadfd3f81c62b2e7cda41c9bceca7167a49916a805dbe3d8d76c83f6ac36e` |
| `cld-reducer-0.2.0.tgz` | `d61759316082ebebdc696f61fdc85dacf51d9809aea3989b877e07f67b5ccabc` |

The R archive passes `R CMD check --as-cran --timings` with its PDF manual and
HTML validation. Result: zero errors, zero warnings, one new-submission NOTE.
The longest example takes 0.357 seconds. See `cran-comments.md`.

Both Python files pass Twine. The wheel and a wheel rebuilt from the source
archive pass API, CLI, label, and example checks in separate clean environments
outside the checkout. The retained npm archive passes clean installation,
WASM execution, and TypeScript consumer checks.

The archive above contains the sole-author metadata change. Both win-builder
queues accepted this exact file on 2026-10-10 at 12:40 UTC. Both FTP transfers
returned 226. Results remain pending. These requests replace the earlier
attempts whose files were blocked in the queues.

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
