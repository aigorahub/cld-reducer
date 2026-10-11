"""Check both Python archives, then install each route outside the checkout."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from email.parser import BytesParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SMOKE = """
from pathlib import Path
import sys
import pandas as pd
import cld_reducer
from cld_reducer import reduce_letters, reduce_from_adjacency
assert Path(cld_reducer.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())
assert dict(reduce_from_adjacency([[True]], groups=["001"]).letters) == {"001": "A"}
for name, count in [("simple_abc_to_ac", 5), ("piepho2004_wheat", 20)]:
    pairs = pd.read_csv(f"examples/{name}_pairs.csv", dtype={"group1": str, "group2": str})
    means_file = Path(f"examples/{name}_means.csv")
    means = pd.read_csv(means_file, dtype={"group": str}) if means_file.exists() else None
    result = reduce_letters(pairs, means, method="assignment_minimum")
    assert len(result.groups) == count
    assert result.relationship_preserved
    assert result.stats["assignments_after"] == (8 if count == 5 else 44)
    c = reduce_letters(pairs, means, method="letter-minimum")
    assert c.method == "letter_minimum"
    assert c.stats["objective"] == c.stats["num_letters_after"]
    assert c.stats["assignments_after"] == (9 if count == 5 else 56)
    assert reduce_letters(pairs, means) == c
from cld_reducer.algorithms.assignment_minimum import reduce_assignment_minimum
sigma = reduce_assignment_minimum([[1]], ["001"], method="metadata-only")
assert sigma.method == "metadata-only" and sigma.stats["objective"] == 1
from cld_reducer.cli import main
for labels in [("001", "002"), ("NA", "NaN"), ("", "b")]:
    pairs = pd.DataFrame({"left": [labels[0]], "right": [labels[1]], "different": [False]})
    pairs.to_csv("pairs.csv", index=False)
    pd.DataFrame({"treatment": labels, "group": [2, 1]}).to_csv("means.csv", index=False)
    args = ["pairs.csv", "--means", "means.csv", "--out", "out.csv", "--group1", "left",
            "--group2", "right", "--significant", "different"]
    assert main(args) == 0
    assert main(args + ["--method", "letter_minimum"]) == 0
    assert main(args + ["--method", "letter-minimum"]) == 0
    result = pd.read_csv("out.csv", dtype=str, keep_default_na=False)
    assert result["group"].tolist() == list(labels)
print("installed API, exact CLI labels, simple and wheat cases passed", cld_reducer.__version__)
"""


def run(args, cwd, env):
    subprocess.run([str(arg) for arg in args], cwd=cwd, env=env, check=True)


def check_contents(wheel, source):
    def check_metadata(raw):
        metadata = BytesParser().parsebytes(raw)
        assert metadata["Name"] == "cld-reducer"
        assert metadata["Version"] == wheel.name.split("-")[1]
        assert metadata["Requires-Python"] == ">=3.10"
        assert "Repository, https://github.com/aigorahub/cld-reducer" in metadata.get_all(
            "Project-URL"
        )

    with zipfile.ZipFile(wheel) as archive:
        files = set(archive.namelist())
        for name in [
            "cld_reducer/__init__.py",
            "cld_reducer/cli.py",
            "cld_reducer/NOTICE",
        ]:
            assert name in files, name
        assert any(name.endswith("/licenses/LICENSE") for name in files), "wheel LICENSE"
        assert all(name.startswith("cld_reducer/") or ".dist-info/" in name for name in files)
        metadata_name = next(name for name in files if name.endswith(".dist-info/METADATA"))
        check_metadata(archive.read(metadata_name))
        assert not any("__pycache__" in name or name.endswith(".pyc") for name in files)
    with tarfile.open(source) as archive:
        members = archive.getmembers()
        files = {member.name.split("/", 1)[1] for member in members if "/" in member.name}
        metadata_member = next(member for member in members if member.name.endswith("/PKG-INFO"))
        check_metadata(archive.extractfile(metadata_member).read())
        required = {
            "src/cld_reducer/__init__.py",
            "LICENSE",
            "NOTICE",
            "pyproject.toml",
            "examples/simple_abc_to_ac.py",
            "examples/piepho2004_wheat.py",
            "examples/simple_abc_to_ac_pairs.csv",
            "examples/simple_abc_to_ac_means.csv",
            "examples/piepho2004_wheat_pairs.csv",
        }
        assert required <= files, required - files
        allowed = {
            "src",
            "tests",
            "examples",
            "README.md",
            "LICENSE",
            "NOTICE",
            "pyproject.toml",
            "PKG-INFO",
            ".gitignore",
        }
        assert all(name.split("/", 1)[0] in allowed for name in files), files
        assert all(not m.issym() and not m.islnk() for m in members)
        assert all(
            not Path(m.name).is_absolute() and ".." not in Path(m.name).parts for m in members
        )


def install_and_check(wheel, workspace, examples, env):
    workspace.mkdir()
    venv = workspace / "venv"
    run(["uv", "venv", venv, "--python", sys.executable], workspace, env)
    python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    run(["uv", "pip", "install", "--python", python, wheel], workspace, env)
    shutil.copytree(examples, workspace / "examples")
    (workspace / "smoke.py").write_text(SMOKE)
    run([python, "-I", "smoke.py"], workspace, env)
    for example in ["simple_abc_to_ac.py", "piepho2004_wheat.py"]:
        run([python, "-I", workspace / "examples" / example], workspace, env)
    command = venv / ("Scripts/cld-reduce.exe" if os.name == "nt" else "bin/cld-reduce")
    run(
        [
            command,
            "pairs.csv",
            "--means",
            "means.csv",
            "--out",
            "entrypoint.csv",
            "--group1",
            "left",
            "--group2",
            "right",
            "--significant",
            "different",
        ],
        workspace,
        env,
    )


def main():
    dist = Path(sys.argv[1]).resolve()
    wheels, sources = list(dist.glob("*.whl")), list(dist.glob("*.tar.gz"))
    assert len(wheels) == len(sources) == 1, "expected one wheel and one source distribution"
    check_contents(wheels[0], sources[0])
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in {"PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "UV_PROJECT_ENVIRONMENT"}
    }
    env["PYTHONNOUSERSITE"] = "1"
    with tempfile.TemporaryDirectory(prefix="cld-python-package-") as directory:
        work = Path(directory)
        install_and_check(wheels[0], work / "wheel", ROOT / "python/examples", env)
        unpack = work / "source"
        unpack.mkdir()
        with tarfile.open(sources[0]) as archive:
            archive.extractall(unpack, filter="data")
        source = next(unpack.iterdir())
        built = work / "rebuilt"
        run(["uv", "build", "--wheel", "--out-dir", built, source], work, env)
        install_and_check(next(built.glob("*.whl")), work / "sdist", source / "examples", env)
    print("wheel and sdist-built wheel verified outside the repository")


if __name__ == "__main__":
    main()
