# Implement the performance plan

The accepted design is design.md, frozen SHA256 7ed56e283d73a3a5089a366a41794d76d7e4d10620c03ef93b0e66942d7b82a5. The user authorized implementation on 2026-10-11. Its planning-only status describes the prior review stage. This execution plan authorizes implementation only. Merge and publication remain separate.

## Batch 1: benchmark PR

Build on commit 0f5a707d65d3fa019269e79279c09786792a1911. Keep runtime files unchanged. Add a common driver protocol, frozen graph families, raw measurement capture, profiling, baseline canonical vectors, acceptance analysis, package exclusions and harness checks. Risks are measurement bias, accidental instrumentation in timed calls, and inconsistent normalization.

### Acceptance criteria

- [ ] B1-A1: Benchmark drivers cover Python, R and JavaScript with full result and canonical vector capture, profiles and uninstrumented full API timing.
- [ ] B1-A2: The manifest fixes graph inputs, tiers, seeds, resource limits, methods, routes and measurement design before candidate timing.
- [ ] B1-A3: Paired analysis implements the accepted per-case and target gates, rejects missing or failed evidence, and passes meaningful harness tests.
- [ ] B1-A4: Baseline vectors and profile evidence bind the source head and dependencies; package archives exclude benchmark code and outputs.
- [ ] B1-A5: The benchmark PR has exact-head CI and the four required independent reviews, with valid findings resolved.

## Batch 2: one measured runtime optimization

Select one candidate from B1 evidence. Freeze target eligibility and gain versus regression-only groups before candidate timing. Change only the selected shared algorithm and required language adapters, tests and docs. Keep the default C method, weighted objectives, canonical outputs, public fields, deadlines and error behavior.

### Acceptance criteria

- [ ] B2-A1: One selected candidate has a shared proof, all three implementations and fault paths that remain tested.
- [ ] B2-A2: Full correctness suites, all conformance, baseline vectors, independent oracles and package checks pass at the runtime head.
- [ ] B2-A3: Two independent paired runs on development and untouched validation inputs pass the frozen acceptance gate, or failed candidates are rejected and the reference is retained as the accepted design permits.
- [ ] B2-A4: The runtime PR contains only an accepted candidate, current release notes and exact-head CI plus four independent code reviews.

## Master acceptance

- [ ] M-A1: Both PR stages preserve existing submissions and contain no unapproved merge or publication.
- [ ] M-A2: The final evidence proves the selected result against every requirement in design.md and the worktrees are clean.
