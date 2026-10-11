"""Check that incomplete, biased, incorrect and slow evidence cannot pass."""

import copy
import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
from analysis import analyze, estimate, select_gain_targets
from cases import frozen_manifest, job_key, jobs, multipartite
from common import Driver, DriverError, digest, input_digest
from run import fixture_mismatch, load_manifest


def source(path="/baseline", head="a" * 40, *, js=False):
    binding = {
        "path": path,
        "head": head,
        "tree": "b" * 40,
        "status": "",
        "build_files": {"js/dist/index.js": "c" * 64},
        "lock_files": {"js/package-lock.json": "d" * 64},
    }
    if js:
        binding.update(
            build_verified=True,
            dependency_files={
                "highs/package.json": "1" * 64,
                "highs/build/highs.mjs": "2" * 64,
                "highs/build/highs.wasm": "3" * 64,
            },
            compiler_files={"typescript/bin/tsc": "4" * 64, "typescript/lib/tsc.js": "5" * 64},
        )
    return binding


def version(head="a" * 40):
    return {
        "ok": True,
        "action": "version",
        "language": "python",
        "runtime": "3.13.0",
        "package": "0.3.0",
        "dependencies": {"highspy": "1.15.1", "numpy": "2.5.4"},
        "solver": {"name": "HiGHS", "version": "1.15.1"},
        "settings": {"presolve": "on", "threads": 1, "mip_rel_gap": 0, "mip_abs_gap": 0},
        "module_load_ns": 100,
        "solver_load_ns": 200,
        "source_head": head,
    }


def evidence(ratio=0.8, targets=True):
    cases = [
        {
            "id": f"{split}/case-{i}",
            "split": split,
            "tier": "solve",
            "classification": "ordinary",
            "wall_seconds": 30,
            "call": "adjacency",
            "input": {"adjacency": [[1] * (i + 1) for _ in range(i + 1)]},
            "options": {},
        }
        for split in ("development", "validation")
        for i in range(5)
    ]
    m = {
        "schema_version": 1,
        "languages": ["python"],
        "methods": ["letter_minimum"],
        "cases": cases,
        "processes": 8,
        "warmup_batches": 3,
        "batches": 9,
        "memory_limit_mb": 8192,
        "presolve": {"python": "on"},
        "bootstrap_resamples": 10000,
        "bootstrap_seed": 41,
        "order_seed": 17,
        "frozen": True,
        "iterations": {},
        "baseline_failures": [],
        "gain_targets": {},
        "baseline_source": source(),
        "pilot_source": source(),
        "baseline_versions": {"python": version()},
    }
    keys = [job_key("python", c) for c in jobs(m)]
    m["iterations"] = dict.fromkeys(keys, 1)
    if targets:
        m["gain_targets"] = {"python|letter_minimum": keys}
    rows = [
        {
            "key": key,
            "process": p,
            "batch": b,
            "iterations": 1,
            "ok": True,
            "correct": True,
            "baseline_ns": 100 + p,
            "candidate_ns": ratio * (100 + p),
        }
        for key in keys
        for p in range(8)
        for b in range(9)
    ]
    before = {"baseline": source(), "candidate": source("/candidate", "e" * 40)}
    meta = {
        "complete": True,
        "manifest_sha256": digest(m),
        "input_sha256": input_digest(m),
        "source_before": before,
        "source_after": copy.deepcopy(before),
        "kind": "candidate",
        "harness": source("/harness"),
        "harness_after": source("/harness"),
        "versions": [
            {"language": "python", "process": p, "versions": [version(), version("e" * 40)]}
            for p in range(8)
        ],
    }
    return m, meta, rows


def calibration(meta):
    meta["kind"] = "calibration"
    for key in ("source_before", "source_after"):
        meta[key]["candidate"] = dict(copy.deepcopy(meta[key]["baseline"]), path="/candidate")
    for row in meta["versions"]:
        row["versions"][1]["source_head"] = "a" * 40


def test_exact_gain_and_paired_process_noise():
    m, meta, rows = evidence()
    report = analyze(m, meta, rows)
    assert report["pass"], report["reasons"]
    assert report["scope"] == "single_run"
    assert all(g["ratio"] == pytest.approx(0.8) for g in report["groups"].values())
    assert all(g["interval_95"][1] == pytest.approx(0.8) for g in report["groups"].values())


@pytest.mark.parametrize(
    "fault",
    [
        "incomplete",
        "missing",
        "duplicate",
        "wrong",
        "failure",
        "binding",
        "source",
        "iterations",
        "nonfinite",
    ],
)
def test_missing_or_invalid_evidence_fails(fault):
    m, meta, rows = evidence()
    if fault == "incomplete":
        meta["complete"] = False
    elif fault == "missing":
        rows.pop()
    elif fault == "duplicate":
        rows.append(copy.deepcopy(rows[0]))
    elif fault == "wrong":
        rows[0]["correct"] = False
    elif fault == "failure":
        rows[0]["ok"] = False
    elif fault == "binding":
        meta["manifest_sha256"] = "wrong"
    elif fault == "source":
        meta["source_after"] = {"head": "other"}
    elif fault == "iterations":
        rows[0]["iterations"] = 2
    elif fault == "nonfinite":
        rows[0]["candidate_ns"] = float("nan")
    assert not analyze(m, meta, rows)["pass"]


def test_one_slow_case_blocks_large_group_gain():
    m, meta, rows = evidence(0.5)
    key = rows[0]["key"]
    for r in rows:
        if r["key"] == key:
            r["candidate_ns"] = r["baseline_ns"] * 1.06
    assert not analyze(m, meta, rows)["pass"]


def test_process_variation_is_resampled():
    baseline = np.full((8, 9), 100.0)
    candidate = np.array([[v] * 9 for v in (40, 50, 60, 80, 100, 110, 140, 190)])
    _, interval, _ = estimate(baseline, candidate, 10000, 17)
    assert interval[1] > 1.05


def test_validation_gain_must_pass_independently():
    m, meta, rows = evidence()
    for row in rows:
        if "validation/" in row["key"]:
            row["candidate_ns"] = row["baseline_ns"]
    r = analyze(m, meta, rows)
    assert not r["pass"]
    assert any("validation" in reason for reason in r["reasons"])


def test_empty_targets_fail_but_calibration_needs_no_gain():
    m, meta, rows = evidence(1.0, targets=False)
    assert not analyze(m, meta, rows)["pass"]
    calibration(meta)
    assert analyze(m, meta, rows)["pass"]


@pytest.mark.parametrize("ratio,passed", [(0.8, False), (0.96, True), (1.04, True), (1.06, False)])
def test_calibration_requires_two_sided_equivalence(ratio, passed):
    m, meta, rows = evidence(ratio, targets=False)
    calibration(meta)
    report = analyze(m, meta, rows)
    assert report["pass"] is passed
    assert all(case["pass"] is passed for case in report["cases"].values())


@pytest.mark.parametrize("fault", ["missing", "changed"])
def test_analysis_rejects_missing_or_changed_collection_harness(fault):
    m, meta, rows = evidence()
    if fault == "missing":
        meta.pop("harness_after")
    else:
        meta["harness_after"]["head"] = "9" * 40
    report = analyze(m, meta, rows)
    assert not report["pass"]
    assert "Harness source binding is missing or changed during collection" in report["reasons"]


def target_profiles(manifest):
    return [
        {
            "key": job_key(language, case),
            "case": case,
            "response": {
                "ok": True,
                "metrics": {"essential_cover": True, "solver_total_ns": 25},
                "phases_ns": {"total": 100},
            },
        }
        for language in manifest["languages"]
        for case in jobs(manifest)
    ]


def test_target_selection_keeps_small_combinations_regression_only():
    manifest, _, _ = evidence()
    manifest["methods"].append("assignment_minimum")
    profiles = target_profiles(manifest)
    for row in profiles:
        if row["case"]["options"]["method"] == "assignment_minimum" and row["case"]["id"].endswith(
            "4"
        ):
            row["response"]["metrics"]["solver_total_ns"] = 24
    targets = select_gain_targets(manifest, profiles)
    assert set(targets) == {"python|letter_minimum"}
    assert len(targets["python|letter_minimum"]) == 10


def test_target_selection_counts_input_digests_not_case_ids():
    manifest, _, _ = evidence()
    for case in manifest["cases"]:
        case["input"] = {"adjacency": [[1]]}
    with pytest.raises(ValueError, match="five distinct inputs"):
        select_gain_targets(manifest, target_profiles(manifest))


@pytest.mark.parametrize(
    "fault",
    [
        "missing_cover",
        "missing_solver",
        "zero_total",
        "nan_solver",
        "boolean_solver",
        "duplicate",
        "missing",
    ],
)
def test_target_selection_requires_complete_numeric_profile_evidence(fault):
    manifest, _, _ = evidence()
    profiles = target_profiles(manifest)
    response = profiles[0]["response"]
    if fault == "missing_cover":
        response["metrics"].pop("essential_cover")
    elif fault == "missing_solver":
        response["metrics"].pop("solver_total_ns")
    elif fault == "zero_total":
        response["phases_ns"]["total"] = 0
    elif fault == "nan_solver":
        response["metrics"]["solver_total_ns"] = float("nan")
    elif fault == "boolean_solver":
        response["metrics"]["solver_total_ns"] = True
    elif fault == "duplicate":
        profiles.append(copy.deepcopy(profiles[0]))
    else:
        profiles.pop()
    with pytest.raises(ValueError):
        select_gain_targets(manifest, profiles)


def test_manifest_families_are_deterministic_and_bounded():
    repo = Path(__file__).resolve().parents[1]
    m = frozen_manifest(repo)
    assert m == frozen_manifest(repo)
    assert len({c["id"] for c in m["cases"]}) == len(m["cases"])
    assert {c["tier"] for c in m["cases"]} == {"solve", "opt-in", "preprocess", "expected-error"}
    a = multipartite(9)
    assert len(a) == 27 and all(a[i][i] == 1 for i in range(27))
    assert 3**9 > 10000
    assert all(c["classification"] in ("ordinary", "stress") for c in m["cases"])


def test_frozen_fixture_check_detects_wrong_objective():
    actual = {
        "groups": ["a"],
        "adjacency": [[True]],
        "rows": [{"group": "a", "letters": "A", "assignments": "A"}],
        "assignments": [["A"]],
        "letters": ["A"],
        "method": "letter_minimum",
        "relationship_preserved": True,
        "stats": {"objective": 2, "solver_status": "Optimal", "reduction_pct": 0},
    }
    expected = {
        "groups": ["a"],
        "assignments": {"a": ["A"]},
        "letters": {"a": "A"},
        "method": "letter_minimum",
        "relationship_preserved": True,
        "stats": {},
        "objective": 1,
        "solver_status": "Optimal",
        "reduction_pct": {"numerator": 0, "denominator": 1},
    }
    assert fixture_mismatch(actual, expected) == ["stats.objective"]


def fake_driver(tmp_path, monkeypatch, body):
    directory = tmp_path / "benchmarks"
    directory.mkdir()
    (directory / "python_driver.py").write_text(body)
    monkeypatch.setattr(common, "ROOT", tmp_path)
    return Driver("python", tmp_path, "on", tmp_path / "stderr", memory_mb=128)


def test_transport_rejects_wrong_action(tmp_path, monkeypatch):
    with fake_driver(  # noqa: SIM117
        tmp_path,
        monkeypatch,
        "import sys,json\n"
        'for l in sys.stdin: print(json.dumps({"ok":True,"action":"wrong"}),flush=True)\n',
    ) as d:
        with pytest.raises(DriverError, match="match"):
            d.request({"action": "version"})


def test_transport_kills_wall_limit(tmp_path, monkeypatch):
    with fake_driver(tmp_path, monkeypatch, "import time\ntime.sleep(30)\n") as d:
        with pytest.raises(DriverError, match="wall limit"):
            d.request({"action": "version"}, timeout=0.15)
        assert d.process.poll() is not None


def test_manifest_rejects_underpowered_process_count(tmp_path):
    m, _, _ = evidence()
    m["processes"] = 3
    p = tmp_path / "manifest.json"
    p.write_text(json.dumps(m))
    with pytest.raises(ValueError, match="measurement design"):
        load_manifest(p)


@pytest.mark.parametrize(
    "fault",
    [
        "missing_before",
        "missing_after",
        "missing_harness",
        "empty",
        "short_head",
        "dirty",
        "missing_build",
        "bad_build_hash",
        "missing_locks",
        "bad_lock_path",
        "frozen_source",
        "stale_driver",
    ],
)
def test_source_bindings_must_be_complete_and_match_frozen_baseline(fault):
    m, meta, rows = evidence()
    if fault == "missing_before":
        meta.pop("source_before")
    elif fault == "missing_after":
        meta.pop("source_after")
    elif fault == "missing_harness":
        meta.pop("harness")
    elif fault == "empty":
        meta["source_before"] = meta["source_after"] = {}
    elif fault == "frozen_source":
        m["baseline_source"]["head"] = "f" * 40
    elif fault == "stale_driver":
        meta["versions"][0]["versions"][0]["source_head"] = "f" * 40
    else:
        for key in ("source_before", "source_after"):
            binding = meta[key]["baseline"]
            if fault == "short_head":
                binding["head"] = "abc"
            elif fault == "dirty":
                binding["status"] = " M runtime.py"
            elif fault == "missing_build":
                binding.pop("build_files")
            elif fault == "bad_build_hash":
                binding["build_files"]["js/dist/index.js"] = "bad"
            elif fault == "missing_locks":
                binding.pop("lock_files")
            elif fault == "bad_lock_path":
                binding["lock_files"] = {"../package-lock.json": "d" * 64}
    meta["manifest_sha256"] = digest(m)
    meta["input_sha256"] = input_digest(m)
    assert not analyze(m, meta, rows)["pass"]


def test_frozen_baseline_can_use_another_clean_checkout_path():
    m, meta, rows = evidence()
    m["baseline_source"]["path"] = "/calibration-checkout"
    meta["manifest_sha256"] = digest(m)
    meta["input_sha256"] = input_digest(m)
    assert analyze(m, meta, rows)["pass"]


@pytest.mark.parametrize("part", ["head", "tree", "build_files", "lock_files"])
def test_aa_cannot_use_different_source_or_executable_build(part):
    m, meta, rows = evidence(1.0, targets=False)
    calibration(meta)
    for key in ("source_before", "source_after"):
        binding = meta[key]["candidate"]
        if part in ("head", "tree"):
            binding[part] = "f" * 40
        else:
            binding[part][next(iter(binding[part]))] = "f" * 64
    if part == "head":
        for row in meta["versions"]:
            row["versions"][1]["source_head"] = "f" * 40
    report = analyze(m, meta, rows)
    assert not report["pass"]
    assert "A/A source identities differ" in report["reasons"]


@pytest.mark.parametrize(
    "fault",
    [
        "missing",
        "missing_process",
        "duplicate",
        "extra",
        "bad_index",
        "language",
        "missing_solver",
        "presolve",
        "threads",
        "pair",
        "drift",
        "frozen",
        "missing_frozen",
        "missing_frozen_language",
    ],
)
def test_complete_stable_runtime_versions_and_settings_are_required(fault):
    m, meta, rows = evidence()
    if fault == "missing":
        meta.pop("versions")
    elif fault == "missing_process":
        meta["versions"].pop()
    elif fault == "duplicate":
        meta["versions"].append(copy.deepcopy(meta["versions"][0]))
    elif fault == "extra":
        meta["versions"][0]["process"] = 8
    elif fault == "bad_index":
        meta["versions"][0]["process"] = False
    elif fault == "language":
        meta["versions"][0]["versions"][0]["language"] = "r"
    elif fault == "missing_solver":
        meta["versions"][0]["versions"][0].pop("solver")
    elif fault == "presolve":
        meta["versions"][0]["versions"][0]["settings"]["presolve"] = "off"
    elif fault == "threads":
        meta["versions"][0]["versions"][0]["settings"]["threads"] = 2
    elif fault == "pair":
        meta["versions"][0]["versions"][1]["dependencies"]["highspy"] = "other"
    elif fault == "drift":
        for v in meta["versions"][1]["versions"]:
            v["dependencies"]["highspy"] = "other"
    elif fault == "frozen":
        m["baseline_versions"]["python"]["dependencies"]["highspy"] = "other"
    elif fault == "missing_frozen":
        m.pop("baseline_versions")
    elif fault == "missing_frozen_language":
        m["baseline_versions"] = {}
    meta["manifest_sha256"] = digest(m)
    meta["input_sha256"] = input_digest(m)
    assert not analyze(m, meta, rows)["pass"]


def test_aa_rejects_dependency_changes_but_ignores_load_times():
    m, meta, rows = evidence(1.0, targets=False)
    calibration(meta)
    meta["versions"][0]["versions"][1]["module_load_ns"] = 99999
    assert analyze(m, meta, rows)["pass"]
    meta["versions"][0]["versions"][1]["dependencies"]["highspy"] = "other"
    assert not analyze(m, meta, rows)["pass"]


@pytest.mark.parametrize(
    "fault",
    [
        "unknown",
        "duplicate",
        "mixed_method",
        "mixed_language",
        "bad_group",
        "short_development",
        "short_validation",
        "same_inputs",
        "baseline_failure",
    ],
)
def test_invalid_gain_target_membership_cannot_pass(fault):
    m, meta, rows = evidence()
    group = "python|letter_minimum"
    keys = m["gain_targets"][group]
    if fault == "unknown":
        keys.append(group + "|development/unknown")
    elif fault == "duplicate":
        keys.append(keys[0])
    elif fault in ("mixed_method", "mixed_language"):
        replacement = "python|assignment_minimum" if fault == "mixed_method" else "r|letter_minimum"
        m["gain_targets"][replacement] = m["gain_targets"].pop(group)
    elif fault == "bad_group":
        m["gain_targets"]["all"] = m["gain_targets"].pop(group)
    elif fault == "short_development":
        keys.pop(0)
    elif fault == "short_validation":
        keys.pop()
    elif fault == "same_inputs":
        for case in m["cases"]:
            case["input"] = {"adjacency": [[1]]}
    elif fault == "baseline_failure":
        failed = keys[0]
        m["baseline_failures"] = [failed]
        rows = [row for row in rows if row["key"] != failed]
    meta["manifest_sha256"] = digest(m)
    meta["input_sha256"] = input_digest(m)
    assert not analyze(m, meta, rows)["pass"]


def test_batch_first_bootstrap_retains_repeated_process_samples():
    # This fixed distribution distinguishes independent batch resampling for
    # duplicate process selections from reusing the original process sample.
    base = np.ones((8, 9)) * 100
    candidate = np.random.default_rng(23).uniform(60, 130, size=(8, 9))
    candidate *= 0.97
    _, interval, _ = estimate(base, candidate, 10000, 12)
    assert interval[1] > 1.05
    legacy_rng = np.random.default_rng(12)
    processes = legacy_rng.integers(0, 8, size=(10000, 8))
    batches = legacy_rng.integers(0, 9, size=(10000, 8, 9))
    legacy_ratios = (
        np.median(np.median(candidate[processes[:, :, None], batches], axis=2), axis=1) / 100
    )
    assert np.exp(np.quantile(np.log(legacy_ratios), 0.975)) < 1.05


def test_bootstrap_matches_small_manual_batch_then_process_resample():
    base = np.array([[10.0, 20.0, 30.0], [100.0, 200.0, 300.0]])
    candidate = np.array([[8.0, 9.0, 10.0], [50.0, 60.0, 70.0]])
    draws, seed = 20, 13
    rng = np.random.default_rng(seed)
    batch_indices = rng.integers(0, 3, size=(draws, 2, 3))
    process_indices = rng.integers(0, 2, size=(draws, 2))
    logs = []
    for draw in range(draws):
        b = [np.median(base[p, batch_indices[draw, p]]) for p in range(2)]
        c = [np.median(candidate[p, batch_indices[draw, p]]) for p in range(2)]
        logs.append(
            np.log(np.median([c[p] for p in process_indices[draw]]))
            - np.log(np.median([b[p] for p in process_indices[draw]]))
        )
    _, interval, actual_logs = estimate(base, candidate, draws, seed)
    assert actual_logs == pytest.approx(logs)
    assert interval == pytest.approx(np.exp(np.quantile(logs, [0.025, 0.975])))


@pytest.mark.parametrize(
    "fault",
    [
        "few_batches",
        "bool_processes",
        "duplicate_language",
        "no_methods",
        "bad_presolve",
        "duplicate_case",
        "bad_split",
        "unknown_run",
        "false_kind",
        "unexpected_samples",
        "unknown_failure",
        "bad_sample_index",
    ],
)
def test_invalid_design_and_sample_sets_fail(fault):
    m, meta, rows = evidence()
    if fault == "few_batches":
        m["batches"] = 3
    elif fault == "bool_processes":
        m["processes"] = True
    elif fault == "duplicate_language":
        m["languages"].append("python")
    elif fault == "no_methods":
        m["methods"] = []
    elif fault == "bad_presolve":
        m["presolve"]["python"] = "auto"
    elif fault == "duplicate_case":
        m["cases"].append(copy.deepcopy(m["cases"][0]))
    elif fault == "bad_split":
        m["cases"][0]["split"] = "other"
    elif fault == "unknown_run":
        meta["kind"] = "other"
    elif fault == "false_kind":
        meta["complete"] = "yes"
    elif fault == "unexpected_samples":
        rows[0]["key"] = "python|letter_minimum|other"
    elif fault == "unknown_failure":
        m["baseline_failures"] = ["other"]
    elif fault == "bad_sample_index":
        rows[0]["batch"] = False
    meta["manifest_sha256"] = digest(m)
    meta["input_sha256"] = input_digest(m)
    assert not analyze(m, meta, rows)["pass"]


@pytest.mark.parametrize("missing", [True, False])
def test_input_digest_is_required_and_must_match(missing):
    m, meta, rows = evidence()
    if missing:
        meta.pop("input_sha256")
    else:
        meta["input_sha256"] = "0" * 64
    assert "Input binding differs" in analyze(m, meta, rows)["reasons"]


def language_evidence(language, ratio=0.8, targets=True):
    m, meta, rows = evidence(ratio, targets)
    m["languages"] = [language]
    presolve = "off" if language == "r" else "on"
    m["presolve"] = {language: presolve}
    m["iterations"] = {
        key.replace("python|", language + "|"): value for key, value in m["iterations"].items()
    }
    m["gain_targets"] = (
        {
            language + "|letter_minimum": [
                key.replace("python|", language + "|")
                for key in m["gain_targets"]["python|letter_minimum"]
            ]
        }
        if targets
        else {}
    )
    m["baseline_versions"] = {language: m["baseline_versions"]["python"]}
    for row in meta["versions"]:
        row["language"] = language
    all_versions = [v for row in meta["versions"] for v in row["versions"]]
    all_versions.append(m["baseline_versions"][language])
    for v in all_versions:
        v["language"] = "javascript" if language == "js" else "r"
        v["runtime"] = "v22.0.0" if language == "js" else {"name": "R", "version": "4.5.0"}
        v["settings"]["presolve"] = presolve
    for row in rows:
        row["key"] = row["key"].replace("python|", language + "|")
    if language == "js":
        m["baseline_source"] = source(js=True)
        m["pilot_source"] = source(js=True)
        for phase in ("source_before", "source_after"):
            meta[phase] = {
                "baseline": source(js=True),
                "candidate": source("/candidate", "e" * 40, js=True),
            }
    meta["manifest_sha256"] = digest(m)
    meta["input_sha256"] = input_digest(m)
    return m, meta, rows


@pytest.mark.parametrize("language", ["r", "js"])
def test_actual_language_version_shapes_are_supported(language):
    m, meta, rows = language_evidence(language)
    result = analyze(m, meta, rows)
    assert result["pass"], result["reasons"]


@pytest.mark.parametrize(
    "fault",
    ["missing_proof", "false_proof", "solver_bytes", "compiler_bytes", "missing_wasm", "bad_hash"],
)
def test_javascript_analysis_requires_build_proof_and_equal_installed_bytes(fault):
    m, meta, rows = language_evidence("js")
    for phase in ("source_before", "source_after"):
        binding = meta[phase]["candidate"]
        if fault == "missing_proof":
            binding.pop("build_verified")
        elif fault == "false_proof":
            binding["build_verified"] = False
        elif fault == "solver_bytes":
            binding["dependency_files"]["highs/build/highs.wasm"] = "9" * 64
        elif fault == "compiler_bytes":
            binding["compiler_files"]["typescript/lib/tsc.js"] = "9" * 64
        elif fault == "missing_wasm":
            binding["dependency_files"].pop("highs/build/highs.wasm")
        else:
            binding["compiler_files"]["typescript/lib/tsc.js"] = "invalid"
    report = analyze(m, meta, rows)
    assert not report["pass"]
    assert any(
        "source binding" in reason or "bytes differ" in reason for reason in report["reasons"]
    )


@pytest.mark.parametrize("fault", ["missing", "missing_proof", "solver_bytes", "source"])
def test_calibration_requires_the_verified_pilot_source(fault):
    m, meta, rows = language_evidence("js", 1.0, targets=False)
    calibration(meta)
    if fault == "missing":
        m.pop("pilot_source")
    elif fault == "missing_proof":
        m["pilot_source"].pop("build_verified")
    elif fault == "solver_bytes":
        m["pilot_source"]["dependency_files"]["highs/build/highs.wasm"] = "9" * 64
    else:
        m["pilot_source"]["head"] = "9" * 40
    meta["manifest_sha256"] = digest(m)
    report = analyze(m, meta, rows)
    assert not report["pass"]
    assert any("ilot" in reason for reason in report["reasons"])
