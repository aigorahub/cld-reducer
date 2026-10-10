# Submission plan review

## First review

Fugu reviewed `plan.md` at commit `dfae58d` on 2026-10-09 through the Elves
read-only runner. The route was `fugu/high`, with a 900 second limit. The run
completed successfully. The review covered the plan and selected source files.
It did not run package tests or upload packages.

The review returned three required corrections and no optional suggestions.

| Priority | Finding | Resolution |
|---|---|---|
| P1 | A historical PyPI upload can be confirmed even when the current project is unavailable. An existing-project publisher cannot then be assumed to work. | Added a separate history case. Continue code work, but stop publication until project access, restoration, or an approved new-project route is established. Retain historical version information. |
| P2 | Requiring example scripts in both Python archives would reject the intended wheel layout. Tests could also load checkout files by mistake. | Require examples in the source distribution only. Use temporary test inputs for wheel checks. Run source-distribution examples from its unpacked directory. |
| P2 | The first manual npm upload was not explicitly tied to the saved checked artifact. | Require downloading the dry-run tarball, verifying its SHA-256 hash, and publishing that exact path without repacking. |

The host checked the findings against the plan and Python build configuration.
The host also required the dispatch workflow and publish environment to use
`main`. This is separate from checking that the package tag points into `main`.

## Recheck

Fugu rechecked the corrections at commit `78f16ef` on 2026-10-09. The route was
`fugu/high`, with a 600 second limit. The run completed successfully and returned:

> No actionable findings

It noted that the publication controls and artifact checks still need to be
implemented and verified. This was a focused plan review. The implementation
has not started.
