"""Raw pilot selection and resource evidence checks, without timing runs."""

import copy
import json

import pytest
from cases import job_key, jobs
from common import digest, input_digest
from pilot_evidence import validate_pilot
from test_resource_evidence import write_resource_fixture


def write_pilot_fixture(directory, manifest, baseline_rows, baseline_metadata):
    """Build a raw pilot with the same deterministic outputs as the captures."""
    original = copy.deepcopy(manifest)
    for name in list(original):
        if name.startswith(("pilot_", "baseline_", "calibration_", "profile_")):
            original.pop(name)
    original.pop("candidate", None)
    original.update(frozen=False, iterations={}, baseline_failures=[], gain_targets={})
    source, harness = baseline_metadata["source"], baseline_metadata["harness"]
    versions = copy.deepcopy(manifest["baseline_versions"])
    metadata = dict(
        complete=True,
        source=source,
        source_after=source,
        harness=harness,
        harness_after=harness,
        versions=versions,
        machine=baseline_metadata.get("machine", {"test": True}),
        manifest_sha256=digest(original),
        input_sha256=input_digest(original),
    )
    rows, iterations, failures = [], {}, []
    captures = {"|".join((r["language"], r["method"], r["id"])): r for r in baseline_rows}
    for language in manifest["languages"]:
        for case in jobs(manifest):
            key = job_key(language, case)
            captured = captures[key]
            if "response" in captured:
                first = dict(copy.deepcopy(captured["response"]), action="measure")
                calls = []
                failures.append(key)
            else:
                count = manifest["iterations"][key]
                first = dict(
                    ok=True,
                    action="measure",
                    iterations=1,
                    elapsed_ns=original["batch_target_ns"] / count,
                    result=copy.deepcopy(captured["result"]),
                )
                calls = [copy.deepcopy(first) for _ in range(original["warmup_batches"])]
                iterations[key] = count
            row = dict(
                key=key,
                versions=versions[language],
                first=first,
                warm=copy.deepcopy(calls[-1] if calls else first),
                warmups=calls,
                peak_rss=1024,
            )
            if key in iterations:
                row["iterations"] = iterations[key]
            rows.append(row)
    selected = dict(
        copy.deepcopy(original),
        iterations=iterations,
        baseline_failures=failures,
        pilot_source=source,
        pilot_harness=harness,
        baseline_versions=versions,
    )
    manifest.setdefault("pilot_source", source)
    manifest.setdefault("pilot_harness", harness)
    write_resource_fixture(directory, metadata, rows, "pilot")
    for name, value in (
        ("input-manifest", original),
        ("manifest", selected),
        ("metadata", metadata),
    ):
        (directory / f"{name}.json").write_text(json.dumps(value) + "\n")
    (directory / "pilot.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
    return validate_pilot(
        directory, manifest, baseline_rows, manifest.get("baseline_failure_classes", {})
    )


@pytest.fixture
def pilot_case(tmp_path):
    source = dict(
        path="/source", head="a" * 40, tree="b" * 40, status="", build_files={}, lock_files={}
    )
    harness = dict(source, path="/harness", head="c" * 40)
    version = dict(
        ok=True,
        action="version",
        language="python",
        runtime="3.13",
        source_head=source["head"],
        module_load_ns=100,
        dependencies={"highspy": "1.14"},
        solver={"name": "HiGHS", "version": "1.14"},
        settings={"presolve": "on", "threads": 1, "mip_rel_gap": 0, "mip_abs_gap": 0},
    )
    manifest = dict(
        languages=["python"],
        methods=["letter_minimum"],
        cases=[dict(id="one", tier="solve", options={})],
        presolve={"python": "on"},
        memory_limit_mb=128,
        memory_growth_tolerance_mb=32,
        warmup_batches=3,
        batch_target_ns=50000000,
        baseline_source=source,
        baseline_versions={"python": version},
        baseline_failures=[],
        iterations={"python|letter_minimum|one": 7},
    )
    captures = [dict(language="python", id="one", method="letter_minimum", result={"value": 1})]
    metadata = dict(source=source, harness=harness, machine={"machine": "test"})
    report = write_pilot_fixture(tmp_path, manifest, captures, metadata)
    return tmp_path, manifest, captures, report


def change_file(directory, name, change, *, rows=False):
    path = directory / name
    values = (
        [json.loads(line) for line in path.read_text().splitlines()]
        if rows
        else json.loads(path.read_text())
    )
    change(values)
    path.write_text("".join(json.dumps(v) + "\n" for v in values) if rows else json.dumps(values))


@pytest.mark.parametrize(
    "fault",
    [
        "receipt",
        "rows_missing",
        "rows_duplicate",
        "iterations",
        "warmup_count",
        "warm_action",
        "warm_result",
        "final_warm",
        "bad_time",
        "bad_iterations",
        "version",
        "source_after",
        "harness_after",
        "input_hash",
        "raw_input",
        "selected_manifest",
        "frozen_iterations",
        "resource_hash",
        "unknown_failure",
    ],
)
def test_pilot_checks_raw_selection_and_resource_evidence(pilot_case, fault):
    directory, manifest, captures, _ = pilot_case
    if fault == "receipt":
        next(directory.glob("*.resource.json")).unlink()
    elif fault in (
        "rows_missing",
        "rows_duplicate",
        "iterations",
        "warmup_count",
        "warm_action",
        "warm_result",
        "final_warm",
        "bad_time",
        "bad_iterations",
        "version",
        "unknown_failure",
    ):

        def change(rows):
            row = rows[0]
            if fault == "rows_missing":
                rows.clear()
            elif fault == "rows_duplicate":
                rows.append(copy.deepcopy(row))
            elif fault == "iterations":
                row["iterations"] += 1
            elif fault == "warmup_count":
                row["warmups"].pop()
            elif fault == "warm_action":
                row["warmups"][0]["action"] = "capture"
            elif fault == "warm_result":
                row["warmups"][0]["result"]["value"] = 2
            elif fault == "final_warm":
                row["warm"]["elapsed_ns"] += 1
            elif fault == "bad_time":
                row["first"]["elapsed_ns"] = 0
            elif fault == "bad_iterations":
                row["first"]["iterations"] = 2
            elif fault == "version":
                row["versions"]["dependencies"]["highspy"] = "changed"
            else:
                row["warm"] = row["warmups"][-1] = dict(
                    ok=False, action="measure", error={"kind": "ExternalLimit", "message": "crash"}
                )

        change_file(directory, "pilot.jsonl", change, rows=True)
    elif fault in ("source_after", "harness_after"):
        change_file(directory, "metadata.json", lambda m: m[fault].update(head="e" * 40))
    elif fault == "input_hash":
        change_file(directory, "metadata.json", lambda m: m.update(manifest_sha256="0" * 64))
    elif fault == "raw_input":
        change_file(directory, "input-manifest.json", lambda m: m.update(batch_target_ns=1))
    elif fault == "selected_manifest":
        change_file(directory, "manifest.json", lambda m: m.update(unrecorded_change=True))
    elif fault == "frozen_iterations":
        manifest["iterations"]["python|letter_minimum|one"] += 1
    else:
        change_file(
            directory,
            "resources.jsonl",
            lambda rows: rows[0].update(sampled_peak_rss=2048),
            rows=True,
        )
    with pytest.raises((ValueError, OSError)):
        validate_pilot(directory, manifest, captures, {})


def test_pilot_allows_later_sampling_count_increase_and_module_load_noise(pilot_case):
    directory, manifest, captures, report = pilot_case
    manifest.update(processes=16, batches=36, warmup_batches=4)
    change_file(
        directory,
        "pilot.jsonl",
        lambda rows: rows[0]["versions"].update(module_load_ns=200),
        rows=True,
    )
    changed = validate_pilot(directory, manifest, captures, {})
    assert changed["sha256"]["rows"] != report["sha256"]["rows"]
    assert changed["sha256"]["resources"] == report["sha256"]["resources"]


@pytest.mark.parametrize("elapsed,expected", [(100000000, 1), (3000000, 17), (1, 100000)])
def test_pilot_recomputes_original_rounding_and_cap(pilot_case, elapsed, expected):
    directory, manifest, captures, _ = pilot_case
    manifest["iterations"]["python|letter_minimum|one"] = expected

    def change(rows):
        row = rows[0]
        row["iterations"] = expected
        for response in [row["first"], row["warm"], *row["warmups"]]:
            response["elapsed_ns"] = elapsed

    change_file(directory, "pilot.jsonl", change, rows=True)
    change_file(
        directory, "manifest.json", lambda m: m["iterations"].update(manifest["iterations"])
    )
    validate_pilot(directory, manifest, captures, {})
