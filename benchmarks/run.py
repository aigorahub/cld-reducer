"""Run bounded profiles, reference capture, calibration and paired measurements."""
from __future__ import annotations

import argparse
import copy
import json
import math
import random
import sys
import time
from contextlib import ExitStack
from pathlib import Path

from analysis import analyze
from cases import frozen_manifest, job_key, jobs
from common import Driver, DriverError, ROOT, digest, provenance, save, source_binding


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
    return Driver(language, repo, manifest["presolve"][language],
                  output / f"{language}-{suffix}.stderr", manifest["memory_limit_mb"])


def require_success(response):
    if not response["ok"]:
        raise DriverError(str(response.get("error", response)))
    return response


def load_manifest(path):
    m = read(path)
    if m.get("schema_version") != 1 or len({c["id"] for c in m["cases"]}) != len(m["cases"]):
        raise ValueError("Invalid manifest schema or duplicate case ids")
    if not m["languages"] or any(lang not in ("python", "r", "js") for lang in m["languages"]):
        raise ValueError("Invalid languages")
    if m["processes"] < 8 or m["warmup_batches"] < 3 or m["batches"] < 1 or m["memory_limit_mb"] <= 0:
        raise ValueError("Invalid measurement design")
    if m["bootstrap_resamples"] < 10000:
        raise ValueError("At least 10000 bootstrap resamples are required")
    for c in m["cases"]:
        if c["classification"] not in ("ordinary", "stress") or c["wall_seconds"] <= 0:
            raise ValueError("Every case needs a class and a finite wall limit")
    return m


def profiles(args):
    m, out = load_manifest(args.manifest), output_dir(args.output)
    metadata = provenance(args.repo)
    metadata.update(manifest_sha256=digest(m), complete=False, versions={})
    save(out / "metadata.json", metadata)
    tiers = ("solve", "preprocess", "expected-error") + (("opt-in",) if args.include_opt_in else ())
    with (out / "profiles.jsonl").open("w") as f:
        for language in m["languages"]:
            with driver(language, args.repo, m, out, "profile") as d:
                metadata["versions"][language] = require_success(d.request({"action": "version"}, 60))
                for c in jobs(m, tiers=tiers):
                    key = job_key(language, c)
                    action = "preprocess" if c["tier"] in ("preprocess", "expected-error") else "profile"
                    try:
                        response = d.request({"action": action, "case": c}, c["wall_seconds"])
                    except DriverError as error:
                        response = {"ok": False, "action": action,
                                    "error": {"kind": "ExternalLimit", "message": str(error)}}
                        emit(f, {"key": key, "case": c, "response": response, "peak_rss": d.peak_rss})
                        raise
                    emit(f, {"key": key, "case": c, "response": response, "peak_rss": d.peak_rss})
                    print(f"profile {key}: {'ok' if response['ok'] else response.get('error')}", flush=True)
    metadata["source_after"] = source_binding(args.repo)
    metadata["complete"] = metadata["source_after"] == metadata["source"]
    save(out / "metadata.json", metadata)


def fixture_mismatch(actual, expected):
    """Check independent frozen fixture expectations, separate from baseline vector equality."""
    groups = expected["groups"]
    wanted = {"groups": groups, "assignments": [expected["assignments"][g] for g in groups],
              "letters": [expected["letters"][g] for g in groups], "method": expected["method"],
              "relationship_preserved": expected["relationship_preserved"]}
    errors = [key for key, value in wanted.items() if actual.get(key) != value]
    stats = dict(expected["stats"], objective=expected["objective"], solver_status=expected["solver_status"])
    p = expected["reduction_pct"]
    stats["reduction_pct"] = p["numerator"] / p["denominator"] * 100 if p["denominator"] else 0
    errors += ["stats." + key for key, value in stats.items() if actual.get("stats", {}).get(key) != value]
    return errors


def captures(args):
    m, out = load_manifest(args.manifest), output_dir(args.output)
    metadata = provenance(args.repo)
    metadata.update(manifest_sha256=digest(m), complete=False, versions={}, checked=0)
    save(out / "metadata.json", metadata)
    cases = []
    for name in ("reduce", "reduce_letter_minimum", "reduce_weighted"):
        for c in read(Path(args.repo) / "conformance/fixtures" / (name + ".json"))["cases"]:
            c["id"] = f"fixture/{name}/{c['id']}"
            c["options"]["method"] = c["expected"]["method"]
            cases.append(c)
    cases.extend(jobs(m))
    reference = {}
    failures = []
    with (out / "vectors.jsonl").open("w") as f:
        for language in m["languages"]:
            with driver(language, args.repo, m, out, "capture") as d:
                metadata["versions"][language] = require_success(d.request({"action": "version"}, 60))
                for index, c in enumerate(cases):
                    result = require_success(d.request({"action": "capture", "case": c}, c.get("wall_seconds", 60)))
                    canonical = result.get("canonical")
                    if not canonical or any(x not in (0, 1) for x in canonical["selected"]):
                        raise ValueError("Missing canonical vector")
                    if canonical["objective"] != result["result"]["stats"]["objective"]:
                        raise ValueError("Canonical and public objectives differ")
                    mismatch = fixture_mismatch(result["result"], c["expected"]) if "expected" in c else []
                    identity = (c["id"], c["options"]["method"])
                    value = {"result": result["result"], "canonical": canonical}
                    if identity in reference and reference[identity] != value:
                        mismatch.append("cross_language_result_or_vector")
                    reference.setdefault(identity, value)
                    if mismatch:
                        failures.append({"language": language, "id": c["id"], "mismatch": mismatch})
                    emit(f, {"language": language, "id": c["id"], "method": c["options"]["method"],
                             "oracle_fixture": "expected" in c, **value, "mismatch": mismatch})
                    metadata["checked"] += 1
                    if index % 100 == 0:
                        print(f"capture {language}: {index + 1}/{len(cases)}", flush=True)
    metadata["source_after"] = source_binding(args.repo)
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
    metadata.update(manifest_sha256=digest(m), complete=False)
    save(out / "metadata.json", metadata)
    with (out / "pilot.jsonl").open("w") as f:
        for language in m["languages"]:
            for index, c in enumerate(jobs(m)):
                key = job_key(language, c)
                with driver(language, args.repo, m, out, f"pilot-{index}") as d:
                    version = require_success(d.request({"action": "version"}, 60))
                    first = d.request({"action": "measure", "case": c, "iterations": 1}, c["wall_seconds"])
                    if not first["ok"]:
                        m["baseline_failures"].append(key)
                        emit(f, {"key": key, "versions": version, "first": first})
                        continue
                    warm = first
                    for _ in range(m["warmup_batches"]):
                        warm = require_success(d.request({"action": "measure", "case": c, "iterations": 1}, c["wall_seconds"]))
                    iterations = max(1, min(100000, math.ceil(m["batch_target_ns"] / warm["elapsed_ns"])))
                    m["iterations"][key] = iterations
                    emit(f, {"key": key, "versions": version, "first": first, "warm": warm,
                             "iterations": iterations, "peak_rss": d.peak_rss})
                    print(f"pilot {key}: {iterations} iterations", flush=True)
    m["pilot_source"] = metadata["source"]
    m["pilot_harness"] = metadata["harness"]
    save(out / "manifest.json", m)
    metadata["source_after"] = source_binding(args.repo)
    metadata["complete"] = metadata["source_after"] == metadata["source"]
    save(out / "metadata.json", metadata)


def compare(args):
    m, out = load_manifest(args.manifest), output_dir(args.output)
    if args.kind == "candidate" and not m["frozen"]:
        raise ValueError("Candidate timing requires a frozen manifest")
    before = {"baseline": source_binding(args.baseline), "candidate": source_binding(args.candidate)}
    meta = {"manifest_sha256": digest(m), "source_before": before, "harness": source_binding(ROOT),
            "complete": False, "kind": args.kind, "run_id": args.run_id, "versions": [],
            "started_unix": time.time(), "machine": provenance(args.baseline)["machine"]}
    save(out / "metadata.json", meta)
    all_rows = []
    try:
        with (out / "samples.jsonl").open("w") as samples, (out / "results.jsonl").open("w") as results:
            for language in m["languages"]:
                for process in range(m["processes"]):
                    with ExitStack() as stack:
                        pair = [stack.enter_context(driver(language, repo, m, out, f"{process}-{label}"))
                                for repo, label in ((args.baseline, "baseline"), (args.candidate, "candidate"))]
                        versions = [require_success(d.request({"action": "version"}, 60)) for d in pair]
                        meta["versions"].append({"language": language, "process": process, "versions": versions})
                        rng = random.Random(m["order_seed"] + process)
                        for c in jobs(m):
                            key = job_key(language, c)
                            if key in m["baseline_failures"]:
                                responses = [d.request({"action": "capture", "case": c}, c["wall_seconds"]) for d in pair]
                                emit(results, {"key": key, "baseline_failure": True, "responses": responses})
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
                                row = {"key": key, "language": language, "process": process, "batch": batch,
                                       "iterations": iterations, "order": order, "ok": ok, "correct": correct,
                                       "baseline_ns": responses[0].get("elapsed_ns", 0) / iterations,
                                       "candidate_ns": responses[1].get("elapsed_ns", 0) / iterations,
                                       "result_hashes": [digest(r.get("result")) for r in responses],
                                       "peak_rss": [d.peak_rss for d in pair]}
                                emit(samples, row)
                                all_rows.append(row)
                                if batch == 0:
                                    emit(results, {"key": key, "process": process, "responses": responses})
                                if not correct:
                                    raise ValueError(f"Output mismatch or failed call: {key}")
                            print(f"{args.kind} {language} process {process + 1}/{m['processes']} {c['id']} {c['options']['method']}", flush=True)
        meta["source_after"] = {"baseline": source_binding(args.baseline), "candidate": source_binding(args.candidate)}
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
    calibration = read(Path(args.calibration) / "analysis.json")
    metadata = read(Path(args.calibration) / "metadata.json")
    if not calibration["pass"] or calibration["manifest_sha256"] != digest(m) or metadata["kind"] != "calibration":
        raise ValueError("A/A calibration must pass for this exact manifest")
    profile_meta = read(Path(args.profiles) / "metadata.json")
    if not profile_meta["complete"] or profile_meta["source"] != metadata["source_before"]["baseline"]:
        raise ValueError("Profiles do not bind the calibrated baseline")
    rows = [json.loads(line) for line in (Path(args.profiles) / "profiles.jsonl").read_text().splitlines()]
    eligible = {}
    for row in rows:
        r, c = row["response"], row["case"]
        if c["tier"] != "solve" or not r["ok"]:
            continue
        metrics, phases = r["metrics"], r["phases_ns"]
        fraction = metrics["solver_total_ns"] / phases["total"]
        if metrics["essential_cover"] and fraction >= .25:
            language, method, _ = row["key"].split("|", 2)
            eligible.setdefault(language + "|" + method, []).append(row["key"])
    if not eligible:
        raise ValueError("Profiles do not support an essential-cover target")
    m["gain_targets"] = eligible
    m["candidate"] = "essential-cover-certificate"
    m["eligibility_rule"] = "essential_cover and measured inclusive adapter wall time >= 25 percent of profiled full API time"
    m["profile_sha256"] = digest(rows)
    m["calibration_sha256"] = digest(calibration)
    m["frozen"] = True
    for group, keys in eligible.items():
        for split in ("development", "validation"):
            if sum(k.split("|", 2)[2].startswith(split + "/") for k in keys) < 5:
                raise ValueError(f"Target group lacks five distinct {split} cases: {group}")
    save(args.output, m)


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
    for arg in ("manifest", "profiles", "calibration", "output"):
        p.add_argument("--" + arg, required=True)
    args = parser.parse_args()
    if args.action == "manifest":
        save(args.output, frozen_manifest(Path(args.repo)))
    else:
        {"profile": profiles, "capture": captures, "pilot": pilot, "compare": compare, "freeze": freeze}[args.action](args)


if __name__ == "__main__":
    main()
