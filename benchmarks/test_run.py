"""Reject invalid measurement designs before launching a driver."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import run
from cases import frozen_manifest, job_key, jobs


@pytest.mark.parametrize(
    "field,value",
    [
        ("processes", 7),
        ("processes", 8.5),
        ("warmup_batches", 2),
        ("batches", 8),
        ("bootstrap_resamples", 9999),
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
    baseline = {
        "path": "/baseline",
        "head": "a" * 40,
        "tree": "b" * 40,
        "status": "",
        "build_files": {},
        "lock_files": {},
    }
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


def test_excluded_timeout_uses_separate_processes(tmp_path, monkeypatch):
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
    monkeypatch.setattr(run, "source_binding", lambda *_, **__: binding)
    monkeypatch.setattr(run, "provenance", lambda _: {"machine": {"test": True}})
    monkeypatch.setattr(run, "analyze", lambda *_: {"pass": True, "reasons": []})
    processes = []

    class FakeDriver:
        def __init__(self, *_):
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
    timed = [p for p in processes if "measure" in p.actions]
    excluded = [p for p in processes if "capture" in p.actions]
    assert len(timed) == 16 and len(excluded) == 2
    assert all("capture" not in p.actions for p in timed)
    rows = [json.loads(line) for line in (args.output / "results.jsonl").read_text().splitlines()]
    failures = [row for row in rows if row.get("baseline_failure")]
    assert len(failures) == 1
    assert all(
        not r["ok"] and r["error"]["kind"] == "ExternalLimit" for r in failures[0]["responses"]
    )
