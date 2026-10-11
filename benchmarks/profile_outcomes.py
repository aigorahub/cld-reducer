"""Validate bounded preprocessing outcomes without scoring failed or partial work.

Callers must also bind profile sources, inputs, versions, and baseline file hashes.
This module checks row coverage, resource outcomes, and exact model dimensions.
"""

from __future__ import annotations

import math

from cases import job_key, jobs

COMPLETE = "completed_preprocessing"
RESOURCE_ERRORS = {
    ("ExternalLimit", "Driver external wall limit exceeded"): "external_wall_timeout",
    ("ExternalLimit", "Driver memory limit exceeded"): "external_memory_limit",
}
DIMENSIONS = (
    "vertices_before",
    "vertices_after",
    "edges",
    "edges_after",
    "maximal_cliques",
    "decision_variables",
    "auxiliary_variables",
    "constraints",
    "nonzeros",
    "essential_decisions",
)
STRUCTURE = DIMENSIONS + ("essential_cover",)
PREPROCESS_PHASES = (
    "input",
    "vertex_reduction",
    "enumeration",
    "model_construction",
    "essential_scan",
)
UNUSED_PHASES = (
    "adapter_setup",
    "model_load",
    "initial_optimization",
    "canonical_trials",
    "output_expansion",
    "final_validation",
)


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _positive(value):
    return type(value) in (int, float) and math.isfinite(value) and value > 0


def _multipartite_structure(case, key):
    """Independent dimension oracle for complete multipartite (6-8) x 3 inputs.

    R/model.R and the Python/JavaScript builders have one coverage row per
    vertex and edge. Letter columns have p vertex entries and choose(p,2)
    edge entries each. Assignment columns add one witness per clique edge,
    with one entry in an edge row and four entries in two linking rows.
    Closed neighborhoods are distinct, so production twin reduction keeps n.
    Each vertex and edge has multiple covering cliques, so no decision is
    essential. This checks the adjacency itself, including permuted vertices.
    """
    missing = f"Missing independent preprocessing structure evidence for {key}: "
    adjacency = case.get("input", {}).get("adjacency")
    _require(
        case.get("call") == "adjacency"
        and isinstance(adjacency, list)
        and len(adjacency) in (18, 21, 24),
        missing + "only complete multipartite inputs with 6-8 parts of size 3 are supported",
    )
    n = len(adjacency)
    _require(
        all(
            isinstance(row, list)
            and len(row) == n
            and all(type(value) in (bool, int) and value in (0, 1) for value in row)
            for row in adjacency
        ),
        missing + "adjacency must be a square Boolean matrix",
    )
    parts = [frozenset(j for j in range(n) if i == j or not adjacency[i][j]) for i in range(n)]
    p = n // 3
    _require(
        len(set(parts)) == p
        and all(len(part) == 3 for part in parts)
        and all(
            bool(adjacency[i][j]) == (i == j or parts[i] != parts[j])
            for i in range(n)
            for j in range(n)
        )
        and len({tuple(row) for row in adjacency}) == n,
        missing + "adjacency does not have exact size-3 parts and distinct closed neighborhoods",
    )
    method = case.get("options", {}).get("method")
    _require(
        method in ("letter_minimum", "assignment_minimum"), missing + "unsupported model method"
    )
    pairs, cliques = p * (p - 1) // 2, 3**p
    sigma = method == "assignment_minimum"
    decisions = p * cliques if sigma else cliques
    auxiliary = pairs * cliques if sigma else 0
    edges = 9 * pairs
    return dict(
        vertices_before=n,
        vertices_after=n,
        edges=edges,
        edges_after=edges,
        maximal_cliques=cliques,
        decision_variables=decisions,
        auxiliary_variables=auxiliary,
        constraints=n + edges + 2 * auxiliary,
        nonzeros=decisions + 5 * auxiliary if sigma else cliques * (p + pairs),
        essential_decisions=0,
        essential_cover=False,
    )


def _complete(response, case, key):
    metrics, phases = response.get("metrics"), response.get("phases_ns")
    _require(isinstance(metrics, dict) and isinstance(phases, dict), f"Missing metrics: {key}")
    _require(
        all(type(metrics.get(name)) is int and metrics[name] >= 0 for name in DIMENSIONS)
        and all(
            metrics[name] > 0
            for name in (
                "vertices_before",
                "vertices_after",
                "maximal_cliques",
                "decision_variables",
                "constraints",
                "nonzeros",
            )
        )
        and metrics["vertices_before"] == len(case["input"]["adjacency"])
        and metrics["vertices_after"] <= metrics["vertices_before"]
        and metrics["essential_decisions"] <= metrics["decision_variables"]
        and type(metrics.get("essential_cover")) is bool,
        f"Incomplete preprocessing dimensions: {key}",
    )
    _require(
        all(
            type(metrics.get(name)) is int and metrics[name] == 0
            for name in (
                "solve_count",
                "solver_total_ns",
                "canonical_feasible_trials",
                "canonical_infeasible_trials",
            )
        )
        and all(
            name in metrics and metrics[name] is None
            for name in (
                "selected",
                "objective",
                "final_zero_decisions",
            )
        )
        and all(name not in response for name in ("result", "canonical", "error")),
        f"Preprocessing contains optimization results or calls: {key}",
    )
    _require(
        all(type(phases.get(name)) is int and phases[name] >= 0 for name in PREPROCESS_PHASES)
        and all(name in phases and phases[name] is None for name in UNUSED_PHASES)
        and type(phases.get("total")) is int
        and 0 < phases["total"] <= case["wall_seconds"] * 1e9,
        f"Incomplete or out-of-bound preprocessing phases: {key}",
    )
    structure = {name: metrics[name] for name in STRUCTURE}
    expected = _multipartite_structure(case, key)
    if "edges_before" in metrics:
        _require(type(metrics["edges_before"]) is int, f"Invalid edges_before: {key}")
        structure["edges_before"] = metrics["edges_before"]
        expected["edges_before"] = expected["edges"]
    _require(
        structure == expected, f"Preprocessing structure differs from independent oracle: {key}"
    )
    return structure


def _outcomes(manifest, profile_rows):
    expected = {
        job_key(language, case): case
        for language in manifest["languages"]
        for case in jobs(manifest, tiers=("preprocess",))
    }
    memory_mb = manifest["memory_limit_mb"]
    _require(_positive(memory_mb), "Invalid preprocessing memory limit")
    result, structures = {}, {}
    for row in profile_rows:
        _require(isinstance(row, dict), "Invalid profile row")
        key, case = row.get("key"), row.get("case")
        _require(isinstance(key, str) and isinstance(case, dict), "Invalid profile identity")
        if key not in expected and case.get("tier") != "preprocess":
            continue
        _require(key in expected, f"Unexpected preprocessing row: {key}")
        _require(key not in result, f"Duplicate preprocessing row: {key}")
        _require(case == expected[key], f"Preprocessing case differs: {key}")
        _require(_positive(case.get("wall_seconds")), f"Invalid preprocessing wall limit: {key}")
        response = row.get("response")
        _require(
            isinstance(response, dict) and response.get("action") == "preprocess",
            f"Invalid preprocessing response: {key}",
        )
        if response.get("ok") is True:
            structures[key] = _complete(response, case, key)
            outcome = COMPLETE
        else:
            error = response.get("error")
            _require(
                response.get("ok") is False
                and isinstance(error, dict)
                and type(error.get("kind")) is str
                and type(error.get("message")) is str
                and all(name not in response for name in ("result", "canonical")),
                f"Malformed preprocessing failure: {key}",
            )
            outcome = RESOURCE_ERRORS.get((error["kind"], error["message"]))
            _require(outcome is not None, f"Unsupported preprocessing failure: {key}")
        peak = row.get("peak_rss")
        _require(_positive(peak), f"Missing preprocessing peak memory: {key}")
        exceeded = peak > memory_mb * 1024**2
        _require(
            exceeded == (outcome == "external_memory_limit"),
            f"Preprocessing memory evidence differs from outcome: {key}",
        )
        result[key] = outcome
    _require(set(result) == set(expected), "Missing preprocessing rows")
    return result, structures


def freeze_preprocess_failures(manifest, profile_rows):
    """Return exact observed resource failures for the manifest's frozen map.

    Do not mutate the manifest. Unsupported errors and incomplete rows raise.
    """
    outcomes, _ = _outcomes(manifest, profile_rows)
    return {key: value for key, value in outcomes.items() if value != COMPLETE}


def validate_preprocess_outcomes(manifest, profile_rows, *, candidate=False, baseline_rows=None):
    """Validate baseline or candidate rows against baseline_preprocess_failures.

    Baseline rows must agree exactly with the frozen map. Candidate rows may
    complete a known failed preprocessing case only with independent structural
    verification. Such completion is unscored. Candidate callers must supply
    baseline_rows from the profile file bound by the frozen profile hash.
    A changed resource failure class or a new failure always raises ValueError.
    """
    outcomes, structures = _outcomes(manifest, profile_rows)
    failures = manifest.get("baseline_preprocess_failures", {})
    _require(
        isinstance(failures, dict)
        and set(failures) <= set(outcomes)
        and all(
            type(value) is str and value in RESOURCE_ERRORS.values() for value in failures.values()
        ),
        "Invalid frozen preprocessing failure map",
    )
    evidence = {}
    for key, outcome in outcomes.items():
        baseline = failures.get(key, COMPLETE)
        _require(
            outcome == baseline or (candidate and outcome == COMPLETE),
            f"Preprocessing outcome differs from frozen baseline: {key} ({baseline} -> {outcome})",
        )
        evidence[key] = {"baseline": baseline, "outcome": outcome, "scored": False}
        if outcome == COMPLETE:
            evidence[key]["structure"] = structures[key]
    if candidate:
        _require(
            baseline_rows is not None,
            "Candidate preprocessing requires frozen baseline profile rows",
        )
        baseline = validate_preprocess_outcomes(manifest, baseline_rows)
        for key, item in evidence.items():
            if item["outcome"] == COMPLETE and baseline[key]["outcome"] == COMPLETE:
                _require(
                    item["structure"] == baseline[key]["structure"],
                    f"Candidate preprocessing structure differs from frozen baseline: {key}",
                )
    return evidence
