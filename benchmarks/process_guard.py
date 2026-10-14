#!/usr/bin/env python3
"""Record a driver's OS peak RSS after exit, without changing its JSONL streams.

Launch guarded_command(argv, receipt_path) with start_new_session=True. Keep the
coordinator's live process-tree RSS checks. After the guard exits, read_receipt
must succeed before the run can pass. The child stays in the guard's process
group. The coordinator must kill that group after shutdown to remove surviving
descendants, even when the guard has already exited.

wait4 reports the child's lifetime high water under OS resource accounting.
This may include reaped descendants. It is not a simultaneous process-tree peak
or a kernel memory ceiling. Unwaited or detached descendants are not fully
covered. SIGKILL of the guard can prevent its receipt; absence is an error.

Units: the current macOS SDK getrusage(2) manual specifies bytes. Linux kernel
getrusage converts pages to KiB (kernel/sys.c, getrusage). Python documents the
wait4 result and waitstatus_to_exitcode at https://docs.python.org/3/library/os.html.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import signal
import stat
import sys
import tempfile
from contextlib import suppress
from pathlib import Path

SUPPORTED_PLATFORMS = {"darwin": ("bytes", 1), "linux": ("KiB", 1024)}
MAX_RECEIPT_BYTES = 64 * 1024
TERMINATION_GRACE_SECONDS = 0.5
COVERAGE = {
    "measurement": "os.wait4 child rusage.ru_maxrss at process exit",
    "scope": "driver lifetime OS high water, including launch",
    "process_tree_rss": "Combine with the coordinator's sampled RSS of live processes",
    "aggregate_process_tree_high_water": False,
    "kernel_memory_ceiling": False,
    "descendant_limits": [
        "OS accounting can include resource use from descendants reaped by the driver",
        "Concurrent descendant RSS is not summed into a process-tree high water",
        "Unwaited or detached descendants are not fully covered",
    ],
    "receipt_limit": "A hard kill or guard failure before publication can prevent the receipt",
}


class ProcessGuardError(RuntimeError):
    """The guard cannot produce or validate required peak RSS evidence."""


class ReceiptError(ProcessGuardError):
    """A missing or invalid receipt must prevent successful evidence collection."""


def _supported():
    if sys.platform not in SUPPORTED_PLATFORMS or any(
        not hasattr(module, name)
        for module, name in (
            (os, "fork"),
            (os, "wait4"),
            (signal, "pthread_sigmask"),
            (signal, "sigwait"),
            (signal, "setitimer"),
        )
    ):
        raise ProcessGuardError("Process peak RSS receipts require Linux or macOS with wait4")


def _command(argv):
    if (
        not isinstance(argv, (list, tuple))
        or not argv
        or any(not isinstance(arg, str) or "\0" in arg for arg in argv)
        or not argv[0]
    ):
        raise ProcessGuardError("Driver command must be a nonempty argv list without NUL bytes")
    return list(argv)


def _command_digest(argv):
    return hashlib.sha256(
        json.dumps(argv, ensure_ascii=True, separators=(",", ":")).encode()
    ).hexdigest()


def _receipt_path(path):
    path = Path(path)
    if not path.is_absolute() or not path.parent.is_dir():
        raise ProcessGuardError("Receipt needs an absolute path in an existing directory")
    return path


def guarded_command(argv, receipt_path, *, termination_grace=TERMINATION_GRACE_SECONDS):
    """Build a shell-free command. The receipt path must be new and unique."""
    _supported()
    argv = _command(argv)
    receipt = _receipt_path(receipt_path)
    if receipt.exists() or receipt.is_symlink():
        raise ProcessGuardError("Receipt path already exists")
    if (
        isinstance(termination_grace, bool)
        or not isinstance(termination_grace, (int, float))
        or (not math.isfinite(termination_grace) or not 0 < termination_grace <= 1)
    ):
        raise ProcessGuardError("Termination grace must be finite and in (0, 1] seconds")
    return [
        sys.executable,
        "-I",
        str(Path(__file__).resolve()),
        "--receipt",
        str(receipt),
        "--termination-grace",
        str(termination_grace),
        "--",
        *argv,
    ]


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate receipt key: {key}")
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError(f"Nonfinite receipt value: {value}")


def read_receipt(path, *, expected_guard_pid=None, expected_command=None):
    """Read completed evidence. Never replace missing peak data with a sampled value."""
    _supported()
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
        with os.fdopen(descriptor, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ValueError("Receipt must be a regular file")
            data = stream.read(MAX_RECEIPT_BYTES + 1)
        if len(data) > MAX_RECEIPT_BYTES:
            raise ValueError("Receipt exceeds its size limit")
        receipt = json.loads(
            data, object_pairs_hook=_unique_object, parse_constant=_invalid_constant
        )
        if (
            not isinstance(receipt, dict)
            or type(receipt.get("schema_version")) is not int
            or receipt.get("schema_version") != 1
            or receipt.get("complete") is not True
        ):
            raise ValueError("Receipt is not complete")
        for key in (
            "guard_pid",
            "child_pid",
            "exitstatus",
            "wait_status",
            "ru_maxrss",
            "peak_rss_bytes",
        ):
            if type(receipt.get(key)) is not int:
                raise ValueError(f"Receipt has invalid {key}")
        if (
            receipt["guard_pid"] <= 0
            or receipt["child_pid"] <= 0
            or receipt["guard_pid"] == receipt["child_pid"]
        ):
            raise ValueError("Receipt has invalid process IDs")
        if not 0 <= receipt["wait_status"] <= 65535:
            raise ValueError("Receipt has invalid wait status")
        if os.waitstatus_to_exitcode(receipt["wait_status"]) != receipt["exitstatus"]:
            raise ValueError("Receipt exit status does not match wait status")
        platform = receipt.get("platform")
        if not isinstance(platform, str) or platform not in SUPPORTED_PLATFORMS:
            raise ValueError("Receipt has an unsupported platform")
        unit, factor = SUPPORTED_PLATFORMS[platform]
        if (
            receipt.get("ru_maxrss_unit") != unit
            or receipt["ru_maxrss"] < 0
            or (receipt["peak_rss_bytes"] != receipt["ru_maxrss"] * factor)
        ):
            raise ValueError("Receipt peak RSS or units are invalid")
        if receipt.get("coverage") != COVERAGE:
            raise ValueError("Receipt coverage is missing or differs")
        command_hash = receipt.get("command_sha256")
        if (
            not isinstance(command_hash, str)
            or len(command_hash) != 64
            or any(char not in "0123456789abcdef" for char in command_hash)
        ):
            raise ValueError("Receipt command binding is invalid")
        if expected_guard_pid is not None and (
            type(expected_guard_pid) is not int
            or expected_guard_pid <= 0
            or receipt["guard_pid"] != expected_guard_pid
        ):
            raise ValueError("Receipt belongs to another guard process")
        if expected_command is not None and command_hash != _command_digest(
            _command(expected_command)
        ):
            raise ValueError("Receipt belongs to another driver command")
        return receipt
    except (OSError, TypeError, ValueError, ProcessGuardError) as error:
        raise ReceiptError(f"Missing or invalid process peak RSS receipt: {error}") from error


def _publish(path, receipt):
    """Publish a complete file atomically, without replacing another receipt."""
    descriptor, temporary = tempfile.mkstemp(prefix=".process-guard-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(receipt, stream, allow_nan=False, separators=(",", ":"))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        # Same-directory hard-link publication is atomic and refuses an existing
        # destination. Thus a stale or competing receipt is never overwritten.
        os.link(temporary, path)
    finally:
        with suppress(FileNotFoundError):
            os.unlink(temporary)


def _signal_child(child_pid, signum):
    with suppress(ProcessLookupError):
        os.kill(child_pid, signum)


def _signal_pending(signum, frame):
    # SIGCHLD has an ignored default disposition on macOS. A handler makes it
    # pending while blocked, so sigwait can consume it after the child exits.
    pass


def supervise(argv, receipt_path, termination_grace=TERMINATION_GRACE_SECONDS):
    """CLI supervisor. Call only in its dedicated, single-threaded process."""
    # Validate with the same rules as the public command builder before fork.
    guarded_command(argv, receipt_path, termination_grace=termination_grace)
    receipt_path = Path(receipt_path)
    watched = {signal.SIGTERM, signal.SIGINT, signal.SIGHUP, signal.SIGCHLD, signal.SIGALRM}
    original_mask = signal.pthread_sigmask(signal.SIG_BLOCK, watched)
    for signum in watched:
        signal.signal(signum, signal.SIG_DFL)
    signal.signal(signal.SIGCHLD, _signal_pending)
    child_pid = os.fork()
    if child_pid == 0:
        # Match subprocess restore_signals for native drivers. Caught handlers
        # otherwise vanish at exec, but inherited ignored handlers would remain.
        for name in ("SIGPIPE", "SIGXFZ", "SIGXFSZ"):
            if hasattr(signal, name):
                signal.signal(getattr(signal, name), signal.SIG_DFL)
        signal.signal(signal.SIGCHLD, signal.SIG_DFL)
        signal.pthread_sigmask(signal.SIG_SETMASK, original_mask)
        try:
            os.execvp(argv[0], argv)
        except OSError as error:
            with suppress(OSError):
                os.write(2, f"process guard: driver exec failed: {error}\n".encode())
            os._exit(127 if isinstance(error, FileNotFoundError) else 126)
    # The guard must not keep either JSONL pipe alive after the driver closes it.
    for descriptor in (0, 1):
        with suppress(OSError):
            os.close(descriptor)
    terminating = False
    while True:
        waited, status, usage = os.wait4(child_pid, os.WNOHANG)
        if waited == child_pid:
            break
        signum = signal.sigwait(watched)
        if signum in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
            _signal_child(child_pid, signum)
            if not terminating:
                terminating = True
                signal.setitimer(signal.ITIMER_REAL, termination_grace)
        elif signum == signal.SIGALRM and terminating:
            _signal_child(child_pid, signal.SIGKILL)
    signal.setitimer(signal.ITIMER_REAL, 0)
    unit, factor = SUPPORTED_PLATFORMS[sys.platform]
    raw_peak = usage.ru_maxrss
    if type(raw_peak) is not int or raw_peak < 0:
        raise ProcessGuardError("wait4 returned an invalid peak RSS")
    receipt = {
        "schema_version": 1,
        "complete": True,
        "guard_pid": os.getpid(),
        "child_pid": child_pid,
        "wait_status": status,
        "exitstatus": os.waitstatus_to_exitcode(status),
        "ru_maxrss": raw_peak,
        "ru_maxrss_unit": unit,
        "peak_rss_bytes": raw_peak * factor,
        "platform": sys.platform,
        "command_sha256": _command_digest(argv),
        "coverage": COVERAGE,
    }
    _publish(receipt_path, receipt)
    # Keep termination signals blocked until the complete receipt is published.
    return receipt["exitstatus"]


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--termination-grace", type=float, default=TERMINATION_GRACE_SECONDS)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    argv = args.command[1:] if args.command[:1] == ["--"] else args.command
    try:
        status = supervise(argv, args.receipt, args.termination_grace)
    except (OSError, ProcessGuardError) as error:
        print(f"process guard: {error}", file=sys.stderr, flush=True)
        return 125
    if status < 0:
        signum = -status
        if signum != signal.SIGKILL:
            signal.signal(signum, signal.SIG_DFL)
        signal.pthread_sigmask(signal.SIG_UNBLOCK, {signum})
        os.kill(os.getpid(), signum)
        return 128 + signum
    return status


if __name__ == "__main__":
    raise SystemExit(main())
