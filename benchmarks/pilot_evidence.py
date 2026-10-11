"""Check the raw baseline pilot that selected the frozen batch lengths."""

from __future__ import annotations

import copy
import json
import math
from pathlib import Path

from analysis import valid_source, valid_version
from cases import job_key, jobs
from common import digest, input_digest, source_identity, version_identity
from resource_evidence import validate_resources
from solve_outcomes import solve_failure_class


def _require(condition, message):
    if not condition:
        raise ValueError(f"Pilot evidence: {message}")


def _parse(text):
    def pairs(values):
        result = {}
        for key, value in values:
            _require(key not in result, f"duplicate field {key}")
            result[key] = value
        return result

    def invalid(value):
        raise ValueError(f"Pilot evidence: nonfinite value {value}")

    return json.loads(text, object_pairs_hook=pairs, parse_constant=invalid)


def validate_pilot(directory, manifest, baseline_rows, baseline_classes):
    """Return raw file digests only after validating outputs, selection and receipts."""
    directory = Path(directory)
    original = _parse((directory / "input-manifest.json").read_text())
    selected = _parse((directory / "manifest.json").read_text())
    metadata = _parse((directory / "metadata.json").read_text())
    rows = [_parse(line) for line in (directory / "pilot.jsonl").read_text().splitlines()]
    languages = manifest["languages"]
    _require(
        original.get("frozen") is False and selected.get("frozen") is False,
        "pilot manifests must precede freeze",
    )
    _require(
        original.get("iterations") == {} and original.get("baseline_failures") == [],
        "pilot input already has selected iterations or exclusions",
    )
    _require(metadata.get("complete") is True, "collection is incomplete")
    _require(metadata.get("manifest_sha256") == digest(original), "input manifest hash differs")
    _require(
        metadata.get("input_sha256")
        == input_digest(original)
        == input_digest(selected)
        == input_digest(manifest),
        "case inputs or resource limits differ",
    )
    source, harness = metadata.get("source"), metadata.get("harness")
    _require(
        valid_source(source, require_js="js" in languages)
        and source == metadata.get("source_after"),
        "source is missing or changed",
    )
    _require(
        valid_source(harness) and harness == metadata.get("harness_after"),
        "harness is missing or changed",
    )
    for design in (selected, manifest):
        _require(
            valid_source(design.get("pilot_source"), require_js="js" in languages)
            and source_identity(design["pilot_source"]) == source_identity(source),
            "source differs from selected baseline",
        )
        _require(
            valid_source(design.get("pilot_harness"))
            and source_identity(design["pilot_harness"]) == source_identity(harness),
            "harness differs from selected pilot",
        )
    if "baseline_source" in manifest:
        _require(
            source_identity(manifest["baseline_source"]) == source_identity(source),
            "source differs from frozen baseline",
        )
    versions = metadata.get("versions")
    _require(
        isinstance(versions, dict) and set(versions) == set(languages),
        "dependency inventory is incomplete",
    )
    for language in languages:
        version = versions[language]
        _require(
            valid_version(version, language, manifest["presolve"][language])
            and version.get("ok") is True
            and version.get("action") == "version"
            and "error" not in version
            and version.get("source_head") == source["head"],
            f"invalid driver version for {language}",
        )
        for design in (selected, manifest):
            _require(
                set(design.get("baseline_versions", {})) == set(languages)
                and version_identity(version)
                == version_identity(design["baseline_versions"][language]),
                f"dependency versions differ for {language}",
            )
    warmups, target = original.get("warmup_batches"), original.get("batch_target_ns")
    _require(type(warmups) is int and warmups >= 3, "invalid warmup count")
    _require(
        type(target) in (int, float)
        and math.isfinite(target)
        and target > 0
        and selected.get("batch_target_ns") == manifest.get("batch_target_ns") == target,
        "batch target differs",
    )
    specs = {job_key(language, case): case for language in languages for case in jobs(original)}
    captures = {"|".join((row["language"], row["method"], row["id"])): row for row in baseline_rows}
    seen, iterations, failures = set(), {}, []
    for row in rows:
        key = row.get("key")
        _require(key in specs and key not in seen, "job inventory is duplicated or unexpected")
        seen.add(key)
        language = key.split("|", 1)[0]
        _require(
            isinstance(row.get("versions"), dict)
            and row["versions"].get("source_head") == source["head"]
            and row["versions"].get("ok") is True
            and row["versions"].get("action") == "version"
            and version_identity(row["versions"]) == version_identity(versions[language]),
            f"row version differs: {key}",
        )
        first, warm, calls = row.get("first"), row.get("warm"), row.get("warmups")
        _require(
            isinstance(first, dict) and isinstance(warm, dict) and isinstance(calls, list),
            f"missing first or warm responses: {key}",
        )
        responses = [first] + calls
        for index, response in enumerate(responses):
            _require(
                isinstance(response, dict) and response.get("action") == "measure",
                f"invalid action: {key}",
            )
            if response.get("ok") is True:
                elapsed = response.get("elapsed_ns")
                _require(
                    "error" not in response
                    and type(response.get("iterations")) is int
                    and response["iterations"] == 1
                    and type(elapsed) in (int, float)
                    and math.isfinite(elapsed)
                    and elapsed > 0,
                    f"invalid single-call time: {key}",
                )
                # An excluded case can succeed before its bounded warm failure.
                captured = captures.get(key, {})
                if "result" in captured:
                    _require(
                        response.get("result") == captured["result"]
                        and digest(response["result"]) == digest(captured["result"]),
                        f"full API output differs from baseline capture: {key}",
                    )
                else:
                    _require(
                        key in baseline_classes and isinstance(response.get("result"), dict),
                        f"missing baseline result: {key}",
                    )
            else:
                outcome = solve_failure_class(response, language, specs[key], "measure")
                _require(
                    index == len(responses) - 1 and outcome == baseline_classes.get(key),
                    f"resource failure class differs: {key}",
                )
        _require(warm == responses[-1], f"final warm response differs: {key}")
        if warm.get("ok") is True:
            _require(
                len(calls) == warmups and key not in baseline_classes,
                f"successful warmup inventory differs: {key}",
            )
            count = max(1, min(100000, math.ceil(target / warm["elapsed_ns"])))
            _require(
                type(row.get("iterations")) is int and row["iterations"] == count,
                f"selected iterations differ from baseline time: {key}",
            )
            iterations[key] = count
        else:
            _require(
                len(calls) <= warmups and "iterations" not in row,
                f"failed warmup inventory differs: {key}",
            )
            failures.append(key)
    _require(seen == set(specs), "job inventory is incomplete")
    _require(set(failures) == set(baseline_classes), "failure inventory differs from capture")
    expected = copy.deepcopy(original)
    expected.update(
        iterations=iterations,
        baseline_failures=failures,
        pilot_source=source,
        pilot_harness=harness,
        baseline_versions=versions,
    )
    _require(
        digest(selected) == digest(expected), "selected manifest differs from raw pilot outcomes"
    )
    _require(
        digest(manifest.get("iterations")) == digest(iterations)
        and manifest.get("baseline_failures") == failures,
        "frozen iterations or failure inventory differs",
    )
    resources = validate_resources(directory, selected, metadata, rows, "pilot")
    return {
        "sha256": {
            "input_manifest": digest(original),
            "manifest": digest(selected),
            "metadata": digest(metadata),
            "rows": digest(rows),
            "resources": resources["sha256"],
        },
        "resources": resources,
        "metadata": metadata,
    }
