"""Bind executing acceptance code to freeze before timing or a final judgment."""

import copy
import hashlib
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import gates
import pytest
import run
from common import source_binding


def git(repo, *args):
    return subprocess.check_output(
        ["git", "-C", str(repo), *args], stderr=subprocess.DEVNULL, text=True
    ).strip()


@pytest.fixture
def code_repo(tmp_path):
    repo = tmp_path / "harness"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.name", "Test")
    git(repo, "config", "user.email", "test@example.invalid")
    files = (
        gates.MEASUREMENT_FILES
        + gates.LIFECYCLE_FILES
        + gates.VALIDATION_FILES
        + (gates.DRIVERS["python"],)
    )
    for name in files:
        path = repo / name
        path.parent.mkdir(exist_ok=True)
        path.write_text("# Frozen " + name + "\n")
    (repo / "benchmarks/analysis.py").write_text("if kind == 'candidate':\n    gain_limit = 0.90\n")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "Freeze acceptance code")
    before = source_binding(repo)
    hashes = gates.acceptance_hashes(before, ["python"])
    return repo, before, hashes


def revise(repo, change):
    if change == "dirty":
        (repo / "benchmarks/cases.py").write_text("# Uncommitted case order\n")
        return
    path = repo / change
    path.parent.mkdir(parents=True, exist_ok=True)
    if change == "benchmarks/analysis.py":
        # The A/A branch remains unchanged. Candidate analysis must still bind.
        path.write_text("if kind == 'candidate':\n    gain_limit = 0.99\n")
    else:
        path.write_text("# Changed content\n")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "Change one file")


@pytest.mark.parametrize(
    "name",
    [
        "benchmarks/cases.py",
        "benchmarks/analysis.py",
        "benchmarks/warmup_policy.py",
        *gates.VALIDATION_FILES,
    ],
)
def test_acceptance_inventory_reads_real_git_blobs(code_repo, name):
    repo, before, hashes = code_repo
    assert (
        hashes[name]
        == hashlib.sha256(
            git(repo, "show", f"{before['head']}:{name}").encode() + b"\n"
        ).hexdigest()
    )
    revise(repo, name)
    after = source_binding(repo)
    changed = gates.acceptance_hashes(after, ["python"])
    assert {key for key in hashes if hashes[key] != changed[key]} == {name}
    # Metadata fields cannot replace bytes in the referenced Git objects.
    after["acceptance_code_sha256"] = hashes
    assert gates.acceptance_hashes(after, ["python"]) == changed


@pytest.mark.parametrize(
    "change",
    [
        "benchmarks/run.py",
        "benchmarks/cases.py",
        "benchmarks/analysis.py",
        "benchmarks/profile_outcomes.py",
        "dirty",
        "README.md",
        "python/runtime.py",
        "tests/test_result.py",
    ],
)
@pytest.mark.parametrize("stage", ["freeze", "candidate", "audit", "captures", "profiles"])
def test_executing_code_is_checked_before_driver_or_judgment(
    tmp_path, monkeypatch, code_repo, change, stage
):
    repo, before, hashes = code_repo
    revise(repo, change)
    unchanged = not change.startswith("benchmarks/") and change != "dirty"
    manifest = {
        "frozen": stage != "freeze",
        "languages": ["python"],
        "methods": ["letter_minimum"],
        "cases": [{"id": "one", "tier": "solve", "options": {}}],
        "baseline_failures": [],
        "iterations": {"python|letter_minimum|one": 1},
        "baseline_source": before,
        "pilot_source": before,
        "acceptance_code_sha256": hashes,
        "processes": 1,
        "warmup_batches": 3,
    }
    monkeypatch.setattr(run, "ROOT", repo)
    monkeypatch.setattr(run, "load_manifest", lambda _: copy.deepcopy(manifest))
    monkeypatch.setattr(
        run,
        "source_binding",
        lambda path, **_: source_binding(repo) if Path(path) == repo else copy.deepcopy(before),
    )
    monkeypatch.setattr(
        run,
        "provenance",
        lambda _: {
            "machine": {"test": True},
            "harness": source_binding(repo),
            "source": copy.deepcopy(before),
        },
    )
    entered = []

    def driver(*_, **__):
        entered.append("driver")
        raise RuntimeError("Reached driver after code check")

    def analyze(*_, **__):
        entered.append("analysis")
        if stage == "freeze":
            raise RuntimeError("Reached analysis after code check")
        return {"pass": False, "reasons": []}

    def audit(*_):
        entered.append("audit")
        return {"pass": True, "reasons": []}

    monkeypatch.setattr(run, "driver", driver)
    monkeypatch.setattr(run, "analyze", analyze)
    monkeypatch.setattr(gates, "audit", audit)
    output = tmp_path / "output"
    if stage == "candidate":
        args = SimpleNamespace(
            manifest="unused",
            output=output,
            kind="candidate",
            baseline="/baseline",
            candidate="/candidate",
            run_id="run",
        )
        action = run.compare
    elif stage in ("captures", "profiles"):
        runtime = tmp_path / "runtime"
        fixtures = runtime / "conformance" / "fixtures"
        fixtures.mkdir(parents=True)
        for name in ("reduce", "reduce_letter_minimum", "reduce_weighted"):
            (fixtures / f"{name}.json").write_text(json.dumps({"cases": []}))
        args = SimpleNamespace(manifest="unused", repo=runtime, output=output, include_opt_in=False)
        action = getattr(run, stage)
    elif stage == "freeze":
        calibration = tmp_path / "calibration"
        calibration.mkdir()
        (calibration / "manifest.json").write_text(json.dumps(manifest))
        (calibration / "metadata.json").write_text(
            json.dumps(
                {
                    "harness": before,
                    "harness_after": before,
                    "machine": {"test": True},
                    "source_before": {"baseline": before},
                }
            )
        )
        (calibration / "samples.jsonl").write_text("")
        args = SimpleNamespace(manifest="unused", calibration=calibration)
        action = run.freeze
    else:
        args = SimpleNamespace(
            manifest="unused",
            runs=["one", "two"],
            baseline_capture="base",
            candidate_capture="candidate",
            baseline_profiles="base",
            candidate_profiles="candidate",
            calibration="calibration",
            pilot="pilot",
            output=output,
        )
        action = run.final_audit
    if unchanged:
        if stage == "audit":
            action(args)
            report = json.loads(output.read_text())
            assert report["audit_harness"]["head"] != before["head"]
            assert report["acceptance_code_sha256"] == hashes
            assert entered == ["audit"]
        else:
            with pytest.raises(RuntimeError, match="after code check"):
                action(args)
            assert entered[0] == ("analysis" if stage == "freeze" else "driver")
    else:
        with pytest.raises(ValueError, match="clean source binding|must be clean|code differs"):
            action(args)
        assert entered == []
        assert not output.is_file()


@pytest.mark.parametrize(
    "change",
    [
        "benchmarks/run.py",
        "benchmarks/cases.py",
        "benchmarks/profile_outcomes.py",
        "README.md",
        "python/runtime.py",
        "tests/test_result.py",
    ],
)
def test_stored_collection_code_is_checked_after_current_code_is_restored(code_repo, change):
    repo, before, hashes = code_repo
    revise(repo, change)
    collected = source_binding(repo)
    metadata = {
        "harness": collected,
        "harness_after": collected,
        "machine": {"test": True},
        # Neither a supplied full hash map nor matching driver bytes can excuse
        # a different coordinator or validator in the recorded Git commit.
        "acceptance_code_sha256": hashes,
        "driver_sha256": {gates.DRIVERS["python"]: hashes[gates.DRIVERS["python"]]},
    }
    git(repo, "checkout", "--detach", before["head"])
    assert gates.acceptance_hashes(source_binding(repo), ["python"]) == hashes
    errors = gates.context_errors(metadata, {"test": True}, hashes, ["python"])
    if change.startswith("benchmarks/"):
        assert errors == ["acceptance code differs"]
    else:
        assert errors == []
