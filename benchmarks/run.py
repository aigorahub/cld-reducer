"""Run bounded profiles, reference capture, calibration and paired measurements."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import random
import time
from contextlib import ExitStack
from pathlib import Path

from analysis import analyze
from cases import frozen_manifest, job_key, jobs
from common import (
    ROOT,
    Driver,
    DriverError,
    digest,
    input_digest,
    provenance,
    save,
    source_binding,
    source_identity,
    version_identity,
)


def read(path):
    return json.loads(Path(path).read_text())


def output_dir(path):
    path = Path(path).resolve()
    for checkout in (ROOT,):
        if path == checkout or checkout in path.parents:
            raise ValueError("Benchmark output must be outside the checkout")
    path.mkdir(parents=True, exist_ok=False)
    return path


def emit(stream, value):
    stream.write(json.dumps(value, allow_nan=False) + "\n")
    stream.flush()


def driver(language, repo, manifest, output, suffix):
    return Driver(
        language,
        repo,
        manifest["presolve"][language],
        output / f"{language}-{suffix}.stderr",
        manifest["memory_limit_mb"],
    )


def require_success(response):
    if not response["ok"]:
        raise DriverError(str(response.get("error", response)))
    return response


def load_manifest(path):
    m = read(path)
    if m.get("schema_version") != 1 or len({c["id"] for c in m["cases"]}) != len(m["cases"]):
        raise ValueError("Invalid manifest schema or duplicate case ids")
    if (
        not m["languages"]
        or len(set(m["languages"])) != len(m["languages"])
        or any(lang not in ("python", "r", "js") for lang in m["languages"])
    ):
        raise ValueError("Invalid languages")
    for field, minimum in (
        ("processes", 8),
        ("warmup_batches", 3),
        ("batches", 9),
        ("bootstrap_resamples", 10000),
        ("batch_target_ns", 1),
    ):
        if type(m[field]) is not int or m[field] < minimum:
            raise ValueError(f"Invalid measurement design: {field}")
    if (
        type(m["memory_limit_mb"]) not in (int, float)
        or not math.isfinite(m["memory_limit_mb"])
        or m["memory_limit_mb"] <= 0
    ):
        raise ValueError("Invalid memory limit")
    if (
        type(m["memory_growth_tolerance_mb"]) not in (int, float)
        or not math.isfinite(m["memory_growth_tolerance_mb"])
        or m["memory_growth_tolerance_mb"] < 0
    ):
        raise ValueError("Invalid memory growth tolerance")
    if set(m["methods"]) != {"letter_minimum", "assignment_minimum"} or len(m["methods"]) != 2:
        raise ValueError("Both methods must be present exactly once")
    for language in m["languages"]:
        if m["presolve"].get(language) not in (("off",) if language == "r" else ("on", "off")):
            raise ValueError("Invalid presolve setting")
    for c in m["cases"]:
        if (
            c["classification"] not in ("ordinary", "stress")
            or type(c["wall_seconds"]) not in (int, float)
            or not math.isfinite(c["wall_seconds"])
            or c["wall_seconds"] <= 0
        ):
            raise ValueError("Every case needs a class and a finite wall limit")
        if c["tier"] not in ("solve", "preprocess", "expected-error", "opt-in"):
            raise ValueError("Invalid case tier")
    return m


def external_failure(action, error):
    return {
        "ok": False,
        "action": action,
        "error": {"kind": "ExternalLimit", "message": str(error)},
    }


def bounded_request(d, request, seconds):
    try:
        return d.request(request, seconds)
    except DriverError as error:
        return external_failure(request["action"], error)


def bind_version(metadata, language, version):
    previous = metadata["versions"].setdefault(language, version)
    if version_identity(previous) != version_identity(version):
        raise ValueError(f"Dependency or settings changed: {language}")


def profiles(args):
    m, out = load_manifest(args.manifest), output_dir(args.output)
    metadata = provenance(args.repo)
    metadata["source"] = source_binding(args.repo, languages=m["languages"])
    metadata.update(
        manifest_sha256=digest(m), input_sha256=input_digest(m), complete=False, versions={}
    )
    metadata["profile_warmup_calls"] = m["warmup_batches"]
    save(out / "metadata.json", metadata)
    tiers = ("solve", "preprocess", "expected-error") + (("opt-in",) if args.include_opt_in else ())
    with (out / "profiles.jsonl").open("w") as f:
        for language in m["languages"]:
            for index, c in enumerate(jobs(m, tiers=tiers)):
                with driver(language, args.repo, m, out, f"profile-{index}") as d:
                    bind_version(
                        metadata, language, require_success(d.request({"action": "version"}, 60))
                    )
                    key = job_key(language, c)
                    action = (
                        "preprocess" if c["tier"] in ("preprocess", "expected-error") else "profile"
                    )
                    response = None
                    if action == "profile":
                        for _ in range(m["warmup_batches"]):
                            response = bounded_request(
                                d,
                                {"action": "measure", "case": c, "iterations": 1},
                                c["wall_seconds"],
                            )
                            if not response["ok"]:
                                break
                    if response is None or response["ok"]:
                        response = bounded_request(
                            d, {"action": action, "case": c}, c["wall_seconds"]
                        )
                    emit(f, {"key": key, "case": c, "response": response, "peak_rss": d.peak_rss})
                    print(
                        f"profile {key}: {'ok' if response['ok'] else response.get('error')}",
                        flush=True,
                    )
    metadata["source_after"] = source_binding(args.repo, languages=m["languages"])
    metadata["complete"] = metadata["source_after"] == metadata["source"]
    save(out / "metadata.json", metadata)


def fixture_mismatch(actual, expected):
    """Check independent frozen fixture expectations, separate from baseline vector equality."""
    groups = expected["groups"]
    wanted = {
        "groups": groups,
        "assignments": [expected["assignments"][g] for g in groups],
        "letters": [expected["letters"][g] for g in groups],
        "method": expected["method"],
        "relationship_preserved": expected["relationship_preserved"],
    }
    tokens = wanted["assignments"]
    wanted["adjacency"] = [[bool(set(a) & set(b)) for b in tokens] for a in tokens]
    wanted["rows"] = [
        {"group": g, "letters": wanted["letters"][i], "assignments": " ".join(tokens[i])}
        for i, g in enumerate(groups)
    ]
    errors = [key for key, value in wanted.items() if actual.get(key) != value]
    stats = dict(
        expected["stats"], objective=expected["objective"], solver_status=expected["solver_status"]
    )
    p = expected["reduction_pct"]
    stats["reduction_pct"] = p["numerator"] / p["denominator"] * 100 if p["denominator"] else 0
    errors += [
        "stats." + key for key, value in stats.items() if actual.get("stats", {}).get(key) != value
    ]
    return errors


def captures(args):
    m, out = load_manifest(args.manifest), output_dir(args.output)
    metadata = provenance(args.repo)
    metadata["source"] = source_binding(args.repo, languages=m["languages"])
    metadata.update(
        manifest_sha256=digest(m),
        input_sha256=input_digest(m),
        complete=False,
        versions={},
        checked=0,
        fixture_sha256={},
    )
    save(out / "metadata.json", metadata)
    cases = []
    for name in ("reduce", "reduce_letter_minimum", "reduce_weighted"):
        path = Path(args.repo) / "conformance/fixtures" / (name + ".json")
        metadata["fixture_sha256"][name] = hashlib.sha256(path.read_bytes()).hexdigest()
        for c in read(path)["cases"]:
            c["id"] = f"fixture/{name}/{c['id']}"
            c["options"]["method"] = c["expected"]["method"]
            cases.append(c)
            if "sigma_expected" in c:
                alternative = copy.deepcopy(c)
                alternative["id"] += "/sigma"
                alternative["expected"] = alternative.pop("sigma_expected")
                alternative["options"]["method"] = "assignment_minimum"
                cases.append(alternative)
    cases.extend(jobs(m))
    metadata["expected_keys"] = [
        {
            "language": lang,
            "id": c["id"],
            "method": c["options"]["method"],
            "oracle_fixture": "expected" in c,
        }
        for lang in m["languages"]
        for c in cases
    ]
    save(out / "metadata.json", metadata)
    reference = {}
    failures = []
    with (out / "vectors.jsonl").open("w") as f:
        for language in m["languages"]:
            with ExitStack() as stack:
                d = stack.enter_context(driver(language, args.repo, m, out, "capture"))
                metadata["versions"][language] = require_success(
                    d.request({"action": "version"}, 60)
                )
                for index, c in enumerate(cases):
                    result = bounded_request(
                        d, {"action": "capture", "case": c}, c.get("wall_seconds", 60)
                    )
                    if not result["ok"]:
                        if job_key(language, c) not in m["baseline_failures"]:
                            raise DriverError(
                                f"Unexpected capture failure: {language}/{c['id']}: {result}"
                            )
                        emit(
                            f,
                            {
                                "language": language,
                                "id": c["id"],
                                "method": c["options"]["method"],
                                "oracle_fixture": False,
                                "case": c,
                                "response": result,
                                "mismatch": [],
                            },
                        )
                        metadata["checked"] += 1
                        d.close()
                        d = stack.enter_context(
                            driver(language, args.repo, m, out, f"capture-after-{index}")
                        )
                        bind_version(
                            metadata,
                            language,
                            require_success(d.request({"action": "version"}, 60)),
                        )
                        continue
                    canonical = result.get("canonical")
                    if not canonical or any(x not in (0, 1) for x in canonical["selected"]):
                        raise ValueError("Missing canonical vector")
                    if canonical["objective"] != result["result"]["stats"]["objective"]:
                        raise ValueError("Canonical and public objectives differ")
                    mismatch = (
                        fixture_mismatch(result["result"], c["expected"]) if "expected" in c else []
                    )
                    identity = (c["id"], c["options"]["method"])
                    value = {"result": result["result"], "canonical": canonical}
                    if identity in reference and reference[identity] != value:
                        mismatch.append("cross_language_result_or_vector")
                    reference.setdefault(identity, value)
                    if mismatch:
                        failures.append({"language": language, "id": c["id"], "mismatch": mismatch})
                    emit(
                        f,
                        {
                            "language": language,
                            "id": c["id"],
                            "method": c["options"]["method"],
                            "oracle_fixture": "expected" in c,
                            "case": c,
                            **value,
                            "mismatch": mismatch,
                        },
                    )
                    metadata["checked"] += 1
                    if index % 100 == 0:
                        print(f"capture {language}: {index + 1}/{len(cases)}", flush=True)
    metadata["source_after"] = source_binding(args.repo, languages=m["languages"])
    metadata["failures"] = failures
    metadata["complete"] = metadata["source_after"] == metadata["source"] and not failures
    save(out / "metadata.json", metadata)
    if failures:
        raise ValueError(f"{len(failures)} canonical or fixture mismatches")


def pilot(args):
    m, out = load_manifest(args.manifest), output_dir(args.output)
    if m["frozen"]:
        raise ValueError("Do not recalibrate a frozen candidate manifest")
    metadata = provenance(args.repo)
    metadata["source"] = source_binding(args.repo, languages=m["languages"])
    metadata.update(
        manifest_sha256=digest(m), input_sha256=input_digest(m), complete=False, versions={}
    )
    save(out / "metadata.json", metadata)
    with (out / "pilot.jsonl").open("w") as f:
        for language in m["languages"]:
            for index, c in enumerate(jobs(m)):
                key = job_key(language, c)
                with driver(language, args.repo, m, out, f"pilot-{index}") as d:
                    version = require_success(d.request({"action": "version"}, 60))
                    bind_version(metadata, language, version)
                    first = bounded_request(
                        d, {"action": "measure", "case": c, "iterations": 1}, c["wall_seconds"]
                    )
                    if not first["ok"]:
                        m["baseline_failures"].append(key)
                        emit(f, {"key": key, "versions": version, "first": first})
                        continue
                    warm = first
                    for _ in range(m["warmup_batches"]):
                        warm = bounded_request(
                            d, {"action": "measure", "case": c, "iterations": 1}, c["wall_seconds"]
                        )
                        if not warm["ok"]:
                            break
                    if not warm["ok"]:
                        m["baseline_failures"].append(key)
                        emit(f, {"key": key, "versions": version, "first": first, "warm": warm})
                        continue
                    iterations = max(
                        1, min(100000, math.ceil(m["batch_target_ns"] / warm["elapsed_ns"]))
                    )
                    m["iterations"][key] = iterations
                    emit(
                        f,
                        {
                            "key": key,
                            "versions": version,
                            "first": first,
                            "warm": warm,
                            "iterations": iterations,
                            "peak_rss": d.peak_rss,
                        },
                    )
                    print(f"pilot {key}: {iterations} iterations", flush=True)
    m["pilot_source"] = metadata["source"]
    m["pilot_harness"] = metadata["harness"]
    m["baseline_versions"] = metadata["versions"]
    save(out / "manifest.json", m)
    metadata["source_after"] = source_binding(args.repo, languages=m["languages"])
    metadata["complete"] = metadata["source_after"] == metadata["source"]
    save(out / "metadata.json", metadata)


def compare(args):
    m, out = load_manifest(args.manifest), output_dir(args.output)
    if args.kind == "candidate" and not m["frozen"]:
        raise ValueError("Candidate timing requires a frozen manifest")
    before = {
        label: source_binding(repo, languages=m["languages"])
        for label, repo in (("baseline", args.baseline), ("candidate", args.candidate))
    }
    if args.kind == "calibration" and source_identity(before["baseline"]) != source_identity(
        before["candidate"]
    ):
        raise ValueError("A/A calibration requires identical source and executable files")
    bound = m.get("baseline_source") if args.kind == "candidate" else m.get("pilot_source")
    if not bound or source_identity(bound) != source_identity(before["baseline"]):
        raise ValueError("Baseline differs from the calibrated reference")
    if set(m["iterations"]) != {job_key(lang, c) for lang in m["languages"] for c in jobs(m)} - set(
        m["baseline_failures"]
    ):
        raise ValueError("Iteration counts do not cover the timed case set")
    meta = {
        "manifest_sha256": digest(m),
        "input_sha256": input_digest(m),
        "source_before": before,
        "harness": source_binding(ROOT),
        "complete": False,
        "kind": args.kind,
        "run_id": args.run_id,
        "versions": [],
        "started_unix": time.time(),
        "machine": provenance(args.baseline)["machine"],
    }
    save(out / "metadata.json", meta)
    all_rows = []
    try:
        with (
            (out / "samples.jsonl").open("w") as samples,
            (out / "results.jsonl").open("w") as results,
        ):
            for language in m["languages"]:
                for process in range(m["processes"]):
                    with ExitStack() as stack:
                        pair = [
                            stack.enter_context(
                                driver(language, repo, m, out, f"{process}-{label}")
                            )
                            for repo, label in (
                                (args.baseline, "baseline"),
                                (args.candidate, "candidate"),
                            )
                        ]
                        versions = [
                            require_success(d.request({"action": "version"}, 60)) for d in pair
                        ]
                        expected_version = version_identity(m["baseline_versions"][language])
                        if any(version_identity(v) != expected_version for v in versions):
                            raise ValueError(
                                f"Dependencies or settings differ from the pilot: {language}"
                            )
                        meta["versions"].append(
                            {
                                "language": language,
                                "process": process,
                                "versions": versions,
                                "pids": [d.process.pid for d in pair],
                            }
                        )
                        rng = random.Random(m["order_seed"] + process)
                        for c in jobs(m):
                            key = job_key(language, c)
                            if key in m["baseline_failures"]:
                                continue
                            iterations = m["iterations"][key]
                            request = {"action": "measure", "case": c, "iterations": iterations}
                            for _ in range(m["warmup_batches"]):
                                for i in rng.sample([0, 1], 2):
                                    require_success(pair[i].request(request, c["wall_seconds"]))
                            for batch in range(m["batches"]):
                                order = rng.sample([0, 1], 2)
                                responses = [None, None]
                                for i in order:
                                    responses[i] = pair[i].request(request, c["wall_seconds"])
                                ok = all(r["ok"] for r in responses)
                                correct = ok and responses[0]["result"] == responses[1]["result"]
                                row = {
                                    "key": key,
                                    "language": language,
                                    "process": process,
                                    "batch": batch,
                                    "iterations": iterations,
                                    "order": order,
                                    "ok": ok,
                                    "correct": correct,
                                    "baseline_ns": responses[0].get("elapsed_ns", 0) / iterations,
                                    "candidate_ns": responses[1].get("elapsed_ns", 0) / iterations,
                                    "result_hashes": [digest(r.get("result")) for r in responses],
                                    "peak_rss": [d.peak_rss for d in pair],
                                    "rss": [d.rss for d in pair],
                                }
                                emit(samples, row)
                                all_rows.append(row)
                                if batch == 0:
                                    emit(
                                        results,
                                        {"key": key, "process": process, "responses": responses},
                                    )
                                if not correct:
                                    raise ValueError(f"Output mismatch or failed call: {key}")
                            print(
                                f"{args.kind} {language} process {process + 1}/{m['processes']} "
                                f"{c['id']} {c['options']['method']}",
                                flush=True,
                            )
            for language in m["languages"]:
                for index, c in enumerate(jobs(m)):
                    key = job_key(language, c)
                    if key not in m["baseline_failures"]:
                        continue
                    responses, versions, pids = [], [], []
                    for repo, label in ((args.baseline, "baseline"), (args.candidate, "candidate")):
                        with driver(language, repo, m, out, f"excluded-{index}-{label}") as d:
                            version = require_success(d.request({"action": "version"}, 60))
                            if version_identity(version) != version_identity(
                                m["baseline_versions"][language]
                            ):
                                raise ValueError("Excluded-case dependencies differ from pilot")
                            versions.append(version)
                            pids.append(d.process.pid)
                            responses.append(
                                bounded_request(
                                    d, {"action": "capture", "case": c}, c["wall_seconds"]
                                )
                            )
                    emit(
                        results,
                        {
                            "key": key,
                            "process": 0,
                            "baseline_failure": True,
                            "responses": responses,
                            "versions": versions,
                            "pids": pids,
                        },
                    )
        meta["source_after"] = {
            "baseline": source_binding(args.baseline, languages=m["languages"]),
            "candidate": source_binding(args.candidate, languages=m["languages"]),
        }
        meta["complete"] = meta["source_after"] == before
    finally:
        meta["finished_unix"] = time.time()
        save(out / "metadata.json", meta)
        report = analyze(m, meta, all_rows)
        save(out / "analysis.json", report)
    print(json.dumps({"pass": report["pass"], "reasons": report["reasons"]}), flush=True)


def freeze(args):
    m = load_manifest(args.manifest)
    if m["frozen"]:
        raise ValueError("Manifest is already frozen")
    metadata = read(Path(args.calibration) / "metadata.json")
    samples = [
        json.loads(line)
        for line in (Path(args.calibration) / "samples.jsonl").read_text().splitlines()
    ]
    calibration = analyze(m, metadata, samples)
    if (
        not calibration["pass"]
        or calibration["manifest_sha256"] != digest(m)
        or metadata["kind"] != "calibration"
    ):
        raise ValueError("A/A calibration must pass for this exact manifest")
    profile_meta = read(Path(args.profiles) / "metadata.json")
    if (
        not profile_meta["complete"]
        or profile_meta["source"] != profile_meta.get("source_after")
        or source_identity(profile_meta["source"])
        != source_identity(metadata["source_before"]["baseline"])
        or profile_meta.get("input_sha256") != input_digest(m)
    ):
        raise ValueError("Profiles do not bind the calibrated baseline")
    rows = [
        json.loads(line)
        for line in (Path(args.profiles) / "profiles.jsonl").read_text().splitlines()
    ]
    expected = {
        job_key(lang, c): c
        for lang in m["languages"]
        for c in jobs(m, tiers=("solve", "preprocess", "expected-error"))
    }
    required_rows = [row for row in rows if row["case"]["tier"] != "opt-in"]
    if len(required_rows) != len(expected) or {row["key"] for row in required_rows} != set(
        expected
    ):
        raise ValueError("Profile rows are incomplete, duplicated, or unexpected")
    for row in required_rows:
        if row["case"] != expected[row["key"]]:
            raise ValueError("Profile inputs differ")
        tier, response = row["case"]["tier"], row["response"]
        if tier == "expected-error":
            if response[
                "ok"
            ] or "maximal clique enumeration exceeded max_cliques=" not in response.get(
                "error", {}
            ).get("message", ""):
                raise ValueError("Expected clique cap was not reached")
        elif not response["ok"] and row["key"] not in m["baseline_failures"]:
            raise ValueError("Unexpected baseline profile or preprocessing failure")
    for language in m["languages"]:
        if version_identity(profile_meta["versions"][language]) != version_identity(
            m["baseline_versions"][language]
        ):
            raise ValueError("Profile dependency versions differ")
    capture_meta = read(Path(args.capture) / "metadata.json")
    if (
        not capture_meta.get("complete")
        or capture_meta.get("failures")
        or capture_meta.get("input_sha256") != input_digest(m)
        or source_identity(capture_meta["source"]) != source_identity(profile_meta["source"])
        or capture_meta["source"] != capture_meta.get("source_after")
    ):
        raise ValueError("Baseline canonical capture is incomplete or mismatched")
    for language in m["languages"]:
        if version_identity(capture_meta["versions"][language]) != version_identity(
            m["baseline_versions"][language]
        ):
            raise ValueError("Capture dependency versions differ")
    captures_data = [
        json.loads(line) for line in (Path(args.capture) / "vectors.jsonl").read_text().splitlines()
    ]

    def keys(row):
        return row["language"], row["id"], row["method"]

    if (
        len(captures_data) != len(capture_meta["expected_keys"])
        or {keys(row) for row in captures_data}
        != {keys(row) for row in capture_meta["expected_keys"]}
        or any(row.get("mismatch") for row in captures_data)
    ):
        raise ValueError("Baseline canonical vectors are missing or duplicated")
    eligible = {}
    for row in rows:
        r, c = row["response"], row["case"]
        if c["tier"] != "solve" or not r["ok"]:
            continue
        metrics, phases = r["metrics"], r["phases_ns"]
        fraction = metrics["solver_total_ns"] / phases["total"]
        if metrics["essential_cover"] and fraction >= 0.25:
            language, method, _ = row["key"].split("|", 2)
            eligible.setdefault(language + "|" + method, []).append(row["key"])
    if not eligible:
        raise ValueError("Profiles do not support an essential-cover target")
    m["gain_targets"] = eligible
    m["candidate"] = "essential-cover-certificate"
    m["eligibility_rule"] = (
        "essential_cover and measured inclusive adapter wall time "
        ">= 25 percent of profiled full API time"
    )
    m["profile_sha256"] = digest(rows)
    m["calibration_sha256"] = digest(calibration)
    m["calibration_metadata_sha256"] = digest(metadata)
    m["baseline_capture_sha256"] = digest(captures_data)
    m["baseline_source"] = metadata["source_before"]["baseline"]
    m["frozen"] = True
    for group, keys in eligible.items():
        for split in ("development", "validation"):
            if sum(k.split("|", 2)[2].startswith(split + "/") for k in keys) < 5:
                raise ValueError(f"Target group lacks five distinct {split} cases: {group}")
    save(args.output, m)


def final_audit(args):
    from gates import audit

    report = audit(
        load_manifest(args.manifest),
        args.runs,
        args.baseline_capture,
        args.candidate_capture,
        args.baseline_profiles,
        args.candidate_profiles,
    )
    save(args.output, report)
    print(json.dumps({"pass": report["pass"], "reasons": report["reasons"]}), flush=True)
    if not report["pass"]:
        raise ValueError("Final acceptance gate failed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    generate = sub.add_parser("manifest")
    generate.add_argument("--repo", required=True)
    generate.add_argument("--output", required=True)
    for name in ("profile", "capture", "pilot"):
        p = sub.add_parser(name)
        p.add_argument("--repo", required=True)
        p.add_argument("--manifest", required=True)
        p.add_argument("--output", required=True)
        if name == "profile":
            p.add_argument("--include-opt-in", action="store_true")
    p = sub.add_parser("compare")
    for arg in ("manifest", "baseline", "candidate", "output", "run-id"):
        p.add_argument("--" + arg, required=True)
    p.add_argument("--kind", choices=("calibration", "candidate"), required=True)
    p = sub.add_parser("freeze")
    for arg in ("manifest", "profiles", "capture", "calibration", "output"):
        p.add_argument("--" + arg, required=True)
    p = sub.add_parser("audit")
    for arg in (
        "manifest",
        "baseline-capture",
        "candidate-capture",
        "baseline-profiles",
        "candidate-profiles",
        "output",
    ):
        p.add_argument("--" + arg, required=True)
    p.add_argument("--runs", nargs=2, required=True)
    args = parser.parse_args()
    if args.action == "manifest":
        save(args.output, frozen_manifest(Path(args.repo)))
    else:
        {
            "profile": profiles,
            "capture": captures,
            "pilot": pilot,
            "compare": compare,
            "freeze": freeze,
            "audit": final_audit,
        }[args.action](args)


if __name__ == "__main__":
    main()
