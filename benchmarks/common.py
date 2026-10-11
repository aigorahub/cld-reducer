"""Source bindings and bounded JSON-line driver transport."""
from __future__ import annotations

import hashlib
import json
import os
import platform
import selectors
import signal
import subprocess
import sys
import time
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parents[1]


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def source_binding(repo):
    repo = Path(repo).resolve()
    def git(*args):
        return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()
    status = git("status", "--porcelain", "--untracked-files=all")
    if status:
        raise ValueError(f"Source checkout must be clean: {repo}\n{status}")
    return {"path": str(repo), "head": git("rev-parse", "HEAD"),
            "tree": git("rev-parse", "HEAD^{tree}"), "status": status}


def provenance(repo):
    return {"source": source_binding(repo), "harness": source_binding(ROOT),
            "machine": {"platform": platform.platform(), "machine": platform.machine(),
                        "cpu_count": os.cpu_count(), "memory_bytes": psutil.virtual_memory().total},
            "created_unix": time.time()}


class DriverError(RuntimeError):
    pass


class Driver:
    """One runtime process. A timeout or memory violation terminates its process group."""
    def __init__(self, language, repo, presolve, output, memory_mb=8192):
        commands = {"python": [sys.executable, str(ROOT / "benchmarks/python_driver.py")],
                    "r": ["Rscript", str(ROOT / "benchmarks/r_driver.R")],
                    "js": ["node", str(ROOT / "benchmarks/js_driver.mjs")]}
        self.stderr = open(output, "w")
        env = dict(os.environ, OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1")
        self.process = subprocess.Popen(commands[language] + ["--repo", str(Path(repo).resolve()),
                                       "--presolve", presolve], stdin=subprocess.PIPE,
                                       stdout=subprocess.PIPE, stderr=self.stderr,
                                       start_new_session=True, env=env)
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.process.stdout, selectors.EVENT_READ)
        self.buffer = b""
        self.memory_limit = memory_mb * 1024 * 1024
        self.peak_rss = 0

    def request(self, value, timeout=30):
        if self.process.poll() is not None:
            raise DriverError(f"Driver exited {self.process.returncode}")
        self.process.stdin.write((json.dumps(value, allow_nan=False) + "\n").encode())
        self.process.stdin.flush()
        deadline = time.monotonic() + timeout
        while b"\n" not in self.buffer:
            try:
                proc = psutil.Process(self.process.pid)
                rss = proc.memory_info().rss + sum(c.memory_info().rss for c in proc.children(recursive=True))
                self.peak_rss = max(rss, self.peak_rss)
                if rss > self.memory_limit:
                    raise DriverError("Driver memory limit exceeded")
            except psutil.NoSuchProcess:
                pass
            if time.monotonic() >= deadline:
                self.close()
                raise DriverError("Driver external wall limit exceeded")
            if self.selector.select(min(.05, max(0, deadline - time.monotonic()))):
                data = os.read(self.process.stdout.fileno(), 65536)
                if not data:
                    raise DriverError(f"Driver closed stdout (exit {self.process.poll()})")
                self.buffer += data
                if len(self.buffer) > 32 * 1024 * 1024:
                    raise DriverError("Driver response exceeds 32 MiB")
        line, self.buffer = self.buffer.split(b"\n", 1)
        try:
            response = json.loads(line)
        except (ValueError, UnicodeError) as error:
            raise DriverError("Driver returned invalid JSON") from error
        if not isinstance(response, dict) or response.get("action") != value["action"] or not isinstance(response.get("ok"), bool):
            raise DriverError("Driver response does not match the request")
        return response

    def close(self):
        if self.process.poll() is None:
            os.killpg(self.process.pid, signal.SIGTERM)
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                os.killpg(self.process.pid, signal.SIGKILL)
                self.process.wait(timeout=2)
        self.selector.close()
        self.process.stdin.close()
        self.process.stdout.close()
        self.stderr.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
