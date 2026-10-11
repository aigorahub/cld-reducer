"""Check observed solver options for every real solve in a successful profile."""

from __future__ import annotations

import math

REQUIRED = {
    "presolve",
    "threads",
    "mip_rel_gap",
    "mip_abs_gap",
    "primal_feasibility_tolerance",
    "mip_feasibility_tolerance",
}
METADATA = {"time_limit", "thread_setting"}


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _scalar(value):
    return type(value) in (str, bool, int, float) and (
        type(value) is not float or math.isfinite(value)
    )


def _same(left, right):
    if type(left) is bool or type(right) is bool:
        return type(left) is type(right) and left == right
    if type(left) in (int, float) and type(right) in (int, float):
        return left == right
    return type(left) is type(right) and left == right


def validate_solver_settings(language, response, declared_settings):
    """Return the stable native option map, or None when no solver ran.

    Version settings are a declared contract. Profile records must read native
    settings before each run. JavaScript's thread count is an API constraint.
    Its returned map contains native options only. R also includes the observed
    package global thread setting. The changing time_limit is never stable.
    """
    _require(language in ("python", "r", "js"), "Unsupported solver settings language")
    _require(
        isinstance(declared_settings, dict) and set(declared_settings) >= REQUIRED,
        "Missing declared solver settings",
    )
    declared = {key: value for key, value in declared_settings.items() if key not in METADATA}
    _require(
        all(isinstance(key, str) and _scalar(value) for key, value in declared.items())
        and declared["presolve"] in ("on", "off")
        and type(declared["threads"]) is int
        and declared["threads"] > 0,
        "Invalid declared solver settings",
    )
    for key in (
        "mip_rel_gap",
        "mip_abs_gap",
        "primal_feasibility_tolerance",
        "mip_feasibility_tolerance",
    ):
        value = declared[key]
        _require(type(value) in (int, float) and value >= 0, f"Invalid declared {key}")
    if "parallel" in declared:
        _require(declared["parallel"] in ("on", "off"), "Invalid declared parallel setting")
    if language in ("python", "js") or "output_flag" in declared:
        _require(type(declared.get("output_flag")) is bool, "Missing declared output_flag")
    if language == "js":
        _require(declared["threads"] == 1, "JavaScript requires the single-threaded API")

    _require(
        isinstance(response, dict)
        and response.get("ok") is True
        and response.get("action") in ("profile", "preprocess")
        and isinstance(response.get("metrics"), dict),
        "Solver settings require a successful profile or preprocessing response",
    )
    metrics = response["metrics"]
    count, observed = metrics.get("solve_count"), metrics.get("solver_settings")
    _require(type(count) is int and count >= 0, "Invalid observed solve_count")
    _require(isinstance(observed, dict), "Missing solver settings observations")
    records = observed.get("records")
    _require(
        isinstance(records, list) and len(records) == count, "Solver settings coverage differs"
    )
    if count == 0:
        _require(observed.get("available") is False, "Zero solves cannot claim observed settings")
        return None
    _require(response["action"] == "profile", "Preprocessing must not run a solver")
    _require(
        observed.get("available") is True
        and not observed.get("errors")
        and isinstance(observed.get("source"), str)
        and bool(observed["source"].strip()),
        "Solver settings observations are unavailable or lack a source",
    )
    if "excluded_from_stable_comparison" in observed:
        _require(
            observed["excluded_from_stable_comparison"] == ["time_limit"],
            "Stable solver options cannot be excluded",
        )
    if language == "js":
        constraint = observed.get("thread_constraint")
        _require(
            isinstance(constraint, dict)
            and constraint.get("kind") == "single_threaded_api"
            and type(constraint.get("threads")) is int
            and constraint["threads"] == 1
            and constraint.get("native_option") is False
            and isinstance(observed.get("thread_control"), str)
            and bool(observed["thread_control"].strip())
            and declared["threads"] == 1
            and declared.get("parallel", "off") == "off",
            "Missing or inconsistent JavaScript single-threaded API constraint",
        )
        declared.pop("threads")
        declared.pop("parallel", None)
    elif language == "r":
        declared["r_global_threads"] = declared["threads"]

    stable = None
    for index, record in enumerate(records, 1):
        _require(
            isinstance(record, dict)
            and type(record.get("solve")) is int
            and record["solve"] == index
            and isinstance(record.get("values"), dict),
            "Solver settings records must follow actual solve order",
        )
        values = record["values"]
        _require(
            all(isinstance(key, str) and _scalar(value) for key, value in values.items())
            and "time_limit" not in values,
            "Invalid stable native solver values",
        )
        for key, value in values.items():
            if key in ("threads", "r_global_threads", "random_seed"):
                _require(type(value) is int and value >= 0, f"Invalid native {key}")
            elif key.endswith(("_tolerance", "_gap")):
                _require(type(value) in (int, float) and value >= 0, f"Invalid native {key}")
        if language == "js":
            _require(
                not {"threads", "parallel"} & set(values),
                "JavaScript threads and parallel are not native observations",
            )
        else:
            _require(type(values.get("threads")) is int, "Native threads must be an integer")
            if language == "r":
                _require(
                    type(values.get("r_global_threads")) is int,
                    "R global threads must be an integer",
                )
        _require(
            all(key in values and _same(value, values[key]) for key, value in declared.items()),
            f"Native solver settings differ from the declared contract at solve {index}",
        )
        if stable is None:
            stable = dict(values)
        else:
            _require(
                set(stable) == set(values)
                and all(_same(stable[key], values[key]) for key in stable),
                f"Native solver settings changed within the profile at solve {index}",
            )
    return stable
