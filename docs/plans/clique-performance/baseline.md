# Baseline profile evidence

Reference source: `0f5a707d65d3fa019269e79279c09786792a1911`.
Profile harness: `9c7348f`.
Date: 2026-10-11.

`baseline-profile.json` records the source and build hashes, driver versions, raw artifact hashes, phase costs, model sizes, and solver call counts. The raw JSONL artifacts remain outside the checkout in the workspace evidence directory. These profiles diagnose costs. They are not speed acceptance results.

All 240 required profiles completed. All 216 full solve profiles succeeded. The 18 preprocessing cases succeeded. All six expected error cases reached the existing 10,000 clique limit. Each full solve profile followed three uninstrumented warmup calls in a fresh process. Profile hooks record inclusive regions, so the phase times must not be summed.

The essential cover certificate is the first candidate supported by these profiles. Its eligibility rule is fixed before candidate timing: the essential decisions cover the graph, and inclusive solver adapter calls consume at least 25 percent of the profiled full API time. Every case that meets this rule belongs to the target set.

| Language | Method | Development inputs | Validation inputs |
| --- | --- | ---: | ---: |
| Python | C | 13 | 12 |
| Python | Sigma | 12 | 12 |
| R | C | 14 | 11 |
| R | Sigma | 12 | 10 |
| JavaScript | C | 16 | 13 |
| JavaScript | Sigma | 13 | 12 |

All six groups meet the five input minimum in each split. A/A calibration, canonical capture, and the final frozen manifest are still required before candidate timing.

The four part multipartite sigma cases need about 291 to 292 solver calls in Python and R. Their profiled full API costs range from about 2.6 to 4.0 seconds. These cases remain in the regression set. The certificate will fall through to the existing BIP when essential decisions do not cover the graph.

If every decision has positive cost, every feasible solution contains all essential decisions. If those decisions already cover all vertices and edges, they form the unique minimum. Any additional decision increases the cost. The candidate will check the exact strategy coverage predicate and the shared deadline. It will preserve the existing expansion and final relationship checks. The full proof and test requirements are in `design.md`.

The Python and npm package archive and clean install checks passed. The built R source archive excludes `benchmarks/`. The runtime files remain unchanged in this benchmark PR.
