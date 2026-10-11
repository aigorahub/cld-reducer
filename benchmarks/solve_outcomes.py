"""Require stable bounded failures before excluding solve cases from timing."""

from __future__ import annotations

from cases import job_key, jobs
from common import digest

EXTERNAL_FAILURES = {
    ("ExternalLimit", "Driver external wall limit exceeded"): "external_wall_timeout",
    ("ExternalLimit", "Driver memory limit exceeded"): "external_memory_limit",
}
SOLVER_KINDS = {"python": "SolverError", "js": "SolverError", "r": "cldreducer_solver_error"}
CAP_SUFFIX = {
    "python": "; increase max_cliques or pass None to disable the cap",
    "r": "; increase max_cliques or pass NULL to disable the cap",
    "js": "; increase maxCliques or pass null to disable the cap",
}


def solve_failure_class(response, language, case, action):
    """Return a known resource class. Arbitrary errors cannot justify exclusion."""
    if not (
        isinstance(response, dict)
        and response.get("ok") is False
        and response.get("action") == action
        and isinstance(response.get("error"), dict)
        and isinstance(response["error"].get("kind"), str)
        and isinstance(response["error"].get("message"), str)
        and all(key not in response for key in ("result", "canonical"))
    ):
        raise ValueError("Excluded solve has no bounded failure response")
    error = response["error"]
    signature = error["kind"], error["message"]
    if signature in EXTERNAL_FAILURES:
        return EXTERNAL_FAILURES[signature]
    if error["kind"] == SOLVER_KINDS[language]:
        prefix = case["options"]["method"].replace("_", "-") + " MILP failed: "
        if error["message"] == prefix + "Time limit reached":
            return "solver_time_limit"
        cap = case["options"].get("max_cliques", 10000)
        if (
            type(cap) is int
            and cap > 0
            and error["message"]
            == (f"maximal clique enumeration exceeded max_cliques={cap}" + CAP_SUFFIX[language])
        ):
            return "clique_cap"
    raise ValueError(f"Excluded solve has an unsupported resource failure: {signature}")


def _specs(manifest):
    specs = {
        job_key(language, case): case
        for language in manifest["languages"]
        for case in jobs(manifest)
    }
    failures = manifest.get("baseline_failures")
    if (
        not isinstance(failures, list)
        or any(not isinstance(key, str) or key not in specs for key in failures)
        or len(set(failures)) != len(failures)
    ):
        raise ValueError("Invalid baseline solve failure inventory")
    return specs, set(failures)


def validate_solve_captures(manifest, rows, *, baseline_classes=None):
    """Check reference failures or candidate outcomes against reference classes.

    Candidate successes remain subject to the caller's independent correctness
    and complete output checks. This helper never declares those results valid.
    """
    specs, failures = _specs(manifest)
    seen, classes = set(), {}
    for row in rows:
        key = "|".join((row["language"], row["method"], row["id"]))
        if key not in specs:
            continue
        if key in seen:
            raise ValueError(f"Duplicate solve capture: {key}")
        seen.add(key)
        if "response" in row:
            if key not in failures:
                raise ValueError(f"Undeclared solve failure: {key}")
            if any(name in row for name in ("result", "canonical")):
                raise ValueError(f"Failed solve capture contains a result: {key}")
            classes[key] = solve_failure_class(
                row["response"], row["language"], specs[key], "capture"
            )
            if classes[key] == "external_memory_limit":
                # Capture and excluded compare currently require all native
                # peaks below the cap. Do not accept a memory label without
                # supported over-cap receipt evidence for that solve.
                raise ValueError(f"Unsupported solve capture memory failure: {key}")
            if baseline_classes is not None and classes[key] != baseline_classes.get(key):
                raise ValueError(f"Solve resource failure class changed: {key}")
        elif key in failures and baseline_classes is None:
            raise ValueError(f"Excluded baseline solve succeeded in capture: {key}")
    if seen != set(specs):
        raise ValueError("Solve capture inventory is incomplete")
    if baseline_classes is None and set(classes) != failures:
        raise ValueError("Excluded baseline solves lack bounded capture failures")
    return classes


def validate_solve_profiles(manifest, rows, baseline_classes, *, candidate=False):
    specs, failures = _specs(manifest)
    seen = set()
    for row in rows:
        key = row["key"]
        if key not in specs:
            continue
        if key in seen:
            raise ValueError(f"Duplicate solve profile: {key}")
        seen.add(key)
        response = row["response"]
        if response.get("ok") is True:
            if key in failures and not candidate:
                raise ValueError(f"Excluded baseline solve succeeded in profile: {key}")
        else:
            if key not in failures:
                raise ValueError(f"Undeclared solve profile failure: {key}")
            outcome = solve_failure_class(response, key.split("|", 1)[0], specs[key], "profile")
            if outcome != baseline_classes.get(key):
                raise ValueError(f"Solve profile resource failure class changed: {key}")
    if seen != set(specs):
        raise ValueError("Solve profile inventory is incomplete")


def validate_calibration_failures(manifest, rows, baseline_classes):
    """Both A/A processes must reproduce each reference exclusion class."""
    specs, failures = _specs(manifest)
    seen = set()
    for row in rows:
        key = row.get("key")
        if key not in failures and row.get("baseline_failure") is not True:
            continue
        if key not in failures or key in seen or row.get("baseline_failure") is not True:
            raise ValueError("Invalid calibration failure inventory")
        seen.add(key)
        responses = row.get("responses")
        if not isinstance(responses, list) or len(responses) != 2:
            raise ValueError(f"Missing calibration excluded outcome pair: {key}")
        for response in responses:
            outcome = solve_failure_class(response, key.split("|", 1)[0], specs[key], "capture")
            if outcome != baseline_classes.get(key):
                raise ValueError(f"Calibration solve failure class changed: {key}")
    if seen != failures:
        raise ValueError("Calibration excluded outcome inventory is incomplete")


def validate_comparison_results(manifest, rows, samples, baseline_rows, candidate_rows=None):
    """Bind every measured batch to a raw response and the full captured output.

    A/A uses the baseline capture for both sides. Candidate comparisons use
    separate captures; their independent correctness checks remain mandatory.
    """
    specs, failures = _specs(manifest)
    captures = [
        {"|".join((row["language"], row["method"], row["id"])): row for row in values}
        for values in (baseline_rows, baseline_rows if candidate_rows is None else candidate_rows)
    ]
    expected = {
        (key, process)
        for key in specs
        if key not in failures
        for process in range(manifest["processes"])
    } | {(key, 0) for key in failures}
    seen, hashes = set(), {}
    for row in rows:
        key, process = row.get("key"), row.get("process")
        index = (key, process)
        if type(process) is not int or index not in expected or index in seen:
            raise ValueError("Comparison result inventory is incomplete, duplicated, or unexpected")
        seen.add(index)
        excluded = key in failures
        if (excluded and row.get("baseline_failure") is not True) or (
            not excluded and "baseline_failure" in row
        ):
            raise ValueError(f"Invalid comparison failure record: {index}")
        pair = row.get("responses")
        if not isinstance(pair, list) or len(pair) != 2:
            raise ValueError(f"Missing recorded API pair: {index}")
        for response, captured in zip(pair, captures, strict=True):
            reference = captured.get(key, {})
            if "response" in reference:
                if not (
                    excluded
                    and isinstance(response, dict)
                    and response.get("ok") is False
                    and response.get("action") == "capture"
                    and response == reference["response"]
                ):
                    raise ValueError(f"Comparison failure response changed: {index}")
            elif not (
                isinstance(response, dict)
                and response.get("ok") is True
                and response.get("action") == ("capture" if excluded else "measure")
                and "error" not in response
                and "result" in reference
                and response.get("result") == reference["result"]
                and digest(response["result"]) == digest(reference["result"])
                and (not excluded or response.get("canonical") == reference.get("canonical"))
            ):
                raise ValueError(f"Recorded API output differs from capture: {index}")
        if not excluded:
            hashes[index] = [digest(response["result"]) for response in pair]
    if seen != expected:
        raise ValueError("Comparison result inventory is incomplete")
    expected_samples = {
        (key, process, batch) for key, process in hashes for batch in range(manifest["batches"])
    }
    seen_samples = set()
    for row in samples:
        key, process, batch = row.get("key"), row.get("process"), row.get("batch")
        index = (key, process, batch)
        if (
            type(process) is not int
            or type(batch) is not int
            or index not in expected_samples
            or index in seen_samples
        ):
            raise ValueError("Comparison sample inventory is incomplete, duplicated, or unexpected")
        seen_samples.add(index)
        if (
            row.get("ok") is not True
            or row.get("correct") is not True
            or row.get("result_hashes") != hashes[(key, process)]
        ):
            raise ValueError(f"Timed full-output hash differs from recorded API result: {index}")
    if seen_samples != expected_samples:
        raise ValueError("Comparison sample inventory is incomplete")
