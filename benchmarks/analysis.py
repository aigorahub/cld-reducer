"""Paired hierarchical bootstrap and fail-closed acceptance checks."""
from __future__ import annotations

import math
from collections import defaultdict

import numpy as np

from cases import job_key, jobs
from common import digest


def estimate(base, candidate, draws, seed):
    """Ratio of medians of per-process medians, resampling paired batches and processes."""
    base, candidate = np.asarray(base, dtype=float), np.asarray(candidate, dtype=float)
    if base.shape != candidate.shape or base.ndim != 2 or not np.all(np.isfinite(base)) or not np.all(np.isfinite(candidate)) or np.any(base <= 0) or np.any(candidate <= 0):
        raise ValueError("Timing arrays must be paired, finite and positive")
    processes, batches = base.shape
    rng = np.random.default_rng(seed)
    pi = rng.integers(0, processes, size=(draws, processes))
    bi = rng.integers(0, batches, size=(draws, processes, batches))
    b = base[pi[:, :, None], bi]
    c = candidate[pi[:, :, None], bi]
    ratios = np.median(np.median(c, axis=2), axis=1) / np.median(np.median(b, axis=2), axis=1)
    point = float(np.median(np.median(candidate, axis=1)) / np.median(np.median(base, axis=1)))
    return point, np.quantile(ratios, [.025, .975]).tolist(), np.log(ratios)


def analyze(manifest, metadata, records):
    reasons, per_case, groups = [], {}, {}
    if not metadata.get("complete"):
        reasons.append("Run is incomplete")
    if metadata.get("manifest_sha256") != digest(manifest):
        reasons.append("Manifest binding differs")
    if metadata.get("source_before") != metadata.get("source_after"):
        reasons.append("Source binding changed during the run")
    by_key = defaultdict(dict)
    for row in records:
        key = row["key"]
        index = (row["process"], row["batch"])
        if index in by_key[key]:
            reasons.append(f"Duplicate sample: {key} {index}")
        by_key[key][index] = row
    expected = {job_key(language, c): c for language in manifest["languages"] for c in jobs(manifest)}
    if set(by_key) - set(expected):
        reasons.append("Unexpected cases are present")
    draws = int(manifest["bootstrap_resamples"])
    failures = set(manifest.get("baseline_failures", []))
    log_draws = {}
    for key, case in expected.items():
        if key in failures:
            continue
        needed = {(p, b) for p in range(manifest["processes"]) for b in range(manifest["batches"])}
        rows = by_key[key]
        if set(rows) != needed:
            reasons.append(f"Missing or invalid sample indices: {key}")
            continue
        ordered = [rows[p, b] for p, b in sorted(needed)]
        if any(not r.get("correct") or not r.get("ok") for r in ordered):
            reasons.append(f"Incorrect output or failed call: {key}")
            continue
        if any(r.get("iterations") != manifest["iterations"].get(key) for r in ordered):
            reasons.append(f"Iteration count differs: {key}")
            continue
        shape = (manifest["processes"], manifest["batches"])
        try:
            base = np.array([r["baseline_ns"] for r in ordered]).reshape(shape)
            candidate = np.array([r["candidate_ns"] for r in ordered]).reshape(shape)
            point, interval, boot = estimate(base, candidate, draws, manifest["bootstrap_seed"])
        except (ValueError, KeyError, TypeError) as error:
            reasons.append(f"Invalid timings: {key}: {error}")
            continue
        per_case[key] = {"ratio": point, "interval_95": interval,
                         "baseline_median_ns": float(np.median(np.median(base, axis=1))),
                         "candidate_median_ns": float(np.median(np.median(candidate, axis=1))),
                         "baseline_range_ns": [float(base.min()), float(base.max())],
                         "candidate_range_ns": [float(candidate.min()), float(candidate.max())],
                         "pass": interval[1] <= 1.05}
        log_draws[key] = boot
        if interval[1] > 1.05:
            reasons.append(f"Nonregression margin not established: {key}")
    aa = metadata.get("kind") == "calibration"
    if not aa and not manifest.get("frozen"):
        reasons.append("Candidate manifest is not frozen")
    if not aa and not manifest.get("gain_targets"):
        reasons.append("No gain targets declared")
    for group, keys in manifest.get("gain_targets", {}).items():
        if aa:
            break
        for split in ("development", "validation"):
            members = [k for k in keys if k in expected and expected[k]["split"] == split]
            if len(set(members)) < 5 or len(set(members)) != len(members):
                reasons.append(f"Invalid target group size: {group}/{split}")
                continue
            if any(k not in per_case for k in members):
                reasons.append(f"Incomplete target group: {group}/{split}")
                continue
            point = math.exp(sum(math.log(per_case[k]["ratio"]) for k in members) / len(members))
            # Identical resample indices retain shared process and batch variation across cases.
            sample = np.exp(np.mean([log_draws[k] for k in members], axis=0))
            interval = np.quantile(sample, [.025, .975]).tolist()
            passed = point <= .90 and interval[1] < 1
            groups[f"{group}/{split}"] = {"ratio": point, "interval_95": interval,
                                          "cases": members, "pass": passed}
            if not passed:
                reasons.append(f"Gain not established: {group}/{split}")
    return {"pass": not reasons, "reasons": reasons, "cases": per_case, "groups": groups,
            "estimator": "ratio of medians of process batch medians; paired hierarchical bootstrap",
            "kind": metadata.get("kind"), "manifest_sha256": digest(manifest)}
