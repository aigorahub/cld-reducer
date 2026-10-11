"""Frozen inputs for development, untouched validation, and bounded stress work."""

from __future__ import annotations

import copy
import json
import random
from pathlib import Path

METHODS = ("letter_minimum", "assignment_minimum")


def graph(n, edges):
    a = [[int(i == j) for j in range(n)] for i in range(n)]
    for i, j in edges:
        a[i][j] = a[j][i] = 1
    return a


def multipartite(parts, size=3):
    n = parts * size
    return graph(n, ((i, j) for i in range(n) for j in range(i) if i // size != j // size))


def twins(a, count):
    return [
        [a[i // count][j // count] for j in range(len(a) * count)] for i in range(len(a) * count)
    ]


def frozen_manifest(repo: Path):
    cases = []

    def add(name, a, split, classification="ordinary", tier="solve", seed=None):
        cases.append(
            {
                "id": f"{split}/{name}",
                "split": split,
                "classification": classification,
                "tier": tier,
                "seed": seed,
                "wall_seconds": 60 if tier == "opt-in" else 30,
                "call": "adjacency",
                "input": {
                    "adjacency": a,
                    "groups": [f"v{i}" for i in range(len(a))],
                    "means": None,
                },
                "options": {},
            }
        )

    fixtures = json.loads((repo / "conformance/fixtures/reduce.json").read_text())["cases"]
    for name in ("hand/simple-abc-pairs-means", "hand/wheat"):
        f = copy.deepcopy(next(c for c in fixtures if c["id"] == name))
        f.pop("expected")
        f.update(
            id="development/" + name,
            split="development",
            classification="ordinary",
            tier="solve",
            seed=None,
            wall_seconds=30,
        )
        cases.append(f)
    for split, offset, seed in (("development", 0, 20261011), ("validation", 1, 73918421)):
        for n in (6 + offset, 20 + offset, 100 - 11 * offset):
            add(f"complete-{n}", [[1] * n for _ in range(n)], split)
        for n in (6 + offset, 24 + offset):
            add(f"edgeless-{n}", graph(n, []), split)
        for n in (6 + offset, 16 + offset):
            add(f"path-{n}", graph(n, ((i, i + 1) for i in range(n - 1))), split)
        n = 8 + offset
        add(f"cycle-{n}", graph(n, ((i, (i + 1) % n) for i in range(n))), split)
        n = 6 + offset
        add("repeated-path", twins(graph(n, ((i, i + 1) for i in range(n - 1))), 3), split)
        twin_path = 3 + offset
        add(
            "repeated-path-large-classes",
            twins(
                graph(twin_path, ((i, i + 1) for i in range(twin_path - 1))),
                10 if split == "development" else 7,
            ),
            split,
        )
        # Interleave two disconnected cycles in the original input order.
        n = 4 + offset
        add(
            "interleaved-components",
            graph(2 * n, ((2 * i + c, 2 * ((i + 1) % n) + c) for c in range(2) for i in range(n))),
            split,
            "stress",
        )
        for parts in (2, 3, 4):
            a = multipartite(parts)
            if split == "validation":
                order = list(range(len(a)))
                random.Random(seed + parts).shuffle(order)
                a = [[a[i][j] for j in order] for i in order]
            add(f"multipartite-{parts}x3", a, split, "stress", seed=seed + parts)
        for index, (n, probability) in enumerate(
            ((9 + offset, 0.25), (10 + offset, 0.5), (12, 0.65))
        ):
            rng = random.Random(seed + 100 + index)
            add(
                f"random-{n}-{probability}",
                graph(
                    n, ((i, j) for i in range(n) for j in range(i) if rng.random() < probability)
                ),
                split,
                "stress",
                seed=seed + 100 + index,
            )
    for parts in (5, 6, 7, 8, 9):
        add(
            f"multipartite-{parts}x3",
            multipartite(parts),
            "bounded",
            "stress",
            "opt-in" if parts == 5 else "expected-error" if parts == 9 else "preprocess",
        )
    return {
        "schema_version": 1,
        "case_generator": "cases.py:1",
        "cases": cases,
        "methods": list(METHODS),
        "languages": ["python", "r", "js"],
        "presolve": {"python": "on", "r": "off", "js": "on"},
        "memory_limit_mb": 8192,
        "memory_growth_tolerance_mb": 32,
        "processes": 8,
        "warmup_batches": 3,
        "batches": 9,
        "batch_target_ns": 50_000_000,
        "bootstrap_resamples": 10000,
        "bootstrap_seed": 146081,
        "order_seed": 193871,
        "iterations": {},
        "gain_targets": {},
        "baseline_failures": [],
        "frozen": False,
    }


def jobs(manifest, *, tiers=("solve",), splits=None):
    for case in manifest["cases"]:
        if case["tier"] not in tiers or (splits and case["split"] not in splits):
            continue
        for method in manifest["methods"]:
            c = copy.deepcopy(case)
            c["options"]["method"] = method
            yield c


def job_key(language, case):
    return "|".join((language, case["options"]["method"], case["id"]))
