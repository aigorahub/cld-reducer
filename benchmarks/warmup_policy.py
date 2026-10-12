"""Bounded reference-only selection and validation of warm measurement schedules."""

from __future__ import annotations

import json
import math
import random
import statistics
from pathlib import Path

from cases import job_key, jobs
from common import digest

POLICY = "warmed-pilot-v1"
MAX_TRIALS = 48
MAX_ITERATIONS = 100000
MAX_WARMUPS = 64
TARGET_NS = 100000000
MIN_BATCH_NS = 50000000
MIN_WARM_NS = 2000000000


def enabled(manifest):
    policy = manifest.get("warmup_policy")
    if policy not in (None, POLICY):
        raise ValueError("Unknown warmup policy")
    return policy == POLICY


def warmup_count(manifest, key):
    if not enabled(manifest):
        return manifest["warmup_batches"]
    value = manifest.get("case_warmup_batches", {}).get(key)
    if type(value) is not int or not 3 <= value <= MAX_WARMUPS:
        raise ValueError(f"Missing or invalid frozen warmup count: {key}")
    return value


def per_call(response):
    elapsed, count = response.get("elapsed_ns"), response.get("iterations")
    if (
        type(elapsed) not in (int, float)
        or not math.isfinite(elapsed)
        or elapsed <= 0
        or type(count) is not int
        or not 1 <= count <= MAX_ITERATIONS
    ):
        raise ValueError("Invalid warm pilot timing")
    return elapsed / count


def next_iterations(history):
    return max(
        1, min(MAX_ITERATIONS, math.ceil(TARGET_NS / min(per_call(r) for r in history[-3:])))
    )


def settled(history):
    if len(history) < 6 or sum(r["elapsed_ns"] for r in history) < MIN_WARM_NS:
        return False
    values = [per_call(r) for r in history[-6:]]
    ratio = statistics.median(values[3:]) / statistics.median(values[:3])
    return 1 / 1.03 <= ratio <= 1.03 and max(values) / min(values) <= 1.15


def replay_count(history, iterations):
    count = max(3, math.ceil(sum(r["iterations"] for r in history) / iterations) + 3)
    if count > MAX_WARMUPS:
        raise ValueError("Warm pilot requires more than 64 replay batches")
    return count


def validate_history(history, initial_count, result):
    """Reconstruct every adaptive request and the first permitted stop."""
    if not isinstance(history, list) or not initial_count <= len(history) <= MAX_TRIALS:
        raise ValueError("Missing or excessive warm pilot history")
    for index, response in enumerate(history):
        if (
            not isinstance(response, dict)
            or response.get("ok") is not True
            or response.get("action") != "measure"
            or "error" in response
            or response.get("result") != result
        ):
            raise ValueError("Warm pilot output or action differs")
        per_call(response)
        expected = 1 if index < initial_count else next_iterations(history[:index])
        if response["iterations"] != expected:
            raise ValueError("Warm pilot adaptive request differs")
        if index >= initial_count and settled(history[:index]):
            raise ValueError("Warm pilot continued after its fixed stopping rule")
    if not settled(history):
        raise ValueError("Warm pilot did not settle within its bounds")
    count = next_iterations(history)
    return count, replay_count(history, count)


def parse_row(text):
    def pairs(items):
        row = {}
        for key, value in items:
            if key in row:
                raise ValueError(f"Duplicate warmup field: {key}")
            row[key] = value
        return row

    def invalid(value):
        raise ValueError(f"Nonfinite warmup JSON value: {value}")

    row = json.loads(text, object_pairs_hook=pairs, parse_constant=invalid)
    if not isinstance(row, dict):
        raise ValueError("Warmup row must be an object")
    return row


def validate_warmups(directory, manifest, metadata, samples):
    """Bind full warm outputs and reconstruct the same RNG use as collection."""
    if not enabled(manifest):
        return None
    from analysis import paired_orders

    path = Path(directory) / "warmups.jsonl"
    rows = [parse_row(line) for line in path.read_text().splitlines()]
    if digest(rows) != metadata.get("warmups_sha256"):
        raise ValueError("Raw warmup digest differs")
    measured = {(r["key"], r["process"]): r for r in samples}
    pids = {(r["language"], r["process"]): r["pids"] for r in metadata["versions"]}
    index = 0
    for language in manifest["languages"]:
        for process in range(manifest["processes"]):
            rng = random.Random(manifest["order_seed"] + process)
            for case in jobs(manifest):
                key = job_key(language, case)
                if key in manifest["baseline_failures"]:
                    continue
                for batch, order in enumerate(
                    paired_orders(rng, warmup_count(manifest, key), process)
                ):
                    if index >= len(rows):
                        raise ValueError("Raw warmup inventory is incomplete")
                    row = rows[index]
                    index += 1
                    if (
                        row.get("key") != key
                        or type(row.get("process")) is not int
                        or type(row.get("batch")) is not int
                        or not isinstance(row.get("order"), list)
                        or any(type(value) is not int for value in row["order"])
                        or not isinstance(row.get("pids"), list)
                        or any(type(value) is not int for value in row["pids"])
                        or row.get("process") != process
                        or row.get("batch") != batch
                        or row.get("order") != order
                        or row.get("pids") != pids[language, process]
                    ):
                        raise ValueError("Raw warmup schedule or process differs")
                    responses = row.get("responses")
                    if not isinstance(responses, list) or len(responses) != 2:
                        raise ValueError("Raw warmup response pair is missing")
                    for side, response in enumerate(responses):
                        if (
                            not isinstance(response, dict)
                            or response.get("ok") is not True
                            or "error" in response
                            or response.get("action") != "measure"
                            or response.get("iterations") != manifest["iterations"][key]
                            or digest(response.get("result"))
                            != measured[key, process]["result_hashes"][side]
                        ):
                            raise ValueError("Raw warmup output or iterations differ")
                        per_call(response)
                paired_orders(rng, manifest["batches"], process)
    if index != len(rows):
        raise ValueError("Raw warmup inventory has extra rows")
    return digest(rows)
