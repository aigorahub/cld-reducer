"""R driver JSONL and conformance checks. No timing thresholds.

Run from any directory: python3 /path/benchmarks/test_r_driver.py --repo /path
Use --all-fixtures to capture every reduction fixture through the protocol.
"""

import argparse
import copy
import json
import pathlib
import subprocess
import tempfile


def fixture_cases(repo, name):
    return json.loads((repo / "conformance" / "fixtures" / f"{name}.json").read_text())["cases"]


def explicit_case(case):
    case = copy.deepcopy(case)
    case.setdefault("options", {}).setdefault(
        "method", case.get("expected", {}).get("method", "letter_minimum")
    )
    return case


def check_result(actual, expected):
    groups = expected["groups"]
    assert actual["groups"] == groups
    assert actual["letters"] == [expected["letters"][group] for group in groups]
    assert actual["assignments"] == [expected["assignments"][group] for group in groups]
    assert actual["method"] == expected["method"]
    assert actual["relationship_preserved"] is True
    for key, value in expected["stats"].items():
        assert actual["stats"][key] == value, key
    for key in ("objective", "solver_status"):
        assert actual["stats"][key] == expected[key], key
    fraction = expected["reduction_pct"]
    assert actual["stats"]["reduction_pct"] == fraction["numerator"] / fraction["denominator"] * 100
    tokens = actual["assignments"]
    assert actual["adjacency"] == [[bool(set(a) & set(b)) for b in tokens] for a in tokens]
    assert all(type(cell) is bool for row in actual["adjacency"] for cell in row)
    assert actual["rows"] == [
        dict(group=g, letters=actual["letters"][i], assignments=" ".join(tokens[i]))
        for i, g in enumerate(groups)
    ]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=pathlib.Path, required=True)
    parser.add_argument("--all-fixtures", action="store_true")
    args = parser.parse_args()
    repo = args.repo.resolve()
    reductions = sum(
        (
            fixture_cases(repo, name)
            for name in ("reduce", "reduce_letter_minimum", "reduce_weighted")
        ),
        [],
    )
    for case in list(reductions):
        if "sigma_expected" in case:
            alternative = copy.deepcopy(case)
            alternative["id"] += "/sigma"
            alternative["expected"] = alternative.pop("sigma_expected")
            alternative["options"]["method"] = "assignment_minimum"
            reductions.append(alternative)
    if not args.all_fixtures:
        # Include each public route, means, empty labels, weighted twins and singleton arrays.
        reductions = [
            case
            for i, case in enumerate(reductions)
            if i < 3
            or case["call"] == "pairs"
            or case["input"].get("means")
            or "" in (case["input"].get("groups") or [])
            or case["id"].startswith("weighted/")
        ]
    errors = fixture_cases(repo, "errors")
    requests = [dict(action="version")]
    requests += [dict(action="capture", case=explicit_case(case)) for case in reductions]
    requests += [dict(action="capture", case=explicit_case(case)) for case in errors]
    simple = explicit_case(reductions[0])
    requests += [
        dict(action=action, case=simple, iterations=2)
        for action in ("profile", "preprocess", "measure")
    ]
    text = "\n".join(map(json.dumps, requests)) + '\n{bad json\nnull\n{"action":"version"}\n'
    # A foreign cwd proves that runtime and fixture resolution use --repo.
    with tempfile.TemporaryDirectory() as foreign:
        result = subprocess.run(
            [
                "Rscript",
                str(repo / "benchmarks" / "r_driver.R"),
                "--repo",
                str(repo),
                "--presolve",
                "off",
            ],
            input=text,
            text=True,
            capture_output=True,
            cwd=foreign,
            timeout=240,
        )
    assert result.returncode == 0, (
        result.returncode,
        len(result.stdout.splitlines()),
        result.stderr,
    )
    lines = result.stdout.splitlines()
    assert len(lines) == len(requests) + 3, result.stdout[-2000:]
    responses = [json.loads(line) for line in lines]
    assert responses[0]["ok"] and responses[0]["settings"]["presolve"] == "off"
    assert responses[0]["settings_kind"] == "declared_contract"
    timer = responses[0]["timer"]
    assert timer["fallback"] is False and timer["absolute_accuracy_calibrated"] is False
    assert isinstance(timer["warnings"], list)
    assert all(isinstance(warning, str) for warning in timer["warnings"])
    assert all(warning not in result.stderr for warning in timer["warnings"])
    for case, response in zip(reductions, responses[1 : 1 + len(reductions)], strict=True):
        assert response["ok"], (case["id"], response)
        check_result(response["result"], case["expected"])
        selected = response["canonical"]["selected"]
        assert isinstance(selected, list) and all(
            type(bit) is int and bit in (0, 1) for bit in selected
        )
        assert response["canonical"]["objective"] == case["expected"]["objective"]
    start = 1 + len(reductions)
    for case, response in zip(errors, responses[start : start + len(errors)], strict=True):
        assert not response["ok"] and "result" not in response, (case["id"], response)
        expected_class = (
            "cldreducer_invalid_input"
            if case["expected"]["kind"] == "invalid_input"
            else "cldreducer_solver_error"
        )
        assert response["error"]["kind"] == expected_class, (case["id"], response)
        assert response["error"]["message"].startswith(case["expected"]["message_prefix"]), (
            case["id"],
            response,
        )
    profile, preprocess, measure = responses[start + len(errors) : start + len(errors) + 3]
    assert profile["ok"] and preprocess["ok"] and measure["ok"]
    assert profile["result"] == measure["result"] == responses[1]["result"]
    assert profile["canonical"] == responses[1]["canonical"]
    assert "result" not in preprocess and preprocess["metrics"]["solve_count"] == 0
    settings = profile["metrics"]["solver_settings"]
    assert settings["available"] is True
    assert settings["excluded_from_stable_comparison"] == ["time_limit"]
    assert [record["solve"] for record in settings["records"]] == list(
        range(1, profile["metrics"]["solve_count"] + 1)
    )
    for record in settings["records"]:
        values = record["values"]
        assert values["presolve"] == "off" and values["parallel"] == "off"
        assert values["mip_rel_gap"] == values["mip_abs_gap"] == 0
        assert values["primal_feasibility_tolerance"] == 1e-9
        assert values["mip_feasibility_tolerance"] == 1e-9
        assert type(values["threads"]) is int and type(values["r_global_threads"]) is int
        assert "time_limit" not in values and "time_limit" in record["excluded_values"]
        assert record["excluded_values"]["time_limit"] is None
    overhead = profile["profile_notes"]["full_call_overhead"]
    assert type(overhead["reference_ns"]) is int and overhead["reference_ns"] >= 0
    assert overhead["instrumented_ns"] == profile["phases_ns"]["total"]
    assert (
        overhead["instrumented_minus_reference_ns"]
        == overhead["instrumented_ns"] - overhead["reference_ns"]
    )
    assert overhead["ratio"] == overhead["instrumented_ns"] / overhead["reference_ns"]
    assert preprocess["metrics"]["solver_settings"]["available"] is False
    assert preprocess["metrics"]["solver_settings"]["records"] == []
    assert preprocess["profile_notes"]["full_call_overhead"] is None
    assert "metrics" not in measure
    assert (
        measure["iterations"] == 2
        and type(measure["elapsed_ns"]) is int
        and measure["elapsed_ns"] >= 0
    )
    assert not responses[-3]["ok"] and not responses[-2]["ok"] and responses[-1]["ok"]
    rejected = subprocess.run(
        [
            "Rscript",
            str(repo / "benchmarks" / "r_driver.R"),
            "--repo",
            str(repo),
            "--presolve",
            "on",
        ],
        text=True,
        capture_output=True,
        timeout=20,
    )
    assert rejected.returncode != 0 and not rejected.stdout and "off only" in rejected.stderr
    print(f"R JSONL checks passed: {len(reductions)} captures, {len(errors)} errors, all actions.")


if __name__ == "__main__":
    main()
