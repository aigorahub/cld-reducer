# Read this file first after any compaction or restart

Survival guide for the Elves run `cld-reducer-r-js-packages-2026-10-07`. If this file and your
memory disagree, trust this file. Read order after a restart: this file, then
`.elves-session.json`, then `docs/elves/learnings.md`, then
`docs/plans/r-js-packages/plan.md`, then `docs/elves/execution-log.md`.

Helper commands use the installed Elves skill root `C:\Users\Megan\.claude\skills\elves`
(Elves 2.39.0) with this worktree as the working directory.

---

## Mission

Restructure `aigorahub/cld-reducer` like `aigorahub/turfLP`: R package `cldreducer` at the root,
npm package `cld-reducer` in `js/`, the Python package in `python/`, one spec, one conformance
suite, HiGHS in all three languages, and the same reduced letter display in all three. The run
ends at a green, reviewed, draft PR. No merge, tag, release, CRAN submission, or publish.

---

## Run Control

- **Run mode:** finite
- **Stop policy:** blocker-only
- **User intent:** John Ennis (2026-10-07 11:15 ET): "take the repo cld-reducer and structure it like turfLP so that it covers R and JavaScript ... The goal is to get it submitted to CRAN and npm for R and javascript ... plan very carefully with robust review then do it as an elves run." Lantern brief: Phase 1 is plan only; wait for `EXECUTE APPROVED`; stop point is a landable, green, reviewed draft PR.
- **Checkpoint due by:** none
- **Checkpoint semantics:** none
- **May continue after checkpoint:** yes
- **Actual stop conditions:** the draft PR meets the plan section "Definition of green" with both final reviews clean at the exact head, or a true blocker.
- **Workspace ownership:** dedicated WSL worktree `/home/mason/src/cld-reducer-r-js-packages` on branch `feat/r-js-packages`, created in the WSL clone `/home/mason/src/cld-reducer` with the Elves `preflight_worktree.py --create-worktree feat/r-js-packages --base origin/main` (dry run first); the staging commits came across with a git bundle (tip `acb144e`). No other agent shares it. The Windows worktree `C:\Claude\cld-reducer-r-js-packages` is kept, unused, until Mason agrees to remove it.
- **Branch tip at start (collision tripwire):** `eb95fe9ad5e983a1f2e6e02668c3419647b9571e` (origin/main at staging). Upstream tracking was removed so a bare `git push` cannot target `main`.
- **Merge policy:** user-merges (default). The driver never merges. No merge-on-green opt-in and no landing command in this run.
- **Final-response policy:** disallowed until the Stop Gate allows it.
- **Coordination mode:** Cobbler-first (default).
- **Execution route:** route (a), chosen by Mason (plan page, 2026-10-07T18:04:37Z). The Elves supervisor, the guide route, and the execution route run in WSL Ubuntu 26.04; the driver stays in this Windows session and runs every WSL step through `wsl.exe`. R Option A: local R 4.6 on the WSL host plus CI.
- **Batch completion rule:** the worker closes each internal batch with its `Close` commit (acceptance ids and evidence in the body) and `.elves/runtime/worker-report-B<N>.md`; the parked driver writes session rows once at a safety, blocked, or terminal wake. Every completed batch must end with a commit and push.
- **Progress visibility rule:** commit subjects `[feat/r-js-packages · Batch N/6 · Contract|Implement|Validate|Review|Close] <concrete outcome>`. No vague subjects. `Close` needs acceptance evidence and a Confidence trailer in the Elves format. No AI attribution lines.
- **Coordinator-to-implementer handoff:** the plan has a handoff block per batch; the consolidated packet is `.elves/runtime/worker-packet.md`. Each batch completion reports confidence (high, medium, or low) and unsure areas; an empty list is a valid answer.
- **Worker packet:** `.elves/runtime/worker-packet.md` (also `worker_packet_path` in `.elves-session.json`; `.elves/` is ignored through `.git/info/exclude`).
- **Handoff validation:** v2.8 advisory path (no explicit v1 capsule).
- **Re-read rule:** after every host-owned commit and push, re-read this survival guide before anything else. During the parked full-run, re-read once on a safety, blocked, or terminal wake.
- **Checkpoint rule:** no checkpoints in this run.
- **E2E mode:** chat-to-work (landable PR only).
- **Work driver:** host-native (a separate native Claude Code worker session with exact-session prewalk, not in-session execution).
- **Implementation lane:** fast
- **Delegation scope:** full_run (B1 to B6 in one packet)
- **Git mode:** branch_progress (the worker commits and pushes only `feat/r-js-packages`)
- **Driver monitor mode:** parked_monitor (`native-worker follow` and `status` through `wsl.exe`, with a fallback watchdog)
- **Driver update policy:** sanitized follow stream; material wakes only.
- **Driver poll policy:** host wait primitive with a fallback watchdog.
- **Driver review policy:** final independent review (Astra in tab `cld-review` and a fresh Opus 5.5 session), then delta re-review until neither has an open finding.
- **Follow mode:** default sanitized stream.
- **Risk posture:** standard (B3 and B5 are high).
- **Trust mode:** trusted
- **Landing outcome:** landable_pr (draft PR, not merged)
- **Driver merge authorized:** no
- **Worker merge authority:** false
- **Stable plan IDs:** B1 to B6, `B#-A#`, `M-A1` to `M-A6`.
- **Staging acceptance validation:** see Launch Readiness; command below.
- **Staging acceptance command:** `python3 ~/.claude/skills/elves/scripts/acceptance_contract.py validate --repo-root . --session .elves-session.json` in the WSL worktree
- **High-risk checkpoints:** B3 Close (Python behavior change), B5 Close (R CRAN checks).
- **GitHub push auth route:** `gh` in WSL, logged in by Mason (pending); never Windows credentials or Windows binaries.
- **Re-drive budget:** 2 substantive re-drives. Transient provider errors retry the same worker with 5m, 10m, 20m backoff and do not use this budget.
- **Continuation harness:** none
- **Routes:** guide phase claude-opus-5-5 at high (changed from xhigh by Mason on 2026-10-07, because Elves 2.39.0 allows only low, medium, high for Claude), execution phase claude-sonnet-5-5 at high, `--prewalk required` through `cobbler_agents.py native-worker launch` in WSL. Qualification failure stops the run; no cold substitute and no silent model change.
- **Continuation rule:** after `EXECUTE APPROVED`, if work remains and the actual stop conditions are not met, continue without waiting for acknowledgment.

---

## Cobbler Session State

- **Cobbler default:** on
- **Activated by:** Elves invocation
- **Scope:** current Elves run
- **Behavior:** Cobbler lenses for planning, risk, review, and synthesis; direct execution for mechanical steps.
- **Persistence:** this file and `.elves-session.json` (`cobbler.default_for_session: true`)
- **Exit phrases:** "Cobbler Mode: off", "leave Cobbler Mode", "stop using Cobbler by default"

---

## Session Budget

- **Started:** 2026-10-07 11:40 ET
- **User returns:** Lantern routes the plan review and later sends `EXECUTE APPROVED`.
- **Checkpoint expectation:** none
- **Time budget:** not set
- **Average batch time so far:** none yet
- **Batches remaining:** 6 of 6
- **Observed usage so far:** unobserved
- **Usage ceiling (advisory):** none

---

## Stop Gate

- **Planned batches remaining:** 6
- **Stop allowed right now:** no
- **Why:** the WSL login works and Claude Code is 2.1.293; the relaunch and all six batches remain.
- **Next required action:** relaunch the worker with required prewalk and park on the follow stream.

After `EXECUTE APPROVED`, set `Stop allowed right now: no` until the stop point.

---

## Effort Standard

- Work as hard as you can for the full run on plan acceptance and blockers. Do not be lazy.
- Keep the same drive on B6 as on B1.
- Do not settle for the minimum acceptable change on the planned path.
- When one task is complete, take the next highest-value action from the plan, not a polish detour.
- Hard work does not mean mid-run nit perfection or repeated full suites between ordinary batches. Impact path mid-run; full suite and deferred hygiene at terminal.

## Deferred hygiene

- **Open items:** none
- **Last drained:** never

## Out-of-scope findings

- **Filed this run:** none
- **Could not file:** LB1 (Elves native-worker supervisor and storage need a POSIX host). Not filed in `aigorahub/elves` during Phase 1; reported to Lantern in the plan section "Execution routes".

---

## Forbidden Stop Reasons

- A checkpoint time was reached.
- A commit or push succeeded.
- CI is green on one workflow while others are pending.
- A draft PR exists.
- The user or Lantern is silent.
- A batch is complete but later batches remain.
- The remaining work feels large for one turn.
- A batch boundary feels like a natural place to pause.

If one of these happens after `EXECUTE APPROVED`, update the docs, commit, push, re-read this file, and continue.

---

## Memory Surfaces

- **Plan:** `docs/plans/r-js-packages/plan.md` (scope, decisions, batches, acceptance)
- **Survival guide:** this file (run control and next action)
- **Learnings:** `docs/elves/learnings.md`
- **Execution log:** `docs/elves/execution-log.md`
- **Session:** `.elves-session.json`

---

## Non-Negotiables

- Never edit, commit, or push in `C:\Claude\turfLP` or `aigorahub/turfLP`.
- Never push to `main`. Only `feat/r-js-packages` is pushed, and only after `EXECUTE APPROVED`.
- You never merge by default. You never approve a merge. No merge, tag, release, CRAN or win-builder submission, npm or PyPI publish in this run.
- Never run destructive git commands: `git reset --hard`, `git checkout .`, `git clean -fd`, `git push --force`, `git rebase` on shared branches.
- One run owns one branch and one checkout. Any unexpected tip move is a collision; stop.
- Never weaken, skip, or delete a test or fixture merely to get green.
- Keep the Python import name, public API, exceptions, and CLI flags.
- No AI attribution in commits, PR text, or files.

---

## Launch Readiness

- [x] Plan cleaned and saved to disk
- [x] Survival guide updated from the current plan
- [x] Learnings file initialized
- [x] Execution log initialized with batch breakdown and preflight notes
- [x] Branch created (`feat/r-js-packages`)
- [x] Dedicated worktree confirmed; no other agent shares this branch
- [ ] PR opened or existing PR recorded (pending: Phase 1 forbids push and PR)
- [ ] Preflight run and critical failures cleared (blocked: LB1; needs the route decision H13)
- [ ] Execution route chosen by Mason (H13); for route (c), the three acceptances of H13 recorded (unqualified prewalk, residual authority risk, launch configuration)
- [ ] Route (c) only: rehearsal R0 passed (lifecycle, guide interruption, working directory, audit drills); then draft PR opened, authority baseline taken, and the live GitHub gate passed (plan route (c) step 1)
- [x] Run mode, return time, and non-negotiables recorded
- [x] Stop Gate initialized with `Stop allowed right now: no` unless a real stop condition already applies (Phase 1 gate applies now)
- [ ] Plan review clean (Astra, routed by Lantern)
- [ ] `EXECUTE APPROVED` received from Lantern
- [ ] Route (a): prewalk qualification passed for claude-sonnet-5-5 at high; route (c): transition checks passed (plan route (c) steps 7 and 10)

---

## Current Phase

**Status:** Launching (route a, WSL)

**Active batch:** none

**What was just finished:** Mason's Claude login in WSL, Claude Code update to 2.1.293, and a passing confirmation call.

**Single next action:** relaunch the worker.

---

## Active Compute

No active paid or long-running compute.

---

## Next Exact Batch

**Batch:** B1: Layout move and specification

**Scope:**
- Move the Python package to `python/` and the example CSV files to `conformance/data/` with `git mv`.
- Split `LICENSE` into the R template and `LICENSE.md`; rename `ci.yml` to `python.yaml`.
- Write `docs/algorithm.md`.

**Acceptance criteria:** B1-A1 to B1-A5 in the plan.

**Risk:** low; the spec must be complete because R and JavaScript are written from it.

**Rollback authority:** host-created `refs/elves/rollback/cld-reducer-r-js-packages-2026-10-07/<session>/b0` before worker handoff, plus worker commit SHAs.

---

## Post-Checkpoint Control Loop

Every completed batch must end with a commit and push (by the worker on `branch_progress`). After every host-owned commit and push, re-read this survival guide before doing anything else. On a parked worker wake, answer:

1. What unfinished batch or task starts now?
2. What compute is active, and is any of it idle?
3. Did Lantern or Mason change scope, stop behavior, or priorities?
4. Does the Stop Gate still say `Stop allowed right now: no`, or does `.elves-session.json` still say `continuation_guard.stop_allowed: false`? If yes, continue.
5. Is there a hard stop, an explicit stop, or a true blocker? If not, continue.

---

## After Any Compaction

1. Read the Run Control section and Stop Gate of this file first.
2. Read `.elves-session.json`, then check `continuation_guard`.
3. Read learnings, plan, and execution log.
4. Resume the single next required action. In Phase 1 that is waiting for Lantern.

---

## Elves Report

- **Generate Elves Report:** yes, at terminal readiness.
- **Default path:** `/tmp/elves-report-cld-reducer-2026-10-07.html` in WSL.
- **Commit report:** no.

---

## Acceptance Checks

Landable is plan acceptance with proof, not green CI alone. Only the driver writes `.elves-session.json`.

- Route (c): a batch is complete when the driver has verified its `B#-A#` rows, written them to `.elves-session.json`, and pushed that run-doc commit; only then does the driver prompt the next batch.
- Routes (a) and (b): a batch is closed by the worker when its `Close` commit (with acceptance ids and evidence in the body) is pushed, its report file exists, and its CI workflow is green on that commit; its session rows stay `met: false` until the driver's terminal or safety reconciliation writes them.
- Before readiness, on every route: every `B#-A#` and `M-A#` row has evidence in the session, the landing check passes on the evidence commit, and "Definition of green" in the plan holds at one exact head.
