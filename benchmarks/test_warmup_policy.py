"""Warm pilot and replay tamper checks use synthetic times, never speed thresholds."""

import copy
import json
import random

import pytest
import run
from analysis import analyze, calibration_design, measurement_orders, paired_orders
from common import digest
from test_harness import evidence, set_sample_orders
from test_run import setup_collection
from warmup_policy import (
    MAX_TRIALS,
    POLICY,
    next_iterations,
    replay_count,
    settled,
    validate_history,
    validate_warmups,
    warmup_count,
)


def response(iterations=1, per_call=1000000):
    return dict(
        ok=True,
        action="measure",
        iterations=iterations,
        elapsed_ns=iterations * per_call,
        result={"value": 1},
    )


def history(per_call=1000000):
    rows = [response(per_call=per_call) for _ in range(3)]
    while len(rows) < MAX_TRIALS and not settled(rows):
        rows.append(response(next_iterations(rows), per_call))
    return rows


def test_fast_pilot_selects_warmed_batch_and_replay():
    rows = history()
    assert len(rows) == 23
    assert validate_history(rows, 3, {"value": 1}) == (100, 24)
    assert not settled(rows[:-1])


def test_slow_success_remains_in_pilot_with_single_call_batches():
    rows = history(2000000000)
    assert len(rows) == 6
    assert validate_history(rows, 3, {"value": 1}) == (1, 9)


@pytest.mark.parametrize(
    "fault", ["missing", "extra", "output", "iterations", "nan", "bool", "unstable"]
)
def test_bad_pilot_histories_fail_closed(fault):
    rows = history()
    if fault == "missing":
        rows.pop()
    elif fault == "extra":
        rows.append(response(100))
    elif fault == "output":
        rows[4]["result"] = {"value": 2}
    elif fault == "iterations":
        rows[4]["iterations"] = 99
    elif fault == "nan":
        rows[4]["elapsed_ns"] = float("nan")
    elif fault == "bool":
        rows[4]["iterations"] = True
    else:
        rows[-1]["elapsed_ns"] *= 2
    with pytest.raises(ValueError):
        validate_history(rows, 3, {"value": 1})


def test_replay_never_truncates_large_warm_history():
    with pytest.raises(ValueError, match="64"):
        replay_count([response(100000)], 1)


def new_evidence(ratio=0.8, base=100000000, iterations=1):
    m, meta, samples = evidence(ratio)
    m.update(
        warmup_policy=POLICY,
        batch_target_ns=100000000,
        case_warmup_batches={key: 7 + i for i, key in enumerate(m["iterations"])},
    )
    m["iterations"] = dict.fromkeys(m["iterations"], iterations)
    for row in samples:
        row.update(
            baseline_ns=base,
            candidate_ns=base * ratio,
            iterations=iterations,
            result_hashes=[digest({"value": 1})] * 2,
        )
    for version in meta["versions"]:
        version["pids"] = [100 + version["process"] * 2, 101 + version["process"] * 2]
    set_sample_orders(m, samples)
    meta["manifest_sha256"] = digest(m)
    return m, meta, samples


@pytest.mark.parametrize(
    "base,iterations,passed", [(49999999, 1, False), (50000000, 1, True), (1, 100000, True)]
)
def test_only_baseline_has_duration_floor(base, iterations, passed):
    m, meta, samples = new_evidence(ratio=0.01, base=base, iterations=iterations)
    report = analyze(m, meta, samples)
    assert report["pass"] is passed, report["reasons"]
    for case in report["cases"].values():
        assert case["batch_floor_pass"] is passed
        assert case["iteration_cap_exception"] is (iterations == 100000)


def warm_rows(m, meta):
    from cases import job_key, jobs

    rows = []
    for lang in m["languages"]:
        for process in range(m["processes"]):
            rng = random.Random(m["order_seed"] + process)
            for case in jobs(m):
                key = job_key(lang, case)
                if key in m["baseline_failures"]:
                    continue
                for batch, order in enumerate(paired_orders(rng, warmup_count(m, key), process)):
                    rows.append(
                        dict(
                            key=key,
                            process=process,
                            batch=batch,
                            order=order,
                            pids=meta["versions"][process]["pids"],
                            responses=[response(m["iterations"][key])] * 2,
                        )
                    )
                paired_orders(rng, m["batches"], process)
    return rows


@pytest.mark.parametrize(
    "fault", [None, "drop", "extra", "order", "result", "pid", "duration", "iterations", "hash"]
)
def test_raw_warmups_bind_schedule_outputs_and_receipts(tmp_path, fault):
    m, meta, samples = new_evidence()
    rows = warm_rows(m, meta)
    if fault == "drop":
        rows.pop()
    elif fault == "extra":
        rows.append(copy.deepcopy(rows[-1]))
    elif fault == "order":
        rows[0]["order"].reverse()
    elif fault == "result":
        rows[0]["responses"][0]["result"] = {"value": 9}
    elif fault == "pid":
        rows[0]["pids"] = [9, 10]
    elif fault == "duration":
        rows[0]["responses"][0]["elapsed_ns"] = -1
    elif fault == "iterations":
        rows[0]["responses"][0]["iterations"] = 2
    meta["warmups_sha256"] = "0" * 64 if fault == "hash" else digest(rows)
    (tmp_path / "warmups.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    if fault:
        with pytest.raises(ValueError):
            validate_warmups(tmp_path, m, meta, samples)
    else:
        assert validate_warmups(tmp_path, m, meta, samples) == digest(rows)


def test_map_changes_both_random_schedule_and_calibration_binding():
    m, _, _ = new_evidence()
    old = copy.deepcopy(m)
    key = next(iter(m["case_warmup_batches"]))
    m["case_warmup_batches"][key] += 1
    assert measurement_orders(m) != measurement_orders(old)
    assert calibration_design(m) != calibration_design(old)
    m["case_warmup_batches"].pop(key)
    with pytest.raises(ValueError):
        measurement_orders(m)


@pytest.mark.parametrize("mode", ["stable", "unstable", "timeout", "output", "wall_budget"])
def test_collection_bounds_and_raw_failure_retention(tmp_path, monkeypatch, mode):
    args, manifest, requests = setup_collection(tmp_path, monkeypatch)
    manifest.update(warmup_policy=POLICY, batch_target_ns=100000000)
    run.save(args.manifest, manifest)
    original = run.bounded_request
    counts = {}

    def request(driver, payload, seconds):
        original(driver, payload, seconds)
        key = payload["case"]["id"], payload["case"]["options"]["method"]
        counts[key] = counts.get(key, 0) + 1
        count = counts[key]
        if mode == "timeout" and count == 5:
            return dict(
                ok=False,
                action="measure",
                error={"kind": "ExternalLimit", "message": "Driver external wall limit exceeded"},
            )
        cost = 1000000 if mode != "unstable" or count % 2 else 2000000
        result = response(payload["iterations"], cost)
        if mode == "output" and count == 5:
            result["result"] = {"value": 2}
        return result

    monkeypatch.setattr(run, "bounded_request", request)
    if mode == "wall_budget":
        clock = iter([0, 100000])
        monkeypatch.setattr(run.time, "monotonic", lambda: next(clock))
    if mode == "stable":
        run.pilot(args)
        selected = run.read(args.output / "manifest.json")
        assert set(selected["case_warmup_batches"].values()) == {24}
    else:
        with pytest.raises(ValueError):
            run.pilot(args)
        assert not (args.output / "manifest.json").exists()
        assert run.read(args.output / "metadata.json")["complete"] is False
    rows = [json.loads(line) for line in (args.output / "pilot.jsonl").read_text().splitlines()]
    assert rows
    for row in rows:
        assert len(row["warmups"]) == 3
        assert len(row["warmups"]) + len(row["trials"]) <= MAX_TRIALS
    assert all(seconds <= 30 for _, seconds in requests if _["action"] == "measure")


@pytest.mark.parametrize(
    "fault",
    [
        None,
        "policy",
        "history",
        "map",
        "count",
        "stop",
        "missing_file",
        "json_duplicate",
        "json_nonfinite",
        "row_type",
        "response_type",
    ],
)
def test_new_pilot_evidence_binding(tmp_path, fault):
    # Reuse the legacy evidence fixture, then replace its timing protocol completely.
    from pilot_evidence import validate_pilot
    from test_pilot_evidence import pilot_case

    directory, manifest, captures, _ = pilot_case.__wrapped__(tmp_path)
    original = run.read(directory / "input-manifest.json")
    selected = run.read(directory / "manifest.json")
    metadata = run.read(directory / "metadata.json")
    rows = [json.loads(line) for line in (directory / "pilot.jsonl").read_text().splitlines()]
    raw_history = history()
    key = rows[0]["key"]
    for design in (original, selected, manifest):
        design.update(warmup_policy=POLICY, batch_target_ns=100000000)
    for design in (selected, manifest):
        design.update(iterations={key: 100}, case_warmup_batches={key: 24})
    rows[0].update(
        first=response(),
        warmups=raw_history[:3],
        trials=raw_history[3:],
        warm=raw_history[-1],
        iterations=100,
        warmup_batches=24,
    )
    if fault == "policy":
        manifest.pop("warmup_policy")
    elif fault == "history":
        rows[0].pop("trials")
    elif fault == "map":
        manifest["case_warmup_batches"][key] = 23
    elif fault == "count":
        rows[0]["warmup_batches"] = 23
    elif fault == "stop":
        rows[0]["trials"].append(response(100))
    metadata["manifest_sha256"] = digest(original)
    for name, obj in (("input-manifest", original), ("manifest", selected), ("metadata", metadata)):
        run.save(directory / f"{name}.json", obj)
    (directory / "pilot.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
    if fault in (
        None,
        "missing_file",
        "json_duplicate",
        "json_nonfinite",
        "row_type",
        "response_type",
    ):
        validate_pilot(directory, manifest, captures, {})
    else:
        with pytest.raises(ValueError):
            validate_pilot(directory, manifest, captures, {})
    if fault in ("missing_file", "json_duplicate", "json_nonfinite", "row_type", "response_type"):
        m, meta, samples = new_evidence()
        data = warm_rows(m, meta)
        meta["warmups_sha256"] = digest(data)
        if fault == "json_duplicate":
            (directory / "warmups.jsonl").write_text('{"key":1,"key":2}\n')
        elif fault == "json_nonfinite":
            (directory / "warmups.jsonl").write_text('{"value":NaN}\n')
        elif fault == "row_type":
            (directory / "warmups.jsonl").write_text("[]\n")
        elif fault == "response_type":
            data[0]["responses"][0] = None
            meta["warmups_sha256"] = digest(data)
            (directory / "warmups.jsonl").write_text("".join(json.dumps(r) + "\n" for r in data))
        with pytest.raises((ValueError, OSError)):
            validate_warmups(directory, m, meta, samples)
