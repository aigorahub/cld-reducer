"""Final correctness, resource and two-run acceptance gate.

The fixture files must remain available at the recorded baseline source path.
Analysis reports are outputs, never inputs to this audit.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import subprocess
from pathlib import Path

import common
from analysis import (
    analyze,
    calibration_design,
    same_javascript_tools,
    select_gain_targets,
    valid_source,
)
from cases import job_key, jobs
from common import digest
from profile_outcomes import validate_preprocess_outcomes
from profile_settings import validate_solver_settings
from resource_evidence import validate_resources

FIXTURES = ("reduce", "reduce_letter_minimum", "reduce_weighted")
TIERS = ("solve", "preprocess", "expected-error")
DRIVERS = {
    "python": "benchmarks/python_driver.py",
    "r": "benchmarks/r_driver.R",
    "js": "benchmarks/js_driver.mjs",
}


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON field: {key}")
        result[key] = value
    return result


def _parse(text):
    def invalid(value):
        raise ValueError(f"Nonfinite JSON number: {value}")

    return json.loads(text, object_pairs_hook=_object, parse_constant=invalid)


def _read(directory, filename):
    return _parse((Path(directory) / filename).read_text())


def _rows(directory, filename):
    return [_parse(line) for line in (Path(directory) / filename).read_text().splitlines()]


def _positive(value):
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value > 0
    )


def _failure(response):
    return (
        isinstance(response, dict)
        and response.get("ok") is False
        and isinstance(response.get("error"), dict)
        and isinstance(response["error"].get("kind"), str)
        and bool(response["error"]["kind"])
        and isinstance(response["error"].get("message"), str)
        and "result" not in response
        and "canonical" not in response
    )


def _bounded_failure(response):
    if not _failure(response):
        return False
    message = response["error"]["message"].lower()
    return any(
        word in message
        for word in (
            "time limit",
            "wall limit",
            "memory limit",
            "maximal clique enumeration exceeded max_cliques=",
        )
    )


def _valid_version(version):
    settings = version.get("settings", {})
    return (
        version.get("ok") is True
        and version.get("action") == "version"
        and bool(version.get("runtime"))
        and isinstance(version.get("dependencies"), dict)
        and bool(version["dependencies"])
        and bool(version.get("solver"))
        and settings.get("threads") == 1
        and settings.get("mip_rel_gap") == 0
        and settings.get("mip_abs_gap") == 0
        and settings.get("primal_feasibility_tolerance") == 1e-9
        and settings.get("mip_feasibility_tolerance") == 1e-9
    )


def _value(row):
    return {"result": row["result"], "canonical": row["canonical"]}


def _essential_certificate(response):
    metrics = response.get("metrics", {})
    selected = response.get("canonical", {}).get("selected")
    return (
        _valid_value(response)
        and metrics.get("essential_cover") is True
        and all(
            type(metrics.get(name)) is int and metrics[name] == 0
            for name in (
                "solver_total_ns",
                "canonical_feasible_trials",
                "canonical_infeasible_trials",
            )
        )
        and type(metrics.get("decision_variables")) is int
        and metrics["decision_variables"] == len(selected)
        and type(metrics.get("essential_decisions")) is int
        and metrics["essential_decisions"] == sum(selected) > 0
        and metrics.get("selected") == selected
        and all(type(bit) is int for bit in metrics["selected"])
        and type(metrics.get("objective")) is int
        and metrics.get("objective") == response["canonical"]["objective"]
    )


def _valid_value(row):
    result, canonical = row.get("result"), row.get("canonical")
    if not isinstance(result, dict) or not isinstance(canonical, dict):
        return False
    selected = canonical.get("selected")
    objective = canonical.get("objective")
    groups, assignments, letters = (
        result.get(name) for name in ("groups", "assignments", "letters")
    )
    if not (
        isinstance(selected, list)
        and selected
        and all(type(bit) is int and bit in (0, 1) for bit in selected)
        and type(objective) is int
        and objective > 0
        and isinstance(groups, list)
        and groups
        and len(set(groups)) == len(groups)
        and all(isinstance(group, str) for group in groups)
        and isinstance(assignments, list)
        and len(assignments) == len(groups)
        and isinstance(letters, list)
        and len(letters) == len(groups)
        and all(
            isinstance(tokens, list) and tokens and all(isinstance(t, str) for t in tokens)
            for tokens in assignments
        )
        and all(isinstance(text, str) for text in letters)
    ):
        return False
    stats = result.get("stats", {})
    counts = (
        "assignments_before",
        "assignments_after",
        "num_letters_before",
        "num_letters_after",
        "num_groups",
        "num_edges",
    )
    if not (
        all(type(stats.get(name)) is int and stats[name] >= 0 for name in counts)
        and isinstance(stats.get("reduction_pct"), (int, float))
        and math.isfinite(stats["reduction_pct"])
    ):
        return False
    if not (
        result.get("relationship_preserved") is True
        and stats.get("solver_status") == "Optimal"
        and stats.get("objective") == objective
        and result.get("method") in ("letter_minimum", "assignment_minimum")
    ):
        return False
    adjacency = result.get("adjacency")
    reconstructed = [
        [bool(set(left) & set(right)) for right in assignments] for left in assignments
    ]
    rows = [
        dict(group=group, letters=letters[i], assignments=" ".join(assignments[i]))
        for i, group in enumerate(groups)
    ]
    return (
        adjacency == reconstructed
        and all(type(cell) is bool for row in adjacency for cell in row)
        and result.get("rows") == rows
    )


def _fixture_result(expected):
    groups = expected["groups"]
    assignments = [expected["assignments"][group] for group in groups]
    letters = [expected["letters"][group] for group in groups]
    fraction = expected["reduction_pct"]
    stats = dict(
        expected["stats"],
        objective=expected["objective"],
        solver_status=expected["solver_status"],
        reduction_pct=fraction["numerator"] / fraction["denominator"] * 100
        if fraction["denominator"]
        else 0,
    )
    return dict(
        groups=groups,
        assignments=assignments,
        letters=letters,
        stats=stats,
        method=expected["method"],
        relationship_preserved=expected["relationship_preserved"],
        adjacency=[[bool(set(left) & set(right)) for right in assignments] for left in assignments],
        rows=[
            dict(group=group, letters=letters[i], assignments=" ".join(assignments[i]))
            for i, group in enumerate(groups)
        ],
    )


def _case_input(case):
    return {name: case.get(name) for name in ("id", "call", "input", "options", "expected")}


def _oracle_input(case):
    options = {
        key: value
        for key, value in case["options"].items()
        if key not in ("time_limit", "max_cliques")
    }
    return {"call": case["call"], "input": case["input"], "options": options}


def _fixture_inventory(metadata):
    specs, hashes = {}, {}
    root = Path(metadata["source"]["path"])
    for name in FIXTURES:
        raw = (root / "conformance" / "fixtures" / f"{name}.json").read_bytes()
        hashes[name] = hashlib.sha256(raw).hexdigest()
        for original in _parse(raw)["cases"]:
            case = copy.deepcopy(original)
            case["id"] = f"fixture/{name}/{case['id']}"
            case["options"]["method"] = case["expected"]["method"]
            variants = [case]
            if "sigma_expected" in case:
                alternate = copy.deepcopy(case)
                alternate["id"] += "/sigma"
                alternate["expected"] = alternate["sigma_expected"]
                alternate["options"]["method"] = "assignment_minimum"
                variants.append(alternate)
            for variant in variants:
                key = (variant["id"], variant["options"]["method"])
                if key in specs:
                    raise ValueError(f"Duplicate oracle fixture: {key}")
                specs[key] = variant
    return specs, hashes


def _driver_hashes(binding, languages):
    if not valid_source(binding):
        raise ValueError("Invalid recorded harness source binding")
    hashes = {}
    for language in languages:
        filename = DRIVERS[language]
        try:
            raw = subprocess.check_output(
                ["git", "-C", binding["path"], "show", f"{binding['head']}:{filename}"],
                stderr=subprocess.DEVNULL,
            )
        except subprocess.CalledProcessError as error:
            raise ValueError(
                f"Recorded driver source is unavailable: {binding['head']}:{filename}"
            ) from error
        hashes[filename] = hashlib.sha256(raw).hexdigest()
    return hashes


def _measurement_hashes(binding, languages):
    """Bind measured code to calibration, including process lifecycle helpers."""
    hashes = _driver_hashes(binding, languages)
    required = ("benchmarks/run.py", "benchmarks/common.py", "benchmarks/analysis.py")
    optional = ("benchmarks/process_guard.py", "benchmarks/resource_evidence.py")
    try:
        present = subprocess.check_output(
            [
                "git",
                "-C",
                binding["path"],
                "ls-tree",
                "--name-only",
                binding["head"],
                "--",
                *optional,
            ],
            stderr=subprocess.DEVNULL,
            text=True,
        ).splitlines()
        hashes.update(dict.fromkeys(optional))
        for filename in required + tuple(present):
            raw = subprocess.check_output(
                ["git", "-C", binding["path"], "show", f"{binding['head']}:{filename}"],
                stderr=subprocess.DEVNULL,
            )
            hashes[filename] = hashlib.sha256(raw).hexdigest()
    except subprocess.CalledProcessError as error:
        raise ValueError(
            f"Recorded measurement source is unavailable: {binding['head']}"
        ) from error
    return hashes


def audit(
    manifest,
    run_dirs,
    baseline_capture_dir,
    candidate_capture_dir,
    baseline_profiles_dir,
    candidate_profiles_dir,
    calibration_dir,
):
    """Return pass/reasons/evidence. Invalid, missing or stale evidence fails closed."""
    reasons, evidence = [], {"runs": [], "captures": {}, "profiles": {}}

    def require(condition, reason):
        if not condition:
            reasons.append(reason)
        return bool(condition)

    def binding(metadata, label):
        require(metadata.get("complete") is True, f"{label}: incomplete evidence")
        require(
            metadata.get("input_sha256") == common.input_digest(manifest),
            f"{label}: input binding differs",
        )
        source = metadata.get("source")
        require(
            valid_source(source, require_js="js" in manifest["languages"]),
            f"{label}: invalid source binding or missing JavaScript build proof",
        )
        require(
            source == metadata.get("source_after"), f"{label}: source changed during collection"
        )
        require(
            valid_source(metadata.get("harness"))
            and metadata.get("harness_after") == metadata["harness"],
            f"{label}: harness binding is missing or changed during collection",
        )
        return common.source_identity(source)

    def versions(metadata, label):
        values = metadata.get("versions", {})
        require(
            isinstance(values, dict) and set(values) == set(manifest["languages"]),
            f"{label}: incomplete dependency versions",
        )
        result = {}
        for language in manifest["languages"]:
            version = values.get(language, {})
            require(_valid_version(version), f"{label}: failed version response for {language}")
            require(
                version.get("source_head") == metadata.get("source", {}).get("head"),
                f"{label}: driver source differs for {language}",
            )
            require(
                version.get("settings", {}).get("presolve") == manifest["presolve"][language],
                f"{label}: presolve differs for {language}",
            )
            result[language] = common.version_identity(version)
        return result

    try:
        if isinstance(manifest, (str, Path)):
            manifest = _parse(Path(manifest).read_text())
        require(manifest.get("frozen") is True, "Manifest is not frozen")
        require(len(run_dirs) == 2, "Exactly two candidate runs are required")
        require(
            len({str(Path(path).resolve()) for path in run_dirs}) == 2,
            "Candidate run directories are not distinct",
        )
        if len(run_dirs) != 2:
            return {
                "pass": False,
                "scope": "two_run_acceptance",
                "reasons": reasons,
                "evidence": evidence,
            }
        languages = manifest["languages"]
        require(
            bool(languages) and len(set(languages)) == len(languages), "Invalid language inventory"
        )
        solve_specs = {
            job_key(language, case): case for language in languages for case in jobs(manifest)
        }
        profile_specs = {
            job_key(language, case): case
            for language in languages
            for case in jobs(manifest, tiers=TIERS + ("opt-in",))
        }
        required_profiles = {key for key, case in profile_specs.items() if case["tier"] in TIERS}
        for parts in (6, 7, 8):
            require(
                any(
                    case["tier"] == "preprocess" and case["id"].endswith(f"multipartite-{parts}x3")
                    for case in manifest["cases"]
                ),
                f"Manifest lacks multipartite {parts} part preprocessing",
            )
        require(
            any(
                case["tier"] == "expected-error" and case["id"].endswith("multipartite-9x3")
                for case in manifest["cases"]
            ),
            "Manifest lacks the multipartite 9 part cap case",
        )
        failures = set(manifest.get("baseline_failures", []))
        require(failures <= set(solve_specs), "Unknown baseline failure cases")
        require(
            valid_source(manifest.get("baseline_source"), require_js="js" in languages),
            "Manifest lacks a valid frozen baseline source or JavaScript build proof",
        )
        frozen_source = common.source_identity(manifest.get("baseline_source"))
        require(
            valid_source(manifest.get("pilot_source"), require_js="js" in languages)
            and common.source_identity(manifest["pilot_source"]) == frozen_source,
            "Pilot source differs from the frozen baseline or lacks build proof",
        )
        calibration_manifest = _read(calibration_dir, "manifest.json")
        calibration_metadata = _read(calibration_dir, "metadata.json")
        calibration_samples = _rows(calibration_dir, "samples.jsonl")
        calibration_report = analyze(
            calibration_manifest,
            calibration_metadata,
            calibration_samples,
            calibration_targets=manifest.get("gain_targets"),
        )
        calibration_resources = validate_resources(
            calibration_dir,
            calibration_manifest,
            calibration_metadata,
            _rows(calibration_dir, "results.jsonl"),
            "compare",
        )
        require(
            calibration_resources["sha256"] == manifest.get("calibration_resource_sha256"),
            "Calibration resources differ from the frozen evidence",
        )
        require(
            calibration_manifest.get("frozen") is False
            and calibration_metadata.get("kind") == "calibration"
            and calibration_report["pass"],
            f"Raw A/A calibration failed: {calibration_report['reasons']}",
        )
        for name, value in (
            ("calibration_manifest_sha256", calibration_manifest),
            ("calibration_metadata_sha256", calibration_metadata),
            ("calibration_samples_sha256", calibration_samples),
            ("calibration_sha256", calibration_report),
        ):
            require(digest(value) == manifest.get(name), f"Calibration evidence differs: {name}")
        require(
            calibration_design(calibration_manifest) == calibration_design(manifest),
            "Calibration sampling design differs from the frozen decision design",
        )
        for variant in ("baseline", "candidate"):
            require(
                common.source_identity(calibration_metadata.get("source_before", {}).get(variant))
                == frozen_source,
                f"Calibration {variant} source differs from the frozen baseline",
            )
        require(
            {
                language: common.version_identity(version)
                for language, version in calibration_manifest.get("baseline_versions", {}).items()
            }
            == {
                language: common.version_identity(version)
                for language, version in manifest.get("baseline_versions", {}).items()
            },
            "Calibration versions differ from the frozen baseline",
        )
        calibration_harness = manifest.get("calibration_harness")
        require(valid_source(calibration_harness), "Missing or invalid calibration harness binding")
        require(
            valid_source(calibration_metadata.get("harness"))
            and valid_source(calibration_harness)
            and common.source_identity(calibration_metadata["harness"])
            == common.source_identity(calibration_harness),
            "Calibration harness differs from the frozen binding",
        )
        calibration_start, calibration_finish = (
            calibration_metadata.get("started_unix"),
            calibration_metadata.get("finished_unix"),
        )
        calibration_interval_valid = (
            _positive(calibration_start)
            and _positive(calibration_finish)
            and calibration_finish > calibration_start
        )
        require(calibration_interval_valid, "Calibration has an invalid real run interval")
        evidence["calibration"] = {
            "directory": str(calibration_dir),
            "analysis": calibration_report,
            "samples_sha256": digest(calibration_samples),
            "resources": calibration_resources,
        }
        capture_dirs = {"baseline": baseline_capture_dir, "candidate": candidate_capture_dir}
        capture_meta = {label: _read(path, "metadata.json") for label, path in capture_dirs.items()}
        fixture_specs, fixture_hashes = _fixture_inventory(capture_meta["baseline"])
        expected_captures = {}
        for language in languages:
            for (identifier, method), case in fixture_specs.items():
                expected_captures[(language, identifier, method)] = (case, True)
            for case in jobs(manifest):
                expected_captures[(language, case["id"], case["options"]["method"])] = (case, False)
        captures, identities, dependency_versions = {}, {}, {}
        for label, path in capture_dirs.items():
            metadata = capture_meta[label]
            identities[label] = binding(metadata, f"{label} capture")
            dependency_versions[label] = versions(metadata, f"{label} capture")
            require(metadata.get("failures") == [], f"{label} capture: reported mismatches")
            require(
                metadata.get("fixture_sha256") == fixture_hashes,
                f"{label} capture: oracle fixture hashes differ",
            )
            inventory = metadata.get("expected_keys", [])
            listed = [(entry["language"], entry["id"], entry["method"]) for entry in inventory]
            require(
                len(listed) == len(set(listed)) and set(listed) == set(expected_captures),
                f"{label} capture: expected oracle and stress inventory differs",
            )
            for entry in inventory:
                key = (entry["language"], entry["id"], entry["method"])
                require(
                    key in expected_captures
                    and entry.get("oracle_fixture") is expected_captures[key][1],
                    f"{label} capture: invalid oracle classification {key}",
                )
            indexed = {}
            capture_rows = _rows(path, "vectors.jsonl")
            capture_resources = validate_resources(
                path, manifest, metadata, capture_rows, "capture"
            )
            if label == "baseline":
                require(
                    capture_resources["sha256"] == manifest.get("baseline_capture_resource_sha256"),
                    "Baseline capture resources differ from the frozen evidence",
                )
                require(
                    digest(capture_rows) == manifest.get("baseline_capture_sha256"),
                    "Baseline capture differs from the frozen evidence",
                )
            for row in capture_rows:
                key = (row["language"], row["id"], row["method"])
                require(key not in indexed, f"{label} capture: duplicate row {key}")
                indexed[key] = row
                if not require(key in expected_captures, f"{label} capture: unexpected row {key}"):
                    continue
                case, oracle = expected_captures[key]
                require(row.get("mismatch") == [], f"{label} capture: mismatch {key}")
                require(
                    row.get("oracle_fixture") is oracle,
                    f"{label} capture: oracle flag differs {key}",
                )
                require(
                    (_case_input(row.get("case", {})) == _case_input(case))
                    if oracle
                    else row.get("case") == case,
                    f"{label} capture: case input differs {key}",
                )
                failed = "response" in row
                if failed:
                    require(
                        job_key(key[0], case) in failures
                        and not oracle
                        and _bounded_failure(row["response"])
                        and row["response"].get("action") == "capture"
                        and "result" not in row
                        and "canonical" not in row,
                        f"{label} capture: unexpected failed call {key}",
                    )
                else:
                    require(
                        _valid_value(row),
                        f"{label} capture: invalid result or canonical vector {key}",
                    )
                    if oracle:
                        require(
                            row.get("result") == _fixture_result(case["expected"]),
                            f"{label} capture: independent oracle mismatch {key}",
                        )
            require(
                set(indexed) == set(expected_captures), f"{label} capture: missing or extra rows"
            )
            require(
                metadata.get("checked") == len(expected_captures) == len(indexed),
                f"{label} capture: count differs from the full baseline inventory",
            )
            captures[label] = indexed
            evidence["captures"][label] = {
                "directory": str(path),
                "rows": len(indexed),
                "oracle_rows": len(fixture_specs) * len(languages),
            }
        require(
            identities["baseline"] == frozen_source,
            "Baseline capture source differs from the frozen baseline",
        )
        require(
            {
                language: common.version_identity(version)
                for language, version in manifest.get("baseline_versions", {}).items()
            }
            == dependency_versions["baseline"],
            "Baseline dependencies differ from the frozen evidence",
        )
        require(
            dependency_versions["baseline"] == dependency_versions["candidate"],
            "Baseline and candidate dependencies or solver settings differ",
        )
        if "js" in languages:
            require(
                same_javascript_tools(
                    capture_meta["baseline"].get("source"), capture_meta["candidate"].get("source")
                ),
                "Baseline and candidate JavaScript solver or compiler bytes differ",
            )
        oracles = [
            row
            for row in captures["baseline"].values()
            if row.get("oracle_fixture") is True and _valid_value(row)
        ]

        def new_success_has_oracle(row):
            return any(
                _oracle_input(oracle["case"]) == _oracle_input(row["case"])
                and _value(oracle) == _value(row)
                for oracle in oracles
            )

        for key in set(captures["baseline"]) & set(captures["candidate"]):
            base, candidate = captures["baseline"][key], captures["candidate"][key]
            if "response" not in base:
                require(
                    "response" not in candidate and _value(base) == _value(candidate),
                    f"Canonical vector or full result differs: {key}",
                )
            elif "response" in candidate:
                require(
                    base["response"]["error"]["kind"] == candidate["response"]["error"]["kind"],
                    f"Baseline failure category changed: {key}",
                )
            else:
                require(
                    new_success_has_oracle(candidate),
                    f"New success lacks an independent matching oracle: {key}",
                )

        machine = capture_meta["baseline"].get("machine")
        driver_hashes = _driver_hashes(capture_meta["baseline"].get("harness"), languages)
        measurement_hashes = _measurement_hashes(calibration_harness, languages)
        require(
            all(measurement_hashes.get(name) == value for name, value in driver_hashes.items()),
            "Language driver bytes differ from calibration",
        )
        require(isinstance(machine, dict) and bool(machine), "Missing machine identity")

        def context(metadata, label):
            require(metadata.get("machine") == machine, f"{label}: machine differs")
            require(valid_source(metadata.get("harness")), f"{label}: invalid harness binding")
            require(
                metadata.get("harness_after") == metadata.get("harness"),
                f"{label}: harness changed during collection",
            )
            observed_drivers = _driver_hashes(metadata.get("harness"), languages)
            require(observed_drivers == driver_hashes, f"{label}: language driver source differs")
            if "driver_sha256" in metadata:
                require(
                    all(
                        metadata["driver_sha256"].get(name) == value
                        for name, value in observed_drivers.items()
                    ),
                    f"{label}: recorded driver hashes differ",
                )

        context(capture_meta["baseline"], "baseline capture")
        context(capture_meta["candidate"], "candidate capture")
        context(calibration_metadata, "calibration")
        profiles, solver_settings = {}, {}
        for label, path in (
            ("baseline", baseline_profiles_dir),
            ("candidate", candidate_profiles_dir),
        ):
            metadata = _read(path, "metadata.json")
            require(
                binding(metadata, f"{label} profiles") == identities[label],
                f"{label} profiles: source differs",
            )
            context(metadata, f"{label} profiles")
            require(
                versions(metadata, f"{label} profiles") == dependency_versions[label],
                f"{label} profiles: dependencies or settings differ",
            )
            indexed = {}
            profile_rows = _rows(path, "profiles.jsonl")
            profile_resources = validate_resources(
                path, manifest, metadata, profile_rows, "profiles"
            )
            preprocess_outcomes = validate_preprocess_outcomes(
                manifest, profile_rows, candidate=label == "candidate"
            )
            solver_settings[label] = {}
            if label == "baseline":
                require(
                    profile_resources["sha256"] == manifest.get("profile_resource_sha256"),
                    "Baseline profile resources differ from the frozen evidence",
                )
                require(
                    digest(profile_rows) == manifest.get("profile_sha256"),
                    "Baseline profiles differ from the frozen evidence",
                )
            for row in profile_rows:
                key = row["key"]
                require(key not in indexed, f"{label} profiles: duplicate row {key}")
                indexed[key] = row
                if not require(key in profile_specs, f"{label} profiles: unexpected case {key}"):
                    continue
                case, response = profile_specs[key], row["response"]
                require(
                    row.get("case") == case, f"{label} profiles: case specification differs {key}"
                )
                if response.get("ok") is True:
                    language = key.split("|", 1)[0]
                    observed = validate_solver_settings(
                        language, response, metadata["versions"][language]["settings"]
                    )
                    solver_settings[label][key] = observed
                    if observed is None and case["tier"] != "preprocess":
                        require(
                            label == "candidate"
                            and manifest.get("candidate") == "essential-cover-certificate"
                            and _essential_certificate(response),
                            f"{label} profiles: zero solves lack an essential certificate {key}",
                        )
                if case["tier"] == "preprocess":
                    continue  # The shared gate checks exact outcomes and their memory evidence.
                require(
                    _positive(row.get("peak_rss"))
                    and row["peak_rss"] <= manifest["memory_limit_mb"] * 1024**2,
                    f"{label} profiles: missing or exceeded memory bound {key}",
                )
                action = (
                    "preprocess" if case["tier"] in ("preprocess", "expected-error") else "profile"
                )
                require(response.get("action") == action, f"{label} profiles: wrong action {key}")
                if case["tier"] == "expected-error":
                    cap = case["options"].get("max_cliques", 10000)
                    message = response.get("error", {}).get("message", "")
                    require(
                        _failure(response)
                        and response["error"]["message"].startswith(
                            "maximal clique enumeration exceeded max_cliques="
                        )
                        and message.split("max_cliques=", 1)[1].split(";", 1)[0] == str(cap),
                        f"{label} profiles: expected cap error missing {key}",
                    )
                elif response.get("ok") is not True:
                    require(
                        key in failures and _bounded_failure(response),
                        f"{label} profiles: failed required case {key}",
                    )
                else:
                    total = response.get("phases_ns", {}).get("total")
                    require(
                        _positive(total) and total <= case["wall_seconds"] * 1e9,
                        f"{label} profiles: missing or exceeded wall bound {key}",
                    )
                    if case["tier"] == "solve":
                        require(
                            _valid_value(response),
                            f"{label} profiles: invalid successful response {key}",
                        )
                        language, method, identifier = key.split("|", 2)
                        captured = captures[label].get((language, identifier, method), {})
                        require(
                            "result" in captured and _value(response) == _value(captured),
                            f"{label} profiles: result differs from capture {key}",
                        )
                    else:
                        require(
                            _valid_value(response),
                            f"{label} profiles: invalid optional stress response {key}",
                        )
            require(
                required_profiles <= set(indexed),
                f"{label} profiles: missing required solve, preprocess or cap rows",
            )
            profiles[label] = indexed
            evidence["profiles"][label] = {
                "directory": str(path),
                "rows": len(indexed),
                "preprocessing": preprocess_outcomes,
                "solver_settings": solver_settings[label],
            }
        targets = select_gain_targets(manifest, list(profiles["baseline"].values()))
        require(
            manifest.get("gain_targets") == targets,
            "Frozen gain targets differ from the full eligible profile set",
        )
        require(
            set(profiles["baseline"]) == set(profiles["candidate"]),
            "Baseline and candidate profile coverage differs",
        )
        for key in set(profiles["baseline"]) & set(profiles["candidate"]):
            base, candidate = (
                profiles[label][key]["response"] for label in ("baseline", "candidate")
            )
            base_settings = solver_settings["baseline"].get(key)
            candidate_settings = solver_settings["candidate"].get(key)
            if base_settings is not None and candidate_settings is not None:
                require(
                    digest(base_settings) == digest(candidate_settings),
                    f"Native solver settings differ between baseline and candidate: {key}",
                )
            if _failure(base) and _failure(candidate):
                require(
                    base["error"]["kind"] == candidate["error"]["kind"],
                    f"Resource failure category changed: {key}",
                )
            if profile_specs[key]["tier"] == "opt-in" and base.get("ok") and candidate.get("ok"):
                require(
                    _value(base) == _value(candidate),
                    f"Optional stress result or canonical vector differs: {key}",
                )

        intervals, run_ids, pids = [], set(), set()
        tolerance = manifest.get("memory_growth_tolerance_mb")
        valid_tolerance = (
            type(tolerance) in (int, float) and math.isfinite(tolerance) and tolerance >= 0
        )
        require(
            valid_tolerance,
            "Manifest lacks a nonnegative finite memory growth allowance",
        )
        for path in run_dirs:
            metadata, samples = _read(path, "metadata.json"), _rows(path, "samples.jsonl")
            label = f"run {path}"
            require(
                metadata.get("kind") == "candidate" and metadata.get("complete") is True,
                f"{label}: requires a complete candidate run",
            )
            require(
                metadata.get("input_sha256") == common.input_digest(manifest),
                f"{label}: input binding differs",
            )
            require(
                metadata.get("manifest_sha256") == digest(manifest), f"{label}: manifest differs"
            )
            require(
                metadata.get("source_before") == metadata.get("source_after"),
                f"{label}: source changed",
            )
            for variant in ("baseline", "candidate"):
                source = metadata.get("source_before", {}).get(variant, {})
                require(source.get("status") == "", f"{label}: {variant} source is dirty")
                require(
                    common.source_identity(metadata.get("source_before", {}).get(variant))
                    == identities[variant],
                    f"{label}: {variant} source differs",
                )
            context(metadata, label)
            require(
                _measurement_hashes(metadata["harness"], languages) == measurement_hashes,
                f"{label}: measurement code differs from calibration",
            )
            run_id = metadata.get("run_id")
            require(
                isinstance(run_id, str) and bool(run_id) and run_id not in run_ids,
                f"{label}: run ID is missing or reused",
            )
            run_ids.add(run_id)
            start, finish = metadata.get("started_unix"), metadata.get("finished_unix")
            if require(
                _positive(start) and _positive(finish) and finish > start,
                f"{label}: invalid real run interval",
            ):
                intervals.append((start, finish))
                require(
                    calibration_interval_valid and calibration_finish <= start,
                    f"{label}: calibration did not finish before candidate timing",
                )
            seen = set()
            for record in metadata.get("versions", []):
                index = (record["language"], record["process"])
                require(index not in seen, f"{label}: duplicate process version record")
                seen.add(index)
                pair, process_ids = record.get("versions", []), record.get("pids", [])
                require(
                    len(pair) == 2 and len(process_ids) == 2,
                    f"{label}: incomplete fresh process evidence",
                )
                for variant, version in zip(("baseline", "candidate"), pair, strict=True):
                    require(
                        _valid_version(version)
                        and common.version_identity(version)
                        == dependency_versions[variant].get(index[0]),
                        f"{label}: runtime, dependency or setting drift",
                    )
                for pid in process_ids:
                    require(
                        type(pid) is int and pid > 0 and pid not in pids,
                        f"{label}: missing or reused process ID",
                    )
                    pids.add(pid)
            require(
                seen
                == {
                    (language, process)
                    for language in languages
                    for process in range(manifest["processes"])
                },
                f"{label}: missing fresh processes",
            )
            rss_by_process = {}
            for row in samples:
                if row.get("key") not in solve_specs or row["key"] in failures:
                    require(False, f"{label}: unexpected scored case {row.get('key')}")
                    continue
                language, method, identifier = row["key"].split("|", 2)
                key = (language, identifier, method)
                wanted_hashes = [
                    digest(captures[variant][key].get("result"))
                    for variant in ("baseline", "candidate")
                ]
                require(
                    row.get("result_hashes") == wanted_hashes,
                    f"{label}: sample result hash differs {row['key']}",
                )
                valid_memory = True
                for field in ("rss", "peak_rss"):
                    memory = row.get(field, [])
                    valid_memory &= require(
                        isinstance(memory, list)
                        and len(memory) == 2
                        and all(
                            _positive(value) and value <= manifest["memory_limit_mb"] * 1024**2
                            for value in memory
                        ),
                        f"{label}: missing or exceeded sample {field} bound",
                    )
                if valid_memory:
                    require(
                        all(
                            current <= peak
                            for current, peak in zip(row["rss"], row["peak_rss"], strict=True)
                        ),
                        f"{label}: current RSS exceeds recorded peak",
                    )
                    rss_by_process.setdefault((language, row["process"]), []).append(row["rss"])
            growth = []
            for (language, process), values in sorted(rss_by_process.items()):
                delta = [values[-1][i] - values[0][i] for i in (0, 1)]
                excess = delta[1] - delta[0]
                require(
                    valid_tolerance and excess <= tolerance * 1024**2,
                    f"{label}: candidate RSS growth exceeds baseline and allowance "
                    f"for {language}/{process}",
                )
                growth.append(
                    dict(
                        language=language,
                        process=process,
                        first_rss=values[0],
                        last_rss=values[-1],
                        baseline_growth_bytes=delta[0],
                        candidate_growth_bytes=delta[1],
                        excess_candidate_growth_bytes=excess,
                    )
                )
            response_rows = _rows(path, "results.jsonl")
            run_resources = validate_resources(path, manifest, metadata, response_rows, "compare")
            seen_results = set()
            for row in response_rows:
                index = (row["key"], row["process"])
                require(index not in seen_results, f"{label}: duplicate recorded result {index}")
                seen_results.add(index)
                language, method, identifier = row["key"].split("|", 2)
                pair = row.get("responses", [])
                require(len(pair) == 2, f"{label}: missing recorded response pair {index}")
                if row["key"] in failures:
                    require(
                        row.get("baseline_failure") is True and row["process"] == 0,
                        f"{label}: invalid separate baseline failure record {index}",
                    )
                    failure_versions, failure_pids = row.get("versions", []), row.get("pids", [])
                    require(
                        len(failure_versions) == 2 and len(failure_pids) == 2,
                        f"{label}: missing separate baseline failure processes {index}",
                    )
                    for variant, version in zip(
                        ("baseline", "candidate"), failure_versions, strict=True
                    ):
                        require(
                            _valid_version(version)
                            and version.get("source_head")
                            == metadata["source_before"][variant]["head"]
                            and common.version_identity(version)
                            == dependency_versions[variant].get(language),
                            f"{label}: baseline failure dependency or source differs {index}",
                        )
                    for pid in failure_pids:
                        require(
                            type(pid) is int and pid > 0 and pid not in pids,
                            f"{label}: missing or reused failure process ID",
                        )
                        pids.add(pid)
                for variant, response in zip(("baseline", "candidate"), pair, strict=True):
                    captured = captures[variant].get((language, identifier, method), {})
                    if "response" in captured:
                        require(
                            response == captured["response"],
                            f"{label}: baseline failure response changed {index}",
                        )
                    else:
                        require(
                            response.get("ok") is True
                            and response.get("result") == captured.get("result")
                            and (
                                row["key"] not in failures
                                or response.get("canonical") == captured.get("canonical")
                            ),
                            f"{label}: recorded API output differs {index}",
                        )
            expected_results = {
                (key, process)
                for key in solve_specs
                if key not in failures
                for process in range(manifest["processes"])
            } | {(key, 0) for key in failures}
            require(
                seen_results == expected_results,
                f"{label}: missing recorded API results or baseline failures",
            )
            report = analyze(manifest, metadata, samples)
            require(
                report.get("scope") == "single_run", f"{label}: analysis is not scoped to one run"
            )
            require(
                report.get("pass") is True,
                f"{label}: raw-sample analysis failed: {report.get('reasons')}",
            )
            evidence["runs"].append(
                {
                    "directory": str(path),
                    "run_id": run_id,
                    "samples_sha256": digest(samples),
                    "analysis": report,
                    "rss_growth": growth,
                    "resources": run_resources,
                }
            )
        if len(intervals) == 2:
            first, second = sorted(intervals)
            require(first[1] <= second[0], "The two candidate runs overlap in real time")
        evidence["manifest_sha256"] = digest(manifest)
        evidence["input_sha256"] = common.input_digest(manifest)
        evidence["baseline_failures_unscored"] = sorted(failures)
        evidence["driver_sha256"] = driver_hashes
        evidence["measurement_sha256"] = measurement_hashes
        evidence["harness_rule"] = (
            "Capture and profile stages may use different recorded harness commits. "
            "Language driver bytes must match across all stages. "
            "Measurement code bytes must match calibration and both timed runs. "
            "An absent process guard is recorded as null."
        )
    except (
        OSError,
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        IndexError,
        OverflowError,
    ) as error:
        reasons.append(f"Invalid or missing evidence: {type(error).__name__}: {error}")
    return {
        "pass": not reasons,
        "scope": "two_run_acceptance",
        "reasons": reasons,
        "evidence": evidence,
    }
