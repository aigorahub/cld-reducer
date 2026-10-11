"""Resource inventory checks and real collector shutdown checks. No solver timing."""

import copy
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import common
import pytest
import resource_evidence as resources
import run
from process_guard import COVERAGE, _command_digest


def write_resource_fixture(directory, metadata, rows, stage):
    """Write valid synthetic OS receipts for other gate tests to mutate."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    if stage != "compare":
        for index, row in enumerate(rows):
            row.setdefault("pid", 10000 + index * 2)
    expected = resources._expected(metadata, rows, stage)
    metadata["resource_processes"] = [
        {"pid": pid, "language": spec["language"], "source_path": spec["source_path"]}
        for pid, spec in expected.items()
    ]
    records = []
    for pid, spec in expected.items():
        language = spec["language"]
        peak = max(
            (row.get("peak_rss", 1024) for row in rows if row.get("pid") == pid), default=1024
        )
        memory_failure = any(
            response.get("error") == resources.MEMORY_ERROR for response in spec["responses"]
        )
        command = [
            {"python": sys.executable, "js": "node", "r": "Rscript"}[language],
            str(Path(metadata["harness"]["path"]) / resources.DRIVERS[language]),
            "--repo",
            spec["source_path"],
            "--presolve",
            "on",
        ]
        receipt = {
            "schema_version": 1,
            "complete": True,
            "guard_pid": pid,
            "child_pid": pid + 10000000,
            "wait_status": 0,
            "exitstatus": 0,
            "ru_maxrss": peak,
            "ru_maxrss_unit": "bytes",
            "peak_rss_bytes": peak,
            "platform": "darwin",
            "command_sha256": _command_digest(command),
            "coverage": copy.deepcopy(COVERAGE),
        }
        filename = f"{pid}.resource.json"
        (directory / filename).write_text(json.dumps(receipt))
        records.append(
            {
                "schema_version": 1,
                "language": language,
                "guard_pid": pid,
                "command": command,
                "receipt_file": filename,
                "receipt": receipt,
                "sampled_peak_rss": peak,
                "peak_rss": peak,
                "resource_error": "Driver memory limit exceeded" if memory_failure else None,
            }
        )
    write_records(directory, records)
    return records


def write_records(directory, records):
    (Path(directory) / "resources.jsonl").write_text(
        "".join(json.dumps(record) + "\n" for record in records)
    )


def fixture(tmp_path, stage="profiles"):
    manifest = {"languages": ["python"], "presolve": {"python": "on"}, "memory_limit_mb": 128}
    metadata = {"source": {"path": "/source"}, "harness": {"path": "/harness"}}
    rows = [
        {
            "key": "python|letter_minimum|case",
            "peak_rss": 1024,
            "response": {"ok": True, "action": "profile"},
        }
    ]
    if stage == "capture":
        rows = [{"language": "python", "result": {"x": 1}}]
    elif stage == "pilot":
        rows = [
            {
                "key": "python|letter_minimum|case",
                "peak_rss": 1024,
                "first": {"ok": True, "action": "measure"},
            }
        ]
    elif stage == "compare":
        manifest.update(
            methods=["letter_minimum"],
            cases=[{"id": name, "tier": "solve", "options": {}} for name in ("case", "failed")],
            processes=2,
            batches=3,
            baseline_failures=["python|letter_minimum|failed"],
        )
        metadata["source_before"] = {
            variant: {"path": f"/{variant}"} for variant in ("baseline", "candidate")
        }
        metadata["versions"] = [
            {
                "language": "python",
                "process": process,
                "pids": [11 + 10 * process, 12 + 10 * process],
            }
            for process in range(manifest["processes"])
        ]
        rows = [
            {
                "baseline_failure": True,
                "key": "python|letter_minimum|failed",
                "pids": [13, 14],
                "responses": [
                    {"ok": False, "error": resources.WALL_ERROR},
                    {"ok": False, "error": resources.WALL_ERROR},
                ],
            }
        ]
        (tmp_path / "samples.jsonl").write_text(
            "".join(
                json.dumps(
                    {
                        "key": "python|letter_minimum|case",
                        "language": "python",
                        "process": process,
                        "batch": batch,
                        "rss": [1024, 1024],
                        "peak_rss": [1024, 1024],
                    }
                )
                + "\n"
                for process in range(manifest["processes"])
                for batch in range(manifest["batches"])
            )
        )
    records = write_resource_fixture(tmp_path, metadata, rows, stage)
    return manifest, metadata, rows, records


@pytest.mark.parametrize("stage", ["profiles", "capture", "pilot", "compare"])
def test_inventory_and_raw_receipts_are_bound(tmp_path, stage):
    manifest, metadata, rows, records = fixture(tmp_path, stage)
    evidence = resources.validate_resources(tmp_path, manifest, metadata, rows, stage)
    assert evidence["sha256"] == common.digest(records)
    assert evidence["processes"] == sorted(record["guard_pid"] for record in records)
    assert evidence["coverage"] == COVERAGE


@pytest.mark.parametrize(
    "fault",
    [
        "missing_log",
        "missing_raw",
        "extra_raw",
        "missing_inventory",
        "empty_inventory",
        "row_pid",
        "duplicate_log",
        "extra_log",
        "duplicate_inventory",
        "extra_inventory",
        "wrong_pid",
        "wrong_source",
        "wrong_harness",
        "wrong_presolve",
        "wrong_interpreter",
        "wrong_command_hash",
        "raw_changed",
        "coverage",
        "native_cap",
        "sampled_cap",
        "wrong_peak",
        "row_peak",
        "resource_error",
        "negative_exit",
        "wrong_language",
        "receipt_traversal",
        "receipt_alias",
        "bool_schema",
        "missing_embedded",
        "nonfinite",
        "duplicate_json",
    ],
)
def test_invalid_resource_evidence_fails_closed(tmp_path, fault):
    manifest, metadata, rows, records = fixture(tmp_path)
    record = records[0]
    receipt = record["receipt"]
    if fault == "missing_inventory":
        metadata.pop("resource_processes")
    elif fault == "empty_inventory":
        metadata["resource_processes"] = []
    elif fault == "row_pid":
        rows[0]["pid"] += 1
    elif fault == "duplicate_log":
        records.append(copy.deepcopy(record))
    elif fault == "extra_log":
        records.append(dict(copy.deepcopy(record), guard_pid=1234))
    elif fault == "duplicate_inventory":
        metadata["resource_processes"].append(copy.deepcopy(metadata["resource_processes"][0]))
    elif fault == "extra_inventory":
        metadata["resource_processes"].append(
            {"pid": 1234, "language": "python", "source_path": "/source"}
        )
    elif fault == "wrong_pid":
        receipt["guard_pid"] += 1
    elif fault in ("wrong_source", "wrong_harness", "wrong_presolve", "wrong_interpreter"):
        record["command"][
            {"wrong_source": 3, "wrong_harness": 1, "wrong_presolve": 5, "wrong_interpreter": 0}[
                fault
            ]
        ] = "wrong"
        receipt["command_sha256"] = _command_digest(record["command"])
    elif fault == "wrong_command_hash":
        receipt["command_sha256"] = "a" * 64
    elif fault == "coverage":
        receipt["coverage"]["kernel_memory_ceiling"] = True
    elif fault == "native_cap":
        receipt["ru_maxrss"] = receipt["peak_rss_bytes"] = record["peak_rss"] = 129 * 1024**2
    elif fault == "sampled_cap":
        record["sampled_peak_rss"] = record["peak_rss"] = 129 * 1024**2
    elif fault == "wrong_peak":
        record["peak_rss"] = 1
    elif fault == "row_peak":
        rows[0]["peak_rss"] = 1
    elif fault == "resource_error":
        record["resource_error"] = "missing receipt"
    elif fault == "negative_exit":
        receipt.update(wait_status=15, exitstatus=-15)
    elif fault == "wrong_language":
        record["language"] = "js"
    elif fault == "receipt_traversal":
        record["receipt_file"] = "../raw.resource.json"
    elif fault == "receipt_alias":
        original = tmp_path / record["receipt_file"]
        original.rename(tmp_path / "raw")
        original.symlink_to(tmp_path / "raw")
    elif fault == "bool_schema":
        record["schema_version"] = True
    if fault not in ("receipt_traversal", "receipt_alias"):
        (tmp_path / record["receipt_file"]).write_text(json.dumps(receipt))
    if fault == "raw_changed":
        receipt["ru_maxrss"] = receipt["peak_rss_bytes"] = 2048
    elif fault == "missing_embedded":
        record["receipt"] = None
    write_records(tmp_path, records)
    if fault == "missing_log":
        (tmp_path / "resources.jsonl").unlink()
    elif fault == "missing_raw":
        (tmp_path / record["receipt_file"]).unlink()
    elif fault == "extra_raw":
        (tmp_path / "extra.resource.json").write_text(json.dumps(receipt))
    elif fault == "nonfinite":
        (tmp_path / "resources.jsonl").write_text('{"peak_rss":NaN}\n')
    elif fault == "duplicate_json":
        (tmp_path / "resources.jsonl").write_text('{"guard_pid":1,"guard_pid":1}\n')
    with pytest.raises((ValueError, OSError)):
        resources.validate_resources(tmp_path, manifest, metadata, rows, "profiles")


@pytest.mark.parametrize(
    "response",
    [
        {"ok": True},
        {"ok": False, "error": resources.WALL_ERROR},
        {"ok": False, "error": {"kind": "SolverError", "message": "Driver memory limit exceeded"}},
        {"ok": False, "error": {"kind": "ExternalLimit", "message": "memory"}},
        {"ok": False, "error": resources.MEMORY_ERROR},
    ],
)
def test_only_exact_profile_memory_failure_can_exceed_cap(tmp_path, response):
    manifest, metadata, rows, records = fixture(tmp_path)
    rows[0]["response"] = response
    rows[0]["peak_rss"] = records[0]["peak_rss"] = 129 * 1024**2
    receipt = records[0]["receipt"]
    receipt["ru_maxrss"] = receipt["peak_rss_bytes"] = rows[0]["peak_rss"]
    records[0]["resource_error"] = "Driver lifetime memory limit exceeded"
    (tmp_path / records[0]["receipt_file"]).write_text(json.dumps(receipt))
    write_records(tmp_path, records)
    if response == {"ok": False, "error": resources.MEMORY_ERROR}:
        assert resources.validate_resources(tmp_path, manifest, metadata, rows, "profiles")
    else:
        with pytest.raises(ValueError, match="cap|resource error"):
            resources.validate_resources(tmp_path, manifest, metadata, rows, "profiles")


def test_capture_can_share_one_driver_but_profiles_cannot(tmp_path):
    manifest, metadata, rows, _ = fixture(tmp_path, "capture")
    rows.append(copy.deepcopy(rows[0]))
    assert resources.validate_resources(tmp_path, manifest, metadata, rows, "capture")
    profiles = [{"pid": rows[0]["pid"], "key": "python|method|case"}] * 2
    with pytest.raises(ValueError, match="reused"):
        resources.validate_resources(tmp_path, manifest, metadata, profiles, "profiles")


def test_timing_and_excluded_processes_cannot_share_receipts(tmp_path):
    manifest, metadata, rows, _ = fixture(tmp_path, "compare")
    rows[0]["pids"][0] = metadata["versions"][0]["pids"][0]
    with pytest.raises(ValueError, match="reused"):
        resources.validate_resources(tmp_path, manifest, metadata, rows, "compare")


def comparison_samples(directory):
    return [json.loads(line) for line in (directory / "samples.jsonl").read_text().splitlines()]


@pytest.mark.parametrize("field", ["rss", "peak_rss"])
@pytest.mark.parametrize("process", [0, 1])
@pytest.mark.parametrize("variant", [0, 1])
def test_comparison_samples_are_bound_to_each_paired_pid(tmp_path, field, process, variant):
    manifest, metadata, rows, records = fixture(tmp_path, "compare")
    samples = comparison_samples(tmp_path)
    pid = metadata["versions"][process]["pids"][variant]
    # Other processes and native receipts have higher peaks. They cannot cover
    # a sample above this PID's final sampled peak, even below the memory cap.
    for record in records:
        receipt = record["receipt"]
        receipt["ru_maxrss"] = receipt["peak_rss_bytes"] = record["peak_rss"] = 4096
        record["sampled_peak_rss"] = 1024 if record["guard_pid"] == pid else 4096
        (tmp_path / record["receipt_file"]).write_text(json.dumps(receipt))
    write_records(tmp_path, records)
    sample = next(sample for sample in samples if sample["process"] == process)
    sample[field][variant] = 2048
    # Version row order has no meaning. The process field owns the PID pair.
    metadata["versions"].reverse()
    with pytest.raises(ValueError, match=f"sample {field} exceeds process {pid} sampled peak"):
        resources.validate_resources(tmp_path, manifest, metadata, rows, "compare", samples=samples)


def test_comparison_accepts_receipt_bounds_independent_of_row_order(tmp_path):
    manifest, metadata, rows, records = fixture(tmp_path, "compare")
    samples = comparison_samples(tmp_path)
    for record in records:
        peak = 1024 * record["guard_pid"]
        record["sampled_peak_rss"] = record["peak_rss"] = peak
        record["receipt"]["ru_maxrss"] = record["receipt"]["peak_rss_bytes"] = peak
        (tmp_path / record["receipt_file"]).write_text(json.dumps(record["receipt"]))
    write_records(tmp_path, records)
    for sample in samples:
        sample["rss"] = sample["peak_rss"] = [
            pid * 1024 for pid in metadata["versions"][sample["process"]]["pids"]
        ]
    metadata["versions"].reverse()
    assert resources.validate_resources(
        tmp_path, manifest, metadata, rows, "compare", samples=samples[::-1]
    )["sha256"] == common.digest(records)


def test_comparison_separates_languages_with_the_same_process_index(tmp_path):
    manifest, metadata, rows, _ = fixture(tmp_path, "compare")
    manifest["languages"].append("js")
    manifest["presolve"]["js"] = "on"
    manifest["baseline_failures"].append("js|letter_minimum|failed")
    metadata["versions"].extend(
        {"language": "js", "process": process, "pids": [31 + 10 * process, 32 + 10 * process]}
        for process in range(manifest["processes"])
    )
    samples = comparison_samples(tmp_path)
    samples += [
        dict(sample, key=sample["key"].replace("python|", "js|"), language="js")
        for sample in samples
    ]
    write_resource_fixture(tmp_path, metadata, rows, "compare")
    assert resources.validate_resources(
        tmp_path, manifest, metadata, rows, "compare", samples=samples
    )
    samples[-1]["peak_rss"] = [1024, 2048]
    with pytest.raises(ValueError, match="sample peak_rss exceeds process 42 sampled peak"):
        resources.validate_resources(tmp_path, manifest, metadata, rows, "compare", samples=samples)


def test_comparison_requires_receipts_for_every_manifest_process_pair(tmp_path):
    manifest, metadata, rows, records = fixture(tmp_path, "compare")
    removed = metadata["versions"].pop()["pids"]
    metadata["resource_processes"] = [
        entry for entry in metadata["resource_processes"] if entry["pid"] not in removed
    ]
    for record in records:
        if record["guard_pid"] in removed:
            (tmp_path / record["receipt_file"]).unlink()
    write_records(tmp_path, [record for record in records if record["guard_pid"] not in removed])
    with pytest.raises(ValueError, match="incomplete timing process inventory"):
        resources.validate_resources(tmp_path, manifest, metadata, rows, "compare")


@pytest.mark.parametrize(
    "fault",
    [
        "missing",
        "duplicate",
        "extra",
        "batch",
        "bool_batch",
        "language",
        "rss",
        "peak_rss",
        "current_gt_peak",
    ],
)
def test_comparison_requires_valid_complete_samples(tmp_path, fault):
    manifest, metadata, rows, _ = fixture(tmp_path, "compare")
    samples = comparison_samples(tmp_path)
    if fault == "missing":
        samples.pop()
    elif fault == "duplicate":
        samples.append(copy.deepcopy(samples[0]))
    elif fault == "extra":
        samples[0]["key"] = "python|letter_minimum|extra"
    elif fault == "batch":
        samples[0]["batch"] = 3
    elif fault == "bool_batch":
        samples[0]["batch"] = False
    elif fault == "language":
        samples[0]["language"] = "js"
    elif fault in ("rss", "peak_rss"):
        samples[0].pop(fault)
    else:
        samples[0]["peak_rss"][0] = 512
    with pytest.raises(ValueError):
        resources.validate_resources(tmp_path, manifest, metadata, rows, "compare", samples=samples)


@pytest.mark.parametrize(
    "fault", ["missing_process", "duplicate_process", "bool_process", "process_range"]
)
def test_comparison_requires_complete_version_process_pairs(tmp_path, fault):
    manifest, metadata, rows, _ = fixture(tmp_path, "compare")
    if fault == "missing_process":
        metadata["versions"][0].pop("process")
    elif fault == "duplicate_process":
        metadata["versions"][0]["process"] = 1
    elif fault == "bool_process":
        metadata["versions"][0]["process"] = False
    else:
        metadata["versions"][0]["process"] = 2
    with pytest.raises(ValueError, match="timing process identity"):
        resources.validate_resources(tmp_path, manifest, metadata, rows, "compare")


@pytest.mark.parametrize("fault", ["missing_file", "missing_sample", "exceeded_peak"])
def test_comparison_loads_and_checks_samples_when_caller_omits_them(tmp_path, fault):
    manifest, metadata, rows, _ = fixture(tmp_path, "compare")
    path = tmp_path / "samples.jsonl"
    samples = comparison_samples(tmp_path)
    if fault == "missing_file":
        path.unlink()
    else:
        if fault == "missing_sample":
            samples.pop()
        else:
            samples[0]["rss"] = samples[0]["peak_rss"] = [2048, 2048]
        path.write_text("".join(json.dumps(sample) + "\n" for sample in samples))
    with pytest.raises((ValueError, OSError)):
        resources.validate_resources(tmp_path, manifest, metadata, rows, "compare")


@pytest.mark.parametrize("failure", ["memory", "wall"])
def test_profile_collector_records_native_resource_failure_after_close(
    tmp_path, monkeypatch, failure
):
    checkout = tmp_path / "checkout"
    (checkout / "benchmarks").mkdir(parents=True)
    source = """import json,mmap,sys
for line in sys.stdin:
    action = json.loads(line)['action']
    if action != 'version':
        region=mmap.mmap(-1,64*1024*1024)
        for offset in range(0,len(region),mmap.PAGESIZE): region[offset]=1
        region.close()
    print(json.dumps({'ok':True,'action':action}),flush=True)
"""
    if failure == "wall":
        source = source.replace(
            "region=mmap.mmap(-1,64*1024*1024)",
            "import time;time.sleep(30)\n        region=mmap.mmap(-1,1)",
        )
    (checkout / "benchmarks/python_driver.py").write_text(source)
    case = {
        "id": "bounded/case",
        "tier": "preprocess",
        "wall_seconds": 0.1 if failure == "wall" else 2,
        "options": {"method": "letter_minimum"},
    }
    manifest = {
        "languages": ["python"],
        "presolve": {"python": "on"},
        "memory_limit_mb": 48,
        "warmup_batches": 0,
    }
    binding = {"path": str(checkout)}
    monkeypatch.setattr(common, "ROOT", checkout)
    monkeypatch.setattr(common.Driver, "_check_memory", lambda _: None)
    monkeypatch.setattr(run, "load_manifest", lambda _: manifest)
    monkeypatch.setattr(run, "provenance", lambda _: {"harness": binding, "source": binding})
    monkeypatch.setattr(run, "source_binding", lambda *_, **__: binding)
    monkeypatch.setattr(run, "jobs", lambda *_, **__: [case])
    output = tmp_path / "evidence"
    run.profiles(
        SimpleNamespace(manifest="unused", output=output, repo=checkout, include_opt_in=False)
    )
    metadata = json.loads((output / "metadata.json").read_text())
    rows = [json.loads(line) for line in (output / "profiles.jsonl").read_text().splitlines()]
    assert rows[0]["response"] == {
        "ok": False,
        "action": "preprocess",
        "error": resources.MEMORY_ERROR if failure == "memory" else resources.WALL_ERROR,
    }
    assert (rows[0]["peak_rss"] > 48 * 1024**2) == (failure == "memory")
    assert resources.validate_resources(output, manifest, metadata, rows, "profiles")


def test_context_records_receipt_and_keeps_original_body_error(tmp_path, monkeypatch):
    checkout = tmp_path / "checkout"
    (checkout / "benchmarks").mkdir(parents=True)
    (checkout / "benchmarks/python_driver.py").write_text("import sys;sys.stdin.buffer.read()")
    monkeypatch.setattr(common, "ROOT", checkout)
    manifest = {"presolve": {"python": "on"}, "memory_limit_mb": 128}
    metadata = {}
    with (
        pytest.raises(RuntimeError, match="original collection error"),
        run.driver("python", checkout, manifest, tmp_path, "failed", metadata=metadata),
    ):
        raise RuntimeError("original collection error")
    record = json.loads((tmp_path / "resources.jsonl").read_text())
    assert record["receipt"]["exitstatus"] == 0
    assert record["guard_pid"] == metadata["resource_processes"][0]["pid"]


@pytest.mark.parametrize("missing", [False, True])
def test_freeze_requires_baseline_profile_capture_and_calibration_receipts(
    tmp_path, monkeypatch, missing
):
    from test_gates import make_evidence, mock_freeze_code

    mock_freeze_code(monkeypatch)

    _, directories = make_evidence(tmp_path)
    manifest = json.loads((directories["calibration"] / "manifest.json").read_text())
    monkeypatch.setattr(run, "load_manifest", lambda _: copy.deepcopy(manifest))
    monkeypatch.setattr(
        run, "analyze", lambda m, *_, **__: {"pass": True, "manifest_sha256": common.digest(m)}
    )
    args = SimpleNamespace(
        manifest="unused",
        profiles=directories["baseline-profiles"],
        capture=directories["baseline-capture"],
        calibration=directories["calibration"],
        pilot=directories["pilot"],
        output=tmp_path / "frozen.json",
    )
    if missing:
        next(directories["calibration"].glob("*.resource.json")).unlink()
        with pytest.raises(ValueError, match="receipt"):
            run.freeze(args)
        assert not args.output.exists()
    else:
        run.freeze(args)
        frozen = json.loads(args.output.read_text())
        for key in (
            "profile_resource_sha256",
            "baseline_capture_resource_sha256",
            "calibration_resource_sha256",
        ):
            assert len(frozen[key]) == 64
