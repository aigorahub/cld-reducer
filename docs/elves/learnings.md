# Project learnings

Durable lessons for this repository and this machine. Run status goes in the execution log.

## Active learnings

- [L1] [2026-10-07] On native Windows, every `cobbler_agents.py` command (Elves 2.39.0) exits at import with `ModuleNotFoundError: No module named 'fcntl'` (`cobbler_runtime/worktree_fingerprint.py`), and `cobbler_runtime/storage.py` needs Unix `fcntl.flock`. Native-worker launch and prewalk need a POSIX host. `acceptance_contract.py validate` and `elves_landing_check.py` import on Windows, but `acceptance_contract.py sync-session --write` fails with `PermissionError` (it opens a directory descriptor); run `sync-session` without `--write` and write its JSON output to the session file. (evidence: execution-log 2026-10-07 staging) (expect: `python cobbler_agents.py preferences show` runs on the host before any worker launch)
- [L2] [2026-10-07] This machine has `core.autocrlf=true` (Git for Windows system config). Working tree text files are CRLF; git stores LF. Compare copies by git blob id, and read, hash, and compare generated text after line ending normalization. (evidence: execution-log 2026-10-07 staging, `od -c` on `examples/simple_abc_to_ac_means.csv`)
- [L3] [2026-10-07] The Piepho (2004) wheat example has 64 assignment-minimum coverings (56 to 44 assignments, 4 cliques). Any cross language comparison of displays needs the canonical tie-break of the spec; the simple ABC example has a unique optimum. (evidence: execution-log 2026-10-07 staging, scratch count script)
- [L4] [2026-10-07] turfLP conformance takes expected values from a standard-library generator, never from a solver, and compares objective values only. cld-reducer compares full displays, so it adds a canonical tie-break. (evidence: turfLP `conformance/README.md` at c6e6b86)
- [L5] [2026-10-07] CRAN `highs` 1.14.0-2 bundles HiGHS 1.14 and `highs_control()` defaults to `threads = 1L`; turfLP keeps presolve off in R because of a HiGHS 1.14 presolve defect. npm `highs` 1.15.3 and PyPI `highspy` 1.15.1 bundle HiGHS 1.15. (evidence: CRAN PACKAGES, cran/highs R/highs.R, npm and PyPI registry reads on 2026-10-07)
- [L6] [2026-10-07] npm trusted publishing works only for a package that already exists, so the first `cld-reducer` publish is manual (turfLP PR #9). (evidence: aigorahub/turfLP PR #9 body)

## Retired learnings

None.
