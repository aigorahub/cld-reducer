"""Synthetic evidence checks for the final gate. No runtime timing is performed."""
import copy
import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from cases import job_key, jobs, multipartite
from common import digest, input_digest
import gates
from gates import audit

recorded_driver_hashes = gates._driver_hashes


@pytest.fixture(autouse=True)
def synthetic_driver_source(monkeypatch):
    # Other tests use synthetic source commits. Exercise Git lookup separately.
    monkeypatch.setattr(gates, "_driver_hashes", lambda binding, languages: {
        gates.DRIVERS[language]: digest(language) for language in languages})


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value) + "\n")


def write_rows(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))


def result(group="v", method="letter_minimum"):
    return dict(groups=[group], assignments=[["A"]], letters=["A"], adjacency=[[True]],
                method=method, relationship_preserved=True,
                rows=[dict(group=group, letters="A", assignments="A")],
                stats=dict(assignments_before=1, assignments_after=1, reduction_pct=0,
                           num_letters_before=1, num_letters_after=1, num_groups=1, num_edges=0,
                           solver_status="Optimal", objective=1))


def make_evidence(tmp_path, *, baseline_failure=False, new_success=False, oracle_match=False):
    base_source = dict(path=str(tmp_path / "source"), head="a" * 40, tree="b" * 40,
                       status="", build_files={}, lock_files={})
    candidate_source = dict(base_source, head="d" * 40, tree="e" * 40)
    harness = dict(base_source, head="c" * 40, tree="f" * 40)
    version = dict(ok=True, action="version", language="python", runtime="3.12",
                   dependencies={"highspy": "1.14"}, solver={"name": "HiGHS", "version": "1.14"},
                   source_head=base_source["head"], module_load_ns=10,
                   settings=dict(presolve="on", threads=1, mip_rel_gap=0, mip_abs_gap=0,
                                 primal_feasibility_tolerance=1e-9, mip_feasibility_tolerance=1e-9))
    candidate_version = dict(version, source_head=candidate_source["head"], module_load_ns=20)
    expected = dict(groups=["v"], assignments={"v": ["A"]}, letters={"v": "A"},
                    stats={name: value for name, value in result()["stats"].items()
                           if name not in ("reduction_pct", "objective", "solver_status")},
                    solver_status="Optimal", objective=1, method="letter_minimum",
                    relationship_preserved=True, reduction_pct={"numerator": 0, "denominator": 1})
    fixture_cases, hashes = [], {}
    for name in ("reduce", "reduce_letter_minimum", "reduce_weighted"):
        case = dict(id="one", call="adjacency", input={"adjacency": [[1]], "groups": ["v"]},
                    options={}, expected=copy.deepcopy(expected))
        if name == "reduce_letter_minimum":
            case["sigma_expected"] = dict(copy.deepcopy(expected), method="assignment_minimum")
        file = tmp_path / "source" / "conformance" / "fixtures" / f"{name}.json"
        write(file, {"cases": [case]})
        hashes[name] = hashlib.sha256(file.read_bytes()).hexdigest()
        case["id"] = f"fixture/{name}/one"
        case["options"]["method"] = case["expected"]["method"]
        fixture_cases.append(case)
        if "sigma_expected" in case:
            alternate = copy.deepcopy(case)
            alternate["id"] += "/sigma"
            alternate["expected"] = alternate["sigma_expected"]
            alternate["options"]["method"] = "assignment_minimum"
            fixture_cases.append(alternate)
    cases = [dict(id=f"{split}/case-{i}", split=split, classification="ordinary", tier="solve",
                  wall_seconds=30, call="adjacency", options={},
                  input={"adjacency": [[1]], "groups": [f"{split}-{i}"]})
             for split in ("development", "validation") for i in range(5)]
    if baseline_failure:
        cases.append(dict(id="development/blocked", split="development", classification="stress", tier="solve",
                          wall_seconds=30, call="adjacency", options={},
                          input={"adjacency": [[1]], "groups": ["v" if oracle_match else "blocked"]}))
    for parts in (6, 7, 8, 9):
        cases.append(dict(id=f"bounded/multipartite-{parts}x3", split="bounded", classification="stress",
                          tier="expected-error" if parts == 9 else "preprocess", wall_seconds=30,
                          call="adjacency", input={"adjacency": multipartite(parts)}, options={}))
    manifest = dict(schema_version=1, case_generator="cases.py:1", cases=cases, methods=["letter_minimum"],
                    languages=["python"], presolve={"python": "on"}, memory_limit_mb=8192,
                    memory_growth_tolerance_mb=32, processes=8, warmup_batches=3, batches=9,
                    bootstrap_resamples=10000, bootstrap_seed=31, frozen=True, baseline_source=base_source,
                    baseline_versions={"python": version}, baseline_failures=[], iterations={}, gain_targets={})
    solve_cases = list(jobs(manifest))
    keys = [job_key("python", case) for case in solve_cases]
    manifest["iterations"] = dict.fromkeys(keys, 1)
    manifest["gain_targets"] = {"python|letter_minimum": keys[:10]}
    if baseline_failure:
        manifest["baseline_failures"] = [keys[-1]]
    failure = dict(ok=False, action="capture", error={"kind": "SolverError", "message": "Time limit reached"})
    directories = {name: tmp_path / name for name in ("baseline-capture", "candidate-capture",
                   "baseline-profiles", "candidate-profiles", "run-1", "run-2")}
    captures, profiles, metadata = {}, {}, {}
    for variant, source, runtime_version in (("baseline", base_source, version),
                                             ("candidate", candidate_source, candidate_version)):
        rows = []
        for case in fixture_cases + solve_cases:
            method = case["options"]["method"]
            row = dict(language="python", id=case["id"], method=method, case=case,
                       oracle_fixture=case["id"].startswith("fixture/"), mismatch=[])
            if job_key("python", case) in manifest["baseline_failures"] and not (variant == "candidate" and new_success):
                row["response"] = failure
            else:
                row.update(result=result(case["input"]["groups"][0], method), canonical={"selected": [1], "objective": 1})
            rows.append(row)
        captures[variant] = rows
        capture_map = {job_key(row["language"], row["case"]): row for row in rows}
        profile_rows = []
        for case in jobs(manifest, tiers=("solve", "preprocess", "expected-error")):
            key = job_key("python", case)
            if case["tier"] == "expected-error":
                response = dict(ok=False, action="preprocess", error={"kind": "SolverError",
                    "message": "maximal clique enumeration exceeded max_cliques=10000"})
            elif case["tier"] == "preprocess":
                vertices = len(case["input"]["adjacency"])
                parts = vertices // 3
                response = dict(ok=True, action="preprocess", phases_ns={"total": 100},
                                metrics=dict(solve_count=0, vertices_before=vertices, vertices_after=vertices,
                                             maximal_cliques=3 ** parts, decision_variables=3 ** parts, auxiliary_variables=0,
                                             constraints=vertices + vertices * (vertices - 3) // 2,
                                             nonzeros=3 ** parts * (parts + parts * (parts - 1) // 2), essential_decisions=0))
            elif "response" in capture_map[key]:
                response = dict(failure, action="profile")
            else:
                response = dict(ok=True, action="profile", phases_ns={"total": 100},
                                **{name: capture_map[key][name] for name in ("result", "canonical")})
            profile_rows.append(dict(key=key, case=case, response=response, peak_rss=1024))
        profiles[variant] = profile_rows
        meta = dict(source=source, source_after=copy.deepcopy(source), harness=harness,
                    machine={"platform": "test", "cpu_count": 8, "memory_bytes": 16384 * 1024 ** 2},
                    complete=True, input_sha256=input_digest(manifest), versions={"python": runtime_version},
                    manifest_sha256="earlier sampling design", fixture_sha256=hashes,
                    checked=len(rows), failures=[], expected_keys=[{name: row[name] for name in
                    ("language", "id", "method", "oracle_fixture")} for row in rows])
        metadata[variant] = meta
    manifest["baseline_capture_sha256"] = digest(captures["baseline"])
    manifest["profile_sha256"] = digest(profiles["baseline"])
    for variant in ("baseline", "candidate"):
        write_rows(directories[f"{variant}-capture"] / "vectors.jsonl", captures[variant])
        write_rows(directories[f"{variant}-profiles"] / "profiles.jsonl", profiles[variant])
        for kind in ("capture", "profiles"):
            write(directories[f"{variant}-{kind}"] / "metadata.json", metadata[variant])
    for run in (1, 2):
        process_versions, samples, results = [], [], []
        for process in range(manifest["processes"]):
            process_versions.append(dict(language="python", process=process,
                                         versions=[version, candidate_version], pids=[run * 1000 + 2 * process,
                                                                                    run * 1000 + 2 * process + 1]))
            for case in solve_cases:
                key = job_key("python", case)
                pair = []
                for variant in ("baseline", "candidate"):
                    captured = next(row for row in captures[variant] if row["id"] == case["id"])
                    pair.append(captured["response"] if "response" in captured else dict(
                        ok=True, action="capture" if key in manifest["baseline_failures"] else "measure",
                        **{name: captured[name] for name in ("result", "canonical")}))
                if key in manifest["baseline_failures"]:
                    if process == 0:
                        results.append(dict(key=key, process=0, baseline_failure=True, responses=pair,
                                            versions=[version, candidate_version],
                                            pids=[run * 1000 + 100, run * 1000 + 101]))
                    continue
                results.append(dict(key=key, process=process, responses=pair))
                for batch in range(manifest["batches"]):
                    samples.append(dict(key=key, language="python", process=process, batch=batch,
                                        iterations=1, order=[0, 1], ok=True, correct=True,
                                        baseline_ns=100 + process, candidate_ns=.8 * (100 + process),
                                        result_hashes=[digest(response["result"]) for response in pair],
                                        rss=[1024, 1024], peak_rss=[1024, 1024]))
        meta = dict(complete=True, kind="candidate", manifest_sha256=digest(manifest),
                    input_sha256=input_digest(manifest), source_before={"baseline": base_source, "candidate": candidate_source},
                    source_after={"baseline": base_source, "candidate": candidate_source},
                    harness=harness, machine=metadata["baseline"]["machine"], versions=process_versions,
                    started_unix=1000 * run, finished_unix=1000 * run + 100, run_id=f"run-{run}")
        write(directories[f"run-{run}"] / "metadata.json", meta)
        write(directories[f"run-{run}"] / "analysis.json", {"pass": False, "reasons": ["Do not trust this file"]})
        write_rows(directories[f"run-{run}"] / "samples.jsonl", samples)
        write_rows(directories[f"run-{run}"] / "results.jsonl", results)
    return manifest, directories


def run_audit(manifest, directories, runs=None):
    return audit(manifest, runs or [directories["run-1"], directories["run-2"]],
                 directories["baseline-capture"], directories["candidate-capture"],
                 directories["baseline-profiles"], directories["candidate-profiles"])


def change_json(path, change):
    value = json.loads(path.read_text())
    change(value)
    write(path, value)


def change_rows(path, change):
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    change(rows)
    write_rows(path, rows)


def test_complete_two_run_gate_uses_raw_samples_and_earlier_capture_design(tmp_path):
    manifest, directories = make_evidence(tmp_path)
    report = run_audit(manifest, directories)
    assert report["pass"], report["reasons"]
    assert report["scope"] == "two_run_acceptance"
    assert len(report["evidence"]["runs"]) == 2
    assert all(run["analysis"]["scope"] == "single_run" for run in report["evidence"]["runs"])
    assert len(report["evidence"]["runs"][0]["rss_growth"]) == 8


@pytest.mark.parametrize("fault", ["one-run", "same-directory", "same-id", "overlap", "same-pid",
                                   "missing-process", "source", "machine", "dependency", "presolve",
                                   "incomplete", "input", "missing-result", "forged-analysis"])
def test_two_run_faults_fail_closed(tmp_path, fault):
    manifest, directories = make_evidence(tmp_path)
    path = directories["run-2"]
    if fault == "one-run":
        report = run_audit(manifest, directories, [directories["run-1"]])
    elif fault == "same-directory":
        report = run_audit(manifest, directories, [directories["run-1"]] * 2)
    else:
        if fault == "same-id": change_json(path / "metadata.json", lambda x: x.update(run_id="run-1"))
        elif fault == "overlap": change_json(path / "metadata.json", lambda x: x.update(started_unix=1050))
        elif fault == "same-pid": change_json(path / "metadata.json", lambda x: x["versions"][0].update(pids=[1000, 1001]))
        elif fault == "missing-process": change_json(path / "metadata.json", lambda x: x["versions"].pop())
        elif fault == "source": change_json(path / "metadata.json", lambda x: x["source_after"]["candidate"].update(head="f" * 40))
        elif fault == "machine": change_json(path / "metadata.json", lambda x: x["machine"].update(cpu_count=16))
        elif fault == "dependency": change_json(path / "metadata.json", lambda x: x["versions"][0]["versions"][1]["dependencies"].update(highspy="2"))
        elif fault == "presolve": change_json(path / "metadata.json", lambda x: x["versions"][0]["versions"][1]["settings"].update(presolve="off"))
        elif fault == "incomplete": change_json(path / "metadata.json", lambda x: x.update(complete=False))
        elif fault == "input": change_json(path / "metadata.json", lambda x: x.update(input_sha256="wrong"))
        elif fault == "missing-result": change_rows(path / "results.jsonl", lambda x: x.pop())
        elif fault == "forged-analysis":
            write(path / "analysis.json", {"pass": True, "scope": "single_run"})
            change_rows(path / "samples.jsonl", lambda rows: [row.update(candidate_ns=2 * row["baseline_ns"]) for row in rows])
        report = run_audit(manifest, directories)
    assert not report["pass"], fault


@pytest.mark.parametrize("fault", ["missing-row", "extra-row", "duplicate-row", "canonical", "full-result",
                                   "mismatch", "oracle-flag", "input", "source", "incomplete", "fixture-hash",
                                   "baseline-fingerprint", "case-spec", "missing-oracle-inventory"])
def test_capture_faults_fail_closed(tmp_path, fault):
    manifest, directories = make_evidence(tmp_path)
    path = directories["candidate-capture"]
    if fault == "missing-row": change_rows(path / "vectors.jsonl", lambda x: x.pop())
    elif fault == "extra-row": change_rows(path / "vectors.jsonl", lambda x: x.append(dict(x[0], id="extra")))
    elif fault == "duplicate-row": change_rows(path / "vectors.jsonl", lambda x: x.append(x[0]))
    elif fault == "canonical": change_rows(path / "vectors.jsonl", lambda x: x[0]["canonical"].update(selected=[0]))
    elif fault == "full-result": change_rows(path / "vectors.jsonl", lambda x: x[0]["result"]["stats"].update(num_edges=1))
    elif fault == "mismatch": change_rows(path / "vectors.jsonl", lambda x: x[0].update(mismatch=["stats"]))
    elif fault == "oracle-flag": change_rows(path / "vectors.jsonl", lambda x: x[0].update(oracle_fixture=False))
    elif fault == "case-spec": change_rows(path / "vectors.jsonl", lambda x: x[0]["case"]["input"].update(groups=["wrong"]))
    elif fault == "input": change_json(path / "metadata.json", lambda x: x.update(input_sha256="wrong"))
    elif fault == "source": change_json(path / "metadata.json", lambda x: x["source_after"].update(tree="f" * 40))
    elif fault == "incomplete": change_json(path / "metadata.json", lambda x: x.update(complete=False))
    elif fault == "fixture-hash": change_json(path / "metadata.json", lambda x: x["fixture_sha256"].update(reduce="wrong"))
    elif fault == "baseline-fingerprint": manifest["baseline_capture_sha256"] = "wrong"
    elif fault == "missing-oracle-inventory":
        # Omitting both the rows and their claimed inventory cannot hide an oracle.
        for variant in ("baseline", "candidate"):
            directory = directories[f"{variant}-capture"]
            change_rows(directory / "vectors.jsonl", lambda x: x.pop(0))
            change_json(directory / "metadata.json", lambda x: (x["expected_keys"].pop(0), x.update(checked=x["checked"] - 1)))
    report = run_audit(manifest, directories)
    assert not report["pass"], fault


@pytest.mark.parametrize("fault", ["missing-preprocess", "missing-cap", "package-error", "cap-kind", "case-spec",
                                   "incomplete-preprocess", "memory", "wall", "baseline-fingerprint", "source", "input"])
def test_resource_faults_fail_closed(tmp_path, fault):
    manifest, directories = make_evidence(tmp_path)
    path = directories["candidate-profiles"]
    if fault == "missing-preprocess": change_rows(path / "profiles.jsonl", lambda x: x.pop(-2))
    elif fault == "missing-cap": change_rows(path / "profiles.jsonl", lambda x: x.pop())
    elif fault == "package-error": change_rows(path / "profiles.jsonl", lambda x: x[-1]["response"].update(error={"kind": "ModuleNotFoundError", "message": "No module named highs"}))
    elif fault == "cap-kind": change_rows(path / "profiles.jsonl", lambda x: x[-1]["response"]["error"].update(kind="OtherError"))
    elif fault == "case-spec": change_rows(path / "profiles.jsonl", lambda x: x[-2]["case"]["options"].update(max_cliques=None))
    elif fault == "incomplete-preprocess": change_rows(path / "profiles.jsonl", lambda x: x[-2]["response"]["metrics"].update(solve_count=1))
    elif fault == "memory": change_rows(path / "profiles.jsonl", lambda x: x[-2].update(peak_rss=10 ** 15))
    elif fault == "wall": change_rows(path / "profiles.jsonl", lambda x: x[-2]["response"]["phases_ns"].update(total=31 * 10 ** 9))
    elif fault == "baseline-fingerprint": manifest["profile_sha256"] = "wrong"
    elif fault == "source": change_json(path / "metadata.json", lambda x: x["source_after"].update(head="f" * 40))
    elif fault == "input": change_json(path / "metadata.json", lambda x: x.update(input_sha256="wrong"))
    assert not run_audit(manifest, directories)["pass"], fault


@pytest.mark.parametrize("fault", ["missing", "negative", "nonfinite", "over-limit", "growth", "result-hash"])
def test_sample_memory_and_result_evidence(tmp_path, fault):
    manifest, directories = make_evidence(tmp_path)
    path = directories["run-2"] / "samples.jsonl"
    if fault == "missing": change_rows(path, lambda rows: rows[0].pop("rss"))
    elif fault == "negative": change_rows(path, lambda rows: rows[0].update(rss=[-1, 1024]))
    elif fault == "nonfinite": change_rows(path, lambda rows: rows[0].update(peak_rss=[float("nan"), 1024]))
    elif fault == "over-limit": change_rows(path, lambda rows: rows[0].update(rss=[1024, 10 ** 15]))
    elif fault == "growth":
        change_rows(path, lambda rows: rows[-1].update(rss=[1024, 33 * 1024 ** 2], peak_rss=[1024, 33 * 1024 ** 2]))
    elif fault == "result-hash": change_rows(path, lambda rows: rows[0].update(result_hashes=["wrong", "wrong"]))
    assert not run_audit(manifest, directories)["pass"], fault


def test_declared_bounded_failure_remains_unscored(tmp_path):
    manifest, directories = make_evidence(tmp_path, baseline_failure=True)
    report = run_audit(manifest, directories)
    assert report["pass"], report["reasons"]
    assert report["evidence"]["baseline_failures_unscored"] == manifest["baseline_failures"]


def test_new_success_requires_independent_oracle(tmp_path):
    manifest, directories = make_evidence(tmp_path, baseline_failure=True, new_success=True)
    report = run_audit(manifest, directories)
    assert not report["pass"]
    assert any("independent matching oracle" in reason for reason in report["reasons"])


def test_new_unscored_success_can_match_independent_fixture(tmp_path):
    manifest, directories = make_evidence(tmp_path, baseline_failure=True, new_success=True, oracle_match=True)
    report = run_audit(manifest, directories)
    assert report["pass"], report["reasons"]


def test_missing_file_returns_failure_report(tmp_path):
    manifest, directories = make_evidence(tmp_path)
    (directories["run-2"] / "samples.jsonl").unlink()
    assert not run_audit(manifest, directories)["pass"]


def test_recorded_driver_hashes_use_git_commit_bytes():
    root = Path(__file__).resolve().parents[1]
    head = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    tree = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD^{tree}"], text=True).strip()
    binding = dict(path=str(root), head=head, tree=tree, status="", build_files={}, lock_files={})
    hashes = recorded_driver_hashes(binding, ["python", "r", "js"])
    assert len(hashes) == 3
    for filename, value in hashes.items():
        raw = subprocess.check_output(["git", "-C", str(root), "show", f"{head}:{filename}"])
        assert value == hashlib.sha256(raw).hexdigest()


def test_separate_stage_harness_commits_with_equal_driver_bytes_are_allowed(tmp_path):
    manifest, directories = make_evidence(tmp_path)
    for name in ("baseline-capture", "candidate-capture", "baseline-profiles", "candidate-profiles"):
        change_json(directories[name] / "metadata.json", lambda x: x["harness"].update(head="9" * 40))
    report = run_audit(manifest, directories)
    assert report["pass"], report["reasons"]


def test_two_timed_runs_require_the_same_harness(tmp_path):
    manifest, directories = make_evidence(tmp_path)
    change_json(directories["run-2"] / "metadata.json", lambda x: x["harness"].update(head="9" * 40))
    assert not run_audit(manifest, directories)["pass"]


def test_changed_driver_bytes_cannot_hide_in_a_different_stage(tmp_path, monkeypatch):
    manifest, directories = make_evidence(tmp_path)
    change_json(directories["candidate-profiles"] / "metadata.json", lambda x: x["harness"].update(head="9" * 40))
    monkeypatch.setattr(gates, "_driver_hashes", lambda binding, languages: {
        gates.DRIVERS[language]: digest("changed" if binding["head"] == "9" * 40 else language)
        for language in languages})
    assert not run_audit(manifest, directories)["pass"]
