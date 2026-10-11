"""Validate bounded preprocessing outcomes without scoring failed or partial work.

Callers must also bind profile sources, inputs, versions, and baseline file hashes.
This module checks row coverage, resource outcomes, and preprocessing completeness.
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
    "maximal_cliques",
    "decision_variables",
    "auxiliary_variables",
    "constraints",
    "nonzeros",
    "essential_decisions",
)
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


def _outcomes(manifest, profile_rows):
    expected = {
        job_key(language, case): case
        for language in manifest["languages"]
        for case in jobs(manifest, tiers=("preprocess",))
    }
    memory_mb = manifest["memory_limit_mb"]
    _require(_positive(memory_mb), "Invalid preprocessing memory limit")
    result = {}
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
            _complete(response, case, key)
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
    return result


def freeze_preprocess_failures(manifest, profile_rows):
    """Return exact observed resource failures for the manifest's frozen map.

    Do not mutate the manifest. Unsupported errors and incomplete rows raise.
    """
    return {
        key: value for key, value in _outcomes(manifest, profile_rows).items() if value != COMPLETE
    }


def validate_preprocess_outcomes(manifest, profile_rows, *, candidate=False):
    """Validate baseline or candidate rows against baseline_preprocess_failures.

    Baseline rows must agree exactly with the frozen map. Candidate rows may
    complete a known failed preprocessing case. Such completion is unscored.
    A changed resource failure class or a new failure always raises ValueError.
    """
    outcomes = _outcomes(manifest, profile_rows)
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
    return evidence
