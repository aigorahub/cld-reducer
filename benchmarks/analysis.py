"""Paired hierarchical bootstrap and checks for one measured run.

A passing result is one run's result. Final acceptance also needs a second
independent passing run and the separate correctness and resource gates.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from pathlib import Path

import numpy as np
from cases import job_key, jobs
from common import digest, input_digest, source_identity, version_identity

LANGUAGES = {"python": {"python"}, "r": {"r"}, "js": {"js", "javascript"}}
METHODS = {"letter_minimum", "assignment_minimum"}


def at_most(value, limit):
    """Include an exact boundary despite roundoff from ratios, logs and exp."""
    return value <= limit or math.isclose(value, limit, rel_tol=4 * np.finfo(float).eps)


def case_input_digest(case):
    return digest({name: case.get(name) for name in ("call", "input", "options")})


def calibration_design(manifest):
    """Fields that must remain fixed between A/A and the decision runs."""
    fields = (
        "processes",
        "warmup_batches",
        "batches",
        "iterations",
        "bootstrap_resamples",
        "bootstrap_seed",
        "order_seed",
        "baseline_failures",
    )
    return {"input_sha256": input_digest(manifest), **{name: manifest[name] for name in fields}}


def select_gain_targets(manifest, profiles):
    """Select every eligible case, then retain groups with five inputs per split."""
    expected = {
        job_key(language, case): case
        for language in manifest["languages"]
        for case in jobs(manifest)
    }
    seen, eligible = set(), defaultdict(list)
    for row in profiles:
        key = row["key"]
        if key not in expected:
            if row["case"]["tier"] == "solve":
                raise ValueError(f"Unexpected solve profile: {key}")
            continue
        if key in seen or row["case"] != expected[key]:
            raise ValueError(f"Duplicate or mismatched solve profile: {key}")
        seen.add(key)
        response = row["response"]
        if response.get("ok") is not True:
            continue
        metrics, phases = response.get("metrics", {}), response.get("phases_ns", {})
        cover, solver, total = (
            metrics.get("essential_cover"),
            metrics.get("solver_total_ns"),
            phases.get("total"),
        )
        if (
            type(cover) is not bool
            or type(solver) not in (int, float)
            or not math.isfinite(solver)
            or solver < 0
            or type(total) not in (int, float)
            or not math.isfinite(total)
            or total <= 0
        ):
            raise ValueError(f"Missing or invalid target eligibility metrics: {key}")
        if cover and solver / total >= 0.25:
            if key in manifest["baseline_failures"]:
                raise ValueError(f"Target profile conflicts with baseline failure: {key}")
            eligible["|".join(key.split("|", 2)[:2])].append(key)
    if seen != set(expected):
        raise ValueError("Target profiles do not cover every solve case")
    targets = {
        group: sorted(keys)
        for group, keys in sorted(eligible.items())
        if all(
            len(
                {
                    case_input_digest(expected[key])
                    for key in keys
                    if expected[key]["split"] == split
                }
            )
            >= 5
            for split in ("development", "validation")
        )
    }
    if not targets:
        raise ValueError("Profiles do not support a gain group with five distinct inputs per split")
    return targets


def estimate(base, candidate, draws, seed):
    """Resample paired batches in each original process, then those processes."""
    base, candidate = np.asarray(base, dtype=float), np.asarray(candidate, dtype=float)
    if (
        base.shape != candidate.shape
        or base.ndim != 2
        or 0 in base.shape
        or not np.all(np.isfinite(base))
        or not np.all(np.isfinite(candidate))
        or np.any(base <= 0)
        or np.any(candidate <= 0)
    ):
        raise ValueError("Timing arrays must be paired, nonempty, finite and positive")
    if type(draws) is not int or draws < 1 or type(seed) is not int or seed < 0:
        raise ValueError("Bootstrap count and seed must be valid integers")
    processes, batches = base.shape
    rng = np.random.default_rng(seed)
    bi = rng.integers(0, batches, size=(draws, processes, batches))
    # Each original process gets one paired batch sample per draw. If a process
    # is selected twice below, both selections reuse that same sampled median.
    original_process = np.arange(processes)[None, :, None]
    b = np.median(base[original_process, bi], axis=2)
    c = np.median(candidate[original_process, bi], axis=2)
    pi = rng.integers(0, processes, size=(draws, processes))
    b = np.take_along_axis(b, pi, axis=1)
    c = np.take_along_axis(c, pi, axis=1)
    log_ratios = np.log(np.median(c, axis=1)) - np.log(np.median(b, axis=1))
    point = float(np.median(np.median(candidate, axis=1)) / np.median(np.median(base, axis=1)))
    interval = np.exp(np.quantile(log_ratios, [0.025, 0.975])).tolist()
    if (
        not math.isfinite(point)
        or point <= 0
        or not all(math.isfinite(value) and value > 0 for value in interval)
    ):
        raise ValueError("Timing ratio is not finite")
    return point, interval, log_ratios


def valid_source(binding, *, require_js=False):
    """Reject absent, dirty, truncated or unhashed source records."""
    if not isinstance(binding, dict):
        return False
    if not isinstance(binding.get("path"), str) or not Path(binding["path"]).is_absolute():
        return False
    if binding.get("status") != "":
        return False
    for name in ("head", "tree"):
        if not isinstance(binding.get(name), str) or not re.fullmatch(
            r"(?:[0-9a-f]{40}|[0-9a-f]{64})", binding[name]
        ):
            return False
    for name in ("build_files", "lock_files", "dependency_files", "compiler_files"):
        if (
            name in ("dependency_files", "compiler_files")
            and name not in binding
            and not require_js
        ):
            continue
        files = binding.get(name)
        if not isinstance(files, dict):
            return False
        for path, checksum in files.items():
            if not isinstance(path, str) or not path or Path(path).is_absolute():
                return False
            if ".." in Path(path).parts:
                return False
            if not isinstance(checksum, str) or not re.fullmatch(r"[0-9a-f]{64}", checksum):
                return False
    if "build_verified" in binding and type(binding["build_verified"]) is not bool:
        return False
    if require_js:
        dependencies, compiler = binding["dependency_files"], binding["compiler_files"]
        if (
            binding.get("build_verified") is not True
            or "js/dist/index.js" not in binding["build_files"]
            or "highs/package.json" not in dependencies
            or not any(
                path.startswith("highs/") and path.endswith(".wasm") for path in dependencies
            )
            or not any(
                path.startswith("highs/") and Path(path).suffix in (".js", ".mjs", ".cjs")
                for path in dependencies
            )
            or "typescript/bin/tsc" not in compiler
            or not any(path.startswith("typescript/") and path.endswith(".js") for path in compiler)
        ):
            return False
    return True


def same_javascript_tools(left, right):
    """Match verified solver and compiler bytes across different source trees."""
    return (
        valid_source(left, require_js=True)
        and valid_source(right, require_js=True)
        and all(left[name] == right[name] for name in ("dependency_files", "compiler_files"))
    )


def valid_version(version, language, presolve):
    if (
        not isinstance(version, dict)
        or not isinstance(version.get("language"), str)
        or version["language"] not in LANGUAGES[language]
    ):
        return False
    if not isinstance(version.get("runtime"), (str, dict)) or not version["runtime"]:
        return False
    if not isinstance(version.get("dependencies"), dict) or not version["dependencies"]:
        return False
    if not isinstance(version.get("solver"), dict) or not version["solver"]:
        return False
    settings = version.get("settings")
    if not isinstance(settings, dict) or settings.get("presolve") != presolve:
        return False
    if type(settings.get("threads")) is not int or settings["threads"] != 1:
        return False
    if any(
        type(settings.get(name)) not in (int, float) or settings[name] != 0
        for name in ("mip_rel_gap", "mip_abs_gap")
    ):
        return False
    try:
        digest(version_identity(version))
    except (TypeError, ValueError):
        return False
    return True


def check_bindings(manifest, metadata, reasons):
    before, after = metadata.get("source_before"), metadata.get("source_after")
    require_js = "js" in manifest["languages"]
    complete = True
    for label, value in (("before", before), ("after", after)):
        if not isinstance(value, dict) or set(value) != {"baseline", "candidate"}:
            reasons.append(f"Incomplete source binding {label}")
            complete = False
            continue
        for role in ("baseline", "candidate"):
            if not valid_source(value[role], require_js=require_js):
                reasons.append(f"Invalid source binding: {label}/{role}")
                complete = False
    if complete and before != after:
        reasons.append("Source binding changed during the run")
    if (
        complete
        and require_js
        and not same_javascript_tools(before["baseline"], before["candidate"])
    ):
        reasons.append("Paired JavaScript solver or compiler bytes differ")
    if not valid_source(metadata.get("harness")):
        reasons.append("Invalid harness source binding")
    if not valid_source(metadata.get("harness_after")) or metadata.get(
        "harness_after"
    ) != metadata.get("harness"):
        reasons.append("Harness source binding is missing or changed during collection")
    if metadata.get("kind") == "calibration":
        if complete and source_identity(before["baseline"]) != source_identity(before["candidate"]):
            reasons.append("A/A source identities differ")
        pilot = manifest.get("pilot_source")
        if not valid_source(pilot, require_js=require_js):
            reasons.append("Pilot source binding is missing or invalid")
        elif complete and source_identity(before["baseline"]) != source_identity(pilot):
            reasons.append("Baseline source differs from the pilot baseline")
    else:
        frozen = manifest.get("baseline_source")
        if not valid_source(frozen, require_js=require_js):
            reasons.append("Frozen baseline source binding is missing or invalid")
        elif complete and source_identity(before["baseline"]) != source_identity(frozen):
            reasons.append("Baseline source differs from the frozen baseline")

    versions = metadata.get("versions")
    if not isinstance(versions, list):
        reasons.append("Version records are missing")
        return
    required = {
        (language, process)
        for language in manifest["languages"]
        for process in range(manifest["processes"])
    }
    seen, stable = set(), {}
    frozen_versions = manifest.get("baseline_versions")
    reference_label = "Frozen baseline" if metadata.get("kind") == "candidate" else "Pilot"
    if not isinstance(frozen_versions, dict) or set(frozen_versions) != set(manifest["languages"]):
        reasons.append(f"{reference_label} versions do not cover the manifest languages")
        frozen_versions = {}
    for row in versions:
        if not isinstance(row, dict) or type(row.get("process")) is not int:
            reasons.append("Invalid version record")
            continue
        language = row.get("language")
        if not isinstance(language, str):
            reasons.append("Invalid version language")
            continue
        key = (language, row["process"])
        if key not in required:
            reasons.append(f"Unexpected version record: {key}")
            continue
        if key in seen:
            reasons.append(f"Duplicate version record: {key}")
        seen.add(key)
        pair = row.get("versions")
        presolve = manifest["presolve"][language]
        if (
            not isinstance(pair, list)
            or len(pair) != 2
            or any(not valid_version(v, language, presolve) for v in pair)
        ):
            reasons.append(f"Invalid runtime or solver settings: {key}")
            continue
        identities = [version_identity(v) for v in pair]
        if identities[0] != identities[1]:
            reasons.append(f"Paired runtime or dependency versions differ: {key}")
        if language in stable and stable[language] != identities[0]:
            reasons.append(f"Runtime or dependency versions changed across processes: {language}")
        stable.setdefault(language, identities[0])
        if complete:
            for role, version in zip(("baseline", "candidate"), pair, strict=True):
                if version.get("source_head") != before[role]["head"]:
                    reasons.append(f"Driver source head differs: {key}/{role}")
        frozen = frozen_versions.get(language)
        if not valid_version(frozen, language, presolve):
            reasons.append(f"{reference_label} version is missing or invalid: {language}")
        elif version_identity(frozen) != identities[0]:
            reasons.append(
                f"Runtime or dependency versions differ from the {reference_label.lower()}: "
                f"{language}"
            )
    if seen != required:
        reasons.append("Version records do not cover every language and process")


def check_design(manifest):
    """Check fields needed by analysis before allocating resample arrays."""
    reasons = []
    if not isinstance(manifest, dict):
        return ["Manifest must be an object"]
    for key, choices in (("languages", LANGUAGES), ("methods", METHODS)):
        values = manifest.get(key)
        if (
            not isinstance(values, list)
            or not values
            or any(not isinstance(value, str) or value not in choices for value in values)
            or len(set(values)) != len(values)
        ):
            reasons.append(f"Invalid manifest {key}")
    if reasons:
        return reasons
    for name, minimum in (
        ("processes", 8),
        ("warmup_batches", 3),
        ("batches", 9),
        ("bootstrap_resamples", 10000),
        ("bootstrap_seed", 0),
        ("order_seed", 0),
    ):
        value = manifest.get(name)
        if type(value) is not int or value < minimum:
            reasons.append(f"Invalid measurement design: {name}")
    for name, maximum in (("processes", 16), ("batches", 36)):
        value = manifest.get(name)
        if type(value) is int and value > maximum:
            reasons.append(f"Measurement design exceeds the fixed limit: {name}")
    presolve = manifest.get("presolve")
    if not isinstance(presolve, dict) or any(
        presolve.get(language) not in (("off",) if language == "r" else ("on", "off"))
        for language in manifest.get("languages", [])
        if isinstance(language, str)
    ):
        reasons.append("Invalid presolve settings")
    cases = manifest.get("cases")
    if not isinstance(cases, list) or not cases:
        reasons.append("Manifest has no cases")
    else:
        ids = set()
        for case in cases:
            if not isinstance(case, dict) or not isinstance(case.get("id"), str):
                reasons.append("Invalid case")
                continue
            if case["id"] in ids:
                reasons.append(f"Duplicate case id: {case['id']}")
            ids.add(case["id"])
            if case.get("tier") not in ("solve", "preprocess", "expected-error", "opt-in"):
                reasons.append(f"Invalid case tier: {case['id']}")
            if case.get("tier") == "solve" and (
                case.get("split") not in ("development", "validation")
                or case.get("classification") not in ("ordinary", "stress")
            ):
                reasons.append(f"Invalid solve case class or split: {case['id']}")
            if not isinstance(case.get("options"), dict) or not isinstance(case.get("input"), dict):
                reasons.append(f"Invalid case input or options: {case['id']}")
    if not isinstance(manifest.get("iterations"), dict):
        reasons.append("Iteration counts are missing")
    return reasons


def analyze(manifest, metadata, records):
    reasons, per_case, groups = check_design(manifest), {}, {}
    try:
        manifest_hash, inputs_hash = digest(manifest), input_digest(manifest)
    except (KeyError, TypeError, ValueError):
        manifest_hash = inputs_hash = None
        reasons.append("Manifest cannot be hashed")
    report = {
        "pass": False,
        "scope": "single_run",
        "reasons": reasons,
        "cases": per_case,
        "groups": groups,
        "estimator": "ratio of medians of process batch medians; paired hierarchical bootstrap",
        "resampling": "paired batches within original processes, then processes",
        "kind": metadata.get("kind") if isinstance(metadata, dict) else None,
        "manifest_sha256": manifest_hash,
        "input_sha256": inputs_hash,
    }
    if reasons:
        return report
    if not isinstance(metadata, dict):
        reasons.append("Metadata must be an object")
        return report
    if metadata.get("complete") is not True:
        reasons.append("Run is incomplete")
    if metadata.get("kind") not in ("calibration", "candidate"):
        reasons.append("Unknown run kind")
    if metadata.get("manifest_sha256") != manifest_hash:
        reasons.append("Manifest binding differs")
    if metadata.get("input_sha256") != inputs_hash:
        reasons.append("Input binding differs")
    check_bindings(manifest, metadata, reasons)
    expected = {
        job_key(language, c): c for language in manifest["languages"] for c in jobs(manifest)
    }
    failures = manifest.get("baseline_failures")
    if (
        not isinstance(failures, list)
        or any(not isinstance(key, str) or key not in expected for key in failures)
        or len(set(failures)) != len(failures)
    ):
        reasons.append("Invalid baseline failure set")
        failures = []
    failures = set(failures)
    by_key = defaultdict(dict)
    if not isinstance(records, list):
        reasons.append("Samples must be a list")
        records = []
    for row in records:
        if (
            not isinstance(row, dict)
            or not isinstance(row.get("key"), str)
            or any(type(row.get(name)) is not int for name in ("process", "batch"))
        ):
            reasons.append("Invalid sample record")
            continue
        key = row["key"]
        index = (row["process"], row["batch"])
        if index in by_key[key]:
            reasons.append(f"Duplicate sample: {key} {index}")
        by_key[key][index] = row
    if set(by_key) - set(expected):
        reasons.append("Unexpected cases are present")
    if set(by_key) & failures:
        reasons.append("Baseline failure cases must not contain timing samples")
    aa = metadata.get("kind") == "calibration"
    draws = manifest["bootstrap_resamples"]
    log_draws = {}
    for key in expected:
        if key in failures:
            continue
        needed = {(p, b) for p in range(manifest["processes"]) for b in range(manifest["batches"])}
        rows = by_key[key]
        if set(rows) != needed:
            reasons.append(f"Missing or invalid sample indices: {key}")
            continue
        ordered = [rows[p, b] for p, b in sorted(needed)]
        if any(r.get("correct") is not True or r.get("ok") is not True for r in ordered):
            reasons.append(f"Incorrect output or failed call: {key}")
            continue
        iterations = manifest["iterations"].get(key)
        if (
            type(iterations) is not int
            or iterations < 1
            or any(
                type(r.get("iterations")) is not int or r["iterations"] != iterations
                for r in ordered
            )
        ):
            reasons.append(f"Iteration count differs: {key}")
            continue
        shape = (manifest["processes"], manifest["batches"])
        try:
            if any(
                type(r.get(name)) not in (int, float)
                for r in ordered
                for name in ("baseline_ns", "candidate_ns")
            ):
                raise ValueError("Timing samples must be numbers")
            base = np.array([r["baseline_ns"] for r in ordered]).reshape(shape)
            candidate = np.array([r["candidate_ns"] for r in ordered]).reshape(shape)
            point, interval, boot = estimate(base, candidate, draws, manifest["bootstrap_seed"])
        except (ValueError, KeyError, TypeError, OverflowError) as error:
            reasons.append(f"Invalid timings: {key}: {error}")
            continue
        per_case[key] = {
            "ratio": point,
            "interval_95": interval,
            "baseline_median_ns": float(np.median(np.median(base, axis=1))),
            "candidate_median_ns": float(np.median(np.median(candidate, axis=1))),
            "baseline_range_ns": [float(base.min()), float(base.max())],
            "candidate_range_ns": [float(candidate.min()), float(candidate.max())],
            "pass": at_most(interval[1], 1.05) and (not aa or at_most(1 / 1.05, interval[0])),
        }
        log_draws[key] = boot
        if not at_most(interval[1], 1.05):
            reasons.append(f"Nonregression margin not established: {key}")
        if aa and not at_most(1 / 1.05, interval[0]):
            reasons.append(f"A/A equivalence margin not established: {key}")
    if not per_case:
        reasons.append("No successful measured cases")
    targets = manifest.get("gain_targets")
    if not aa and manifest.get("frozen") is not True:
        reasons.append("Candidate manifest is not frozen")
    if not isinstance(targets, dict) or (not aa and not targets):
        reasons.append("No valid gain targets declared")
        targets = {}
    for group, keys in targets.items():
        valid_groups = {
            f"{language}|{method}"
            for language in manifest["languages"]
            for method in manifest["methods"]
        }
        if (
            group not in valid_groups
            or not isinstance(keys, list)
            or not keys
            or any(
                not isinstance(key, str)
                or key not in expected
                or key in failures
                or "|".join(key.split("|", 2)[:2]) != group
                for key in keys
            )
            or len(set(keys)) != len(keys)
        ):
            reasons.append(f"Invalid target group membership: {group}")
            continue
        for split in ("development", "validation"):
            members = [key for key in keys if expected[key]["split"] == split]
            distinct_inputs = {case_input_digest(expected[key]) for key in members}
            if len(distinct_inputs) < 5:
                reasons.append(f"Target group lacks five distinct inputs: {group}/{split}")
                continue
            if any(key not in per_case for key in members):
                reasons.append(f"Incomplete target group: {group}/{split}")
                continue
            if aa:
                continue
            point = math.exp(
                sum(math.log(per_case[key]["ratio"]) for key in members) / len(members)
            )
            # Calls to estimate use identical grouped resamples for every case.
            samples = np.mean([log_draws[key] for key in members], axis=0)
            interval = np.exp(np.quantile(samples, [0.025, 0.975])).tolist()
            passed = at_most(point, 0.90) and interval[1] < 1
            groups[f"{group}/{split}"] = {
                "ratio": point,
                "interval_95": interval,
                "cases": members,
                "pass": passed,
            }
            if not passed:
                reasons.append(f"Gain not established: {group}/{split}")
    report["pass"] = not reasons
    return report
