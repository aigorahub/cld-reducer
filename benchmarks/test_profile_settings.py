"""Native observations must expose drift that a version declaration cannot."""

import copy

import pytest
from profile_settings import validate_solver_settings


def sample(language="r", count=1):
    declared = {
        "presolve": "off",
        "threads": 1,
        "mip_rel_gap": 0,
        "mip_abs_gap": 0,
        "primal_feasibility_tolerance": 1e-9,
        "mip_feasibility_tolerance": 1e-9,
    }
    # R values were captured from HiGHS 1.14.0 before a real path3 solve.
    values = {
        **declared,
        "parallel": "off",
        "solver": "choose",
        "random_seed": 0,
        "dual_feasibility_tolerance": 1e-7,
        "r_global_threads": 1,
    }
    observed = {
        "available": count > 0,
        "source": "HiGHS typed native option getters immediately before solver_run.",
        "excluded_from_stable_comparison": ["time_limit"],
    }
    if language == "r":
        declared["parallel"] = "off"
    else:
        declared["output_flag"] = values["output_flag"] = False
        values.pop("r_global_threads")
        if language == "js":
            values.pop("threads")
            values.pop("parallel")
            declared["thread_setting"] = "Single-threaded package API"
            declared["time_limit"] = "Per case budget"
            observed["thread_constraint"] = {
                "kind": "single_threaded_api",
                "threads": 1,
                "native_option": False,
            }
            observed["thread_control"] = "The loader uses the single-threaded WebAssembly API."
    observed["records"] = [
        {
            "solve": index,
            "values": copy.deepcopy(values),
            "excluded_values": {"time_limit": "Inf" if index == 1 else 9.99},
        }
        for index in range(1, count + 1)
    ]
    response = {
        "ok": True,
        "action": "profile",
        "metrics": {"solve_count": count, "solver_settings": observed},
    }
    return declared, response


@pytest.mark.parametrize("language", ["r", "python", "js"])
def test_native_values_cover_all_solves_and_keep_extra_options(language):
    declared, response = sample(language, 3)
    before = copy.deepcopy(response)
    result = validate_solver_settings(language, response, declared)
    assert result == response["metrics"]["solver_settings"]["records"][0]["values"]
    assert result["dual_feasibility_tolerance"] == 1e-7
    assert result["random_seed"] == 0
    assert "time_limit" not in result
    result["random_seed"] = 5
    assert response == before


@pytest.mark.parametrize("language", ["r", "python", "js"])
@pytest.mark.parametrize("action", ["profile", "preprocess"])
def test_zero_solve_certificate_or_preprocess(language, action):
    declared, response = sample(language, 0)
    response["action"] = action
    assert validate_solver_settings(language, response, declared) is None


@pytest.mark.parametrize("language", ["r", "python", "js"])
@pytest.mark.parametrize(
    "key,value",
    [
        ("mip_rel_gap", 0.025),
        ("mip_abs_gap", 1e-6),
        ("primal_feasibility_tolerance", 1e-7),
        ("mip_feasibility_tolerance", 1e-6),
        ("presolve", "on"),
        ("mip_rel_gap", False),
        ("primal_feasibility_tolerance", True),
    ],
)
def test_native_drift_is_rejected_while_declaration_stays_fixed(language, key, value):
    declared, response = sample(language, 2)
    response["metrics"]["solver_settings"]["records"][1]["values"][key] = value
    with pytest.raises(ValueError):
        validate_solver_settings(language, response, declared)


@pytest.mark.parametrize(
    "key,value",
    [
        ("threads", 0),
        ("threads", 2),
        ("threads", True),
        ("threads", 1.0),
        ("r_global_threads", 0),
        ("r_global_threads", 2),
        ("r_global_threads", True),
        ("parallel", "on"),
    ],
)
def test_r_checks_native_and_package_global_threads(key, value):
    declared, response = sample()
    response["metrics"]["solver_settings"]["records"][0]["values"][key] = value
    with pytest.raises(ValueError):
        validate_solver_settings("r", response, declared)


@pytest.mark.parametrize("value", [0, 2, True, 1.0, None])
def test_python_requires_actual_native_threads(value):
    declared, response = sample("python")
    response["metrics"]["solver_settings"]["records"][0]["values"]["threads"] = value
    with pytest.raises(ValueError):
        validate_solver_settings("python", response, declared)


@pytest.mark.parametrize(
    "mutation",
    [
        "constraint_missing",
        "kind",
        "threads",
        "bool_threads",
        "native_option",
        "control_missing",
        "control_empty",
        "native_threads",
        "native_parallel",
        "output_flag",
        "numeric_output_flag",
        "declared_threads",
        "declared_parallel",
    ],
)
def test_js_requires_explicit_api_constraint_and_native_available_options(mutation):
    declared, response = sample("js")
    observed = response["metrics"]["solver_settings"]
    if mutation == "constraint_missing":
        observed.pop("thread_constraint")
    elif mutation == "kind":
        observed["thread_constraint"]["kind"] = "declared"
    elif mutation in ("threads", "bool_threads"):
        observed["thread_constraint"]["threads"] = True if mutation == "bool_threads" else 2
    elif mutation == "native_option":
        observed["thread_constraint"]["native_option"] = True
    elif mutation == "control_missing":
        observed.pop("thread_control")
    elif mutation == "control_empty":
        observed["thread_control"] = "  "
    elif mutation == "native_threads":
        observed["records"][0]["values"]["threads"] = 1
    elif mutation == "native_parallel":
        observed["records"][0]["values"]["parallel"] = "off"
    elif mutation in ("output_flag", "numeric_output_flag"):
        observed["records"][0]["values"]["output_flag"] = True if mutation == "output_flag" else 0
    elif mutation == "declared_threads":
        declared["threads"] = 2
    else:
        declared["parallel"] = "on"
    with pytest.raises(ValueError):
        validate_solver_settings("js", response, declared)


@pytest.mark.parametrize("count", [True, False, 1.0, -1, None, "1"])
def test_count_must_be_a_nonnegative_integer(count):
    declared, response = sample()
    response["metrics"]["solve_count"] = count
    with pytest.raises(ValueError, match="solve_count"):
        validate_solver_settings("r", response, declared)


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "duplicate",
        "reversed",
        "bool_index",
        "float_index",
        "zero_index",
        "unavailable",
        "numeric_available",
        "source_missing",
        "errors",
        "values_missing",
        "option_missing",
        "time_limit",
        "excluded_option",
        "extra_changed",
        "extra_type",
        "nonfinite",
        "nested",
        "preprocess_solve",
    ],
)
def test_incomplete_or_inconsistent_profile_observations(mutation):
    declared, response = sample("r", 2)
    observed = response["metrics"]["solver_settings"]
    records = observed["records"]
    if mutation == "missing":
        records.pop()
    elif mutation == "duplicate":
        records.append(copy.deepcopy(records[0]))
    elif mutation == "reversed":
        records.reverse()
    elif mutation in ("bool_index", "float_index", "zero_index"):
        records[0]["solve"] = {"bool_index": True, "float_index": 1.0, "zero_index": 0}[mutation]
    elif mutation in ("unavailable", "numeric_available"):
        observed["available"] = False if mutation == "unavailable" else 1
    elif mutation == "source_missing":
        observed.pop("source")
    elif mutation == "errors":
        observed["errors"] = [{"solve": 1, "message": "getter failed"}]
    elif mutation == "values_missing":
        records[0].pop("values")
    elif mutation == "option_missing":
        records[0]["values"].pop("mip_rel_gap")
    elif mutation == "time_limit":
        records[0]["values"]["time_limit"] = 1
    elif mutation == "excluded_option":
        observed["excluded_from_stable_comparison"].append("mip_rel_gap")
    elif mutation == "extra_changed":
        records[1]["values"]["dual_feasibility_tolerance"] = 1e-6
    elif mutation == "extra_type":
        records[0]["values"]["random_seed"] = False
    elif mutation == "nonfinite":
        records[0]["values"]["dual_feasibility_tolerance"] = float("nan")
    elif mutation == "nested":
        records[0]["values"]["extra"] = {}
    else:
        response["action"] = "preprocess"
    with pytest.raises(ValueError):
        validate_solver_settings("r", response, declared)


@pytest.mark.parametrize("mutation", ["missing", "records", "available", "numeric_available"])
def test_zero_solves_still_need_an_explicit_empty_observation(mutation):
    declared, response = sample("r", 0)
    observed = response["metrics"]["solver_settings"]
    if mutation == "missing":
        response["metrics"].pop("solver_settings")
    elif mutation == "records":
        observed["records"] = [{"solve": 1, "values": {}}]
    else:
        observed["available"] = True if mutation == "available" else 0
    with pytest.raises(ValueError):
        validate_solver_settings("r", response, declared)


@pytest.mark.parametrize(
    "key,value",
    [
        ("threads", True),
        ("presolve", 0),
        ("mip_rel_gap", False),
        ("mip_abs_gap", float("inf")),
        ("mip_feasibility_tolerance", None),
    ],
)
def test_invalid_declarations_cannot_validate_observations(key, value):
    declared, response = sample()
    declared[key] = value
    with pytest.raises(ValueError):
        validate_solver_settings("r", response, declared)
