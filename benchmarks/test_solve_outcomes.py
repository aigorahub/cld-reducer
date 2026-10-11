"""Excluded solve outcomes and shared calibration/candidate RSS checks."""

import copy
import json
from types import SimpleNamespace

import pytest
import run
from analysis import rss_growth
from common import digest
from solve_outcomes import (
    solve_failure_class,
    validate_calibration_failures,
    validate_solve_captures,
    validate_solve_profiles,
)


def evidence():
    case = {"id": "case", "tier": "solve", "options": {"method": "letter_minimum"}}
    manifest = {
        "languages": ["python"],
        "methods": ["letter_minimum"],
        "cases": [case],
        "baseline_failures": ["python|letter_minimum|case"],
    }
    response = {
        "ok": False,
        "action": "capture",
        "error": {"kind": "ExternalLimit", "message": "Driver external wall limit exceeded"},
    }
    row = {
        "language": "python",
        "id": "case",
        "method": "letter_minimum",
        "case": case,
        "response": response,
    }
    return manifest, case, row


@pytest.mark.parametrize(
    "language,kind",
    [("python", "SolverError"), ("js", "SolverError"), ("r", "cldreducer_solver_error")],
)
@pytest.mark.parametrize("method", ["letter_minimum", "assignment_minimum"])
def test_exact_production_solver_time_limit_classes(language, kind, method):
    _, case, row = evidence()
    case["options"]["method"] = method
    response = row["response"]
    response["error"] = {
        "kind": kind,
        "message": method.replace("_", "-") + " MILP failed: Time limit reached",
    }
    assert solve_failure_class(response, language, case, "capture") == "solver_time_limit"
    response["error"]["message"] += " after a crash"
    with pytest.raises(ValueError, match="unsupported"):
        solve_failure_class(response, language, case, "capture")


@pytest.mark.parametrize(
    "language,kind,suffix",
    [
        ("python", "SolverError", "; increase max_cliques or pass None to disable the cap"),
        ("js", "SolverError", "; increase maxCliques or pass null to disable the cap"),
        ("r", "cldreducer_solver_error", "; increase max_cliques or pass NULL to disable the cap"),
    ],
)
def test_clique_cap_must_match_the_actual_frozen_cap(language, kind, suffix):
    _, case, row = evidence()
    case["options"]["max_cliques"] = 25
    row["response"]["error"] = {
        "kind": kind,
        "message": "maximal clique enumeration exceeded max_cliques=25" + suffix,
    }
    assert solve_failure_class(row["response"], language, case, "capture") == "clique_cap"
    case["options"]["max_cliques"] = 26
    with pytest.raises(ValueError, match="unsupported"):
        solve_failure_class(row["response"], language, case, "capture")


@pytest.mark.parametrize(
    "kind,message",
    [
        ("ExternalLimit", "Driver exited -11"),
        ("ExternalLimit", "Driver transport failed: missing library"),
        ("ExternalLimit", "unrelated memory limit phrase"),
        ("SolverError", "Time limit reached"),
        ("SolverError", "assignment-minimum MILP failed: Time limit reached"),
        ("InvalidInputError", "Driver external wall limit exceeded"),
    ],
)
def test_arbitrary_failure_cannot_remove_a_solve_from_timing(kind, message):
    manifest, _, row = evidence()
    row["response"]["error"] = {"kind": kind, "message": message}
    with pytest.raises(ValueError, match="unsupported"):
        validate_solve_captures(manifest, [row])


def test_reference_failure_is_required_but_candidate_success_stays_unscored():
    manifest, _, row = evidence()
    classes = validate_solve_captures(manifest, [row])
    assert classes == {"python|letter_minimum|case": "external_wall_timeout"}
    healthy = {key: value for key, value in row.items() if key != "response"}
    healthy.update(result={"unchecked": True}, canonical={"selected": [1]})
    with pytest.raises(ValueError, match="succeeded in capture"):
        validate_solve_captures(manifest, [healthy])
    # This accepts only the outcome transition. The final gate must still check
    # the candidate's complete output against an independent matching oracle.
    assert validate_solve_captures(manifest, [healthy], baseline_classes=classes) == {}
    changed = copy.deepcopy(row)
    changed["response"]["error"] = {
        "kind": "SolverError",
        "message": "letter-minimum MILP failed: Time limit reached",
    }
    with pytest.raises(ValueError, match="class changed"):
        validate_solve_captures(manifest, [changed], baseline_classes=classes)


@pytest.mark.parametrize("stage", ["profile", "calibration"])
@pytest.mark.parametrize("fault", ["healthy", "changed", "missing"])
def test_baseline_failure_must_be_repeated_in_other_baseline_evidence(stage, fault):
    manifest, case, row = evidence()
    classes = validate_solve_captures(manifest, [row])
    response = copy.deepcopy(row["response"])
    if fault == "healthy":
        response = {"ok": True, "action": "capture", "result": {}}
    elif fault == "changed":
        response["error"]["message"] = "Driver memory limit exceeded"
    if stage == "profile":
        response["action"] = "profile"
        rows = (
            []
            if fault == "missing"
            else [{"key": next(iter(classes)), "case": case, "response": response}]
        )
        call = validate_solve_profiles
    else:
        rows = (
            []
            if fault == "missing"
            else [
                {
                    "key": next(iter(classes)),
                    "baseline_failure": True,
                    "responses": [response, row["response"]],
                }
            ]
        )
        call = validate_calibration_failures
    with pytest.raises(ValueError):
        call(manifest, rows, classes)


def rss_evidence(tolerance=0):
    manifest = {
        "languages": ["python"],
        "methods": ["letter_minimum"],
        "cases": [{"id": "case", "tier": "solve", "options": {}}],
        "processes": 2,
        "baseline_failures": [],
        "memory_limit_mb": 128,
        "memory_growth_tolerance_mb": tolerance,
    }
    rows = [
        {
            "key": "python|letter_minimum|case",
            "process": process,
            "rss": [1024, 1024],
            "peak_rss": [1024, 1024],
        }
        for process in (0, 1, 0, 1)
    ]
    return manifest, rows


def test_rss_growth_accepts_zero_allowance_and_compares_paired_growth():
    manifest, rows = rss_evidence()
    rows[-1]["rss"] = rows[-1]["peak_rss"] = [2048, 2048]
    assert rss_growth(manifest, rows)[1]["excess_candidate_growth_bytes"] == 0
    rows[-1]["rss"][1] += 1
    with pytest.raises(ValueError, match="exceeds baseline"):
        rss_growth(manifest, rows)


@pytest.mark.parametrize(
    "fault",
    [
        "missing",
        "cap",
        "current_gt_peak",
        "missing_process",
        "negative_allowance",
        "nonfinite",
        "bool",
        "growth",
    ],
)
def test_shared_rss_gate_rejects_faults(fault):
    manifest, rows = rss_evidence(1)
    if fault == "missing":
        rows[0].pop("rss")
    elif fault == "cap":
        rows[0]["rss"][0] = 129 * 1024**2
    elif fault == "current_gt_peak":
        rows[0]["rss"][0] += 1
    elif fault == "missing_process":
        rows = [row for row in rows if row["process"] == 0]
    elif fault == "negative_allowance":
        manifest["memory_growth_tolerance_mb"] = -1
    elif fault == "nonfinite":
        rows[0]["rss"][0] = float("inf")
    elif fault == "bool":
        rows[0]["rss"][0] = True
    else:
        rows[-1]["rss"] = rows[-1]["peak_rss"] = [1024, 2 * 1024**2]
    with pytest.raises(ValueError):
        rss_growth(manifest, rows)


@pytest.mark.parametrize("fault", ["capture_healthy", "capture_crash", "calibration_growth"])
def test_freeze_rejects_unstable_failures_and_bad_calibration_memory(tmp_path, monkeypatch, fault):
    from test_gates import make_evidence, write_rows

    manifest, directories = make_evidence(tmp_path, baseline_failure=True)
    path = directories["calibration"]
    design = json.loads((path / "manifest.json").read_text())
    monkeypatch.setattr(run, "load_manifest", lambda _: copy.deepcopy(design))
    monkeypatch.setattr(
        run, "analyze", lambda *_: {"pass": True, "manifest_sha256": digest(design)}
    )
    if fault == "calibration_growth":
        rows = [json.loads(line) for line in (path / "samples.jsonl").read_text().splitlines()]
        rows[-1]["rss"] = rows[-1]["peak_rss"] = [1024, 1024 + 33 * 1024**2]
        write_rows(path / "samples.jsonl", rows)
    else:
        path = directories["baseline-capture"]
        rows = [json.loads(line) for line in (path / "vectors.jsonl").read_text().splitlines()]
        row = next(row for row in rows if "response" in row)
        if fault == "capture_healthy":
            row.pop("response")
            row.update(result={"unchecked": True}, canonical={"selected": [1]})
        else:
            row["response"]["error"] = {"kind": "ExternalLimit", "message": "Driver exited -11"}
        write_rows(path / "vectors.jsonl", rows)
    args = SimpleNamespace(
        manifest="unused",
        profiles=directories["baseline-profiles"],
        capture=directories["baseline-capture"],
        calibration=directories["calibration"],
        output=tmp_path / "frozen.json",
    )
    with pytest.raises(
        ValueError, match="succeeded in capture|unsupported resource failure|RSS growth"
    ):
        run.freeze(args)
    assert not args.output.exists()


def test_solve_capture_memory_exclusion_fails_closed_under_current_receipt_policy():
    manifest, _, row = evidence()
    row["response"]["error"]["message"] = "Driver memory limit exceeded"
    with pytest.raises(ValueError, match="Unsupported solve capture memory failure"):
        validate_solve_captures(manifest, [row])
