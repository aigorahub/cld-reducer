"""Correctness checks for the Python benchmark adapter, with no timing thresholds."""

from __future__ import annotations

import copy
import importlib.util
import io
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO = Path(__file__).resolve().parents[1]
DRIVER_PATH = REPO / "benchmarks" / "python_driver.py"
SPEC = importlib.util.spec_from_file_location("benchmark_python_driver", DRIVER_PATH)
driver = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(driver)


@pytest.fixture(scope="module")
def runtime():
    return driver.Runtime(REPO, "on")


def graph_case(method="assignment_minimum"):
    # Two maximal triangles share an edge. Some memberships are optional.
    return {
        "id": "overlap",
        "call": "adjacency",
        "input": {
            "adjacency": [[1, 1, 1, 0], [1, 1, 1, 1], [1, 1, 1, 1], [0, 1, 1, 1]],
            "groups": ["", "B", "C", "D"],
            "means": [
                {"group": "", "mean": 1},
                {"group": "B", "mean": 2},
                {"group": "C", "mean": 3},
                {"group": "D", "mean": 4},
            ],
        },
        "options": {"method": method},
    }


def solver_case(method="assignment_minimum"):
    # K(2,2,2) has multiple covers and no essential decisions.
    return {
        "call": "adjacency",
        "input": {
            "adjacency": [[int(i == j or i // 2 != j // 2) for j in range(6)] for i in range(6)]
        },
        "options": {"method": method},
    }


def originals(runtime):
    return (
        runtime.api.reduce_validated,
        runtime.reduction.reduce_graph,
        runtime.reduction.maximal_cliques,
        runtime.reduction.METHODS,
        runtime.reduction._solve_canonical,
        runtime.reduction.reconstruct_adjacency_from_assignments,
        runtime.solver.run,
        runtime.solver.highspy,
    )


@pytest.mark.parametrize("method", ["letter_minimum", "assignment_minimum"])
def test_capture_profile_measure_and_model_structure(runtime, method, monkeypatch):
    monkeypatch.setattr(
        runtime.solver, "run", lambda *a, **k: pytest.fail("Certified public call used a solver")
    )
    prepared = runtime.prepare(graph_case(method))
    before = originals(runtime)
    measured = runtime.measure(prepared, 2)
    capture = runtime.capture(prepared)
    profile = runtime.profile(prepared)
    assert originals(runtime) == before
    assert measured["iterations"] == 2
    assert isinstance(measured["elapsed_ns"], int)
    assert measured["result"] == capture["result"] == profile["result"]
    assert capture["canonical"] == profile["canonical"]
    result, metrics = profile["result"], profile["metrics"]
    assert result["groups"][0] == ""
    assert result["rows"][0]["group"] == ""
    assert result["stats"]["objective"] == capture["canonical"]["objective"]
    assert result["letters"] == ["B", "AB", "AB", "A"]
    assert result["assignments"] == [["B"], ["A", "B"], ["A", "B"], ["A"]]
    assert result["rows"] == [
        {"group": group, "letters": letters, "assignments": " ".join(assignments)}
        for group, letters, assignments in zip(
            result["groups"], result["letters"], result["assignments"], strict=True
        )
    ]
    assert metrics["vertices_before"] == 4
    assert metrics["vertices_after"] == 3
    assert metrics["edges"] == 5
    assert metrics["edges_after"] == 2
    assert metrics["maximal_cliques"] == 2
    assert metrics["essential_cover"] is True
    assert metrics["solve_count"] == 0
    assert metrics["solver_total_ns"] == 0
    assert metrics["solve_records"] == []
    assert metrics["solver_settings"]["available"] is False
    assert metrics["solver_settings"]["records"] == []
    assert metrics["solver_total_ns"] == sum(r["elapsed_ns"] for r in metrics["solve_records"])
    assert metrics["probe_ns"] == sum(r["probe_ns"] for r in metrics["solve_records"])
    assert metrics["solver_total_ns"] + metrics["probe_ns"] <= profile["phases_ns"]["total"]
    if method == "letter_minimum":
        assert (
            metrics["decision_variables"],
            metrics["auxiliary_variables"],
            metrics["constraints"],
            metrics["nonzeros"],
        ) == (2, None, None, None)
        assert capture["canonical"] == {"selected": [1, 1], "objective": 2}
    else:
        assert (
            metrics["decision_variables"],
            metrics["auxiliary_variables"],
            metrics["constraints"],
            metrics["nonzeros"],
        ) == (4, None, None, None)
        assert capture["canonical"] == {"selected": [1, 1, 1, 1], "objective": 6}
    assert metrics["essential_decisions"] == metrics["decision_variables"]
    assert metrics["solver_counters"]["available"] is False
    assert metrics["solver_counters"]["per_solve"] == []
    assert profile["profile_schema"] == 2
    assert metrics["model_compiled"] is False
    missing = {
        "model_construction",
        "adapter_setup",
        "model_load",
        "initial_optimization",
        "canonical_trials",
    }
    assert set(profile["profile_notes"]["phase_unavailable"]) == missing
    for name, value in profile["phases_ns"].items():
        if name in missing:
            assert value is None
        else:
            assert isinstance(value, int) and value >= 0


@pytest.mark.parametrize("method", ["letter_minimum", "assignment_minimum"])
def test_fallback_profile_records_native_calls_and_timings(runtime, method):
    prepared = runtime.prepare(solver_case(method))
    measured = runtime.measure(prepared, 1)
    capture = runtime.capture(prepared)
    profile = runtime.profile(prepared)
    assert measured["result"] == capture["result"] == profile["result"]
    assert capture["canonical"] == profile["canonical"]
    metrics = profile["metrics"]
    assert metrics["essential_cover"] is False
    assert metrics["solve_count"] > 1
    assert metrics["solver_total_ns"] == sum(r["elapsed_ns"] for r in metrics["solve_records"])
    assert metrics["probe_ns"] == sum(r["probe_ns"] for r in metrics["solve_records"])
    assert metrics["solver_total_ns"] + metrics["probe_ns"] <= profile["phases_ns"]["total"]
    assert metrics["solver_counters"]["available"] is True
    assert len(metrics["solver_counters"]["per_solve"]) == metrics["solve_count"]
    assert all(isinstance(value, int) and value >= 0 for value in profile["phases_ns"].values())


def test_pairs_custom_columns_mean_order_and_empty_name(runtime):
    case = graph_case("letter_minimum")
    inputs = case["input"]
    case["call"] = "pairs"
    groups, adjacency = inputs["groups"], inputs.pop("adjacency")
    inputs["means"] = list(reversed(inputs["means"]))
    inputs["pairs"] = [
        {"first": groups[i], "second": groups[j], "diff": not adjacency[i][j]}
        for i in range(len(groups))
        for j in range(i + 1, len(groups))
    ]
    case["options"].update(group1="first", group2="second", significant="diff")
    result = runtime.capture(runtime.prepare(case))["result"]
    assert result["groups"] == ["D", "C", "B", ""]
    assert result["letters"] == ["A", "AB", "AB", "B"]
    assert result["adjacency"] == [
        [bool(adjacency[i][j]) for j in (3, 2, 1, 0)] for i in (3, 2, 1, 0)
    ]


def test_measure_has_no_capture_hooks_or_normalization_in_timed_region(runtime, monkeypatch):
    prepared = runtime.prepare(graph_case())
    original = originals(runtime)
    calls = []
    real_call = prepared[0]
    real_normalize = driver.normalize

    def call(*args, **kwargs):
        assert originals(runtime) == original
        calls.append("call")
        return real_call(*args, **kwargs)

    def normalize(result):
        assert calls == ["clock", "call", "call", "clock"]
        return real_normalize(result)

    def clock():
        calls.append("clock")
        return len(calls) * 10

    monkeypatch.setattr(driver.time, "perf_counter_ns", clock)
    monkeypatch.setattr(driver, "normalize", normalize)
    measured = runtime.measure((call, prepared[1], prepared[2]), 2)
    assert measured["elapsed_ns"] == 30


@pytest.mark.parametrize("action", ["capture", "profile", "preprocess"])
def test_hooks_restore_after_model_solver_and_input_errors(runtime, monkeypatch, action):
    original = originals(runtime)
    method = getattr(runtime, "profile" if action == "preprocess" else action)
    kwargs = {"preprocess": True} if action == "preprocess" else {}
    bad = graph_case()
    bad["input"]["adjacency"][0][1] = 0
    with pytest.raises(runtime.package.InvalidInputError):
        method(runtime.prepare(bad), **kwargs)
    assert originals(runtime) == original
    bad = graph_case()
    bad["options"]["max_cliques"] = 1
    with pytest.raises(runtime.package.SolverError, match="max_cliques"):
        method(runtime.prepare(bad), **kwargs)
    assert originals(runtime) == original
    if action != "preprocess":

        def failure(*args, **kwargs):
            raise runtime.package.SolverError("injected adapter error")

        monkeypatch.setattr(runtime.solver, "run", failure)
        patched = originals(runtime)
        with pytest.raises(runtime.package.SolverError, match="injected"):
            method(runtime.prepare(solver_case()), **kwargs)
        assert originals(runtime) == patched
        monkeypatch.undo()
    assert runtime.measure(runtime.prepare(graph_case()), 1)["result"]["stats"]["objective"] == 6


def test_preprocess_uses_real_builder_and_does_not_optimize(runtime, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Preprocess must not call the optimizer")

    monkeypatch.setattr(runtime.solver, "run", forbidden)
    prepared = runtime.prepare(graph_case())
    response = runtime.profile(prepared, preprocess=True)
    assert "result" not in response and "canonical" not in response
    metrics = response["metrics"]
    assert metrics["decision_variables"] == 4
    assert metrics["constraints"] == 9
    assert metrics["nonzeros"] == 14
    assert metrics["essential_cover"] is True
    assert metrics["solve_count"] == 0
    assert metrics["selected"] is None and metrics["objective"] is None
    assert response["phases_ns"]["initial_optimization"] is None
    assert "initial_optimization" in response["profile_notes"]["phase_unavailable"]


def test_canonical_trials_use_only_decisions_and_weighted_objective(runtime, monkeypatch):
    case = solver_case()
    original_run = runtime.solver.run

    def different_initial_incumbent(problem, lower, upper, **kwargs):
        if kwargs.get("sum_limit") is None:
            # Symmetry gives an optimum with decision 0 excluded. This makes
            # canonical search perform a feasible trial, independent of HiGHS ties.
            upper = upper.copy()
            upper[0] = 0
        return original_run(problem, lower, upper, **kwargs)

    monkeypatch.setattr(runtime.solver, "run", different_initial_incumbent)
    response = runtime.profile(runtime.prepare(case))
    metrics, vector = response["metrics"], response["canonical"]["selected"]
    assert metrics["essential_decisions"] == 0
    assert metrics["essential_cover"] is False
    assert len(vector) == metrics["decision_variables"] == 24
    assert metrics["auxiliary_variables"] == 24
    assert sum(vector) == response["canonical"]["objective"] == 12
    assert metrics["canonical_infeasible_trials"] == vector.count(0)
    assert metrics["canonical_feasible_trials"] > 0
    assert metrics["solve_count"] == 1 + metrics["canonical_feasible_trials"] + vector.count(0)
    assert response["phases_ns"]["canonical_trials"] == (
        metrics["canonical_feasible_trials_ns"] + metrics["canonical_infeasible_trials_ns"]
    )


def test_version_does_not_solve(runtime, monkeypatch):
    monkeypatch.setattr(runtime.solver, "run", lambda *a, **kw: pytest.fail("Unexpected solve"))
    response = runtime.versions()
    assert response["language"] == "python"
    assert response["settings"]["presolve"] == "on"
    assert response["settings"]["threads"] == 1
    assert response["source_path"] == str(REPO)
    assert len(response["source_head"]) == 40


@pytest.mark.parametrize("iterations", [0, -1, 1.5, True, None])
def test_bad_iterations(runtime, iterations):
    with pytest.raises(ValueError, match="positive integer"):
        runtime.measure(runtime.prepare(graph_case()), iterations)


def test_jsonl_continues_after_errors_and_uses_repo_from_another_cwd(tmp_path):
    bad = copy.deepcopy(graph_case())
    bad["input"]["adjacency"][0][0] = "yes"
    lines = [
        "{",
        "null",
        json.dumps({"action": "version"}),
        json.dumps({"action": "measure", "case": bad, "iterations": 1}),
        json.dumps({"action": "capture", "case": graph_case()}),
        json.dumps({"action": "measure", "case": graph_case(), "iterations": 1}),
    ]
    process = subprocess.run(
        [sys.executable, str(DRIVER_PATH), "--repo", str(REPO), "--presolve", "off"],
        input="\n".join(lines) + "\n",
        capture_output=True,
        text=True,
        cwd=tmp_path,
        check=True,
    )
    assert process.stderr == ""
    responses = [json.loads(line) for line in process.stdout.splitlines()]
    assert len(responses) == len(lines)
    assert [response["ok"] for response in responses] == [False, False, True, False, True, True]
    assert responses[2]["settings"]["presolve"] == "off"
    assert responses[3]["error"]["kind"] == "InvalidInputError"
    assert "result" not in responses[3]
    assert responses[4]["result"] == responses[5]["result"]


def test_malformed_request_after_valid_request(runtime, monkeypatch):
    monkeypatch.setattr(driver, "Runtime", lambda *args: runtime)
    input_stream = io.StringIO('{"action":"version"}\n{"action":"bogus"}\n[]\n')
    output = io.StringIO()
    driver.serve(REPO, "on", input_stream, output)
    responses = [json.loads(line) for line in output.getvalue().splitlines()]
    assert [response["ok"] for response in responses] == [True, False, False]


def test_preprocess_honors_default_clique_cap(runtime):
    # Nine parts of size three have 3**9 maximal cliques, above the default cap.
    adjacency = [[int(i == j or i // 3 != j // 3) for j in range(27)] for i in range(27)]
    case = {
        "call": "adjacency",
        "input": {"adjacency": adjacency},
        "options": {"method": "letter_minimum"},
    }
    before = originals(runtime)
    with pytest.raises(runtime.package.SolverError, match="max_cliques=10000"):
        runtime.profile(runtime.prepare(case), preprocess=True)
    assert originals(runtime) == before


@pytest.mark.parametrize("presolve", ["on", "off"])
def test_presolve_reaches_native_solver(runtime, presolve):
    saved = runtime.solver.settings.presolve
    try:
        configured = driver.Runtime(REPO, presolve)
        prepared = configured.prepare(solver_case())
        measured = configured.measure(prepared, 1)
        assert configured.solver.last_options["presolve"] == presolve
        profiled = configured.profile(prepared)
        assert configured.solver.last_options["presolve"] == presolve
        assert measured["result"] == profiled["result"]
        assert configured.solver.last_options["threads"] == 1
        assert configured.solver.last_options["mip_rel_gap"] == 0
        assert configured.solver.last_options["mip_abs_gap"] == 0
    finally:
        runtime.solver.settings.presolve = saved


@pytest.mark.parametrize("fixture", ["reduce", "reduce_letter_minimum", "reduce_weighted"])
def test_capture_matches_public_conformance_values(runtime, fixture):
    records = json.loads((REPO / "conformance" / "fixtures" / (fixture + ".json")).read_text())
    cases = records["cases"]
    # Include all named cases and one exhaustive graph. Large exhaustive sets
    # are covered by the baseline vector export, outside this smoke suite.
    selected = [case for case in cases if case["id"].startswith("hand/")]
    selected += [cases[-1]]
    for case in selected:
        case = copy.deepcopy(case)
        expected = case["expected"]
        case["options"]["method"] = expected["method"]
        captured = runtime.capture(runtime.prepare(case))
        result = captured["result"]
        assert result["groups"] == expected["groups"], case["id"]
        assert result["letters"] == [expected["letters"][g] for g in result["groups"]]
        assert result["assignments"] == [expected["assignments"][g] for g in result["groups"]]
        for key, value in expected["stats"].items():
            assert result["stats"][key] == value
        assert result["stats"]["objective"] == expected["objective"]
        assert captured["canonical"]["objective"] == expected["objective"]
        parts = expected["reduction_pct"]
        assert result["stats"]["reduction_pct"] == parts["numerator"] / parts["denominator"] * 100
        assert result["stats"]["solver_status"] == expected["solver_status"]
        assert result["method"] == expected["method"]
        assert result["relationship_preserved"] is expected["relationship_preserved"]


def test_profile_records_actual_solver_settings_and_overhead(runtime, monkeypatch):
    native = runtime.highspy.Highs

    class ChangedOptions(native):
        def setOptionValue(self, name, value):
            return super().setOptionValue(name, 0.025 if name == "mip_rel_gap" else value)

    monkeypatch.setattr(runtime.highspy, "Highs", ChangedOptions)
    declared = runtime.versions()
    assert declared["settings_kind"] == "declared_contract"
    assert declared["settings"]["mip_rel_gap"] == 0
    response = runtime.profile(runtime.prepare(solver_case()))
    settings = response["metrics"]["solver_settings"]
    assert settings["available"] is True
    assert len(settings["records"]) == response["metrics"]["solve_count"]
    assert [r["solve"] for r in settings["records"]] == list(range(1, len(settings["records"]) + 1))
    for record in settings["records"]:
        assert record["values"]["mip_rel_gap"] == 0.025
        assert record["values"]["threads"] == 1
        assert record["values"]["presolve"] == "on"
        assert "time_limit" not in record["values"]
    overhead = response["profile_notes"]["full_call_overhead"]
    assert overhead["reference_ns"] > 0
    assert overhead["instrumented_ns"] == response["phases_ns"]["total"]
    assert (
        overhead["instrumented_minus_reference_ns"]
        == overhead["instrumented_ns"] - overhead["reference_ns"]
    )
    assert overhead["ratio"] == overhead["instrumented_ns"] / overhead["reference_ns"]


def test_preprocessing_has_no_solver_settings_or_full_call_reference(runtime):
    response = runtime.profile(runtime.prepare(graph_case()), preprocess=True)
    assert response["metrics"]["solver_settings"]["available"] is False
    assert response["metrics"]["solver_settings"]["records"] == []
    assert response["profile_notes"]["full_call_overhead"] is None
    assert response["metrics"]["probe_ns"] == 0


def test_adapter_timing_subtracts_only_diagnostic_reads(runtime, monkeypatch):
    clock = 0
    monkeypatch.setattr(driver.time, "perf_counter_ns", lambda: clock)
    profile = driver.Profile(runtime, preprocess=False)
    statuses = iter((runtime.solver.OPTIMAL, runtime.solver.OPTIMAL, runtime.solver.INFEASIBLE))

    class Native:
        def passModel(self):
            nonlocal clock
            clock += 5

        def run(self):
            nonlocal clock
            clock += 11

        def getInfo(self):
            nonlocal clock
            clock += 1000
            return SimpleNamespace(
                mip_node_count=1, simplex_iteration_count=2, ipm_iteration_count=3
            )

        def getOptionValue(self, name):
            nonlocal clock
            clock += 1000
            return None, float("inf") if name == "time_limit" else 0

    def adapter(**_):
        nonlocal clock
        clock += 2
        native = driver.HighsProxy(Native(), profile)
        native.passModel()
        native.run()
        # Production reads must remain in adapter time, even when the added
        # diagnostic probes use the same native methods.
        native.getInfo()
        native.getOptionValue("presolve")
        clock += 3
        return SimpleNamespace(status=next(statuses))

    monkeypatch.setattr(runtime.solver, "run", adapter)
    wrapped = next(
        replacement
        for target, name, replacement in profile.hooks()
        if target is runtime.solver and name == "run"
    )
    for cap in (None, 1, 1):
        wrapped(sum_limit=cap)
    probe_per_solve = 1000 * (len(runtime.solver.OPTION_NAMES) + 2)
    assert profile.probe_ns == 3 * probe_per_solve
    assert [record["probe_ns"] for record in profile.solve_records] == [probe_per_solve] * 3
    assert [record["elapsed_ns"] for record in profile.solve_records] == [2021] * 3
    assert profile.native_totals == {"model_load": 15, "native_optimization": 33}
    assert clock == 3 * 2021 + profile.probe_ns
    assert [record["primary"] for record in profile.solve_records] == [True, False, False]
