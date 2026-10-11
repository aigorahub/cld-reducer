"""Bind process peak receipts to the exact benchmark process inventory."""

from __future__ import annotations

import json
import math
import re
from contextlib import contextmanager
from pathlib import Path

from common import DriverError, digest
from process_guard import COVERAGE, ProcessGuardError, read_receipt

DRIVERS = {
    "python": "benchmarks/python_driver.py",
    "r": "benchmarks/r_driver.R",
    "js": "benchmarks/js_driver.mjs",
}
MEMORY_ERROR = {"kind": "ExternalLimit", "message": "Driver memory limit exceeded"}
WALL_ERROR = {"kind": "ExternalLimit", "message": "Driver external wall limit exceeded"}


@contextmanager
def record_driver(driver, language, repo, output, inventory, *, allow_close_failure=False):
    """Append one record after close, including cleanup after a failed request."""
    inventory.append(
        {"pid": driver.process.pid, "language": language, "source_path": str(Path(repo).resolve())}
    )
    body_failed = False
    close_error = None
    try:
        yield driver
    except BaseException:
        body_failed = True
        raise
    finally:
        try:
            driver.close()
        except DriverError as error:
            close_error = error
        record = {
            "schema_version": 1,
            "language": language,
            "guard_pid": driver.process.pid,
            "command": driver.command,
            "receipt_file": driver.receipt_path.name,
            "receipt": driver.memory_receipt,
            "sampled_peak_rss": driver.sampled_peak_rss,
            "peak_rss": driver.peak_rss,
            "resource_error": driver.resource_error,
        }
        try:
            with (Path(output) / "resources.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(record, allow_nan=False, separators=(",", ":")) + "\n")
                stream.flush()
        except OSError:
            if not body_failed:
                raise
            # The original error still aborts collection. Missing resource
            # evidence prevents any later audit from accepting this directory.
        if close_error is not None and not body_failed and not allow_close_failure:
            raise close_error


def closed_response(driver, response, action):
    """Remove apparent success when native peak evidence fails at process exit."""
    if driver.resource_error and response.get("ok") is True:
        message = (
            MEMORY_ERROR["message"]
            if driver.peak_rss > driver.memory_limit
            else driver.resource_error
        )
        return {
            "ok": False,
            "action": action,
            "error": {"kind": "ExternalLimit", "message": message},
        }
    if response.get("ok") is False and response.get("action") != action:
        return dict(response, action=action)
    return response


def _require(condition, message):
    if not condition:
        raise ValueError(f"Resource evidence: {message}")


def _pid(value):
    return type(value) is int and value > 0


def _failed(response, error):
    return (
        isinstance(response, dict)
        and response.get("ok") is False
        and response.get("error") == error
        and "result" not in response
        and "canonical" not in response
    )


def _parse(text):
    def object_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"Duplicate resource field: {key}")
            result[key] = value
        return result

    def invalid(value):
        raise ValueError(f"Nonfinite resource field: {value}")

    return json.loads(text, object_pairs_hook=object_pairs, parse_constant=invalid)


def _expected(metadata, rows, stage):
    expected = {}

    def add(pid, language, source, response=None, *, shared=False):
        _require(_pid(pid), "missing or invalid process ID")
        _require(language in DRIVERS, "invalid process language")
        _require(isinstance(source, dict) and isinstance(source.get("path"), str), "missing source")
        _require(Path(source["path"]).is_absolute(), "source path is not absolute")
        value = {"language": language, "source_path": source["path"], "responses": []}
        if pid in expected:
            _require(
                shared and all(expected[pid][k] == value[k] for k in ("language", "source_path")),
                "process ID was reused",
            )
        else:
            expected[pid] = value
        if response is not None:
            expected[pid]["responses"].append(response)

    if stage == "compare":
        for pair in metadata["versions"]:
            _require(
                isinstance(pair.get("pids"), list) and len(pair["pids"]) == 2,
                "missing timing process pair",
            )
            for pid, variant in zip(pair["pids"], ("baseline", "candidate"), strict=True):
                add(pid, pair["language"], metadata["source_before"][variant])
        for row in rows:
            if row.get("baseline_failure") is True:
                _require(
                    len(row.get("pids", [])) == len(row.get("responses", [])) == 2,
                    "missing excluded process pair",
                )
                for index, variant in enumerate(("baseline", "candidate")):
                    add(
                        row["pids"][index],
                        row["key"].split("|", 1)[0],
                        metadata["source_before"][variant],
                        row["responses"][index],
                    )
    else:
        _require(stage in ("profiles", "capture", "pilot"), "unknown evidence stage")
        for row in rows:
            language = row["language"] if stage == "capture" else row["key"].split("|", 1)[0]
            response = row.get("response")
            if stage == "pilot":
                response = row.get("warm", row["first"])
            add(row.get("pid"), language, metadata["source"], response, shared=stage == "capture")
    _require(bool(expected), "empty process inventory")
    return expected


def validate_resources(directory, manifest, metadata, rows, stage):
    """Validate raw receipts and exact PID coverage. Return a frozen evidence digest.

    A profile memory failure can exceed the cap only with the exact external
    memory error. The caller must separately check its frozen outcome class.
    Missing receipts and unrelated resource errors always fail.
    """
    directory = Path(directory)
    expected = _expected(metadata, rows, stage)
    inventory = metadata.get("resource_processes")
    _require(isinstance(inventory, list), "missing metadata process inventory")
    listed = {}
    for entry in inventory:
        _require(
            isinstance(entry, dict) and set(entry) == {"pid", "language", "source_path"},
            "invalid metadata process inventory",
        )
        _require(_pid(entry["pid"]) and entry["pid"] not in listed, "duplicate metadata process ID")
        listed[entry["pid"]] = {key: entry[key] for key in ("language", "source_path")}
    _require(
        listed
        == {
            pid: {key: value[key] for key in ("language", "source_path")}
            for pid, value in expected.items()
        },
        "process inventory differs from rows",
    )
    limit = manifest["memory_limit_mb"]
    _require(
        type(limit) in (int, float) and math.isfinite(limit) and limit > 0, "invalid memory cap"
    )
    limit *= 1024**2
    _require(Path(metadata["harness"]["path"]).is_absolute(), "harness path is not absolute")
    records = [_parse(line) for line in (directory / "resources.jsonl").read_text().splitlines()]
    observed, process_ids, files = {}, set(), set()
    for record in records:
        _require(
            isinstance(record, dict)
            and type(record.get("schema_version")) is int
            and record["schema_version"] == 1,
            "invalid record schema",
        )
        pid = record.get("guard_pid")
        _require(
            _pid(pid) and pid in expected and pid not in observed,
            "extra, missing or reused guard PID",
        )
        spec = expected[pid]
        language = spec["language"]
        _require(
            record.get("language") == language and language in manifest["languages"],
            "record language differs",
        )
        command = record.get("command")
        _require(
            isinstance(command, list)
            and len(command) == 6
            and all(isinstance(arg, str) and "\0" not in arg for arg in command),
            "invalid command",
        )
        executable = Path(command[0]).name
        _require(
            bool(re.fullmatch(r"python(?:3(?:\.\d+)?)?", executable))
            if language == "python"
            else executable == {"js": "node", "r": "Rscript"}[language],
            "wrong interpreter",
        )
        driver_path = str(Path(metadata["harness"]["path"]) / DRIVERS[language])
        _require(
            command[1:]
            == [
                driver_path,
                "--repo",
                spec["source_path"],
                "--presolve",
                manifest["presolve"][language],
            ],
            "command source or harness path differs",
        )
        filename = record.get("receipt_file")
        _require(
            isinstance(filename, str)
            and Path(filename).name == filename
            and filename.endswith(".resource.json")
            and filename not in files,
            "invalid or reused receipt file",
        )
        files.add(filename)
        try:
            receipt = read_receipt(
                directory / filename, expected_guard_pid=pid, expected_command=command
            )
        except ProcessGuardError as error:
            raise ValueError(f"Resource evidence: {error}") from error
        _require(record.get("receipt") == receipt, "raw receipt differs from embedded evidence")
        _require(not ({pid, receipt["child_pid"]} & process_ids), "native process ID was reused")
        process_ids.update((pid, receipt["child_pid"]))
        sampled, peak = record.get("sampled_peak_rss"), record.get("peak_rss")
        _require(
            type(sampled) is int
            and sampled >= 0
            and type(peak) is int
            and peak > 0
            and peak == max(sampled, receipt["peak_rss_bytes"]),
            "invalid peak accounting",
        )
        responses = spec["responses"]
        memory_failure = (
            stage == "profiles" and len(responses) == 1 and _failed(responses[0], MEMORY_ERROR)
        )
        bounded_failure = any(
            _failed(response, error)
            for response in responses
            for error in (MEMORY_ERROR, WALL_ERROR)
        )
        _require(
            peak <= limit or memory_failure, "memory cap exceeded without a profile memory failure"
        )
        _require(not memory_failure or peak > limit, "memory failure has no exceeded peak")
        resource_error = record.get("resource_error")
        _require(
            "resource_error" in record and (peak <= limit or resource_error is not None),
            "missing resource failure status",
        )
        _require(
            resource_error is None
            or (
                memory_failure
                and isinstance(resource_error, str)
                and all(
                    part
                    in ("Driver memory limit exceeded", "Driver lifetime memory limit exceeded")
                    for part in resource_error.split("; ")
                )
            ),
            "unaccepted resource error",
        )
        _require(
            receipt["exitstatus"] == 0 or (bounded_failure and receipt["exitstatus"] in (-9, -15)),
            "unexpected native exit status",
        )
        observed[pid] = record
    _require(set(observed) == set(expected), "missing process receipts")
    _require(
        {path.name for path in directory.glob("*.resource.json")} == files,
        "missing or extra raw receipt files",
    )
    for row in rows:
        if stage in ("profiles", "pilot"):
            _require(
                row.get("peak_rss") == observed[row["pid"]]["peak_rss"],
                "row peak differs from receipt",
            )
    return {
        "sha256": digest(records),
        "processes": sorted(expected),
        "peak_rss_bytes": max(record["peak_rss"] for record in records),
        "coverage": COVERAGE,
    }
