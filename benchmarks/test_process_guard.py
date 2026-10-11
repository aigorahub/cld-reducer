"""Real child-process checks for peak RSS receipts, with bounded allocations."""

from __future__ import annotations

import copy
import importlib.util
import json
import os
import selectors
import signal
import subprocess
import sys
from contextlib import contextmanager, suppress
from pathlib import Path

import psutil
import pytest

PATH = Path(__file__).with_name("process_guard.py")
SPEC = importlib.util.spec_from_file_location("benchmark_process_guard", PATH)
guard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guard)
pytestmark = pytest.mark.skipif(
    sys.platform not in ("darwin", "linux"), reason="wait4 peak receipts support Linux and macOS"
)


@contextmanager
def child(tmp_path, code, *arguments):
    receipt_path = tmp_path / "peak.json"
    argv = [sys.executable, "-c", code, *arguments]
    command = guard.guarded_command(argv, receipt_path)
    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        yield process, receipt_path, argv
    finally:
        with suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
        process.communicate(timeout=5)


def line_from(process):
    with selectors.DefaultSelector() as selector:
        selector.register(process.stdout, selectors.EVENT_READ)
        assert selector.select(5), "Child did not produce its expected line or EOF"
    return process.stdout.readline()


def read_bound(path, process, command):
    return guard.read_receipt(path, expected_guard_pid=process.pid, expected_command=command)


def test_jsonl_input_output_and_eof_are_unchanged(tmp_path):
    code = (
        "import sys,json\nfor line in sys.stdin: print(json.dumps(json.loads(line)),flush=True)\n"
    )
    with child(tmp_path, code) as (process, path, command):
        lines = [{"action": "version"}, {"text": "quote ' ; $() and é"}]
        payload = "".join(json.dumps(line) + "\n" for line in lines).encode()
        output, error = process.communicate(payload, timeout=5)
        assert process.returncode == 0
        assert error == b""
        assert [json.loads(line) for line in output.splitlines()] == lines
        receipt = read_bound(path, process, command)
        assert receipt["exitstatus"] == 0
        assert receipt["peak_rss_bytes"] > 0
        assert receipt["coverage"]["aggregate_process_tree_high_water"] is False
        assert receipt["coverage"]["kernel_memory_ceiling"] is False


def test_supervisor_does_not_keep_stdout_open(tmp_path):
    code = "import os,sys\nprint('ready',flush=True)\nos.close(1)\nsys.stdin.buffer.read()\n"
    with child(tmp_path, code) as (process, path, command):
        assert line_from(process) == b"ready\n"
        assert line_from(process) == b""
        # The child is still waiting for input. EOF comes from its closed output,
        # not from waiting for the whole guard to exit.
        assert process.poll() is None
        process.communicate(timeout=5)
        assert read_bound(path, process, command)["exitstatus"] == 0


def test_short_allocate_release_spike_survives_in_receipt(tmp_path):
    code = """import json,mmap,os,resource,sys
size = 64 * 1024 * 1024
region = mmap.mmap(-1, size)
for offset in range(0, size, mmap.PAGESIZE):
    region[offset] = 1
region.close()
peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
print(json.dumps({'pid': os.getpid(), 'peak': peak}), flush=True)
sys.stdin.buffer.read()
"""
    with child(tmp_path, code) as (process, path, command):
        after_release = json.loads(line_from(process))
        sampled_after_release = psutil.Process(after_release["pid"]).memory_info().rss
        process.communicate(timeout=5)
        receipt = read_bound(path, process, command)
        factor = 1 if sys.platform == "darwin" else 1024
        assert receipt["child_pid"] == after_release["pid"]
        assert receipt["peak_rss_bytes"] >= 64 * 1024 * 1024
        assert receipt["peak_rss_bytes"] >= after_release["peak"] * factor
        assert receipt["peak_rss_bytes"] > sampled_after_release + 32 * 1024 * 1024


@pytest.mark.parametrize("exitstatus", [0, 7, 126, 255])
def test_exit_status_is_preserved(tmp_path, exitstatus):
    with child(tmp_path, f"import sys;sys.exit({exitstatus})") as (process, path, command):
        output, error = process.communicate(timeout=5)
        assert output == error == b""
        assert process.returncode == exitstatus
        assert read_bound(path, process, command)["exitstatus"] == exitstatus


def test_failed_exec_still_records_child_rusage(tmp_path):
    path = tmp_path / "peak.json"
    command = [str(tmp_path / "missing-executable")]
    process = subprocess.Popen(
        guard.guarded_command(command, path),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        output, error = process.communicate(timeout=5)
    finally:
        with suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
        process.communicate(timeout=5)
    assert output == b""
    assert b"driver exec failed" in error
    assert process.returncode == 127
    assert read_bound(path, process, command)["exitstatus"] == 127


@pytest.mark.parametrize("ignore_term", [False, True])
def test_group_term_records_receipt_and_bounds_child_cleanup(tmp_path, ignore_term):
    code = "import os,signal,time\n"
    if ignore_term:
        code += "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
    code += "print(os.getpid(),flush=True)\ntime.sleep(30)\n"
    with child(tmp_path, code) as (process, path, command):
        child_pid = int(line_from(process))
        os.killpg(process.pid, signal.SIGTERM)
        _, error = process.communicate(timeout=3)
        assert error == b""
        receipt = read_bound(path, process, command)
        expected = -signal.SIGKILL if ignore_term else -signal.SIGTERM
        assert receipt["exitstatus"] == process.returncode == expected
        assert not psutil.pid_exists(child_pid)


def test_guard_only_term_is_forwarded_to_child(tmp_path):
    with child(tmp_path, "import os,time\nprint(os.getpid(),flush=True)\ntime.sleep(30)") as (
        process,
        path,
        command,
    ):
        child_pid = int(line_from(process))
        process.terminate()
        process.communicate(timeout=3)
        assert read_bound(path, process, command)["exitstatus"] == -signal.SIGTERM
        assert not psutil.pid_exists(child_pid)


def test_hard_killed_guard_has_no_successful_receipt(tmp_path):
    with child(tmp_path, "import time\nprint('ready',flush=True)\ntime.sleep(30)") as (
        process,
        path,
        command,
    ):
        assert line_from(process) == b"ready\n"
        os.killpg(process.pid, signal.SIGKILL)
        process.communicate(timeout=3)
        with pytest.raises(guard.ReceiptError, match="Missing or invalid"):
            read_bound(path, process, command)


def test_command_builder_preserves_literal_arguments(tmp_path):
    marker = tmp_path / "must-not-exist"
    argument = f"$(touch {marker}); spaced argument ' quote"
    with child(tmp_path, "import json,sys;print(json.dumps(sys.argv[1:]))", argument, "") as (
        process,
        path,
        command,
    ):
        output, error = process.communicate(timeout=5)
        assert error == b""
        assert json.loads(output) == [argument, ""]
        assert not marker.exists()
        assert read_bound(path, process, command)["exitstatus"] == 0


def valid_receipt():
    unit, factor = guard.SUPPORTED_PLATFORMS[sys.platform]
    return {
        "schema_version": 1,
        "complete": True,
        "guard_pid": 10,
        "child_pid": 11,
        "wait_status": 0,
        "exitstatus": 0,
        "ru_maxrss": 8192,
        "ru_maxrss_unit": unit,
        "peak_rss_bytes": 8192 * factor,
        "platform": sys.platform,
        "command_sha256": guard._command_digest(["driver"]),
        "coverage": copy.deepcopy(guard.COVERAGE),
    }


@pytest.mark.parametrize(
    "fault",
    [
        "missing",
        "partial",
        "complete",
        "bool_schema",
        "pid",
        "bool_peak",
        "negative",
        "units",
        "mismatch_peak",
        "status",
        "platform",
        "coverage",
        "stale_pid",
        "stale_command",
        "duplicate",
        "nonfinite",
        "oversize",
    ],
)
def test_invalid_or_missing_receipts_fail_closed(tmp_path, fault):
    path = tmp_path / "peak.json"
    receipt = valid_receipt()
    options = {"expected_guard_pid": 10, "expected_command": ["driver"]}
    if fault == "missing":
        pass
    elif fault == "partial":
        path.write_text('{"schema_version":1,')
    elif fault == "duplicate":
        path.write_text('{"schema_version":1,"schema_version":1}')
    elif fault == "nonfinite":
        path.write_text('{"peak_rss_bytes":NaN}')
    elif fault == "oversize":
        path.write_bytes(b" " * (guard.MAX_RECEIPT_BYTES + 1))
    else:
        if fault == "complete":
            receipt["complete"] = False
        elif fault == "bool_schema":
            receipt["schema_version"] = True
        elif fault == "pid":
            receipt["child_pid"] = 10
        elif fault == "bool_peak":
            receipt["peak_rss_bytes"] = True
        elif fault == "negative":
            receipt["ru_maxrss"] = -1
        elif fault == "units":
            receipt["ru_maxrss_unit"] = "wrong"
        elif fault == "mismatch_peak":
            receipt["peak_rss_bytes"] += 1
        elif fault == "status":
            receipt["exitstatus"] = 1
        elif fault == "platform":
            receipt["platform"] = "unsupported"
        elif fault == "coverage":
            receipt["coverage"]["kernel_memory_ceiling"] = True
        elif fault == "stale_pid":
            options["expected_guard_pid"] = 12
        elif fault == "stale_command":
            options["expected_command"] = ["another-driver"]
        path.write_text(json.dumps(receipt))
    with pytest.raises(guard.ReceiptError):
        guard.read_receipt(path, **options)


@pytest.mark.parametrize("platform,factor", [("linux", 1024), ("darwin", 1)])
def test_receipt_unit_conversion_is_checked(tmp_path, platform, factor):
    path = tmp_path / "peak.json"
    receipt = valid_receipt()
    receipt.update(
        platform=platform,
        ru_maxrss=4096,
        peak_rss_bytes=4096 * factor,
        ru_maxrss_unit="KiB" if platform == "linux" else "bytes",
    )
    path.write_text(json.dumps(receipt))
    assert guard.read_receipt(path)["peak_rss_bytes"] == 4096 * factor


@pytest.mark.parametrize("command", [[], "driver", [""], ["driver", 1], ["driver\0"]])
def test_command_builder_rejects_invalid_commands(tmp_path, command):
    with pytest.raises(guard.ProcessGuardError):
        guard.guarded_command(command, tmp_path / "peak.json")


@pytest.mark.parametrize("seconds", [0, -1, 2, float("inf"), float("nan"), True])
def test_command_builder_requires_bounded_grace(tmp_path, seconds):
    with pytest.raises(guard.ProcessGuardError, match="grace"):
        guard.guarded_command(["driver"], tmp_path / "peak.json", termination_grace=seconds)


def test_receipt_path_cannot_reuse_stale_evidence(tmp_path):
    path = tmp_path / "peak.json"
    path.write_text("old receipt")
    with pytest.raises(guard.ProcessGuardError, match="already exists"):
        guard.guarded_command(["driver"], path)
    assert path.read_text() == "old receipt"


@pytest.mark.parametrize("kind", ["fifo", "symlink", "directory"])
def test_receipt_reader_rejects_nonregular_paths_without_waiting(tmp_path, kind):
    path = tmp_path / "peak.json"
    if kind == "fifo":
        os.mkfifo(path)
    elif kind == "symlink":
        original = tmp_path / "original.json"
        original.write_text(json.dumps(valid_receipt()))
        path.symlink_to(original)
    else:
        path.mkdir()
    with pytest.raises(guard.ReceiptError):
        guard.read_receipt(path)


def test_atomic_publication_refuses_another_receipt(tmp_path):
    path = tmp_path / "peak.json"
    receipt = valid_receipt()
    guard._publish(path, receipt)
    with pytest.raises(FileExistsError):
        guard._publish(path, {"different": True})
    assert guard.read_receipt(path) == receipt
    assert not list(tmp_path.glob(".process-guard-*"))


def test_unsupported_platform_is_explicit(tmp_path, monkeypatch):
    monkeypatch.setattr(guard.sys, "platform", "unsupported")
    with pytest.raises(guard.ProcessGuardError, match="Linux or macOS"):
        guard.guarded_command(["driver"], tmp_path / "peak.json")
