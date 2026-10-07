# Project learnings

Durable lessons for this repository and this machine. Run status goes in the execution log.

## Active learnings

- [L1] [2026-10-07] On native Windows, every `cobbler_agents.py` command (Elves 2.39.0) exits at import with `ModuleNotFoundError: No module named 'fcntl'` (`cobbler_runtime/worktree_fingerprint.py`), and `cobbler_runtime/storage.py` needs Unix `fcntl.flock`. Native-worker launch and prewalk need a POSIX host. `acceptance_contract.py validate` and `elves_landing_check.py` import on Windows, but `acceptance_contract.py sync-session --write` fails with `PermissionError` (it opens a directory descriptor); run `sync-session` without `--write` and write its JSON output to the session file. (evidence: execution-log 2026-10-07 staging) (expect: `python cobbler_agents.py preferences show` runs on the host before any worker launch)
- [L2] [2026-10-07] This machine has `core.autocrlf=true` (Git for Windows system config). Working tree text files are CRLF; git stores LF. Compare copies by git blob id, and read, hash, and compare generated text after line ending normalization. (evidence: execution-log 2026-10-07 staging, `od -c` on `examples/simple_abc_to_ac_means.csv`)
- [L3] [2026-10-07] The Piepho (2004) wheat example has 64 assignment-minimum coverings (56 to 44 assignments, 4 cliques). Any cross language comparison of displays needs the canonical tie-break of the spec; the simple ABC example has a unique optimum. (evidence: execution-log 2026-10-07 staging, scratch count script)
- [L4] [2026-10-07] turfLP conformance takes expected values from a standard-library generator, never from a solver, and compares objective values only. cld-reducer compares full displays, so it adds a canonical tie-break. (evidence: turfLP `conformance/README.md` at c6e6b86)
- [L5] [2026-10-07] CRAN `highs` 1.14.0-2 bundles HiGHS 1.14 and `highs_control()` defaults to `threads = 1L`; turfLP keeps presolve off in R because of a HiGHS 1.14 presolve defect. npm `highs` 1.15.3 and PyPI `highspy` 1.15.1 bundle HiGHS 1.15. (evidence: CRAN PACKAGES, cran/highs R/highs.R, npm and PyPI registry reads on 2026-10-07)
- [L6] [2026-10-07] npm trusted publishing works only for a package that already exists, so the first `cld-reducer` publish is manual (turfLP PR #9). (evidence: aigorahub/turfLP PR #9 body)

- [L7] [2026-10-07] Elves `references/agent-teams.md` says native Windows Python is not a qualified Elves execution host (Windows only through WSL2). The pure validators in `cobbler_runtime/prewalk.py` still import on Windows and can check prewalk TODO and checkpoint artifacts by hand. (evidence: execution-log 2026-10-07 plan review round 1)
- [L8] [2026-10-07] Claude Code transcripts (`~/.claude/projects/<slug>/<session>.jsonl`) record `model`, `sessionId`, and `cwd` on each message, so a resume with a new `--model` can be checked from the transcript; effort is not recorded. (evidence: execution-log 2026-10-07 plan review round 1)
- [L9] [2026-10-07] `herdr --skill` prints the herdr skill when it is not installed as a Claude skill. (evidence: execution-log 2026-10-07 plan review round 1)

- [L10] [2026-10-07] The Elves git contract helpers (`cobbler_runtime/git_contract.py`) fail on this Windows host with `FileNotFoundError` when they call git; route (c) needs its own audit script. (evidence: execution-log 2026-10-07 plan review round 2)
- [L11] [2026-10-07] User settings on this host run a Stop hook with plain `bash` and a Herdr SessionStart hook (`herdr-agent-state.ps1`, which calls `herdr pane report-agent-session`) and enable three plugins. `claude --safe-mode` turns all of them off; a supervisor must then report the Herdr session identity itself. Transcripts record a `stop_hook_summary` entry when a Stop hook runs. (evidence: execution-log 2026-10-07 plan review round 2)

- [L12] [2026-10-07] WSL on this machine appends Windows folders to `PATH` (Windows `npm`, `gh.exe`, `git.exe`); a Linux run must set a Linux-only `PATH` (`$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin`). (evidence: execution-log 2026-10-07 route (a) setup)
- [L13] [2026-10-07] In WSL, Claude Code lives in `~/.local/bin` (not on the default login `PATH`) and was already logged in; check `claude auth status` before asking for a login. (evidence: execution-log 2026-10-07 route (a) setup)
- [L14] [2026-10-07] PowerShell mangles `|` and `$` inside `wsl.exe -- bash -c '...'`; write a script to a Windows folder and run it as `wsl.exe -d Ubuntu -- bash /mnt/c/.../script.sh`. Git Bash also rewrites `/mnt/...` arguments. (evidence: execution-log 2026-10-07 route (a) setup)

- [L15] [2026-10-07] Elves 2.39.0 accepts only `low`, `medium`, `high` as Claude worker efforts (no Claude model catalog), so a Claude guide or execution route at `xhigh` or `max` fails qualification before any model call, although Claude Code accepts those levels. (evidence: execution-log 2026-10-07 launch attempt)

- [L16] [2026-10-07] `claude auth status` can report `loggedIn: true` while the OAuth session is expired; one real `claude --print` call is the reliable login check before a qualification canary. The canary does not keep Claude's error text. (evidence: execution-log 2026-10-07 relaunch)

- [L17] [2026-10-07] Claude Code before 2.1.280 rejects claude-opus-5-5 with an API 400; a confirmation call must use the exact guide model, not only the execution model. (evidence: execution-log 2026-10-07 login fixed)

## Retired learnings

None.
