"""Source bindings and bounded JSON-line driver transport."""

from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import selectors
import signal
import subprocess
import sys
import time
from contextlib import suppress
from pathlib import Path
from tempfile import TemporaryDirectory

import psutil
from process_guard import ProcessGuardError, guarded_command, read_receipt

ROOT = Path(__file__).resolve().parents[1]
MAX_RESPONSE_BYTES = 32 * 1024 * 1024


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


BUILD_SUFFIXES = {".js", ".mjs", ".cjs", ".json", ".wasm", ".node", ".so", ".dylib", ".dll"}
LOCK_NAMES = {
    "package-lock.json",
    "npm-shrinkwrap.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "uv.lock",
    "poetry.lock",
    "Pipfile.lock",
    "renv.lock",
    "requirements.lock",
}


def _file_hash(path):
    before = path.stat()
    sha = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            sha.update(block)
    after = path.stat()
    if (before.st_size, before.st_mtime_ns, before.st_ino) != (
        after.st_size,
        after.st_mtime_ns,
        after.st_ino,
    ):
        raise ValueError(f"File changed while binding source: {path}")
    return sha.hexdigest()


def _javascript_tools(repo):
    """Resolve the ESM solver from the same location as the production import."""
    compiler = repo / "js/node_modules/typescript/bin/tsc"
    if not compiler.is_file():
        raise ValueError("JavaScript build verification requires installed TypeScript")
    script = (
        'import {fileURLToPath} from "node:url";'
        'process.stdout.write(fileURLToPath(import.meta.resolve("highs")));'
    )
    try:
        resolved = subprocess.run(
            ["node", "--input-type=module", "--eval", script],
            cwd=(repo / "js/dist/solver.js").resolve().parent,
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        ).stdout
    except (OSError, subprocess.SubprocessError) as error:
        raise ValueError(f"Cannot resolve the installed JavaScript solver: {error}") from error
    entry = Path(resolved).resolve(strict=True)
    for directory in entry.parents:
        package = directory / "package.json"
        if package.is_file() and json.loads(package.read_text()).get("name") == "highs":
            # The installed loader resolves highs.wasm next to its own entry.
            if not entry.with_name("highs.wasm").is_file():
                raise ValueError("Resolved HiGHS loader has no adjacent highs.wasm")
            return compiler.resolve(), directory, entry
    raise ValueError("Resolved JavaScript solver is outside a HiGHS package")


def _package_hashes(directory, name, *, compiler=False):
    files = [
        path
        for path in directory.rglob("*")
        if path.is_file()
        and (
            path.suffix in BUILD_SUFFIXES
            or compiler
            and (path.suffix == ".ts" or path.parent == directory / "bin")
        )
    ]
    return {
        f"{name}/{path.relative_to(directory).as_posix()}": _file_hash(path)
        for path in sorted(files)
    }


def _compile_javascript(repo, compiler, destination):
    # Disable incremental state and keep declarations inside the temporary
    # directory too. Neither actual dist nor a project build cache is written.
    command = [
        "node",
        str(compiler),
        "--project",
        str(repo / "js/tsconfig.build.json"),
        "--outDir",
        str(destination),
        "--declarationDir",
        str(destination / "declarations"),
        "--incremental",
        "false",
    ]
    try:
        subprocess.run(
            command, cwd=repo / "js", check=True, capture_output=True, text=True, timeout=120
        )
    except subprocess.CalledProcessError as error:
        raise ValueError(
            f"Fresh JavaScript compilation failed: {error.stdout}{error.stderr}"
        ) from error
    except (OSError, subprocess.SubprocessError) as error:
        raise ValueError(f"Fresh JavaScript compilation failed: {error}") from error


def _javascript_proof(repo, build_files):
    compiler, highs, entry = _javascript_tools(repo)
    compiler_root = compiler.parent.parent
    dependencies = _package_hashes(highs, "highs")
    dependencies["highs/" + entry.relative_to(highs).as_posix()] = _file_hash(entry)
    compiler_files = _package_hashes(compiler_root, "typescript", compiler=True)
    with TemporaryDirectory(prefix="cld-js-build-proof-") as temporary:
        destination = Path(temporary) / "dist"
        _compile_javascript(repo, compiler, destination)
        emitted = {
            "js/dist/" + path.relative_to(destination).as_posix(): _file_hash(path)
            for path in sorted(destination.rglob("*"))
            if path.is_file() and path.suffix in BUILD_SUFFIXES
        }
        missing = sorted(emitted.keys() - build_files.keys())
        extra = sorted(build_files.keys() - emitted.keys())
        changed = sorted(
            key for key in emitted.keys() & build_files.keys() if emitted[key] != build_files[key]
        )
        if not emitted or missing or extra or changed:
            raise ValueError(
                "JavaScript dist does not match fresh source compilation: "
                f"missing={missing}, extra={extra}, changed={changed}"
            )
    after_dependencies = _package_hashes(highs, "highs")
    after_dependencies["highs/" + entry.relative_to(highs).as_posix()] = _file_hash(entry)
    if dependencies != after_dependencies or compiler_files != _package_hashes(
        compiler_root, "typescript", compiler=True
    ):
        raise ValueError(
            "JavaScript dependency or compiler files changed during build verification"
        )
    actual_after = {
        path.relative_to(repo).as_posix(): _file_hash(path)
        for path in sorted((repo / "js/dist").rglob("*"))
        if path.is_file() and path.suffix in BUILD_SUFFIXES
    }
    if actual_after != build_files:
        raise ValueError("JavaScript dist changed during build verification")
    return {
        "dependency_files": dependencies,
        "compiler_files": compiler_files,
        "build_verified": True,
    }


def source_binding(repo, *, languages=None, require_js=False):
    """Bind a clean source tree and the ignored files that JavaScript executes.

    Always bind a present build. When JavaScript is requested, prove it matches
    a fresh temporary compilation and bind the installed solver/compiler bytes.
    A harness-only checkout need not have js/dist or TypeScript installed.
    """
    repo = Path(repo).resolve()

    def git(*args):
        return subprocess.check_output(["git", "-C", str(repo), *args], text=True).rstrip("\n")

    if Path(git("rev-parse", "--show-toplevel")).resolve() != repo:
        raise ValueError(f"Source path must be the checkout root: {repo}")
    status = git("status", "--porcelain", "--untracked-files=all")
    if status:
        raise ValueError(f"Source checkout must be clean: {repo}\n{status}")
    # Git status can hide changed source behind these index flags.
    flagged = [
        entry[2:]
        for entry in git("ls-files", "-v", "-z").split("\0")
        if entry and (entry[0].islower() or entry[0] == "S")
    ]
    if flagged:
        raise ValueError(f"Source index has assume-unchanged or skip-worktree paths: {flagged}")
    head = git("rev-parse", "HEAD")
    tree = git("rev-parse", "HEAD^{tree}")
    tracked = [name for name in git("ls-files", "-z").split("\0") if name]
    if isinstance(languages, str):
        languages = [languages]
    needs_js = require_js or bool({"js", "javascript"}.intersection(languages or ()))
    dist = repo / "js/dist"
    if needs_js:
        required = {"js/dist/index.js"}
        for name in tracked:
            if name.startswith("js/src/") and name.endswith(".ts") and not name.endswith(".d.ts"):
                required.add("js/dist/" + name[len("js/src/") : -3] + ".js")
        missing = sorted(name for name in required if not (repo / name).is_file())
        if missing:
            raise ValueError(f"JavaScript runtime requires built js/dist files: {missing}")
    builds = sorted(
        path for path in dist.rglob("*") if path.is_file() and path.suffix in BUILD_SUFFIXES
    )
    locks = {
        repo / name for name in tracked if Path(name).name in LOCK_NAMES or name.endswith(".lock")
    }
    # Include ignored lockfiles at package roots, as well as tracked lockfiles
    # anywhere in the checkout. Never scan installed dependency directories.
    for directory in (repo, repo / "js", repo / "python", repo / "R", repo / "benchmarks"):
        locks.update(directory / name for name in LOCK_NAMES if (directory / name).is_file())
    binding = {
        "path": str(repo),
        "head": head,
        "tree": tree,
        "status": status,
        "build_files": {path.relative_to(repo).as_posix(): _file_hash(path) for path in builds},
        "lock_files": {
            path.relative_to(repo).as_posix(): _file_hash(path) for path in sorted(locks)
        },
        "dependency_files": {},
        "compiler_files": {},
        "build_verified": False,
    }
    if needs_js:
        binding.update(_javascript_proof(repo, binding["build_files"]))
    if git("status", "--porcelain", "--untracked-files=all") or git("rev-parse", "HEAD") != head:
        raise ValueError(f"Source checkout changed while binding: {repo}")
    return binding


def source_identity(binding):
    """The same source and build can live at different absolute paths."""
    return {key: value for key, value in binding.items() if key != "path"}


def version_identity(version):
    """Keep runtime, dependency and solver settings; remove observations/location.

    Source commits and paths belong to source_binding. Do not drop settings
    such as time_limit, or stable timer descriptions, as if they were timings.
    The reducer's own release version stays in the raw record. It is part of
    the changed source, not a dependency that must match the reference.
    """
    ignored = {
        "module_load_ns",
        "solver_load_ns",
        "wasm_load_ns",
        "load_ns",
        "elapsed_ns",
        "load_time_ns",
        "total_load_ns",
        "source_head",
        "source_path",
        "repo",
        "package_version",
    }
    identity = {key: value for key, value in version.items() if key not in ignored}
    if isinstance(identity.get("package"), dict):
        identity["package"] = {
            key: value for key, value in identity["package"].items() if key != "version"
        }
    else:
        # Python reports its own version as a string; R reports name/version.
        identity.pop("package", None)
    if isinstance(identity.get("timer"), dict):
        # R observes clock resolution and warnings in every fresh process.
        # Keep the clock, accuracy, method and fallback descriptions bound.
        identity["timer"] = {
            key: value
            for key, value in identity["timer"].items()
            if key not in {"resolution_ns", "warnings"}
        }
    return identity


def input_digest(manifest):
    """Bind solve inputs and resource limits, independently of calibration.

    Cases include route, representation, labels, options, seeds, split, class,
    tier and wall limit. Sampling counts, fitted batch lengths and decisions
    made from pilot/profile/calibration evidence are not input definitions.
    """
    keys = {
        "schema_version",
        "case_generator",
        "cases",
        "methods",
        "languages",
        "presolve",
        "memory_limit_mb",
        "memory_growth_tolerance_mb",
        "resource_limits",
        "resource_design",
        "wall_seconds",
        "threads",
    }
    return digest({key: value for key, value in manifest.items() if key in keys})


def provenance(repo):
    return {
        "source": source_binding(repo),
        "harness": source_binding(ROOT),
        "machine": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "cpu_count": os.cpu_count(),
            "memory_bytes": psutil.virtual_memory().total,
        },
        "created_unix": time.time(),
    }


class DriverError(RuntimeError):
    pass


class Driver:
    """One guarded runtime, sampled tree RSS, and required lifetime peak evidence."""

    def __init__(self, language, repo, presolve, output, memory_mb=8192):
        commands = {
            "python": [sys.executable, str(ROOT / "benchmarks/python_driver.py")],
            "r": ["Rscript", str(ROOT / "benchmarks/r_driver.R")],
            "js": ["node", str(ROOT / "benchmarks/js_driver.mjs")],
        }
        if language not in commands:
            raise ValueError(f"Unsupported driver language: {language}")
        if (
            isinstance(memory_mb, bool)
            or not isinstance(memory_mb, (int, float))
            or not math.isfinite(memory_mb)
            or memory_mb <= 0
        ):
            raise ValueError("Driver memory limit must be finite and positive")
        self.stderr = None
        self.process = None
        self.selector = None
        self._closed = False
        self._request_failed = False
        self.buffer = b""
        self.memory_limit = memory_mb * 1024 * 1024
        self.peak_rss = 0
        self.sampled_peak_rss = 0
        self.rss = 0
        self.memory_receipt = None
        self.resource_error = None
        output = Path(output).resolve()
        self.receipt_path = output.with_name(output.name + ".resource.json")
        self.command = commands[language] + [
            "--repo",
            str(Path(repo).resolve()),
            "--presolve",
            presolve,
        ]
        env = dict(os.environ, OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1")
        try:
            command = guarded_command(self.command, self.receipt_path)
            self.stderr = open(output, "w")  # noqa: SIM115 - Driver.close owns this stream.
            self.process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=self.stderr,
                start_new_session=True,
                env=env,
                bufsize=0,
            )
            os.set_blocking(self.process.stdin.fileno(), False)
            os.set_blocking(self.process.stdout.fileno(), False)
            self.selector = selectors.DefaultSelector()
            self.selector.register(self.process.stdout, selectors.EVENT_READ)
        except BaseException:
            with suppress(DriverError):
                self.close()
            raise

    def _check_memory(self):
        try:
            proc = psutil.Process(self.process.pid)
            processes = [proc, *proc.children(recursive=True)]
        except psutil.NoSuchProcess:
            self.rss = 0
            return
        rss = 0
        for proc in processes:
            try:
                rss += proc.memory_info().rss
            except psutil.NoSuchProcess:
                continue
        self.rss = rss
        self.sampled_peak_rss = max(rss, self.sampled_peak_rss)
        self.peak_rss = max(rss, self.peak_rss)
        if rss > self.memory_limit:
            raise DriverError("Driver memory limit exceeded")

    def request(self, value, timeout=30):
        if self._closed:
            raise DriverError("Driver is closed")
        try:
            if not isinstance(value, dict) or not isinstance(value.get("action"), str):
                raise DriverError("Driver request requires an action string")
            if (
                isinstance(timeout, bool)
                or not isinstance(timeout, (int, float))
                or not math.isfinite(timeout)
                or timeout <= 0
            ):
                raise DriverError("Driver timeout must be finite and positive")
            if self.process.poll() is not None:
                raise DriverError(f"Driver exited {self.process.returncode}")
            payload = memoryview((json.dumps(value, allow_nan=False) + "\n").encode("utf-8"))
            deadline = time.monotonic() + timeout
            self.selector.register(self.process.stdin, selectors.EVENT_WRITE)
            while b"\n" not in self.buffer:
                self._check_memory()
                if time.monotonic() >= deadline:
                    raise DriverError("Driver external wall limit exceeded")
                for key, _ in self.selector.select(min(0.05, max(0, deadline - time.monotonic()))):
                    if key.fileobj is self.process.stdin:
                        try:
                            written = os.write(self.process.stdin.fileno(), payload)
                        except BlockingIOError:
                            continue
                        payload = payload[written:]
                        if not payload:
                            self.selector.unregister(self.process.stdin)
                    else:
                        try:
                            data = os.read(self.process.stdout.fileno(), 65536)
                        except BlockingIOError:
                            continue
                        if not data:
                            raise DriverError(f"Driver closed stdout (exit {self.process.poll()})")
                        self.buffer += data
                        if len(self.buffer) > MAX_RESPONSE_BYTES:
                            raise DriverError(f"Driver response exceeds {MAX_RESPONSE_BYTES} bytes")
            if payload:
                raise DriverError("Driver responded before the request was sent")
            line, self.buffer = self.buffer.split(b"\n", 1)
            if self.buffer:
                raise DriverError("Driver returned extra data after its response")
            try:
                response = json.loads(
                    line.decode("utf-8"),
                    parse_constant=_invalid_json_constant,
                    object_pairs_hook=_unique_json_object,
                )
            except (ValueError, UnicodeError) as error:
                raise DriverError("Driver returned invalid JSON") from error
            if (
                not isinstance(response, dict)
                or response.get("action") != value["action"]
                or not isinstance(response.get("ok"), bool)
            ):
                raise DriverError("Driver response does not match the request")
            if not response["ok"] and (
                "result" in response
                or "canonical" in response
                or not isinstance(response.get("error"), dict)
                or not all(
                    isinstance(response["error"].get(key), str) for key in ("kind", "message")
                )
            ):
                raise DriverError("Driver returned an invalid error response")
            if response["ok"] and "error" in response:
                raise DriverError("Driver returned both success and error")
            self._check_memory()
            return response
        except BaseException as error:
            self._request_failed = True
            try:
                self.close()
            except DriverError as cleanup_error:
                if hasattr(error, "add_note"):
                    error.add_note(f"Driver cleanup failed: {cleanup_error}")
            if isinstance(error, (OSError, psutil.Error, ValueError, TypeError)):
                raise DriverError(f"Driver transport failed: {error}") from error
            raise

    def close(self):
        """Collect peak evidence once. Keep cleanup errors on the closed object."""
        if self._closed:
            return
        self._closed = True
        failures = []
        try:
            if self.process is not None:
                try:
                    self._check_memory()
                except (DriverError, OSError, psutil.Error) as error:
                    failures.append(str(error))
                # EOF lets a healthy driver exit and the guard publish its
                # receipt. The guard does not retain the child's input pipe.
                if self.process.stdin is not None:
                    with suppress(OSError, ValueError):
                        self.process.stdin.close()
                try:
                    self.process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    with suppress(ProcessLookupError):
                        os.killpg(self.process.pid, signal.SIGTERM)
                    try:
                        # The guard gives the direct driver at most one second
                        # before SIGKILL, then publishes its wait4 receipt.
                        self.process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        failures.append("Driver guard did not stop after SIGTERM")
                finally:
                    # A direct driver can exit while descendants keep running.
                    # Clean the owned group even when the guard has exited.
                    with suppress(ProcessLookupError):
                        os.killpg(self.process.pid, signal.SIGKILL)
                    try:
                        self.process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        failures.append("Driver guard did not stop after SIGKILL")
                try:
                    self.memory_receipt = read_receipt(
                        self.receipt_path,
                        expected_guard_pid=self.process.pid,
                        expected_command=self.command,
                    )
                    self.peak_rss = max(self.peak_rss, self.memory_receipt["peak_rss_bytes"])
                    if self.memory_receipt["exitstatus"] != self.process.returncode:
                        failures.append("Driver receipt exit status differs from guard status")
                    if self.peak_rss > self.memory_limit:
                        failures.append("Driver lifetime memory limit exceeded")
                    if not self._request_failed and self.memory_receipt["exitstatus"] != 0:
                        failures.append(
                            f"Driver exited {self.memory_receipt['exitstatus']} during close"
                        )
                except ProcessGuardError as error:
                    failures.append(str(error))
        finally:
            if self.selector is not None:
                self.selector.close()
            streams = [self.stderr]
            if self.process is not None:
                streams += [self.process.stdin, self.process.stdout]
            for stream in streams:
                if stream is not None:
                    with suppress(OSError, ValueError):
                        stream.close()
            self.buffer = b""
        if failures:
            self.resource_error = "; ".join(failures)
            raise DriverError(self.resource_error)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def _invalid_json_constant(value):
    raise ValueError(f"Non-finite JSON value: {value}")


def _unique_json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result
