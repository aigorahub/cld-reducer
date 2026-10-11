"""Synthetic evidence checks for the final gate. No runtime timing is performed."""

import copy
import hashlib
import json
import subprocess
from pathlib import Path

import gates
import pytest
from analysis import analyze, select_gain_targets
from cases import job_key, jobs, multipartite
from common import digest, input_digest
from gates import audit
from profile_outcomes import PREPROCESS_PHASES, UNUSED_PHASES, freeze_preprocess_failures
from test_resource_evidence import write_resource_fixture

recorded_driver_hashes = gates._driver_hashes
recorded_measurement_hashes = gates._measurement_hashes


@pytest.fixture(autouse=True)
def synthetic_driver_source(monkeypatch):
    # Other tests use synthetic source commits. Exercise Git lookup separately.
    monkeypatch.setattr(
        gates,
        "_driver_hashes",
        lambda binding, languages: {
            gates.DRIVERS[language]: digest(language) for language in languages
        },
    )
    monkeypatch.setattr(
        gates,
        "_measurement_hashes",
        lambda binding, languages: {
            **gates._driver_hashes(binding, languages),
            **{
                name: digest(name)
                for name in ("benchmarks/run.py", "benchmarks/common.py", "benchmarks/analysis.py")
            },
            "benchmarks/process_guard.py": None,
        },
    )


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value) + "\n")


def write_rows(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))


def result(group="v", method="letter_minimum"):
    return dict(
        groups=[group],
        assignments=[["A"]],
        letters=["A"],
        adjacency=[[True]],
        method=method,
        relationship_preserved=True,
        rows=[dict(group=group, letters="A", assignments="A")],
        stats=dict(
            assignments_before=1,
            assignments_after=1,
            reduction_pct=0,
            num_letters_before=1,
            num_letters_after=1,
            num_groups=1,
            num_edges=0,
            solver_status="Optimal",
            objective=1,
        ),
    )


def solver_observations(language, settings, count):
    values = copy.deepcopy(settings)
    values.pop("thread_setting", None)
    values.pop("time_limit", None)
    values["random_seed"] = 0
    observed = dict(available=count > 0, records=[], source="Synthetic native option read")
    if language == "r":
        values["r_global_threads"] = values["threads"]
    elif language == "js":
        values.pop("threads")
        values.pop("parallel", None)
        observed.update(
            thread_constraint=dict(kind="single_threaded_api", threads=1, native_option=False),
            thread_control="The test models the single-threaded package API.",
        )
    observed["records"] = [dict(solve=i + 1, values=copy.deepcopy(values)) for i in range(count)]
    return observed


def preprocess_response(case, language, settings):
    vertices = len(case["input"]["adjacency"])
    parts = vertices // 3
    edges = vertices * (vertices - 3) // 2
    sigma = case["options"]["method"] == "assignment_minimum"
    decisions = parts * 3**parts if sigma else 3**parts
    auxiliary = parts * (parts - 1) // 2 * 3**parts if sigma else 0
    return dict(
        ok=True,
        action="preprocess",
        phases_ns={
            **dict.fromkeys(PREPROCESS_PHASES, 10),
            **dict.fromkeys(UNUSED_PHASES),
            "total": 100,
        },
        metrics=dict(
            solve_count=0,
            solver_total_ns=0,
            solver_settings=solver_observations(language, settings, 0),
            vertices_before=vertices,
            vertices_after=vertices,
            edges=edges,
            maximal_cliques=3**parts,
            decision_variables=decisions,
            auxiliary_variables=auxiliary,
            constraints=vertices + edges + 2 * auxiliary,
            nonzeros=decisions + 5 * auxiliary
            if sigma
            else 3**parts * (parts + parts * (parts - 1) // 2),
            essential_decisions=0,
            essential_cover=False,
            canonical_feasible_trials=0,
            canonical_infeasible_trials=0,
            selected=None,
            objective=None,
            final_zero_decisions=None,
        ),
    )


def make_evidence(
    tmp_path,
    *,
    baseline_failure=False,
    new_success=False,
    oracle_match=False,
    language="python",
    cases_per_split=5,
    preprocess_failure=None,
    memory_growth_tolerance_mb=32,
):
    base_source = dict(
        path=str(tmp_path / "source"),
        head="a" * 40,
        tree="b" * 40,
        status="",
        build_files={},
        lock_files={},
    )
    if language == "js":
        # Synthetic proof is explicit. These tests do not compile a runtime.
        base_source.update(
            build_files={"js/dist/index.js": "0" * 64},
            build_verified=True,
            dependency_files={
                "highs/package.json": "1" * 64,
                "highs/build/highs.mjs": "2" * 64,
                "highs/build/highs.wasm": "3" * 64,
            },
            compiler_files={"typescript/bin/tsc": "4" * 64, "typescript/lib/tsc.js": "5" * 64},
        )
    candidate_source = dict(base_source, head="d" * 40, tree="e" * 40)
    harness = dict(base_source, head="c" * 40, tree="f" * 40)
    version = dict(
        ok=True,
        action="version",
        language=language,
        runtime="3.12",
        dependencies={"highspy": "1.14"},
        solver={"name": "HiGHS", "version": "1.14"},
        source_head=base_source["head"],
        module_load_ns=10,
        settings=dict(
            presolve="off" if language == "r" else "on",
            threads=1,
            mip_rel_gap=0,
            mip_abs_gap=0,
            primal_feasibility_tolerance=1e-9,
            mip_feasibility_tolerance=1e-9,
            output_flag=False,
        ),
    )
    if language == "r":
        version["settings"].pop("output_flag")
        version["settings"]["parallel"] = "off"
    candidate_version = dict(version, source_head=candidate_source["head"], module_load_ns=20)
    expected = dict(
        groups=["v"],
        assignments={"v": ["A"]},
        letters={"v": "A"},
        stats={
            name: value
            for name, value in result()["stats"].items()
            if name not in ("reduction_pct", "objective", "solver_status")
        },
        solver_status="Optimal",
        objective=1,
        method="letter_minimum",
        relationship_preserved=True,
        reduction_pct={"numerator": 0, "denominator": 1},
    )
    fixture_cases, hashes = [], {}
    for name in ("reduce", "reduce_letter_minimum", "reduce_weighted"):
        case = dict(
            id="one",
            call="adjacency",
            input={"adjacency": [[1]], "groups": ["v"]},
            options={},
            expected=copy.deepcopy(expected),
        )
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
    cases = [
        dict(
            id=f"{split}/case-{i}",
            split=split,
            classification="ordinary",
            tier="solve",
            wall_seconds=30,
            call="adjacency",
            options={},
            input={"adjacency": [[1]], "groups": [f"{split}-{i}"]},
        )
        for split in ("development", "validation")
        for i in range(cases_per_split)
    ]
    if baseline_failure:
        cases.append(
            dict(
                id="development/blocked",
                split="development",
                classification="stress",
                tier="solve",
                wall_seconds=30,
                call="adjacency",
                options={},
                input={"adjacency": [[1]], "groups": ["v" if oracle_match else "blocked"]},
            )
        )
    for parts in (6, 7, 8, 9):
        cases.append(
            dict(
                id=f"bounded/multipartite-{parts}x3",
                split="bounded",
                classification="stress",
                tier="expected-error" if parts == 9 else "preprocess",
                wall_seconds=30,
                call="adjacency",
                input={"adjacency": multipartite(parts)},
                options={},
            )
        )
    manifest = dict(
        schema_version=1,
        case_generator="cases.py:1",
        cases=cases,
        methods=["letter_minimum"],
        languages=[language],
        presolve={language: version["settings"]["presolve"]},
        memory_limit_mb=8192,
        memory_growth_tolerance_mb=memory_growth_tolerance_mb,
        candidate="essential-cover-certificate",
        processes=8,
        warmup_batches=3,
        batches=9,
        bootstrap_resamples=10000,
        bootstrap_seed=31,
        order_seed=17,
        frozen=True,
        baseline_source=base_source,
        pilot_source=copy.deepcopy(base_source),
        calibration_harness=harness,
        baseline_versions={language: version},
        baseline_failures=[],
        iterations={},
        gain_targets={},
    )
    solve_cases = list(jobs(manifest))
    keys = [job_key(language, case) for case in solve_cases]
    manifest["iterations"] = dict.fromkeys(keys, 1)
    manifest["gain_targets"] = {language + "|letter_minimum": keys[:10]}
    if baseline_failure:
        manifest["baseline_failures"] = [keys[-1]]
    failure = dict(
        ok=False, action="capture", error={"kind": "SolverError", "message": "Time limit reached"}
    )
    directories = {
        name: tmp_path / name
        for name in (
            "baseline-capture",
            "candidate-capture",
            "baseline-profiles",
            "candidate-profiles",
            "run-1",
            "run-2",
            "calibration",
        )
    }
    captures, profiles, metadata = {}, {}, {}
    for variant, source, runtime_version in (
        ("baseline", base_source, version),
        ("candidate", candidate_source, candidate_version),
    ):
        rows = []
        for case in fixture_cases + solve_cases:
            method = case["options"]["method"]
            row = dict(
                language=language,
                id=case["id"],
                method=method,
                case=case,
                oracle_fixture=case["id"].startswith("fixture/"),
                mismatch=[],
            )
            if job_key(language, case) in manifest["baseline_failures"] and not (
                variant == "candidate" and new_success
            ):
                row["response"] = failure
            else:
                row.update(
                    result=result(case["input"]["groups"][0], method),
                    canonical={"selected": [1], "objective": 1},
                )
            rows.append(row)
        captures[variant] = rows
        capture_map = {job_key(row["language"], row["case"]): row for row in rows}
        profile_rows = []
        for case in jobs(manifest, tiers=("solve", "preprocess", "expected-error")):
            key = job_key(language, case)
            if case["tier"] == "expected-error":
                response = dict(
                    ok=False,
                    action="preprocess",
                    error={
                        "kind": "SolverError",
                        "message": "maximal clique enumeration exceeded max_cliques=10000",
                    },
                )
            elif case["tier"] == "preprocess":
                response = preprocess_response(case, language, version["settings"])
                if preprocess_failure and case["id"].endswith("multipartite-8x3"):
                    response = dict(
                        ok=False,
                        action="preprocess",
                        error={
                            "kind": "ExternalLimit",
                            "message": "Driver " + preprocess_failure + " limit exceeded",
                        },
                    )
            elif "response" in capture_map[key]:
                response = dict(failure, action="profile")
            else:
                response = dict(
                    ok=True,
                    action="profile",
                    phases_ns={"total": 100},
                    metrics={
                        "essential_cover": True,
                        "solver_total_ns": 40,
                        "solve_count": 1,
                        "solver_settings": solver_observations(language, version["settings"], 1),
                        "decision_variables": 1,
                        "essential_decisions": 1,
                        "canonical_feasible_trials": 0,
                        "canonical_infeasible_trials": 0,
                        "selected": [1],
                        "objective": 1,
                    },
                    **{name: capture_map[key][name] for name in ("result", "canonical")},
                )
            peak = (
                (manifest["memory_limit_mb"] + 1) * 1024**2
                if (response.get("error", {}).get("message") == "Driver memory limit exceeded")
                else 1024
            )
            profile_rows.append(dict(key=key, case=case, response=response, peak_rss=peak))
        profiles[variant] = profile_rows
        meta = dict(
            source=source,
            source_after=copy.deepcopy(source),
            harness=harness,
            harness_after=copy.deepcopy(harness),
            machine={"platform": "test", "cpu_count": 8, "memory_bytes": 16384 * 1024**2},
            complete=True,
            input_sha256=input_digest(manifest),
            versions={language: runtime_version},
            manifest_sha256="earlier sampling design",
            fixture_sha256=hashes,
            checked=len(rows),
            failures=[],
            expected_keys=[
                {name: row[name] for name in ("language", "id", "method", "oracle_fixture")}
                for row in rows
            ],
        )
        metadata[variant] = meta
    for variant in ("baseline", "candidate"):
        for kind in ("capture", "profiles"):
            path = directories[f"{variant}-{kind}"]
            values = captures[variant] if kind == "capture" else profiles[variant]
            meta = copy.deepcopy(metadata[variant])
            records = write_resource_fixture(path, meta, values, kind)
            write_rows(path / ("vectors.jsonl" if kind == "capture" else "profiles.jsonl"), values)
            write(path / "metadata.json", meta)
            if variant == "baseline":
                field = (
                    "baseline_capture_resource_sha256"
                    if kind == "capture"
                    else "profile_resource_sha256"
                )
                manifest[field] = digest(records)
    manifest["baseline_capture_sha256"] = digest(captures["baseline"])
    manifest["profile_sha256"] = digest(profiles["baseline"])
    manifest["baseline_preprocess_failures"] = freeze_preprocess_failures(
        manifest, profiles["baseline"]
    )
    manifest["gain_targets"] = select_gain_targets(manifest, profiles["baseline"])
    calibration_manifest = copy.deepcopy(manifest)
    for name in (
        "baseline_source",
        "calibration_harness",
        "baseline_capture_sha256",
        "profile_sha256",
        "baseline_preprocess_failures",
        "candidate",
    ):
        calibration_manifest.pop(name)
    calibration_manifest.update(frozen=False, gain_targets={})
    calibration_samples = [
        dict(
            key=key,
            process=process,
            batch=batch,
            iterations=1,
            ok=True,
            correct=True,
            baseline_ns=100 + process,
            candidate_ns=100 + process,
        )
        for key in keys
        if key not in manifest["baseline_failures"]
        for process in range(manifest["processes"])
        for batch in range(manifest["batches"])
    ]
    calibration_metadata = dict(
        complete=True,
        kind="calibration",
        manifest_sha256=digest(calibration_manifest),
        input_sha256=input_digest(calibration_manifest),
        source_before={"baseline": base_source, "candidate": base_source},
        source_after={"baseline": base_source, "candidate": base_source},
        harness=harness,
        harness_after=copy.deepcopy(harness),
        machine=metadata["baseline"]["machine"],
        versions=[
            dict(
                language=language,
                process=process,
                versions=[version, version],
                pids=[100 + 2 * process, 101 + 2 * process],
            )
            for process in range(manifest["processes"])
        ],
        started_unix=100,
        finished_unix=200,
        run_id="calibration",
    )
    calibration_results = [
        dict(
            key=key,
            process=0,
            baseline_failure=True,
            pids=[10000 + 2 * index, 10001 + 2 * index],
            responses=[
                next(
                    row["response"]
                    for row in captures["baseline"]
                    if job_key(language, row["case"]) == key
                )
            ]
            * 2,
        )
        for index, key in enumerate(manifest["baseline_failures"])
    ]
    calibration_resources = write_resource_fixture(
        directories["calibration"], calibration_metadata, calibration_results, "compare"
    )
    write_rows(directories["calibration"] / "results.jsonl", calibration_results)
    calibration_report = analyze(
        calibration_manifest,
        calibration_metadata,
        calibration_samples,
        calibration_targets=manifest["gain_targets"],
    )
    assert calibration_report["pass"], calibration_report["reasons"]
    for name, value in (
        ("manifest", calibration_manifest),
        ("metadata", calibration_metadata),
        ("analysis", calibration_report),
    ):
        write(directories["calibration"] / f"{name}.json", value)
    write_rows(directories["calibration"] / "samples.jsonl", calibration_samples)
    manifest.update(
        calibration_manifest_sha256=digest(calibration_manifest),
        calibration_metadata_sha256=digest(calibration_metadata),
        calibration_samples_sha256=digest(calibration_samples),
        calibration_sha256=digest(calibration_report),
        calibration_resource_sha256=digest(calibration_resources),
    )
    for run in (1, 2):
        process_versions, samples, results = [], [], []
        for process in range(manifest["processes"]):
            process_versions.append(
                dict(
                    language=language,
                    process=process,
                    versions=[version, candidate_version],
                    pids=[run * 1000 + 2 * process, run * 1000 + 2 * process + 1],
                )
            )
            for case in solve_cases:
                key = job_key(language, case)
                pair = []
                for variant in ("baseline", "candidate"):
                    captured = next(row for row in captures[variant] if row["id"] == case["id"])
                    pair.append(
                        captured["response"]
                        if "response" in captured
                        else dict(
                            ok=True,
                            action="capture" if key in manifest["baseline_failures"] else "measure",
                            **{name: captured[name] for name in ("result", "canonical")},
                        )
                    )
                if key in manifest["baseline_failures"]:
                    if process == 0:
                        results.append(
                            dict(
                                key=key,
                                process=0,
                                baseline_failure=True,
                                responses=pair,
                                versions=[version, candidate_version],
                                pids=[run * 1000 + 100, run * 1000 + 101],
                            )
                        )
                    continue
                results.append(dict(key=key, process=process, responses=pair))
                for batch in range(manifest["batches"]):
                    samples.append(
                        dict(
                            key=key,
                            language=language,
                            process=process,
                            batch=batch,
                            iterations=1,
                            order=[0, 1],
                            ok=True,
                            correct=True,
                            baseline_ns=100 + process,
                            candidate_ns=0.8 * (100 + process),
                            result_hashes=[digest(response["result"]) for response in pair],
                            rss=[1024, 1024],
                            peak_rss=[1024, 1024],
                        )
                    )
        meta = dict(
            complete=True,
            kind="candidate",
            manifest_sha256=digest(manifest),
            input_sha256=input_digest(manifest),
            source_before={"baseline": base_source, "candidate": candidate_source},
            source_after={"baseline": base_source, "candidate": candidate_source},
            harness=harness,
            harness_after=copy.deepcopy(harness),
            machine=metadata["baseline"]["machine"],
            versions=process_versions,
            started_unix=1000 * run,
            finished_unix=1000 * run + 100,
            run_id=f"run-{run}",
        )
        write_resource_fixture(directories[f"run-{run}"], meta, results, "compare")
        write(directories[f"run-{run}"] / "metadata.json", meta)
        write(
            directories[f"run-{run}"] / "analysis.json",
            {"pass": False, "reasons": ["Do not trust this file"]},
        )
        write_rows(directories[f"run-{run}"] / "samples.jsonl", samples)
        write_rows(directories[f"run-{run}"] / "results.jsonl", results)
    return manifest, directories


def run_audit(manifest, directories, runs=None):
    return audit(
        manifest,
        runs or [directories["run-1"], directories["run-2"]],
        directories["baseline-capture"],
        directories["candidate-capture"],
        directories["baseline-profiles"],
        directories["candidate-profiles"],
        directories["calibration"],
    )


def change_json(path, change):
    value = json.loads(path.read_text())
    change(value)
    write(path, value)


def change_harness_head(metadata, head):
    for name in ("harness", "harness_after"):
        metadata[name]["head"] = head


def change_rows(path, change):
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    change(rows)
    write_rows(path, rows)


def bind_decision_manifest(manifest, directories):
    for name in ("run-1", "run-2"):
        change_json(
            directories[name] / "metadata.json",
            lambda meta: meta.update(manifest_sha256=digest(manifest)),
        )


def bind_calibration_files(manifest, directories):
    path = directories["calibration"]
    design = json.loads((path / "manifest.json").read_text())
    metadata = json.loads((path / "metadata.json").read_text())
    samples = [json.loads(line) for line in (path / "samples.jsonl").read_text().splitlines()]
    metadata.update(manifest_sha256=digest(design), input_sha256=input_digest(design))
    write(path / "metadata.json", metadata)
    manifest.update(
        calibration_manifest_sha256=digest(design),
        calibration_metadata_sha256=digest(metadata),
        calibration_samples_sha256=digest(samples),
        calibration_sha256=digest(
            analyze(design, metadata, samples, calibration_targets=manifest["gain_targets"])
        ),
    )
    bind_decision_manifest(manifest, directories)


@pytest.mark.parametrize("filename", ["manifest.json", "metadata.json", "samples.jsonl"])
def test_audit_requires_raw_calibration_files(tmp_path, filename):
    manifest, directories = make_evidence(tmp_path)
    (directories["calibration"] / filename).unlink()
    assert not run_audit(manifest, directories)["pass"]


def test_audit_recomputes_calibration_and_rejects_spurious_aa_speedup(tmp_path):
    manifest, directories = make_evidence(tmp_path)
    path = directories["calibration"]
    change_rows(
        path / "samples.jsonl",
        lambda rows: [row.update(candidate_ns=0.8 * row["baseline_ns"]) for row in rows],
    )
    write(path / "analysis.json", {"pass": True})
    bind_calibration_files(manifest, directories)
    report = run_audit(manifest, directories)
    assert not report["pass"]
    assert any("Raw A/A calibration failed" in reason for reason in report["reasons"])
    assert any(
        "A/A equivalence" in reason
        for reason in report["evidence"]["calibration"]["analysis"]["reasons"]
    )


@pytest.mark.parametrize("part", ["samples", "metadata", "manifest"])
def test_raw_calibration_hashes_must_match_freeze(tmp_path, part):
    manifest, directories = make_evidence(tmp_path)
    path = directories["calibration"]
    if part == "samples":
        change_rows(
            path / "samples.jsonl",
            lambda rows: rows[0].update(candidate_ns=rows[0]["baseline_ns"] * 1.001),
        )
    else:
        change_json(path / f"{part}.json", lambda value: value.update(extra="changed after freeze"))
    report = run_audit(manifest, directories)
    assert not report["pass"]
    assert f"Calibration evidence differs: calibration_{part}_sha256" in report["reasons"]


@pytest.mark.parametrize(
    "field",
    [
        "processes",
        "warmup_batches",
        "batches",
        "iterations",
        "bootstrap_resamples",
        "bootstrap_seed",
        "order_seed",
    ],
)
def test_calibration_and_decision_sampling_design_must_match(tmp_path, field):
    manifest, directories = make_evidence(tmp_path)
    if field == "iterations":
        key = next(iter(manifest[field]))
        manifest[field][key] += 1
    else:
        manifest[field] += 1
    bind_decision_manifest(manifest, directories)
    report = run_audit(manifest, directories)
    assert not report["pass"]
    assert (
        "Calibration sampling design differs from the frozen decision design" in report["reasons"]
    )


@pytest.mark.parametrize("finish", [1500, None, -1])
def test_calibration_must_end_before_both_candidate_runs(tmp_path, finish):
    manifest, directories = make_evidence(tmp_path)
    change_json(
        directories["calibration"] / "metadata.json", lambda meta: meta.update(finished_unix=finish)
    )
    bind_calibration_files(manifest, directories)
    report = run_audit(manifest, directories)
    assert not report["pass"]
    assert any("calibration did not finish" in reason for reason in report["reasons"])


def test_audit_rejects_omitted_eligible_case_even_when_declared_group_still_passes(tmp_path):
    manifest, directories = make_evidence(tmp_path, cases_per_split=6)
    manifest["gain_targets"]["python|letter_minimum"].pop(0)
    bind_decision_manifest(manifest, directories)
    report = run_audit(manifest, directories)
    assert not report["pass"]
    assert "Frozen gain targets differ from the full eligible profile set" in report["reasons"]
    assert all(run["analysis"]["pass"] for run in report["evidence"]["runs"])


def test_audit_requires_eligibility_metrics_in_bound_profiles(tmp_path):
    manifest, directories = make_evidence(tmp_path)
    path = directories["baseline-profiles"] / "profiles.jsonl"
    change_rows(path, lambda rows: rows[0]["response"]["metrics"].pop("essential_cover"))
    manifest["profile_sha256"] = digest(
        [json.loads(line) for line in path.read_text().splitlines()]
    )
    bind_decision_manifest(manifest, directories)
    report = run_audit(manifest, directories)
    assert not report["pass"]
    assert any("eligibility metrics" in reason for reason in report["reasons"])


@pytest.mark.parametrize(
    "stage", ["baseline-capture", "candidate-profiles", "calibration", "run-1"]
)
@pytest.mark.parametrize("fault", ["missing", "changed"])
def test_audit_rejects_harness_change_during_any_collection(tmp_path, stage, fault):
    manifest, directories = make_evidence(tmp_path)

    def change(meta):
        if fault == "missing":
            meta.pop("harness_after")
        else:
            meta["harness_after"]["head"] = "9" * 40

    change_json(directories[stage] / "metadata.json", change)
    report = run_audit(manifest, directories)
    assert not report["pass"]
    assert any(
        "harness" in reason.lower() and ("collection" in reason or "changed" in reason)
        for reason in report["reasons"]
    )


def test_complete_two_run_gate_uses_raw_samples_and_earlier_capture_design(tmp_path):
    manifest, directories = make_evidence(tmp_path)
    report = run_audit(manifest, directories)
    assert report["pass"], report["reasons"]
    assert report["scope"] == "two_run_acceptance"
    assert len(report["evidence"]["runs"]) == 2
    assert all(run["analysis"]["scope"] == "single_run" for run in report["evidence"]["runs"])
    assert len(report["evidence"]["runs"][0]["rss_growth"]) == 8


@pytest.mark.parametrize(
    "fault",
    [
        "one-run",
        "same-directory",
        "same-id",
        "overlap",
        "same-pid",
        "missing-process",
        "source",
        "machine",
        "dependency",
        "presolve",
        "incomplete",
        "input",
        "missing-result",
        "forged-analysis",
    ],
)
def test_two_run_faults_fail_closed(tmp_path, fault):
    manifest, directories = make_evidence(tmp_path)
    path = directories["run-2"]
    if fault == "one-run":
        report = run_audit(manifest, directories, [directories["run-1"]])
    elif fault == "same-directory":
        report = run_audit(manifest, directories, [directories["run-1"]] * 2)
    else:
        if fault == "same-id":
            change_json(path / "metadata.json", lambda x: x.update(run_id="run-1"))
        elif fault == "overlap":
            change_json(path / "metadata.json", lambda x: x.update(started_unix=1050))
        elif fault == "same-pid":
            change_json(
                path / "metadata.json", lambda x: x["versions"][0].update(pids=[1000, 1001])
            )
        elif fault == "missing-process":
            change_json(path / "metadata.json", lambda x: x["versions"].pop())
        elif fault == "source":
            change_json(
                path / "metadata.json",
                lambda x: x["source_after"]["candidate"].update(head="f" * 40),
            )
        elif fault == "machine":
            change_json(path / "metadata.json", lambda x: x["machine"].update(cpu_count=16))
        elif fault == "dependency":
            change_json(
                path / "metadata.json",
                lambda x: x["versions"][0]["versions"][1]["dependencies"].update(highspy="2"),
            )
        elif fault == "presolve":
            change_json(
                path / "metadata.json",
                lambda x: x["versions"][0]["versions"][1]["settings"].update(presolve="off"),
            )
        elif fault == "incomplete":
            change_json(path / "metadata.json", lambda x: x.update(complete=False))
        elif fault == "input":
            change_json(path / "metadata.json", lambda x: x.update(input_sha256="wrong"))
        elif fault == "missing-result":
            change_rows(path / "results.jsonl", lambda x: x.pop())
        elif fault == "forged-analysis":
            write(path / "analysis.json", {"pass": True, "scope": "single_run"})
            change_rows(
                path / "samples.jsonl",
                lambda rows: [row.update(candidate_ns=2 * row["baseline_ns"]) for row in rows],
            )
        report = run_audit(manifest, directories)
    assert not report["pass"], fault


@pytest.mark.parametrize(
    "fault",
    [
        "missing-row",
        "extra-row",
        "duplicate-row",
        "canonical",
        "full-result",
        "mismatch",
        "oracle-flag",
        "input",
        "source",
        "incomplete",
        "fixture-hash",
        "baseline-fingerprint",
        "case-spec",
        "missing-oracle-inventory",
    ],
)
def test_capture_faults_fail_closed(tmp_path, fault):
    manifest, directories = make_evidence(tmp_path)
    path = directories["candidate-capture"]
    if fault == "missing-row":
        change_rows(path / "vectors.jsonl", lambda x: x.pop())
    elif fault == "extra-row":
        change_rows(path / "vectors.jsonl", lambda x: x.append(dict(x[0], id="extra")))
    elif fault == "duplicate-row":
        change_rows(path / "vectors.jsonl", lambda x: x.append(x[0]))
    elif fault == "canonical":
        change_rows(path / "vectors.jsonl", lambda x: x[0]["canonical"].update(selected=[0]))
    elif fault == "full-result":
        change_rows(path / "vectors.jsonl", lambda x: x[0]["result"]["stats"].update(num_edges=1))
    elif fault == "mismatch":
        change_rows(path / "vectors.jsonl", lambda x: x[0].update(mismatch=["stats"]))
    elif fault == "oracle-flag":
        change_rows(path / "vectors.jsonl", lambda x: x[0].update(oracle_fixture=False))
    elif fault == "case-spec":
        change_rows(
            path / "vectors.jsonl", lambda x: x[0]["case"]["input"].update(groups=["wrong"])
        )
    elif fault == "input":
        change_json(path / "metadata.json", lambda x: x.update(input_sha256="wrong"))
    elif fault == "source":
        change_json(path / "metadata.json", lambda x: x["source_after"].update(tree="f" * 40))
    elif fault == "incomplete":
        change_json(path / "metadata.json", lambda x: x.update(complete=False))
    elif fault == "fixture-hash":
        change_json(path / "metadata.json", lambda x: x["fixture_sha256"].update(reduce="wrong"))
    elif fault == "baseline-fingerprint":
        manifest["baseline_capture_sha256"] = "wrong"
    elif fault == "missing-oracle-inventory":
        # Omitting both the rows and their claimed inventory cannot hide an oracle.
        for variant in ("baseline", "candidate"):
            directory = directories[f"{variant}-capture"]
            change_rows(directory / "vectors.jsonl", lambda x: x.pop(0))
            change_json(
                directory / "metadata.json",
                lambda x: (x["expected_keys"].pop(0), x.update(checked=x["checked"] - 1)),
            )
    report = run_audit(manifest, directories)
    assert not report["pass"], fault


@pytest.mark.parametrize(
    "fault",
    [
        "missing-preprocess",
        "missing-cap",
        "package-error",
        "cap-kind",
        "case-spec",
        "incomplete-preprocess",
        "memory",
        "wall",
        "baseline-fingerprint",
        "source",
        "input",
    ],
)
def test_resource_faults_fail_closed(tmp_path, fault):
    manifest, directories = make_evidence(tmp_path)
    path = directories["candidate-profiles"]
    if fault == "missing-preprocess":
        change_rows(path / "profiles.jsonl", lambda x: x.pop(-2))
    elif fault == "missing-cap":
        change_rows(path / "profiles.jsonl", lambda x: x.pop())
    elif fault == "package-error":
        change_rows(
            path / "profiles.jsonl",
            lambda x: x[-1]["response"].update(
                error={"kind": "ModuleNotFoundError", "message": "No module named highs"}
            ),
        )
    elif fault == "cap-kind":
        change_rows(
            path / "profiles.jsonl", lambda x: x[-1]["response"]["error"].update(kind="OtherError")
        )
    elif fault == "case-spec":
        change_rows(
            path / "profiles.jsonl", lambda x: x[-2]["case"]["options"].update(max_cliques=None)
        )
    elif fault == "incomplete-preprocess":
        change_rows(
            path / "profiles.jsonl", lambda x: x[-2]["response"]["metrics"].update(solve_count=1)
        )
    elif fault == "memory":
        change_rows(path / "profiles.jsonl", lambda x: x[-2].update(peak_rss=10**15))
    elif fault == "wall":
        change_rows(
            path / "profiles.jsonl",
            lambda x: x[-2]["response"]["phases_ns"].update(total=31 * 10**9),
        )
    elif fault == "baseline-fingerprint":
        manifest["profile_sha256"] = "wrong"
    elif fault == "source":
        change_json(path / "metadata.json", lambda x: x["source_after"].update(head="f" * 40))
    elif fault == "input":
        change_json(path / "metadata.json", lambda x: x.update(input_sha256="wrong"))
    assert not run_audit(manifest, directories)["pass"], fault


@pytest.mark.parametrize("failure", ["external wall", "memory"])
def test_frozen_preprocessing_failures_remain_visible_and_unscored(tmp_path, failure):
    manifest, directories = make_evidence(tmp_path, preprocess_failure=failure)
    report = run_audit(manifest, directories)
    assert report["pass"], report["reasons"]
    outcomes = report["evidence"]["profiles"]["candidate"]["preprocessing"]
    key = next(iter(manifest["baseline_preprocess_failures"]))
    assert outcomes[key] == {
        "baseline": manifest["baseline_preprocess_failures"][key],
        "outcome": manifest["baseline_preprocess_failures"][key],
        "scored": False,
    }


def test_new_preprocessing_completion_is_unscored(tmp_path):
    manifest, directories = make_evidence(tmp_path, preprocess_failure="external wall")
    key = next(iter(manifest["baseline_preprocess_failures"]))

    def complete(rows):
        row = next(row for row in rows if row["key"] == key)
        row["response"] = preprocess_response(
            row["case"], "python", manifest["baseline_versions"]["python"]["settings"]
        )

    change_rows(directories["candidate-profiles"] / "profiles.jsonl", complete)
    report = run_audit(manifest, directories)
    assert report["pass"], report["reasons"]
    assert report["evidence"]["profiles"]["candidate"]["preprocessing"][key] == {
        "baseline": "external_wall_timeout",
        "outcome": "completed_preprocessing",
        "scored": False,
    }


@pytest.mark.parametrize("known_failure", [False, True])
def test_new_or_changed_preprocessing_failure_rejects_candidate(tmp_path, known_failure):
    manifest, directories = make_evidence(
        tmp_path, preprocess_failure="external wall" if known_failure else None
    )

    def fail(rows):
        row = rows[-2]
        row["response"] = dict(
            ok=False,
            action="preprocess",
            error={
                "kind": "ExternalLimit",
                "message": "Driver memory limit exceeded",
            },
        )
        row["peak_rss"] = (manifest["memory_limit_mb"] + 1) * 1024**2

    path = directories["candidate-profiles"]
    change_rows(path / "profiles.jsonl", fail)
    rows = [json.loads(line) for line in (path / "profiles.jsonl").read_text().splitlines()]
    metadata = json.loads((path / "metadata.json").read_text())
    write_resource_fixture(path, metadata, rows, "profiles")
    write(path / "metadata.json", metadata)
    report = run_audit(manifest, directories)
    assert not report["pass"]
    assert any("outcome differs from frozen baseline" in reason for reason in report["reasons"])


@pytest.mark.parametrize("fault", ["missing", "gap", "threads", "extra"])
def test_audit_checks_native_options_and_compares_extra_stable_values(tmp_path, fault):
    manifest, directories = make_evidence(tmp_path)

    def alter(rows):
        metrics = rows[0]["response"]["metrics"]
        if fault == "missing":
            metrics.pop("solver_settings")
        else:
            values = metrics["solver_settings"]["records"][0]["values"]
            key, value = {
                "gap": ("mip_rel_gap", 0.1),
                "threads": ("threads", 2),
                "extra": ("random_seed", 1),
            }[fault]
            values[key] = value

    change_rows(directories["candidate-profiles"] / "profiles.jsonl", alter)
    report = run_audit(manifest, directories)
    assert not report["pass"]
    assert any("solver settings" in reason.lower() for reason in report["reasons"])


@pytest.mark.parametrize("fault", [None, "cover", "selected", "essential_count", "time", "trial"])
def test_zero_solve_candidate_requires_the_complete_essential_certificate(tmp_path, fault):
    manifest, directories = make_evidence(tmp_path)

    def certificate(rows):
        metrics = rows[0]["response"]["metrics"]
        metrics.update(
            solve_count=0,
            solver_total_ns=0,
            solver_settings={
                "available": False,
                "records": [],
                "reason": "Essential certificate used",
            },
        )
        if fault:
            key, value = {
                "cover": ("essential_cover", False),
                "selected": ("selected", [0]),
                "essential_count": ("essential_decisions", True),
                "time": ("solver_total_ns", 1),
                "trial": ("canonical_feasible_trials", 1),
            }[fault]
            metrics[key] = value

    change_rows(directories["candidate-profiles"] / "profiles.jsonl", certificate)
    report = run_audit(manifest, directories)
    if fault:
        assert not report["pass"]
        assert any(
            "zero solves lack an essential certificate" in reason for reason in report["reasons"]
        )
    else:
        assert report["pass"], report["reasons"]


@pytest.mark.parametrize("growth", [False, True])
def test_zero_memory_growth_allowance_enforces_exact_growth_bound(tmp_path, growth):
    manifest, directories = make_evidence(tmp_path, memory_growth_tolerance_mb=0)
    if growth:
        change_rows(
            directories["run-2"] / "samples.jsonl",
            lambda rows: rows[-1].update(rss=[1024, 2048], peak_rss=[1024, 2048]),
        )
    report = run_audit(manifest, directories)
    assert report["pass"] is not growth, report["reasons"]
    if growth:
        assert any("RSS growth exceeds baseline" in reason for reason in report["reasons"])


def test_baseline_zero_solve_profile_is_not_a_candidate_certificate(tmp_path):
    manifest, directories = make_evidence(tmp_path)
    path = directories["baseline-profiles"] / "profiles.jsonl"

    def certificate(rows):
        rows[0]["response"]["metrics"].update(
            solve_count=0,
            solver_total_ns=0,
            solver_settings={
                "available": False,
                "records": [],
                "reason": "Essential certificate used",
            },
        )

    change_rows(path, certificate)
    manifest["profile_sha256"] = digest(
        [json.loads(line) for line in path.read_text().splitlines()]
    )
    report = run_audit(manifest, directories)
    assert not report["pass"]
    assert any(
        "baseline profiles: zero solves lack an essential certificate" in reason
        for reason in report["reasons"]
    )


@pytest.mark.parametrize(
    "fault", ["missing", "negative", "nonfinite", "over-limit", "growth", "result-hash"]
)
def test_sample_memory_and_result_evidence(tmp_path, fault):
    manifest, directories = make_evidence(tmp_path)
    path = directories["run-2"] / "samples.jsonl"
    if fault == "missing":
        change_rows(path, lambda rows: rows[0].pop("rss"))
    elif fault == "negative":
        change_rows(path, lambda rows: rows[0].update(rss=[-1, 1024]))
    elif fault == "nonfinite":
        change_rows(path, lambda rows: rows[0].update(peak_rss=[float("nan"), 1024]))
    elif fault == "over-limit":
        change_rows(path, lambda rows: rows[0].update(rss=[1024, 10**15]))
    elif fault == "growth":
        change_rows(
            path,
            lambda rows: rows[-1].update(rss=[1024, 33 * 1024**2], peak_rss=[1024, 33 * 1024**2]),
        )
    elif fault == "result-hash":
        change_rows(path, lambda rows: rows[0].update(result_hashes=["wrong", "wrong"]))
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
    manifest, directories = make_evidence(
        tmp_path, baseline_failure=True, new_success=True, oracle_match=True
    )
    report = run_audit(manifest, directories)
    assert report["pass"], report["reasons"]


def test_missing_file_returns_failure_report(tmp_path):
    manifest, directories = make_evidence(tmp_path)
    (directories["run-2"] / "samples.jsonl").unlink()
    assert not run_audit(manifest, directories)["pass"]


def test_recorded_driver_hashes_use_git_commit_bytes():
    root = Path(__file__).resolve().parents[1]
    head = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    tree = subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD^{tree}"], text=True
    ).strip()
    binding = dict(path=str(root), head=head, tree=tree, status="", build_files={}, lock_files={})
    hashes = recorded_driver_hashes(binding, ["python", "r", "js"])
    assert len(hashes) == 3
    for filename, value in hashes.items():
        raw = subprocess.check_output(["git", "-C", str(root), "show", f"{head}:{filename}"])
        assert value == hashlib.sha256(raw).hexdigest()


def test_separate_stage_harness_commits_with_equal_driver_bytes_are_allowed(tmp_path):
    manifest, directories = make_evidence(tmp_path)
    for name in (
        "baseline-capture",
        "candidate-capture",
        "baseline-profiles",
        "candidate-profiles",
    ):
        change_json(directories[name] / "metadata.json", lambda x: change_harness_head(x, "9" * 40))
    report = run_audit(manifest, directories)
    assert report["pass"], report["reasons"]


def test_two_timed_runs_allow_other_commits_with_equal_measurement_code(tmp_path):
    manifest, directories = make_evidence(tmp_path)
    change_json(directories["run-2"] / "metadata.json", lambda x: change_harness_head(x, "9" * 40))
    report = run_audit(manifest, directories)
    assert report["pass"], report["reasons"]


def test_changed_driver_bytes_cannot_hide_in_a_different_stage(tmp_path, monkeypatch):
    manifest, directories = make_evidence(tmp_path)
    change_json(
        directories["candidate-profiles"] / "metadata.json",
        lambda x: change_harness_head(x, "9" * 40),
    )
    monkeypatch.setattr(
        gates,
        "_driver_hashes",
        lambda binding, languages: {
            gates.DRIVERS[language]: digest("changed" if binding["head"] == "9" * 40 else language)
            for language in languages
        },
    )
    assert not run_audit(manifest, directories)["pass"]


def test_verified_javascript_records_pass_final_gate(tmp_path):
    manifest, directories = make_evidence(tmp_path, language="js")
    report = run_audit(manifest, directories)
    assert report["pass"], report["reasons"]


@pytest.mark.parametrize("fault", ["missing_proof", "solver_bytes", "compiler_bytes"])
def test_javascript_gate_rejects_consistent_candidate_binding_with_changed_bytes(tmp_path, fault):
    manifest, directories = make_evidence(tmp_path, language="js")

    def alter(binding):
        if fault == "missing_proof":
            binding.pop("build_verified")
        elif fault == "solver_bytes":
            binding["dependency_files"]["highs/build/highs.wasm"] = "9" * 64
        else:
            binding["compiler_files"]["typescript/lib/tsc.js"] = "9" * 64

    for name in ("candidate-capture", "candidate-profiles"):

        def change_stage(meta):
            alter(meta["source"])
            alter(meta["source_after"])

        change_json(directories[name] / "metadata.json", change_stage)
    for name in ("run-1", "run-2"):

        def change_run(meta):
            alter(meta["source_before"]["candidate"])
            alter(meta["source_after"]["candidate"])

        change_json(directories[name] / "metadata.json", change_run)
    report = run_audit(manifest, directories)
    assert not report["pass"]
    assert "Baseline and candidate JavaScript solver or compiler bytes differ" in report["reasons"]


@pytest.mark.parametrize("field", ["pilot_source", "baseline_source"])
def test_javascript_gate_requires_frozen_build_proof(tmp_path, field):
    manifest, directories = make_evidence(tmp_path, language="js")
    manifest[field].pop("build_verified")
    report = run_audit(manifest, directories)
    assert not report["pass"]
    assert any("proof" in reason for reason in report["reasons"])


@pytest.mark.parametrize("fault", ["missing", "dirty"])
def test_gate_requires_calibration_harness(tmp_path, fault):
    manifest, directories = make_evidence(tmp_path)
    if fault == "missing":
        manifest.pop("calibration_harness")
    else:
        manifest["calibration_harness"]["status"] = " M benchmarks/run.py"
    report = run_audit(manifest, directories)
    assert not report["pass"]
    assert "Missing or invalid calibration harness binding" in report["reasons"]


@pytest.mark.parametrize(
    "changed",
    [
        "benchmarks/run.py",
        "benchmarks/common.py",
        "benchmarks/analysis.py",
        "benchmarks/process_guard.py",
        "benchmarks/resource_evidence.py",
    ],
)
def test_measurement_code_change_fails_with_unchanged_drivers(tmp_path, monkeypatch, changed):
    manifest, directories = make_evidence(tmp_path)
    for name in ("run-1", "run-2"):
        change_json(
            directories[name] / "metadata.json", lambda meta: change_harness_head(meta, "9" * 40)
        )
    original = gates._measurement_hashes

    def changed_hashes(binding, languages):
        hashes = original(binding, languages)
        if binding["head"] == "9" * 40:
            hashes[changed] = "9" * 64
        return hashes

    monkeypatch.setattr(gates, "_measurement_hashes", changed_hashes)
    report = run_audit(manifest, directories)
    assert not report["pass"]
    assert (
        sum(
            reason.endswith("measurement code differs from calibration")
            for reason in report["reasons"]
        )
        == 2
    )


@pytest.mark.parametrize("helper", ["process_guard.py", "resource_evidence.py"])
def test_recorded_measurement_hashes_bind_optional_helper_presence(tmp_path, monkeypatch, helper):
    def git(*args):
        return subprocess.check_output(
            ["git", "-C", str(tmp_path), *args], stderr=subprocess.DEVNULL, text=True
        ).strip()

    git("init", "-q")
    git("config", "user.name", "Test")
    git("config", "user.email", "test@example.invalid")
    required = ("run.py", "common.py", "analysis.py", "python_driver.py")
    for name in required:
        file = tmp_path / "benchmarks" / name
        file.parent.mkdir(exist_ok=True)
        file.write_text(name + "\n")
    git("add", ".")
    git("commit", "-qm", "Initial measurement files")
    binding = dict(
        path=str(tmp_path),
        head=git("rev-parse", "HEAD"),
        tree=git("rev-parse", "HEAD^{tree}"),
        status="",
        build_files={},
        lock_files={},
    )
    monkeypatch.setattr(gates, "_driver_hashes", recorded_driver_hashes)
    absent = recorded_measurement_hashes(binding, ["python"])
    assert absent[f"benchmarks/{helper}"] is None
    (tmp_path / "benchmarks" / helper).write_text("guard\n")
    git("add", ".")
    git("commit", "-qm", "Add process guard")
    binding.update(head=git("rev-parse", "HEAD"), tree=git("rev-parse", "HEAD^{tree}"))
    present = recorded_measurement_hashes(binding, ["python"])
    assert present[f"benchmarks/{helper}"] == hashlib.sha256(b"guard\n").hexdigest()
    assert all(absent[name] == present[name] for name in absent if not name.endswith(helper))
    (tmp_path / "benchmarks/run.py").write_text("different uncommitted loop\n")
    assert recorded_measurement_hashes(binding, ["python"]) == present


@pytest.mark.parametrize(
    "stage",
    [
        "calibration",
        "baseline-capture",
        "candidate-capture",
        "baseline-profiles",
        "candidate-profiles",
        "run-1",
        "run-2",
    ],
)
def test_final_gate_requires_every_raw_process_receipt(tmp_path, stage):
    manifest, directories = make_evidence(tmp_path)
    next(directories[stage].glob("*.resource.json")).unlink()
    report = run_audit(manifest, directories)
    assert not report["pass"]
    assert any("receipt" in reason for reason in report["reasons"])
