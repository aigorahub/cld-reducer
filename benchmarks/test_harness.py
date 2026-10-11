"""Check that incomplete, biased, incorrect and slow evidence cannot pass."""
import copy
import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
from analysis import analyze, estimate
from cases import frozen_manifest, job_key, jobs, multipartite
from common import Driver, DriverError, digest
from run import fixture_mismatch, load_manifest


def evidence(ratio=.8, targets=True):
    cases = [{"id": f"{split}/case-{i}", "split": split, "tier": "solve", "classification": "ordinary",
              "wall_seconds": 30, "call": "adjacency", "input": {"adjacency": [[1]]}, "options": {}}
             for split in ("development", "validation") for i in range(5)]
    m = {"schema_version": 1, "languages": ["python"], "methods": ["letter_minimum"], "cases": cases,
         "processes": 8, "warmup_batches": 3, "batches": 3, "memory_limit_mb": 8192,
         "bootstrap_resamples": 10000, "bootstrap_seed": 41, "frozen": True,
         "iterations": {}, "baseline_failures": [], "gain_targets": {}}
    keys = [job_key("python", c) for c in jobs(m)]
    m["iterations"] = dict.fromkeys(keys, 1)
    if targets:
        m["gain_targets"] = {"python|letter_minimum": keys}
    rows = [{"key": key, "process": p, "batch": b, "iterations": 1, "ok": True, "correct": True,
             "baseline_ns": 100 + p, "candidate_ns": ratio * (100 + p)}
            for key in keys for p in range(8) for b in range(3)]
    meta = {"complete": True, "manifest_sha256": digest(m), "source_before": {"head": "abc"},
            "source_after": {"head": "abc"}, "kind": "candidate"}
    return m, meta, rows


def test_exact_gain_and_paired_process_noise():
    m, meta, rows = evidence()
    report = analyze(m, meta, rows)
    assert report["pass"], report["reasons"]
    assert all(g["ratio"] == pytest.approx(.8) for g in report["groups"].values())
    assert all(g["interval_95"][1] == pytest.approx(.8) for g in report["groups"].values())


@pytest.mark.parametrize("fault", ["incomplete", "missing", "duplicate", "wrong", "failure", "binding", "source", "iterations", "nonfinite"])
def test_missing_or_invalid_evidence_fails(fault):
    m, meta, rows = evidence()
    if fault == "incomplete": meta["complete"] = False
    elif fault == "missing": rows.pop()
    elif fault == "duplicate": rows.append(copy.deepcopy(rows[0]))
    elif fault == "wrong": rows[0]["correct"] = False
    elif fault == "failure": rows[0]["ok"] = False
    elif fault == "binding": meta["manifest_sha256"] = "wrong"
    elif fault == "source": meta["source_after"] = {"head": "other"}
    elif fault == "iterations": rows[0]["iterations"] = 2
    elif fault == "nonfinite": rows[0]["candidate_ns"] = float("nan")
    assert not analyze(m, meta, rows)["pass"]


def test_one_slow_case_blocks_large_group_gain():
    m, meta, rows = evidence(.5)
    key = rows[0]["key"]
    for r in rows:
        if r["key"] == key: r["candidate_ns"] = r["baseline_ns"] * 1.06
    assert not analyze(m, meta, rows)["pass"]


def test_process_variation_is_resampled():
    baseline = np.full((8, 9), 100.)
    candidate = np.array([[v] * 9 for v in (40, 50, 60, 80, 100, 110, 140, 190)])
    _, interval, _ = estimate(baseline, candidate, 10000, 17)
    assert interval[1] > 1.05


def test_validation_gain_must_pass_independently():
    m, meta, rows = evidence()
    for row in rows:
        if "validation/" in row["key"]: row["candidate_ns"] = row["baseline_ns"]
    r = analyze(m, meta, rows)
    assert not r["pass"]
    assert any("validation" in reason for reason in r["reasons"])


def test_empty_targets_fail_but_calibration_needs_no_gain():
    m, meta, rows = evidence(1., targets=False)
    assert not analyze(m, meta, rows)["pass"]
    meta["kind"] = "calibration"
    assert analyze(m, meta, rows)["pass"]


def test_manifest_families_are_deterministic_and_bounded():
    repo = Path(__file__).resolve().parents[1]
    m = frozen_manifest(repo)
    assert m == frozen_manifest(repo)
    assert len({c["id"] for c in m["cases"]}) == len(m["cases"])
    assert {c["tier"] for c in m["cases"]} == {"solve", "opt-in", "preprocess", "expected-error"}
    a = multipartite(9)
    assert len(a) == 27 and all(a[i][i] == 1 for i in range(27))
    assert 3 ** 9 > 10000
    assert all(c["classification"] in ("ordinary", "stress") for c in m["cases"])


def test_frozen_fixture_check_detects_wrong_objective():
    actual = {"groups": ["a"], "assignments": [["A"]], "letters": ["A"], "method": "letter_minimum",
              "relationship_preserved": True, "stats": {"objective": 2, "solver_status": "Optimal", "reduction_pct": 0}}
    expected = {"groups": ["a"], "assignments": {"a": ["A"]}, "letters": {"a": "A"},
                "method": "letter_minimum", "relationship_preserved": True, "stats": {}, "objective": 1,
                "solver_status": "Optimal", "reduction_pct": {"numerator": 0, "denominator": 1}}
    assert fixture_mismatch(actual, expected) == ["stats.objective"]


def fake_driver(tmp_path, monkeypatch, body):
    directory = tmp_path / "benchmarks"
    directory.mkdir()
    (directory / "python_driver.py").write_text(body)
    monkeypatch.setattr(common, "ROOT", tmp_path)
    return Driver("python", tmp_path, "on", tmp_path / "stderr", memory_mb=128)


def test_transport_rejects_wrong_action(tmp_path, monkeypatch):
    with fake_driver(tmp_path, monkeypatch, 'import sys,json\nfor l in sys.stdin: print(json.dumps({"ok":True,"action":"wrong"}),flush=True)\n') as d:
        with pytest.raises(DriverError, match="match"):
            d.request({"action": "version"})


def test_transport_kills_wall_limit(tmp_path, monkeypatch):
    with fake_driver(tmp_path, monkeypatch, 'import time\ntime.sleep(30)\n') as d:
        with pytest.raises(DriverError, match="wall limit"):
            d.request({"action": "version"}, timeout=.15)
        assert d.process.poll() is not None


def test_manifest_rejects_underpowered_process_count(tmp_path):
    m, _, _ = evidence()
    m["processes"] = 3
    p = tmp_path / "manifest.json"
    p.write_text(json.dumps(m))
    with pytest.raises(ValueError, match="measurement design"):
        load_manifest(p)
