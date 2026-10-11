"""Missing, changed, and malformed preprocessing evidence must fail closed."""

import copy

import pytest
from cases import job_key, jobs, multipartite
from profile_outcomes import (
    COMPLETE,
    PREPROCESS_PHASES,
    UNUSED_PHASES,
    freeze_preprocess_failures,
    validate_preprocess_outcomes,
)


def success(case):
    parts = len(case["input"]["adjacency"]) // 3
    cliques = 3**parts
    decisions = parts * cliques
    edges = 9 * parts * (parts - 1) // 2
    witnesses = cliques * parts * (parts - 1) // 2
    return {
        "ok": True,
        "action": "preprocess",
        "metrics": {
            "vertices_before": 3 * parts,
            "vertices_after": 3 * parts,
            "edges": edges,
            "maximal_cliques": cliques,
            "decision_variables": decisions,
            "auxiliary_variables": witnesses,
            "constraints": 3 * parts + edges + 2 * witnesses,
            "nonzeros": decisions + 5 * witnesses,
            "essential_decisions": 0,
            "essential_cover": False,
            "solve_count": 0,
            "solver_total_ns": 0,
            "canonical_feasible_trials": 0,
            "canonical_infeasible_trials": 0,
            "selected": None,
            "objective": None,
            "final_zero_decisions": None,
        },
        "phases_ns": {
            **dict.fromkeys(PREPROCESS_PHASES, 1000),
            **dict.fromkeys(UNUSED_PHASES),
            "total": 10000,
        },
    }


def failure(message="Driver external wall limit exceeded", kind="ExternalLimit"):
    return {"ok": False, "action": "preprocess", "error": {"kind": kind, "message": message}}


@pytest.fixture
def baseline():
    manifest = {
        "languages": ["r"],
        "methods": ["assignment_minimum"],
        "memory_limit_mb": 8192,
        "cases": [
            {
                "id": f"bounded/multipartite-{parts}x3",
                "tier": "preprocess",
                "wall_seconds": 30,
                "input": {"adjacency": multipartite(parts)},
                "options": {},
            }
            for parts in (6, 7, 8)
        ],
    }
    rows = [
        {
            "key": job_key("r", case),
            "case": case,
            "response": success(case) if index == 0 else failure(),
            "peak_rss": 256 * 1024**2,
        }
        for index, case in enumerate(jobs(manifest, tiers=("preprocess",)))
    ]
    manifest["baseline_preprocess_failures"] = {
        row["key"]: "external_wall_timeout" for row in rows[1:]
    }
    return manifest, rows


def test_freeze_derives_exact_failures_without_mutation(baseline):
    manifest, rows = baseline
    before = copy.deepcopy(manifest)
    assert freeze_preprocess_failures(manifest, rows) == manifest["baseline_preprocess_failures"]
    assert manifest == before
    rows[1]["response"] = success(rows[1]["case"])
    assert freeze_preprocess_failures(manifest, rows) == {rows[2]["key"]: "external_wall_timeout"}


def test_baseline_and_unchanged_candidate(baseline):
    manifest, rows = baseline
    expected = {
        row["key"]: {
            "baseline": COMPLETE if index == 0 else "external_wall_timeout",
            "outcome": COMPLETE if index == 0 else "external_wall_timeout",
            "scored": False,
        }
        for index, row in enumerate(rows)
    }
    assert validate_preprocess_outcomes(manifest, rows) == expected
    assert validate_preprocess_outcomes(manifest, rows, candidate=True) == expected


def test_new_completion_is_only_unscored_preprocessing(baseline):
    manifest, rows = baseline
    rows[1]["response"] = success(rows[1]["case"])
    record = validate_preprocess_outcomes(manifest, rows, candidate=True)[rows[1]["key"]]
    assert record == {"baseline": "external_wall_timeout", "outcome": COMPLETE, "scored": False}
    with pytest.raises(ValueError, match="differs from frozen baseline"):
        validate_preprocess_outcomes(manifest, rows)


def test_failure_map_is_required_when_rows_failed(baseline):
    manifest, rows = baseline
    manifest.pop("baseline_preprocess_failures")
    with pytest.raises(ValueError, match="differs from frozen baseline"):
        validate_preprocess_outcomes(manifest, rows)


@pytest.mark.parametrize(
    "declaration",
    [
        [],
        {"preprocess": "external_wall_timeout"},
        {"*": "external_wall_timeout"},
        {"r|assignment_minimum|bounded/multipartite-7x3": "SolverError"},
        {"r|assignment_minimum|bounded/multipartite-7x3": None},
        {"r|assignment_minimum|bounded/multipartite-7x3": []},
    ],
)
def test_invalid_declaration(baseline, declaration):
    manifest, rows = baseline
    manifest["baseline_preprocess_failures"] = declaration
    with pytest.raises(ValueError, match="failure map"):
        validate_preprocess_outcomes(manifest, rows)


@pytest.mark.parametrize("change", ["missing", "duplicate", "extra", "input", "limit", "tier"])
def test_row_coverage_and_case_binding(baseline, change):
    manifest, rows = baseline
    if change == "missing":
        rows.pop()
    elif change == "duplicate":
        rows.append(copy.deepcopy(rows[-1]))
    elif change == "extra":
        row = copy.deepcopy(rows[-1])
        row["key"] += "/extra"
        rows.append(row)
    elif change == "input":
        rows[0]["case"]["input"]["adjacency"][0][0] = 0
    elif change == "limit":
        rows[0]["case"]["wall_seconds"] = 180
    else:
        rows[0]["case"]["tier"] = "solve"
    for check in (freeze_preprocess_failures, validate_preprocess_outcomes):
        with pytest.raises(ValueError):
            check(manifest, rows)


@pytest.mark.parametrize(
    "response",
    [
        failure(kind="SolverError"),
        failure("Driver closed stdout (exit 1)"),
        failure("Driver returned invalid JSON"),
        failure("Driver memory limit exceeded at response"),
        failure("maximal clique enumeration exceeded max_cliques=10000", "ValueError"),
        failure("time limit"),
        failure("Driver external wall limit exceeded unexpectedly"),
        {"ok": False, "action": "preprocess", "error": None},
        {"ok": 0, "action": "preprocess", "error": failure()["error"]},
        {**failure(), "action": "profile"},
        {**failure(), "result": {}},
        {**failure(), "canonical": {}},
    ],
)
def test_only_exact_supported_resource_failures_can_freeze(baseline, response):
    manifest, rows = baseline
    rows[1]["response"] = response
    with pytest.raises(ValueError):
        freeze_preprocess_failures(manifest, rows)
    with pytest.raises(ValueError):
        validate_preprocess_outcomes(manifest, rows, candidate=True)


def test_new_candidate_timeout_rejects_successful_baseline(baseline):
    manifest, rows = baseline
    rows[0]["response"] = failure()
    with pytest.raises(ValueError, match="differs from frozen baseline"):
        validate_preprocess_outcomes(manifest, rows, candidate=True)


def test_resource_class_change_is_not_allowed(baseline):
    manifest, rows = baseline
    rows[1]["response"] = failure("Driver memory limit exceeded")
    rows[1]["peak_rss"] = (manifest["memory_limit_mb"] + 1) * 1024**2
    with pytest.raises(ValueError, match="differs from frozen baseline"):
        validate_preprocess_outcomes(manifest, rows, candidate=True)
    manifest["baseline_preprocess_failures"] = freeze_preprocess_failures(manifest, rows)
    validate_preprocess_outcomes(manifest, rows)
    rows[1]["peak_rss"] = 1024
    with pytest.raises(ValueError, match="memory evidence"):
        validate_preprocess_outcomes(manifest, rows)


@pytest.mark.parametrize("peak", [None, False, 0, -1, float("nan"), float("inf"), 9000 * 1024**2])
def test_memory_evidence_is_required(baseline, peak):
    manifest, rows = baseline
    rows[0]["peak_rss"] = peak
    with pytest.raises(ValueError, match="memory"):
        validate_preprocess_outcomes(manifest, rows)


@pytest.mark.parametrize(
    "path,value",
    [
        (("metrics", "nonzeros"), None),
        (("metrics", "auxiliary_variables"), -1),
        (("metrics", "vertices_before"), 17),
        (("metrics", "vertices_after"), 19),
        (("metrics", "decision_variables"), False),
        (("metrics", "essential_decisions"), 999999999),
        (("metrics", "essential_cover"), 0),
        (("metrics", "solve_count"), 1),
        (("metrics", "solve_count"), False),
        (("metrics", "solver_total_ns"), 1),
        (("metrics", "canonical_feasible_trials"), 1),
        (("metrics", "canonical_infeasible_trials"), 1),
        (("metrics", "selected"), [1]),
        (("metrics", "objective"), 1),
        (("metrics", "final_zero_decisions"), 0),
        (("phases_ns", "total"), 30_000_000_001),
        (("phases_ns", "total"), 0),
        (("phases_ns", "total"), float("inf")),
        (("phases_ns", "total"), True),
        (("phases_ns", "essential_scan"), None),
        (("phases_ns", "model_construction"), -1),
        (("phases_ns", "initial_optimization"), 0),
        (("result",), {}),
        (("canonical",), {}),
        (("error",), {}),
    ],
)
def test_incomplete_or_optimized_success_cannot_pass(baseline, path, value):
    manifest, rows = baseline
    response = rows[0]["response"]
    for name in path[:-1]:
        response = response[name]
    response[path[-1]] = value
    with pytest.raises(ValueError):
        freeze_preprocess_failures(manifest, rows)
    with pytest.raises(ValueError):
        validate_preprocess_outcomes(manifest, rows, candidate=True)


def test_missing_null_field_is_not_complete(baseline):
    manifest, rows = baseline
    del rows[0]["response"]["metrics"]["selected"]
    with pytest.raises(ValueError):
        validate_preprocess_outcomes(manifest, rows)


def test_other_tiers_are_checked_by_the_caller(baseline):
    manifest, rows = baseline
    expected = freeze_preprocess_failures(manifest, rows)
    rows.append(
        {
            "key": "r|assignment_minimum|bounded/multipartite-9x3",
            "case": {"tier": "expected-error"},
            "response": failure(),
        }
    )
    assert freeze_preprocess_failures(manifest, rows) == expected
