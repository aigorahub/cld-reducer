"""Missing, changed, and malformed preprocessing evidence must fail closed."""

import copy

import pytest
from cases import job_key, jobs, multipartite
from profile_outcomes import (
    COMPLETE,
    DIMENSIONS,
    PREPROCESS_PHASES,
    STRUCTURE,
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
    if case["options"]["method"] == "letter_minimum":
        decisions, witnesses = cliques, 0
    return {
        "ok": True,
        "action": "preprocess",
        "metrics": {
            "vertices_before": 3 * parts,
            "vertices_after": 3 * parts,
            "edges": edges,
            "edges_after": edges,
            "maximal_cliques": cliques,
            "decision_variables": decisions,
            "auxiliary_variables": witnesses,
            "constraints": 3 * parts + edges + 2 * witnesses,
            "nonzeros": decisions + 5 * witnesses
            if witnesses
            else cliques * (parts + parts * (parts - 1) // 2),
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
                "call": "adjacency",
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
    expected[rows[0]["key"]]["structure"] = {
        name: rows[0]["response"]["metrics"][name] for name in STRUCTURE
    }
    assert validate_preprocess_outcomes(manifest, rows) == expected
    assert (
        validate_preprocess_outcomes(manifest, rows, candidate=True, baseline_rows=rows) == expected
    )


def test_new_completion_is_only_unscored_preprocessing(baseline):
    manifest, rows = baseline
    frozen_rows = copy.deepcopy(rows)
    rows[1]["response"] = success(rows[1]["case"])
    record = validate_preprocess_outcomes(
        manifest, rows, candidate=True, baseline_rows=frozen_rows
    )[rows[1]["key"]]
    assert record == {
        "baseline": "external_wall_timeout",
        "outcome": COMPLETE,
        "scored": False,
        "structure": {name: rows[1]["response"]["metrics"][name] for name in STRUCTURE},
    }
    with pytest.raises(ValueError, match="differs from frozen baseline"):
        validate_preprocess_outcomes(manifest, rows)


@pytest.mark.parametrize("field", DIMENSIONS + ("essential_cover",))
@pytest.mark.parametrize("new_completion", [False, True])
def test_candidate_structural_change_rejects_even_plausible_counts(baseline, field, new_completion):
    manifest, frozen = baseline
    rows = copy.deepcopy(frozen)
    row = rows[1 if new_completion else 0]
    row["response"] = success(row["case"])
    metrics = row["response"]["metrics"]
    metrics[field] = not metrics[field] if field == "essential_cover" else metrics[field] + 1
    with pytest.raises(ValueError, match="dimensions|structure"):
        validate_preprocess_outcomes(manifest, rows, candidate=True, baseline_rows=frozen)


@pytest.mark.parametrize("field", STRUCTURE)
def test_each_declared_structural_metric_is_required(baseline, field):
    manifest, frozen = baseline
    rows = copy.deepcopy(frozen)
    del rows[0]["response"]["metrics"][field]
    with pytest.raises(ValueError, match="dimensions"):
        validate_preprocess_outcomes(manifest, rows, candidate=True, baseline_rows=frozen)


def test_candidate_requires_the_frozen_baseline_records(baseline):
    manifest, rows = baseline
    with pytest.raises(ValueError, match="requires frozen baseline profile rows"):
        validate_preprocess_outcomes(manifest, rows, candidate=True)


def test_optional_structural_metric_must_match_frozen_baseline(baseline):
    manifest, frozen = baseline
    frozen[0]["response"]["metrics"]["edges_before"] = frozen[0]["response"]["metrics"]["edges"]
    rows = copy.deepcopy(frozen)
    del rows[0]["response"]["metrics"]["edges_before"]
    with pytest.raises(ValueError, match="differs from frozen baseline"):
        validate_preprocess_outcomes(manifest, rows, candidate=True, baseline_rows=frozen)


@pytest.mark.parametrize(
    "mutation", ["diagonal", "cross_edge", "within_edge", "ragged", "true_twins"]
)
def test_new_completion_needs_actual_multipartite_input_evidence(baseline, mutation):
    manifest, _ = baseline
    matrix = manifest["cases"][1]["input"]["adjacency"]
    if mutation == "diagonal":
        matrix[0][0] = 0
    elif mutation == "cross_edge":
        matrix[0][3] = matrix[3][0] = 0
    elif mutation == "within_edge":
        matrix[0][1] = matrix[1][0] = 1
    elif mutation == "ragged":
        matrix[0].pop()
    else:
        for i in range(3):
            for j in range(3):
                matrix[i][j] = 1
    frozen = [
        dict(key=job_key("r", c), case=c, response=failure(), peak_rss=1024)
        for c in jobs(manifest, tiers=("preprocess",))
    ]
    manifest["baseline_preprocess_failures"] = {
        row["key"]: "external_wall_timeout" for row in frozen
    }
    rows = copy.deepcopy(frozen)
    rows[1]["response"] = success(rows[1]["case"])
    with pytest.raises(ValueError, match="Missing independent preprocessing structure evidence"):
        validate_preprocess_outcomes(manifest, rows, candidate=True, baseline_rows=frozen)


@pytest.mark.parametrize(
    "parts,method,decisions,auxiliary,constraints,nonzeros",
    [
        (6, "letter_minimum", 729, 0, 153, 15309),
        (7, "letter_minimum", 2187, 0, 210, 61236),
        (8, "letter_minimum", 6561, 0, 276, 236196),
        (6, "assignment_minimum", 4374, 10935, 22023, 59049),
        (7, "assignment_minimum", 15309, 45927, 92064, 244944),
        (8, "assignment_minimum", 52488, 183708, 367692, 971028),
    ],
)
def test_exact_closed_form_dimensions_and_permuted_parts(
    parts, method, decisions, auxiliary, constraints, nonzeros
):
    matrix = multipartite(parts)
    # Interleave the partitions. A case ID cannot supply the graph proof.
    order = [i for offset in range(3) for i in range(offset, 3 * parts, 3)]
    matrix = [[bool(matrix[i][j]) for j in order] for i in order]
    case = dict(
        id="unlabelled/graph",
        tier="preprocess",
        call="adjacency",
        wall_seconds=30,
        input={"adjacency": matrix},
        options={"method": method},
    )
    manifest = dict(
        cases=[case],
        methods=[method],
        languages=["r"],
        memory_limit_mb=8192,
        baseline_preprocess_failures={},
    )
    response = success(case)
    response["metrics"].update(
        decision_variables=decisions,
        auxiliary_variables=auxiliary,
        constraints=constraints,
        nonzeros=nonzeros,
    )
    rows = [dict(key=job_key("r", case), case=case, response=response, peak_rss=1024)]
    result = validate_preprocess_outcomes(manifest, rows)
    structure = result[rows[0]["key"]]["structure"]
    assert structure["decision_variables"] == decisions
    assert structure["auxiliary_variables"] == auxiliary
    assert structure["constraints"] == constraints
    assert structure["nonzeros"] == nonzeros
    assert structure["edges"] == structure["edges_after"]
    assert structure["vertices_before"] == structure["vertices_after"] == parts * 3
    frozen = copy.deepcopy(rows)
    frozen[0]["response"] = failure()
    manifest["baseline_preprocess_failures"] = {rows[0]["key"]: "external_wall_timeout"}
    new = validate_preprocess_outcomes(manifest, rows, candidate=True, baseline_rows=frozen)
    assert new[rows[0]["key"]]["structure"] == structure


def test_unsupported_new_completion_has_a_missing_evidence_reason(baseline):
    manifest, _ = baseline
    manifest["cases"][1]["input"]["adjacency"] = multipartite(5)
    frozen = [
        dict(key=job_key("r", c), case=c, response=failure(), peak_rss=1024)
        for c in jobs(manifest, tiers=("preprocess",))
    ]
    manifest["baseline_preprocess_failures"] = {
        row["key"]: "external_wall_timeout" for row in frozen
    }
    rows = copy.deepcopy(frozen)
    rows[1]["response"] = success(rows[1]["case"])
    with pytest.raises(ValueError, match="only complete multipartite inputs with 6-8 parts"):
        validate_preprocess_outcomes(manifest, rows, candidate=True, baseline_rows=frozen)


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
