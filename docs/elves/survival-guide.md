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
- **Stop policy:** blocker-only after `EXECUTE APPROVED`; before it, the plan review gate applies
- **User intent:** John Ennis (2026-10-07 11:15 ET): "take the repo cld-reducer and structure it like turfLP so that it covers R and JavaScript ... The goal is to get it submitted to CRAN and npm for R and javascript ... plan very carefully with robust review then do it as an elves run." Lantern brief: Phase 1 is plan only; wait for `EXECUTE APPROVED`; stop point is a landable, green, reviewed draft PR.
- **Checkpoint due by:** none
- **Checkpoint semantics:** none
- **May continue after checkpoint:** yes
- **Actual stop conditions:** Phase 1: plan printed as `PLAN READY FOR REVIEW` and waiting for Lantern. Execution: draft PR green per the plan section "Definition of green", or a true blocker.
- **Workspace ownership:** dedicated worktree `C:\Claude\cld-reducer-r-js-packages` on branch `feat/r-js-packages`, created with the Elves `preflight_worktree.py --create-worktree feat/r-js-packages --base origin/main` (dry run first). No other agent shares it. The main checkout `C:\Claude\cld-reducer` stays on `main` and is not used for edits. Route dependent: routes (b) and (c) keep this worktree; route (a) re-registers a worktree in WSL.
- **Branch tip at start (collision tripwire):** `eb95fe9ad5e983a1f2e6e02668c3419647b9571e` (origin/main at staging). Upstream tracking was removed so a bare `git push` cannot target `main`.
- **Merge policy:** user-merges (default). The driver never merges. No merge-on-green opt-in and no landing command in this run.
- **Final-response policy:** allowed in Phase 1 after the `PLAN READY FOR REVIEW` line; after `EXECUTE APPROVED`, disallowed until the Stop Gate allows it.
- **Coordination mode:** Cobbler-first (default).
- **Execution route:** pending Mason (H13). Proposed: route (c), manual experimental prewalk in Herdr tab `cld-worker`, driver-supervised batches. Route (c) worker starts always use `--safe-mode`; the driver reports the Herdr session identity; driver-private state (phase record, audit script, baseline, driver-commit record, audit logs) lives outside the worktree in `C:\Users\Megan\AppData\Local\elves-runs\cld-reducer-r-js-packages-2026-10-07\route-c`; recovery is phase-specific (guide failures resume the guide route only); the authority audit and the transcript checks run at every gate and detect, not prevent; every driver commit SHA goes in `driver-commits.json` and the driver transcript at once, and into the execution log with the next driver evidence commit (no commit records its own SHA). Values below marked (c) change for routes (a) and (b); see the plan section "Route-dependent content".
- **Batch completion rule:** route (c): the worker pushes the batch `Close` commit and writes `.elves/runtime/worker-report-B<N>.md`; the driver verifies each row, writes the session rows, commits and pushes the run docs (`Batch N/6 · Review`), then prompts the next batch. Routes (a) and (b): the worker closes internal batches with the Close commit body and report file as interim evidence; the parked driver writes session rows once at a safety, blocked, or terminal wake. Every completed batch must end with a commit and push.
- **Progress visibility rule:** commit subjects `[feat/r-js-packages · Batch N/6 · Contract|Implement|Validate|Review|Close] <concrete outcome>`. No vague subjects. `Close` needs acceptance evidence and a Confidence trailer in the Elves format. No AI attribution lines.
- **Coordinator-to-implementer handoff:** the plan has a handoff block per batch; the consolidated packet is `.elves/runtime/worker-packet.md`. Each batch completion reports confidence (high, medium, or low) and unsure areas; an empty list is a valid answer.
- **Worker packet:** `.elves/runtime/worker-packet.md` (also `worker_packet_path` in `.elves-session.json`; `.elves/` is ignored through `.git/info/exclude`).
- **Handoff validation:** v2.8 advisory path (no explicit v1 capsule).
- **Re-read rule:** after every host-owned commit and push, re-read this survival guide before anything else. During the parked full-run, re-read once on a safety, blocked, or terminal wake.
- **Checkpoint rule:** no checkpoints in this run.
- **E2E mode:** chat-to-work (landable PR only).
- **Work driver:** host-native (a separate native Claude Code worker session with exact-session prewalk, not in-session execution).
- **Implementation lane:** fast
- **Delegation scope:** batch for route (c) (one packet at the guide turn, then one prompt per batch that points to the batch handoff block); full_run for routes (a) and (b)
- **Git mode:** branch_progress (the worker commits and pushes only `feat/r-js-packages`)
- **Driver monitor mode:** interactive for route (c) (`herdr agent wait` with timeouts as watchdog); parked_monitor for routes (a) and (b)
- **Driver update policy:** route (c): progress lines in the driver pane at batch boundaries; routes (a) and (b): sanitized follow stream, material wakes only.
- **Driver poll policy:** route (c): `herdr agent wait cld-worker` with a timeout, then `herdr agent get` and `git log`; routes (a) and (b): host wait primitive with a fallback watchdog.
- **Driver review policy:** route (c): per-batch contract walk of the acceptance rows by the driver; all routes: final independent review (Astra plus a fresh Opus 5.5 session), then delta re-review until clean.
- **Follow mode:** route (c): `herdr agent read` and the worker transcript; routes (a) and (b): default sanitized stream.
- **Risk posture:** standard (B3 and B5 are high).
- **Trust mode:** trusted
- **Landing outcome:** landable_pr (draft PR, not merged)
- **Driver merge authorized:** no
- **Worker merge authority:** false
- **Stable plan IDs:** B1 to B6, `B#-A#`, `M-A1` to `M-A6`.
- **Staging acceptance validation:** see Launch Readiness; command below.
- **Staging acceptance command:** `python C:\Users\Megan\.claude\skills\elves\scripts\acceptance_contract.py validate --repo-root . --session .elves-session.json`
- **High-risk checkpoints:** B3 Close (Python behavior change), B5 Close (R CRAN checks).
- **GitHub push auth route:** host `gh` (account MasonHsu02, scopes repo and workflow).
- **Re-drive budget:** 2 substantive re-drives. Transient provider errors retry the same worker with 5m, 10m, 20m backoff and do not use this budget.
- **Continuation harness:** none
- **Routes:** guide phase claude-opus-5-5 at xhigh, execution phase claude-sonnet-5-5 at high. Prewalk: `required` (qualified) for route (a); experimental, manual, Mason-accepted for route (c). Qualification failure, or a failed route (c) transition check, stops the run; no cold substitute and no silent model change.
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
- **Stop allowed right now:** yes
- **Why:** Phase 1 ends at the plan review gate; execution needs `EXECUTE APPROVED` from Lantern and Mason's route decision (H13).
- **Next required action:** print `PLAN READY FOR REVIEW: C:\Claude\cld-reducer-r-js-packages\docs\plans\r-js-packages\plan.md` and wait for Lantern.

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

**Status:** Staging (Phase 1, plan review gate)

**Active batch:** none

**What was just finished:** plan, run docs, session file, and worker packet written in the registered worktree.

**Single next action:** print the plan-ready line and wait for Lantern.

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
- **Default path:** `C:\Users\Megan\AppData\Local\Temp\elves-report-cld-reducer-2026-10-07.html` (the Windows temp folder stands in for `/tmp`).
- **Commit report:** no.

---

## Acceptance Checks

Landable is plan acceptance with proof, not green CI alone. Only the driver writes `.elves-session.json`.

- Route (c): a batch is complete when the driver has verified its `B#-A#` rows, written them to `.elves-session.json`, and pushed that run-doc commit; only then does the driver prompt the next batch.
- Routes (a) and (b): a batch is closed by the worker when its `Close` commit (with acceptance ids and evidence in the body) is pushed, its report file exists, and its CI workflow is green on that commit; its session rows stay `met: false` until the driver's terminal or safety reconciliation writes them.
- Before readiness, on every route: every `B#-A#` and `M-A#` row has evidence in the session, the landing check passes on the evidence commit, and "Definition of green" in the plan holds at one exact head.
