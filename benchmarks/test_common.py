"""Source identity and process cleanup tests. These do not time solver calls."""

import copy
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import psutil
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
from common import (
    Driver,
    DriverError,
    input_digest,
    source_binding,
    source_identity,
    version_identity,
)


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


@pytest.fixture
def checkout(tmp_path):
    repo = tmp_path / "source"
    (repo / "js/src").mkdir(parents=True)
    (repo / "js/dist").mkdir()
    (repo / "python").mkdir()
    (repo / ".gitignore").write_text("js/dist/\nnode_modules/\npoetry.lock\n")
    (repo / "js/src/index.ts").write_text("export const value = 1;\n")
    (repo / "js/src/solver.ts").write_text("export const solver = 1;\n")
    (repo / "js/dist/index.js").write_text("export const value = 1;\n")
    (repo / "js/dist/solver.js").write_text("export const solver = 1;\n")
    (repo / "js/package-lock.json").write_text('{"lockfileVersion":3}\n')
    (repo / "python/uv.lock").write_text("version = 1\n")
    git(repo, "init", "-q")
    git(repo, "add", ".")
    git(
        repo,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-qm",
        "Fixture",
    )
    return repo


@pytest.fixture
def compile_mock(checkout, monkeypatch):
    """Use a deterministic compiler stand-in; real TypeScript has a separate smoke test."""
    compiler = checkout / "js/node_modules/typescript/bin/tsc"
    compiler.parent.mkdir(parents=True)
    compiler.write_text("fixture compiler version 1\n")
    highs = checkout / "js/node_modules/highs"
    (highs / "build").mkdir(parents=True)
    (highs / "package.json").write_text('{"name":"highs","version":"1.15.3"}\n')
    (highs / "build/highs.mjs").write_text("export default function fixture() {}\n")
    (highs / "build/highs.wasm").write_bytes(b"fixture wasm version 1")
    destinations = []

    def tools(repo):
        root = repo / "js/node_modules"
        return root / "typescript/bin/tsc", root / "highs", root / "highs/build/highs.mjs"

    def compile_source(repo, compiler, destination):
        assert destination != repo / "js/dist"
        destinations.append(destination)
        destination.mkdir(parents=True)
        for source in (repo / "js/src").glob("*.ts"):
            (destination / source.with_suffix(".js").name).write_bytes(source.read_bytes())

    monkeypatch.setattr(common, "_javascript_tools", tools)
    monkeypatch.setattr(common, "_compile_javascript", compile_source)
    return destinations


def test_bindings_hash_built_code_and_lockfiles(checkout, compile_mock):
    bound = source_binding(checkout, languages=["js"])
    assert bound["path"] == str(checkout.resolve())
    assert len(bound["head"]) == len(bound["tree"]) == 40
    assert bound["status"] == ""
    assert bound["build_verified"] is True
    assert bound["dependency_files"]
    assert bound["compiler_files"]
    for category in ("build_files", "lock_files"):
        assert len(bound[category]) == 2
        for name, value in bound[category].items():
            assert value == hashlib.sha256((checkout / name).read_bytes()).hexdigest()
    other = checkout.with_name("other-source")
    shutil.copytree(checkout, other)
    assert source_identity(bound) == source_identity(source_binding(other, require_js=True))
    assert source_identity(bound) == {key: value for key, value in bound.items() if key != "path"}
    assert all(not path.exists() for path in compile_mock)


@pytest.mark.parametrize("mutation", ["change", "extra", "missing"])
def test_required_js_rejects_stale_or_extra_build_without_changing_it(
    checkout, compile_mock, mutation
):
    if mutation == "change":
        (checkout / "js/dist/index.js").write_text("export const value = 2;\n")
    elif mutation == "extra":
        (checkout / "js/dist/stale-module.js").write_text("export const stale = true;\n")
    else:
        (checkout / "js/dist/solver.js").unlink()
    before = {path.name: path.read_bytes() for path in (checkout / "js/dist").iterdir()}
    with pytest.raises(ValueError, match="fresh source compilation|requires built js/dist"):
        source_binding(checkout, languages=["js"])
    assert {path.name: path.read_bytes() for path in (checkout / "js/dist").iterdir()} == before
    assert all(not path.exists() for path in compile_mock)


def test_new_source_commit_with_old_dist_is_rejected(checkout, compile_mock):
    (checkout / "js/src/index.ts").write_text("export const value = 2;\n")
    git(checkout, "add", "js/src/index.ts")
    git(
        checkout,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-qm",
        "Change source",
    )
    with pytest.raises(ValueError, match="changed=.*index.js"):
        source_binding(checkout, require_js=True)


@pytest.mark.parametrize(
    "artifact", ["highs/build/highs.mjs", "highs/build/highs.wasm", "typescript/bin/tsc"]
)
def test_same_version_altered_installed_bytes_change_identity(checkout, compile_mock, artifact):
    before = source_binding(checkout, require_js=True)
    package = (checkout / "js/node_modules/highs/package.json").read_bytes()
    target = checkout / "js/node_modules" / artifact
    target.write_bytes(target.read_bytes() + b"changed\n")
    after = source_binding(checkout, require_js=True)
    assert package == (checkout / "js/node_modules/highs/package.json").read_bytes()
    assert before["head"] == after["head"]
    assert before["build_files"] == after["build_files"]
    assert source_identity(before) != source_identity(after)
    key = "compiler_files" if artifact.startswith("typescript/") else "dependency_files"
    assert before[key] != after[key]


def test_build_verification_rejects_dependency_change_during_compile(
    checkout, compile_mock, monkeypatch
):
    compile_source = common._compile_javascript

    def mutate(repo, compiler, destination):
        compile_source(repo, compiler, destination)
        (repo / "js/node_modules/highs/build/highs.wasm").write_bytes(b"changed during compile")

    monkeypatch.setattr(common, "_compile_javascript", mutate)
    with pytest.raises(ValueError, match="changed during build verification"):
        source_binding(checkout, require_js=True)
    assert all(not path.exists() for path in compile_mock)


def test_build_verification_rejects_dist_change_during_compile(checkout, compile_mock, monkeypatch):
    compile_source = common._compile_javascript

    def mutate(repo, compiler, destination):
        compile_source(repo, compiler, destination)
        (repo / "js/dist/index.js").write_text("changed during compilation")

    monkeypatch.setattr(common, "_compile_javascript", mutate)
    with pytest.raises(ValueError, match="dist changed during build verification"):
        source_binding(checkout, require_js=True)


def test_real_typescript_build_and_resolved_solver_smoke(tmp_path):
    installed = Path(__file__).resolve().parents[1] / "js"
    if not (installed / "node_modules/typescript/bin/tsc").is_file() or not shutil.which("node"):
        pytest.skip("Install JavaScript development dependencies for the real build smoke check")
    repo = tmp_path / "real-source"
    (repo / "js").mkdir(parents=True)
    (repo / ".gitignore").write_text("node_modules/\njs/dist/\n")
    shutil.copytree(installed / "src", repo / "js/src")
    for name in ("package.json", "package-lock.json", "tsconfig.json", "tsconfig.build.json"):
        shutil.copyfile(installed / name, repo / "js" / name)
    (repo / "js/node_modules").symlink_to(installed / "node_modules", target_is_directory=True)
    common._compile_javascript(
        repo, installed / "node_modules/typescript/bin/tsc", repo / "js/dist"
    )
    git(repo, "init", "-q")
    git(repo, "add", ".")
    git(
        repo,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-qm",
        "Fixture",
    )
    before = {
        path.relative_to(repo): path.read_bytes()
        for path in (repo / "js/dist").rglob("*")
        if path.is_file()
    }
    binding = source_binding(repo, languages=["js"])
    assert binding["build_verified"] is True
    assert "highs/build/highs.mjs" in binding["dependency_files"]
    assert "highs/build/highs.wasm" in binding["dependency_files"]
    assert "typescript/bin/tsc" in binding["compiler_files"]
    assert "typescript/lib/_tsc.js" in binding["compiler_files"]
    assert before == {
        path.relative_to(repo): path.read_bytes()
        for path in (repo / "js/dist").rglob("*")
        if path.is_file()
    }


@pytest.mark.parametrize("mutation", ["change", "add", "remove", "lock"])
def test_ignored_build_and_lock_changes_break_identity(checkout, mutation):
    before = source_binding(checkout)
    if mutation == "change":
        (checkout / "js/dist/index.js").write_text("export const value = 2;\n")
    elif mutation == "add":
        (checkout / "js/dist/new-module.mjs").write_text("export default 1;\n")
    elif mutation == "remove":
        (checkout / "js/dist/solver.js").unlink()
    else:
        (checkout / "poetry.lock").write_text("ignored lockfile\n")
    after = source_binding(checkout)
    assert before["head"] == after["head"]
    assert before["tree"] == after["tree"]
    assert source_identity(before) != source_identity(after)


def test_types_and_maps_do_not_change_executable_binding(checkout):
    before = source_binding(checkout)
    (checkout / "js/dist/index.d.ts").write_text("export declare const value: number;\n")
    (checkout / "js/dist/index.js.map").write_text("{}\n")
    assert source_identity(before) == source_identity(source_binding(checkout))


@pytest.mark.parametrize("mutation", ["tracked", "staged", "untracked", "hidden", "skip"])
def test_dirty_or_hidden_source_is_rejected(checkout, mutation):
    path = checkout / "js/src/index.ts"
    if mutation == "hidden":
        git(checkout, "update-index", "--assume-unchanged", "js/src/index.ts")
    elif mutation == "skip":
        git(checkout, "update-index", "--skip-worktree", "js/src/index.ts")
    if mutation == "untracked":
        (checkout / "extra.py").write_text("value = 2\n")
    else:
        path.write_text("export const value = 2;\n")
    if mutation == "staged":
        git(checkout, "add", "js/src/index.ts")
    with pytest.raises(ValueError, match="clean|index"):
        source_binding(checkout)


def test_missing_js_build_fails_only_when_js_is_required(checkout):
    shutil.rmtree(checkout / "js/dist")
    assert source_binding(checkout, languages=["python", "r"])["build_files"] == {}
    for kwargs in ({"languages": ["js"]}, {"languages": "javascript"}, {"require_js": True}):
        with pytest.raises(ValueError, match="requires built js/dist"):
            source_binding(checkout, **kwargs)
    (checkout / "js/dist").mkdir()
    (checkout / "js/dist/index.js").write_text("export const value = 1;\n")
    with pytest.raises(ValueError, match="solver.js"):
        source_binding(checkout, require_js=True)


def test_source_binding_requires_checkout_root(checkout):
    with pytest.raises(ValueError, match="checkout root"):
        source_binding(checkout / "js")


@pytest.mark.parametrize("language", ["python", "r", "javascript"])
def test_version_identity_drops_load_times_and_source_but_binds_dependencies(language):
    version = {
        "ok": True,
        "action": "version",
        "language": language,
        "runtime": {"name": language, "version": "1.2"},
        "package_version": "0.3.0",
        "dependencies": {"highs": "1.15.3"},
        "solver": {"version": "1.15.1"},
        "settings": {"presolve": "on", "threads": 1, "time_limit_ns": 5000},
        "timer": {
            "resolution_ns": 1,
            "warnings": [],
            "absolute_accuracy_calibrated": False,
            "name": "clock",
            "fallback": False,
            "monotonic": True,
            "resolution_method": "sample10000",
        },
        "module_load_ns": 10,
        "solver_load_ns": 20,
        "source_head": "before",
        "source_path": "/before",
        "repo": "/before",
    }
    other = copy.deepcopy(version)
    other.update(
        module_load_ns=99,
        solver_load_ns=999,
        source_head="after",
        source_path="/after",
        repo="/after",
    )
    other["timer"]["resolution_ns"] = 20
    other["timer"]["warnings"] = ["clock warning"]
    assert version_identity(version) == version_identity(other)
    assert version_identity(version)["settings"] == version["settings"]
    assert version_identity(version)["timer"] == {
        key: value
        for key, value in version["timer"].items()
        if key not in {"resolution_ns", "warnings"}
    }
    changed = copy.deepcopy(other)
    changed["timer"]["absolute_accuracy_calibrated"] = True
    assert version_identity(version) != version_identity(changed)
    for field in ("runtime", "dependencies", "solver", "settings", "timer"):
        changed = copy.deepcopy(other)
        changed[field] = "changed"
        assert version_identity(version) != version_identity(changed)


def manifest():
    return {
        "schema_version": 1,
        "case_generator": "cases.py:1",
        "languages": ["js"],
        "methods": ["letter_minimum"],
        "presolve": {"js": "on"},
        "memory_limit_mb": 128,
        "cases": [
            {
                "id": "case",
                "call": "adjacency",
                "input": {"adjacency": [[1]], "groups": [""]},
                "options": {},
                "wall_seconds": 30,
                "tier": "solve",
                "classification": "ordinary",
                "split": "validation",
                "seed": 123,
            }
        ],
        "iterations": {},
        "processes": 8,
        "warmup_batches": 3,
        "batches": 9,
        "frozen": False,
    }


def test_input_digest_stays_fixed_through_calibration_and_freeze():
    original = manifest()
    changed = copy.deepcopy(original)
    changed.update(
        iterations={"case": 20},
        processes=16,
        warmup_batches=5,
        batches=20,
        frozen=True,
        batch_target_ns=70_000_000,
        bootstrap_resamples=20000,
        order_seed=900,
        bootstrap_seed=901,
        pilot_source={"head": "abc"},
        pilot_harness={"head": "def"},
        calibration={"path": "/evidence"},
        freeze_metadata={"date": "today"},
        gain_targets={"js": ["case"]},
        baseline_failures=["case"],
    )
    assert input_digest(changed) == input_digest(original)


@pytest.mark.parametrize(
    "field",
    [
        "schema_version",
        "case_generator",
        "languages",
        "methods",
        "presolve",
        "memory_limit_mb",
        "memory_growth_tolerance_mb",
        "resource_limits",
        "resource_design",
        "wall_seconds",
        "threads",
    ],
)
def test_input_digest_binds_runtime_and_resource_fields(field):
    original = manifest()
    changed = copy.deepcopy(original)
    changed[field] = "changed"
    assert input_digest(changed) != input_digest(original)


@pytest.mark.parametrize(
    "field",
    ["id", "call", "input", "options", "wall_seconds", "tier", "classification", "split", "seed"],
)
def test_input_digest_binds_every_case_definition(field):
    original = manifest()
    changed = copy.deepcopy(original)
    changed["cases"][0][field] = "changed"
    assert input_digest(changed) != input_digest(original)


def fake_driver(tmp_path, monkeypatch, source, memory_mb=128):
    directory = tmp_path / "benchmarks"
    directory.mkdir(exist_ok=True)
    (directory / "python_driver.py").write_text(source)
    monkeypatch.setattr(common, "ROOT", tmp_path)
    number = len(list(tmp_path.glob("driver*.stderr")))
    return Driver("python", tmp_path, "on", tmp_path / f"driver{number}.stderr", memory_mb)


def assert_closed(driver):
    assert driver._closed
    assert driver.process.poll() is not None
    assert driver.process.stdin.closed
    assert driver.process.stdout.closed
    assert driver.stderr.closed
    assert driver.memory_receipt is not None or driver.resource_error is not None
    driver.close()
    with pytest.raises(DriverError, match="closed"):
        driver.request({"action": "version"})


@pytest.mark.parametrize(
    "response",
    [
        b"not json\n",
        b"\xff\n",
        b'{"ok":true,"action":"other"}\n',
        b"[]\n",
        b'{"ok":"true","action":"version"}\n',
        b'{"ok":false,"action":"version","error":{"kind":"X","message":"x"},"result":{}}\n',
        b'{"ok":false,"action":"version","error":"bad"}\n',
        b'{"ok":true,"action":"version","error":{}}\n',
        b'{"ok":true,"action":"version","value":NaN}\n',
        b'{"ok":true,"action":"version","ok":false}\n',
        b'{"ok":true,"action":"version"}\nextra\n',
    ],
)
def test_invalid_responses_close_process_and_streams(tmp_path, monkeypatch, response):
    driver = fake_driver(
        tmp_path,
        monkeypatch,
        f"import os,sys,time\nsys.stdin.readline()\nos.write(1,{response!r})\ntime.sleep(30)\n",
    )
    try:
        with pytest.raises(DriverError):
            driver.request({"action": "version"})
        assert_closed(driver)
    finally:
        driver.close()


def test_valid_package_error_keeps_transport_usable(tmp_path, monkeypatch):
    source = """import sys,json
for line in sys.stdin:
    action=json.loads(line)['action']
    response={'ok':action=='version','action':action}
    if not response['ok']: response['error']={'kind':'SolverError','message':'expected'}
    print(json.dumps(response),flush=True)
"""
    with fake_driver(tmp_path, monkeypatch, source) as driver:
        assert not driver.request({"action": "capture"})["ok"]
        assert driver.request({"action": "version"})["ok"]
        assert driver.rss > 0
        assert driver.peak_rss >= driver.rss
    assert_closed(driver)
    assert driver.resource_error is None
    assert driver.memory_receipt["exitstatus"] == 0
    assert driver.memory_receipt["guard_pid"] == driver.process.pid
    assert driver.memory_receipt["child_pid"] != driver.process.pid
    assert driver.peak_rss >= driver.memory_receipt["peak_rss_bytes"] > 0


def test_close_allows_bounded_healthy_shutdown_after_eof(tmp_path, monkeypatch):
    source = """import json,sys,time
for line in sys.stdin:
    print(json.dumps({'ok':True,'action':'version'}),flush=True)
time.sleep(0.8)
"""
    with fake_driver(tmp_path, monkeypatch, source) as driver:
        assert driver.request({"action": "version"})["ok"]
    assert_closed(driver)
    assert driver.resource_error is None
    assert driver.memory_receipt["exitstatus"] == 0


@pytest.mark.parametrize("memory_mb", [48, 128])
def test_close_checks_native_peak_after_memory_was_released(tmp_path, monkeypatch, memory_mb):
    source = """import json,mmap,os,sys
sys.stdin.readline()
region = mmap.mmap(-1, 64 * 1024 * 1024)
for offset in range(0, len(region), mmap.PAGESIZE): region[offset] = 1
region.close()
print(json.dumps({'ok':True,'action':'version','pid':os.getpid()}),flush=True)
sys.stdin.buffer.read()
"""
    driver = fake_driver(tmp_path, monkeypatch, source, memory_mb)
    # Model the watchdog missing a short spike. Native wait4 evidence must still
    # catch it after release and after the process has exited.
    monkeypatch.setattr(driver, "_check_memory", lambda: None)
    try:
        response = driver.request({"action": "version"})
        sampled_after_release = psutil.Process(response["pid"]).memory_info().rss
        assert driver.peak_rss == 0
        if memory_mb == 48:
            with pytest.raises(DriverError, match="lifetime memory limit"):
                driver.close()
            assert "lifetime memory limit" in driver.resource_error
        else:
            driver.close()
            assert driver.resource_error is None
        assert driver.memory_receipt["peak_rss_bytes"] >= 64 * 1024 * 1024
        assert driver.peak_rss > sampled_after_release + 32 * 1024 * 1024
        assert_closed(driver)
    finally:
        driver.close()


def test_close_rejects_missing_receipt_and_remains_idempotent(tmp_path, monkeypatch):
    source = """import json,sys
for line in sys.stdin: print(json.dumps({'ok':True,'action':'version'}),flush=True)
"""
    driver = fake_driver(tmp_path, monkeypatch, source)
    try:
        assert driver.request({"action": "version"})["ok"]
        os.killpg(driver.process.pid, signal.SIGKILL)
        driver.process.wait(timeout=2)
        with pytest.raises(DriverError, match="Missing or invalid"):
            driver.close()
        assert driver.memory_receipt is None
        assert "Missing or invalid" in driver.resource_error
        assert_closed(driver)
    finally:
        driver.close()


def test_close_binds_receipt_to_the_guard_pid(tmp_path, monkeypatch):
    driver = fake_driver(tmp_path, monkeypatch, "import sys;sys.stdin.buffer.read()\n")
    try:
        driver.process.stdin.close()
        driver.process.wait(timeout=2)
        receipt = json.loads(driver.receipt_path.read_text())
        receipt["guard_pid"] += 1
        driver.receipt_path.write_text(json.dumps(receipt))
        with pytest.raises(DriverError, match="another guard|invalid process IDs"):
            driver.close()
        assert driver.memory_receipt is None
        assert driver.resource_error is not None
        assert_closed(driver)
    finally:
        driver.close()


def test_successful_response_cannot_hide_abnormal_native_exit(tmp_path, monkeypatch):
    source = """import json,sys
sys.stdin.readline()
print(json.dumps({'ok':True,'action':'version'}),flush=True)
sys.stdin.buffer.read()
sys.exit(7)
"""
    driver = fake_driver(tmp_path, monkeypatch, source)
    try:
        assert driver.request({"action": "version"})["ok"]
        with pytest.raises(DriverError, match="exited 7"):
            driver.close()
        assert driver.memory_receipt["exitstatus"] == 7
        assert "exited 7" in driver.resource_error
        assert_closed(driver)
    finally:
        driver.close()


@pytest.mark.parametrize("failure", ["timeout", "memory"])
def test_request_failure_inside_context_keeps_failed_profile_collectable(
    tmp_path, monkeypatch, failure
):
    source = "import sys,time\nsys.stdin.readline()\n"
    if failure == "memory":
        source += "data=bytearray(80*1024*1024)\n"
    source += "time.sleep(30)\n"
    driver = fake_driver(tmp_path, monkeypatch, source, memory_mb=64)
    with driver:
        try:
            driver.request({"action": "profile"}, timeout=0.2 if failure == "timeout" else 2)
        except DriverError as error:
            # bounded_request catches this inside its context and emits a row.
            response = {"ok": False, "error": str(error)}
        else:
            pytest.fail("Expected the request to fail")
    assert not response["ok"]
    assert ("wall limit" if failure == "timeout" else "memory limit") in response["error"]
    assert driver.memory_receipt is not None
    if failure == "memory":
        assert "memory limit" in driver.resource_error
    assert_closed(driver)


def test_memory_violation_closes_without_context_manager(tmp_path, monkeypatch):
    driver = fake_driver(
        tmp_path,
        monkeypatch,
        "import sys,time\nsys.stdin.readline()\ndata=bytearray(80*1024*1024)\ntime.sleep(30)\n",
        memory_mb=64,
    )
    try:
        with pytest.raises(DriverError, match="memory limit"):
            driver.request({"action": "version"})
        assert driver.peak_rss > 64 * 1024 * 1024
        assert_closed(driver)
    finally:
        driver.close()


def test_memory_is_checked_after_fast_response(tmp_path, monkeypatch):
    driver = fake_driver(
        tmp_path,
        monkeypatch,
        "import sys,json\nfor line in sys.stdin: "
        'print(json.dumps({"ok":True,"action":"version"}),flush=True)\n',
    )
    initial = driver._check_memory
    parse = common.json.loads
    parsed = False
    checks = 0

    def parsed_response(*args, **kwargs):
        nonlocal parsed
        result = parse(*args, **kwargs)
        parsed = True
        return result

    def checked():
        nonlocal checks
        checks += 1
        initial()
        if parsed:
            raise DriverError("Driver memory limit exceeded at response")

    monkeypatch.setattr(common.json, "loads", parsed_response)
    monkeypatch.setattr(driver, "_check_memory", checked)
    try:
        with pytest.raises(DriverError, match="memory limit"):
            driver.request({"action": "version"})
        assert checks >= 2
        assert_closed(driver)
    finally:
        driver.close()


def test_response_size_limit_closes_transport(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "MAX_RESPONSE_BYTES", 128)
    driver = fake_driver(
        tmp_path,
        monkeypatch,
        "import os,sys,time\nsys.stdin.readline()\nos.write(1,b'x'*129)\ntime.sleep(30)\n",
    )
    try:
        with pytest.raises(DriverError, match="response exceeds"):
            driver.request({"action": "version"})
        assert_closed(driver)
    finally:
        driver.close()


def test_timeout_also_bounds_a_blocked_request_write(tmp_path, monkeypatch):
    driver = fake_driver(tmp_path, monkeypatch, "import time\ntime.sleep(30)\n")
    try:
        with pytest.raises(DriverError, match="wall limit"):
            driver.request({"action": "version", "large": "x" * (2 * 1024 * 1024)}, timeout=0.1)
        assert_closed(driver)
    finally:
        driver.close()


def wait_for(predicate):
    deadline = time.monotonic() + 3
    while not predicate():
        if time.monotonic() > deadline:
            pytest.fail("Test process did not reach the required state")
        time.sleep(0.01)


def test_broken_pipe_and_closed_stdout_close_process(tmp_path, monkeypatch):
    ready = tmp_path / "ready"
    source = (
        "import os,time\nfrom pathlib import Path\nos.close(0)\n"
        f"Path({str(ready)!r}).write_text('ready')\ntime.sleep(30)\n"
    )
    driver = fake_driver(tmp_path, monkeypatch, source)
    try:
        wait_for(ready.exists)
        with pytest.raises(DriverError, match="transport failed"):
            driver.request({"action": "version"})
        assert_closed(driver)
    finally:
        driver.close()
    driver = fake_driver(tmp_path, monkeypatch, "import os,time\nos.close(1)\ntime.sleep(30)\n")
    try:
        with pytest.raises(DriverError, match="closed stdout"):
            driver.request({"action": "version"})
        assert_closed(driver)
    finally:
        driver.close()


def test_close_kills_children_after_leader_exits(tmp_path, monkeypatch):
    child_ready = tmp_path / "child.pid"
    child = (
        "import os,signal,time\nfrom pathlib import Path\n"
        "signal.signal(signal.SIGTERM,signal.SIG_IGN)\n"
        f"Path({str(child_ready)!r}).write_text(str(os.getpid()))\ntime.sleep(30)\n"
    )
    source = (
        "import subprocess,sys,json,time\nfrom pathlib import Path\nsys.stdin.readline()\n"
        f"subprocess.Popen([sys.executable,'-c',{child!r}])\n"
        f"while not Path({str(child_ready)!r}).exists(): time.sleep(.01)\n"
        "print(json.dumps({'ok':True,'action':'version'}),flush=True)\n"
    )
    driver = fake_driver(tmp_path, monkeypatch, source)
    try:
        assert driver.request({"action": "version"})["ok"]
        child_pid = int(child_ready.read_text())
        driver.process.wait(timeout=2)
        driver.close()

        def dead():
            try:
                return psutil.Process(child_pid).status() == psutil.STATUS_ZOMBIE
            except psutil.NoSuchProcess:
                return True

        wait_for(dead)
        assert_closed(driver)
    finally:
        driver.close()


def test_failed_startup_closes_stderr(tmp_path, monkeypatch):
    opened = []
    real_open = open

    def tracked_open(*args, **kwargs):
        stream = real_open(*args, **kwargs)
        opened.append(stream)
        return stream

    monkeypatch.setattr(common, "open", tracked_open, raising=False)

    def fail(*args, **kwargs):
        raise FileNotFoundError("missing interpreter")

    monkeypatch.setattr(common.subprocess, "Popen", fail)
    with pytest.raises(FileNotFoundError, match="missing interpreter"):
        Driver("python", tmp_path, "on", tmp_path / "stderr")
    assert len(opened) == 1 and opened[0].closed


@pytest.mark.parametrize(
    "value,timeout",
    [
        ({}, 1),
        ({"action": "version"}, 0),
        ({"action": "version"}, float("inf")),
        ({"action": "version", "value": float("nan")}, 1),
    ],
)
def test_bad_requests_close_transport(tmp_path, monkeypatch, value, timeout):
    driver = fake_driver(tmp_path, monkeypatch, "import time\ntime.sleep(30)\n")
    with pytest.raises(DriverError):
        driver.request(value, timeout)
    assert_closed(driver)


@pytest.mark.parametrize(
    "field,baseline,candidate",
    [
        ("package", "0.3.0", "0.4.0"),
        ("package_version", "0.3.0", "0.4.0"),
        (
            "package",
            {"name": "cldreducer", "version": "0.3.0"},
            {"name": "cldreducer", "version": "0.4.0"},
        ),
    ],
)
def test_reducer_release_version_is_recorded_but_not_a_dependency(field, baseline, candidate):
    before = {field: baseline, "dependencies": {"highs": "1.15.1"}, "runtime": "3.13"}
    after = dict(copy.deepcopy(before), **{field: candidate})
    assert version_identity(before) == version_identity(after)
    assert before[field] == baseline and after[field] == candidate
    after["dependencies"]["highs"] = "1.15.2"
    assert version_identity(before) != version_identity(after)
    if isinstance(candidate, dict):
        after = copy.deepcopy(before)
        after[field]["name"] = "another-package"
        assert version_identity(before) != version_identity(after)
