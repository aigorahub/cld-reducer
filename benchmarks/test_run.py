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


@pytest.mark.parametrize("fault", ["r_presolve", "wall", "method", "language", "case"])
def test_invalid_inputs(tmp_path, fault):
    manifest = frozen_manifest(Path(__file__).resolve().parents[1])
    if fault == "r_presolve":
        manifest["presolve"]["r"] = "on"
    elif fault == "wall":
        manifest["cases"][0]["wall_seconds"] = float("inf")
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
