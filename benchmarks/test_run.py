"""Reject invalid measurement designs before launching a driver."""

import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import run
from cases import frozen_manifest, job_key, jobs
from test_gates import preprocess_response, solver_observations
from test_profile_settings import sample as settings_sample
from test_resource_evidence import write_resource_fixture


def javascript_source():
    """Explicit synthetic proof for tests that must not compile or time a runtime."""
    return {
        "path": "/baseline",
        "head": "a" * 40,
        "tree": "b" * 40,
        "status": "",
        "build_files": {"js/dist/index.js": "c" * 64},
        "lock_files": {},
        "build_verified": True,
        "dependency_files": {
            "highs/package.json": "1" * 64,
            "highs/build/highs.mjs": "2" * 64,
            "highs/build/highs.wasm": "3" * 64,
        },
        "compiler_files": {"typescript/bin/tsc": "4" * 64, "typescript/lib/tsc.js": "5" * 64},
    }


@pytest.mark.parametrize(
    "field,value",
    [
        ("processes", 7),
        ("processes", 17),
        ("processes", 8.5),
        ("warmup_batches", 2),
        ("batches", 8),
        ("batches", 37),
        ("bootstrap_resamples", 9999),
        ("bootstrap_seed", True),
        ("order_seed", -1),
        ("memory_limit_mb", float("inf")),
        ("memory_limit_mb", float("nan")),
        ("memory_limit_mb", True),
        ("memory_growth_tolerance_mb", False),
        ("memory_growth_tolerance_mb", -1),
        ("batch_target_ns", 0),
    ],
)
def test_invalid_design(tmp_path, field, value):
    manifest = frozen_manifest(Path(__file__).resolve().parents[1])
    manifest[field] = value
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        run.load_manifest(path)


def test_zero_memory_growth_allowance_is_a_valid_design(tmp_path):
    manifest = frozen_manifest(Path(__file__).resolve().parents[1])
    manifest["memory_growth_tolerance_mb"] = 0
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest))
    assert run.load_manifest(path)["memory_growth_tolerance_mb"] == 0


@pytest.mark.parametrize(
    "fault", ["r_presolve", "wall", "boolean_wall", "method", "language", "case"]
)
def test_invalid_inputs(tmp_path, fault):
    manifest = frozen_manifest(Path(__file__).resolve().parents[1])
    if fault == "r_presolve":
        manifest["presolve"]["r"] = "on"
    elif fault == "wall":
        manifest["cases"][0]["wall_seconds"] = float("inf")
    elif fault == "boolean_wall":
        manifest["cases"][0]["wall_seconds"] = True
    elif fault == "method":
        manifest["methods"] = ["letter_minimum"]
    elif fault == "language":
        manifest["languages"].append("r")
    else:
        manifest["cases"].append(manifest["cases"][0])
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        run.load_manifest(path)


@pytest.mark.parametrize("kind", ["calibration", "candidate"])
def test_source_rejection_precedes_driver_start(tmp_path, monkeypatch, kind):
    manifest = frozen_manifest(Path(__file__).resolve().parents[1])
    baseline = javascript_source()
    manifest["pilot_source"] = baseline
    manifest["baseline_source"] = dict(baseline, head="c" * 40)
    manifest["frozen"] = kind == "candidate"
    manifest["iterations"] = {
        job_key(lang, c): 1 for lang in manifest["languages"] for c in jobs(manifest)
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest))
    monkeypatch.setattr(
        run,
        "source_binding",
        lambda repo, **_: baseline if repo == "/baseline" else dict(baseline, head="d" * 40),
    )

    def forbidden(*_, **__):
        pytest.fail("A driver started before source validation")

    monkeypatch.setattr(run, "driver", forbidden)
    args = SimpleNamespace(
        manifest=path,
        output=tmp_path / "output",
        kind=kind,
        baseline="/baseline",
        candidate="/candidate",
        run_id="rejected",
    )
    with pytest.raises(ValueError, match="A/A|Baseline differs"):
        run.compare(args)


@pytest.mark.parametrize("kind", ["candidate", "calibration"])
@pytest.mark.parametrize(
    "fault",
    [
        "missing_baseline_proof",
        "missing_candidate_proof",
        "missing_bound_proof",
        "solver_bytes",
        "compiler_bytes",
    ],
)
def test_javascript_proof_rejection_precedes_driver_start(tmp_path, monkeypatch, kind, fault):
    manifest = frozen_manifest(Path(__file__).resolve().parents[1])
    manifest["languages"] = ["js"]
    baseline = javascript_source()
    candidate = copy.deepcopy(baseline)
    bound = copy.deepcopy(baseline)
    if fault == "missing_baseline_proof":
        baseline.pop("build_verified")
    elif fault == "missing_candidate_proof":
        candidate.pop("build_verified")
    elif fault == "missing_bound_proof":
        bound.pop("build_verified")
    elif fault == "solver_bytes":
        candidate["dependency_files"]["highs/build/highs.wasm"] = "9" * 64
    else:
        candidate["compiler_files"]["typescript/lib/tsc.js"] = "9" * 64
    manifest["baseline_source"] = manifest["pilot_source"] = bound
    manifest["frozen"] = kind == "candidate"
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest))
    monkeypatch.setattr(
        run, "source_binding", lambda repo, **_: baseline if repo == "/baseline" else candidate
    )

    def forbidden(*_, **__):
        pytest.fail("A driver started before JavaScript proof validation")

    monkeypatch.setattr(run, "driver", forbidden)
    with pytest.raises(ValueError, match="proof|bytes differ|Baseline differs"):
        run.compare(
            SimpleNamespace(
                manifest=path,
                output=tmp_path / "output",
                kind=kind,
                baseline="/baseline",
                candidate="/candidate",
                run_id="proof",
            )
        )


@pytest.mark.parametrize(
    "fault", ["missing", "missing_proof", "solver_bytes", "compiler_bytes", "source"]
)
def test_freeze_rechecks_pilot_binding(tmp_path, monkeypatch, fault):
    manifest = frozen_manifest(Path(__file__).resolve().parents[1])
    manifest["languages"] = ["js"]
    baseline = javascript_source()
    manifest["pilot_source"] = copy.deepcopy(baseline)
    if fault == "missing":
        manifest.pop("pilot_source")
    elif fault == "missing_proof":
        manifest["pilot_source"].pop("build_verified")
    elif fault == "solver_bytes":
        manifest["pilot_source"]["dependency_files"]["highs/build/highs.wasm"] = "9" * 64
    elif fault == "compiler_bytes":
        manifest["pilot_source"]["compiler_files"]["typescript/lib/tsc.js"] = "9" * 64
    else:
        manifest["pilot_source"]["head"] = "9" * 40
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest))
    calibration = tmp_path / "calibration"
    calibration.mkdir()
    run.save(calibration / "manifest.json", manifest)
    (calibration / "metadata.json").write_text(
        json.dumps({"kind": "calibration", "source_before": {"baseline": baseline}})
    )
    (calibration / "samples.jsonl").write_text("")
    # Isolate freeze's own check from analysis's independent pilot check.
    monkeypatch.setattr(
        run, "analyze", lambda *_: {"pass": True, "manifest_sha256": run.digest(manifest)}
    )
    with pytest.raises(ValueError, match="Pilot source"):
        run.freeze(SimpleNamespace(manifest=path, calibration=calibration))


@pytest.mark.parametrize("small_sigma", [False, True])
@pytest.mark.parametrize("preprocess_failure", [None, "external wall", "memory"])
@pytest.mark.parametrize("native_fault", [None, "gap", "missing", "zero"])
def test_freeze_records_calibration_harness_with_equal_source_at_other_path(
    tmp_path, monkeypatch, small_sigma, preprocess_failure, native_fault
):
    manifest = frozen_manifest(Path(__file__).resolve().parents[1])
    manifest["languages"] = ["js"]
    manifest["cases"] = [
        case
        for split in ("development", "validation")
        for case in [c for c in manifest["cases"] if c["split"] == split and c["tier"] == "solve"][
            :5
        ]
    ] + [c for c in manifest["cases"] if c["tier"] == "preprocess"]
    baseline = javascript_source()
    manifest["pilot_source"] = dict(copy.deepcopy(baseline), path="/pilot-checkout")
    settings = settings_sample("js")[0]
    manifest["baseline_versions"] = {
        "js": {
            "language": "javascript",
            "runtime": "synthetic",
            "settings": settings,
        }
    }
    harness = dict(copy.deepcopy(baseline), path="/harness", head="e" * 40)
    calibration = tmp_path / "calibration"
    run.save(calibration / "manifest.json", manifest)
    run.save(
        calibration / "metadata.json",
        {
            "kind": "calibration",
            "source_before": {"baseline": baseline, "candidate": baseline},
            "versions": [{"language": "js", "pids": [1, 2]}],
            "harness": harness,
            "harness_after": harness,
        },
    )
    (calibration / "samples.jsonl").write_text("")
    (calibration / "results.jsonl").write_text("")
    calibration_metadata = run.read(calibration / "metadata.json")
    write_resource_fixture(calibration, calibration_metadata, [], "compare")
    run.save(calibration / "metadata.json", calibration_metadata)
    profiles, capture = tmp_path / "profiles", tmp_path / "capture"
    profile_rows = [
        {
            "key": job_key("js", case),
            "case": case,
            "peak_rss": 1024,
            "response": {
                "ok": True,
                "action": "profile",
                "metrics": {
                    "solver_total_ns": 40,
                    "essential_cover": True,
                    "solve_count": 1,
                    "solver_settings": solver_observations("js", settings, 1),
                },
                "phases_ns": {"total": 100},
            },
        }
        for case in jobs(manifest)
    ]
    if small_sigma:
        for split in ("development", "validation"):
            row = next(
                row
                for row in profile_rows
                if row["case"]["split"] == split
                and row["case"]["options"]["method"] == "assignment_minimum"
            )
            row["response"]["metrics"]["solver_total_ns"] = 24
    declared_failures = {}
    for case in jobs(manifest, tiers=("preprocess",)):
        response = preprocess_response(case, "js", settings)
        peak = 1024
        if preprocess_failure and case["id"].endswith("multipartite-8x3"):
            response = dict(
                ok=False,
                action="preprocess",
                error={
                    "kind": "ExternalLimit",
                    "message": f"Driver {preprocess_failure} limit exceeded",
                },
            )
            declared_failures[job_key("js", case)] = (
                "external_memory_limit"
                if preprocess_failure == "memory"
                else "external_wall_timeout"
            )
            if preprocess_failure == "memory":
                peak = (manifest["memory_limit_mb"] + 1) * 1024**2
        profile_rows.append(
            dict(key=job_key("js", case), case=case, response=response, peak_rss=peak)
        )
    capture_rows = [
        {"language": "js", "id": case["id"], "method": case["options"]["method"], "mismatch": []}
        for case in jobs(manifest)
    ]
    metadata = {
        "complete": True,
        "source": baseline,
        "source_after": baseline,
        "input_sha256": run.input_digest(manifest),
        "versions": manifest["baseline_versions"],
        "failures": [],
        "expected_keys": capture_rows,
        "harness": harness,
        "harness_after": harness,
    }
    if native_fault:
        metrics = profile_rows[0]["response"]["metrics"]
        if native_fault == "gap":
            metrics["solver_settings"]["records"][0]["values"]["mip_rel_gap"] = 0.1
        elif native_fault == "missing":
            metrics.pop("solver_settings")
        else:
            metrics.update(solve_count=0, solver_settings={"available": False, "records": []})
    for directory, name, rows in (
        (profiles, "profiles.jsonl", profile_rows),
        (capture, "vectors.jsonl", capture_rows),
    ):
        stage_metadata = copy.deepcopy(metadata)
        write_resource_fixture(
            directory, stage_metadata, rows, "profiles" if directory == profiles else "capture"
        )
        run.save(directory / "metadata.json", stage_metadata)
        (directory / name).write_text("".join(json.dumps(row) + "\n" for row in rows))
    path, output = tmp_path / "manifest.json", tmp_path / "frozen.json"
    run.save(path, manifest)
    monkeypatch.setattr(
        run, "analyze", lambda *_: {"pass": True, "manifest_sha256": run.digest(manifest)}
    )
    args = SimpleNamespace(
        manifest=path,
        calibration=calibration,
        profiles=profiles,
        capture=capture,
        output=output,
    )
    if native_fault:
        with pytest.raises(ValueError, match="solver settings"):
            run.freeze(args)
        assert not output.exists()
        return
    run.freeze(args)
    frozen = run.read(output)
    assert frozen["frozen"] is True
    assert frozen["calibration_harness"] == harness
    assert frozen["baseline_source"] == baseline
    assert frozen["calibration_manifest_sha256"] == run.digest(manifest)
    assert frozen["calibration_samples_sha256"] == run.digest([])
    assert frozen["baseline_preprocess_failures"] == declared_failures
    assert set(frozen["gain_targets"]) == (
        {"js|letter_minimum"} if small_sigma else {"js|letter_minimum", "js|assignment_minimum"}
    )


@pytest.mark.parametrize("harness_changed", [False, True])
def test_excluded_timeout_uses_separate_processes(tmp_path, monkeypatch, harness_changed):
    manifest = frozen_manifest(Path(__file__).resolve().parents[1])
    manifest["languages"] = ["python"]
    manifest["cases"] = manifest["cases"][:1]
    cases = list(jobs(manifest))
    manifest["baseline_failures"] = [job_key("python", cases[1])]
    manifest["iterations"] = {job_key("python", cases[0]): 1}
    binding = {
        "path": "/baseline",
        "head": "a" * 40,
        "tree": "b" * 40,
        "status": "",
        "build_files": {},
        "lock_files": {},
    }
    manifest["pilot_source"] = binding
    version = {"ok": True, "action": "version", "language": "python", "runtime": "3.13"}
    manifest["baseline_versions"] = {"python": version}
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest))
    root_reads = 0

    def recorded_source(repo, **_):
        nonlocal root_reads
        if repo == run.ROOT:
            root_reads += 1
            if harness_changed and root_reads > 1:
                return dict(binding, head="e" * 40)
        return binding

    monkeypatch.setattr(run, "source_binding", recorded_source)
    monkeypatch.setattr(run, "provenance", lambda _: {"machine": {"test": True}})
    monkeypatch.setattr(run, "analyze", lambda *_: {"pass": True, "reasons": []})
    processes = []

    class FakeDriver:
        def __init__(self, *_, **__):
            self.process = SimpleNamespace(pid=len(processes) + 1)
            self.actions = []
            self.rss = self.peak_rss = 1024
            processes.append(self)

        def request(self, request, _):
            self.actions.append(request["action"])
            if request["action"] == "version":
                return version
            if request["action"] == "capture":
                raise run.DriverError("Driver external wall limit exceeded")
            return {
                "ok": True,
                "action": "measure",
                "elapsed_ns": 100,
                "result": {"id": request["case"]["id"]},
            }

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

    monkeypatch.setattr(run, "driver", FakeDriver)
    args = SimpleNamespace(
        manifest=path,
        output=tmp_path / "output",
        kind="calibration",
        baseline="/baseline",
        candidate="/baseline",
        run_id="excluded",
    )
    run.compare(args)
    metadata = run.read(args.output / "metadata.json")
    assert metadata["complete"] is not harness_changed
    assert (metadata["harness"] == metadata["harness_after"]) is not harness_changed
    assert run.read(args.output / "manifest.json") == manifest
    timed = [p for p in processes if "measure" in p.actions]
    excluded = [p for p in processes if "capture" in p.actions]
    assert len(timed) == 16 and len(excluded) == 2
    samples = [
        json.loads(line) for line in (args.output / "samples.jsonl").read_text().splitlines()
    ]
    assert sum(row["order"][0] == 0 for row in samples) == len(samples) // 2
    for process in range(manifest["processes"]):
        orders = [row["order"] for row in samples if row["process"] == process]
        assert all(sorted(order) == [0, 1] for order in orders)
        assert abs(sum(order[0] == 0 for order in orders) - len(orders) / 2) <= 0.5
    assert all("capture" not in p.actions for p in timed)
    rows = [json.loads(line) for line in (args.output / "results.jsonl").read_text().splitlines()]
    failures = [row for row in rows if row.get("baseline_failure")]
    assert len(failures) == 1
    assert all(
        not r["ok"] and r["error"]["kind"] == "ExternalLimit" for r in failures[0]["responses"]
    )


def setup_collection(tmp_path, monkeypatch, *, changed=False, warmup_failure=False):
    manifest = frozen_manifest(Path(__file__).resolve().parents[1])
    manifest["languages"] = ["python"]
    manifest["cases"] = manifest["cases"][:1]
    path = tmp_path / "manifest.json"
    run.save(path, manifest)
    repo = tmp_path / "source"
    for name in ("reduce", "reduce_letter_minimum", "reduce_weighted"):
        run.save(repo / "conformance" / "fixtures" / f"{name}.json", {"cases": []})
    binding = javascript_source()
    monkeypatch.setattr(run, "provenance", lambda *_: {"source": binding, "harness": binding})
    monkeypatch.setattr(
        run,
        "source_binding",
        lambda target, **_: (
            dict(binding, head="e" * 40) if changed and target == run.ROOT else binding
        ),
    )
    requests = []

    class FakeDriver:
        peak_rss = 1024
        resource_error = None
        process = SimpleNamespace(pid=100)

        def request(self, request, seconds):
            requests.append((copy.deepcopy(request), seconds))
            action = request["action"]
            if action == "version":
                return {"ok": True, "action": action, "language": "python", "runtime": "synthetic"}
            if action == "profile" and warmup_failure:
                # Preserve the reported error while normalizing the phase's action.
                return {
                    "ok": False,
                    "action": "measure",
                    "error": {"kind": "SolverError", "message": "warmup failed"},
                }
            return {
                "ok": True,
                "action": action,
                "elapsed_ns": 100,
                "result": {"stats": {"objective": 1}},
                "canonical": {"selected": [1], "objective": 1},
            }

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

    monkeypatch.setattr(run, "driver", lambda *_, **__: FakeDriver())
    return (
        SimpleNamespace(manifest=path, repo=repo, output=tmp_path / "output", include_opt_in=False),
        manifest,
        requests,
    )


@pytest.mark.parametrize("stage", ["profiles", "captures", "pilot"])
def test_collection_cannot_complete_after_harness_mutation(tmp_path, monkeypatch, stage):
    args, _, _ = setup_collection(tmp_path, monkeypatch, changed=True)
    if stage == "pilot":
        with pytest.raises(ValueError, match="harness changed"):
            run.pilot(args)
        assert not (args.output / "manifest.json").exists()
    else:
        getattr(run, stage)(args)
    metadata = run.read(args.output / "metadata.json")
    assert metadata["complete"] is False
    assert metadata["source"] == metadata["source_after"]
    assert metadata["harness"] != metadata["harness_after"]


@pytest.mark.parametrize("failure", [False, True])
def test_profile_warmups_use_the_profile_path_and_preserve_failure(tmp_path, monkeypatch, failure):
    args, manifest, requests = setup_collection(tmp_path, monkeypatch, warmup_failure=failure)
    run.profiles(args)
    calls = [(request, seconds) for request, seconds in requests if request["action"] != "version"]
    assert all(request["action"] == "profile" for request, _ in calls)
    assert all(seconds == manifest["cases"][0]["wall_seconds"] for _, seconds in calls)
    assert len(calls) == len(manifest["methods"]) * (
        1 if failure else manifest["warmup_batches"] + 1
    )
    metadata = run.read(args.output / "metadata.json")
    assert metadata["warmup_profile_calls"] == manifest["warmup_batches"]
    rows = [json.loads(line) for line in (args.output / "profiles.jsonl").read_text().splitlines()]
    if failure:
        assert all(
            row["response"]
            == {
                "ok": False,
                "action": "profile",
                "failed_phase": "profile_warmup",
                "error": {"kind": "SolverError", "message": "warmup failed"},
            }
            for row in rows
        )
    else:
        assert all(row["response"]["ok"] for row in rows)


def test_audit_cli_requires_calibration(monkeypatch, capsys):
    monkeypatch.setattr(
        "sys.argv",
        [
            "run.py",
            "audit",
            "--manifest",
            "manifest.json",
            "--baseline-capture",
            "baseline-capture",
            "--candidate-capture",
            "candidate-capture",
            "--baseline-profiles",
            "baseline-profiles",
            "--candidate-profiles",
            "candidate-profiles",
            "--output",
            "audit.json",
            "--runs",
            "run-1",
            "run-2",
        ],
    )
    with pytest.raises(SystemExit) as error:
        run.main()
    assert error.value.code == 2
    assert "--calibration" in capsys.readouterr().err


@pytest.mark.parametrize("unsafe", ["checkout", "symlink", "existing"])
def test_artifact_outputs_preserve_source_and_existing_evidence(tmp_path, monkeypatch, unsafe):
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    monkeypatch.setattr(run, "ROOT", checkout)
    output = tmp_path / "result.json"
    if unsafe == "checkout":
        output = checkout / "result.json"
    elif unsafe == "symlink":
        alias = tmp_path / "alias"
        alias.symlink_to(checkout, target_is_directory=True)
        output = alias / "result.json"
    else:
        output.write_text("prior evidence")
    with pytest.raises((ValueError, FileExistsError)):
        run.save_artifact(output, {"new": True})
    if unsafe == "existing":
        assert output.read_text() == "prior evidence"
    else:
        assert not output.exists()


def test_new_artifact_output_is_valid_json(tmp_path):
    output = tmp_path / "nested" / "new.json"
    run.save_artifact(output, {"pass": False, "reasons": ["inconclusive"]})
    assert run.read(output) == {"pass": False, "reasons": ["inconclusive"]}
