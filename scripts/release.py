"""Shared checks for the two manual publication workflows. No upload commands."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib

ROOT = Path(__file__).resolve().parents[1]
TAG = re.compile(r"v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\Z")


def tag_version(tag):
    if not TAG.fullmatch(tag):
        raise ValueError("tag must have the form v0.2.0")
    return tag[1:]


def version(root=ROOT, tag=None):
    project = tomllib.loads((root / "python/pyproject.toml").read_text())["project"]
    lock = tomllib.loads((root / "python/uv.lock").read_text())
    npm = json.loads((root / "js/package.json").read_text())
    npm_lock = json.loads((root / "js/package-lock.json").read_text())
    runtime = ast.parse((root / "python/src/cld_reducer/__init__.py").read_text())
    runtime_version = next(
        ast.literal_eval(node.value)
        for node in runtime.body
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "__version__" for t in node.targets)
    )
    values = {
        "R": re.search(r"^Version: (.+)$", (root / "DESCRIPTION").read_text(), re.M)[1],
        "citation": re.search(r"^version: (.+)$", (root / "CITATION.cff").read_text(), re.M)[1],
        "Python": project["version"],
        "runtime": runtime_version,
        "Python lock": next(p["version"] for p in lock["package"] if p["name"] == "cld-reducer"),
        "npm": npm["version"],
        "npm lock": npm_lock["version"],
        "npm root lock": npm_lock["packages"][""]["version"],
    }
    if tag is not None:
        values["tag"] = tag_version(tag)
    if len(set(values.values())) != 1:
        raise ValueError(f"package versions differ: {values}")
    candidate = project["version"]
    tag_version(f"v{candidate}")
    if not re.search(
        rf"^# cldreducer {re.escape(candidate)}$", (root / "NEWS.md").read_text(), re.M
    ):
        raise ValueError("NEWS.md must describe the candidate version")
    notices = [
        (root / name).read_text() for name in ["inst/COPYRIGHTS", "python/NOTICE", "js/NOTICE"]
    ]
    if len(set(notices)) != 1:
        raise ValueError("data notices differ across packages")
    return candidate


def resolve(tag, root=ROOT, dispatch_ref=None):
    tag_version(tag)
    if (dispatch_ref or os.environ.get("GITHUB_REF")) != "refs/heads/main":
        raise ValueError("dispatch the publication workflow from main")

    def git(*args):
        return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()

    sha = git("rev-parse", "--verify", f"refs/tags/{tag}^{{commit}}")
    subprocess.run(
        ["git", "-C", str(root), "merge-base", "--is-ancestor", sha, "refs/remotes/origin/main"],
        check=True,
    )
    return sha


def available(registry, candidate):
    tag_version(f"v{candidate}")
    url = (
        f"https://registry.npmjs.org/cld-reducer/{candidate}"
        if registry == "npm"
        else f"https://pypi.org/pypi/cld-reducer/{candidate}/json"
    )
    try:
        with urllib.request.urlopen(url, timeout=30):
            pass
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return
        raise
    raise ValueError(f"{registry} already has cld-reducer {candidate}; do not overwrite it")


def package_hashes(bundle, registry, candidate):
    packages = bundle / "packages"
    expected = (
        {f"cld-reducer-{candidate}.tgz"}
        if registry == "npm"
        else {f"cld_reducer-{candidate}-py3-none-any.whl", f"cld_reducer-{candidate}.tar.gz"}
    )
    actual = {p.name for p in packages.iterdir()}
    if actual != expected:
        raise ValueError(f"expected {expected}, found {actual}")
    if any(not p.is_file() or p.is_symlink() for p in packages.iterdir()):
        raise ValueError("package files must be regular files")
    return {
        name: hashlib.sha256((packages / name).read_bytes()).hexdigest()
        for name in sorted(expected)
    }


def manifest(bundle, registry, tag, commit, verify=False):
    candidate = version(tag=tag)
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("commit must be a full Git SHA")
    record = {
        "registry": registry,
        "tag": tag,
        "version": candidate,
        "commit": commit,
        "sha256": package_hashes(bundle, registry, candidate),
    }
    path = bundle / "release-manifest.json"
    if verify:
        if json.loads(path.read_text()) != record:
            raise ValueError("artifact manifest or SHA-256 mismatch")
    else:
        path.write_text(json.dumps(record, indent=2) + "\n")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a") as handle:
            handle.write("Verified build evidence (not publication confirmation):\n\n```json\n")
            handle.write(json.dumps(record, indent=2) + "\n```\n")
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=["version", "resolve", "available", "manifest", "verify"]
    )
    parser.add_argument("--tag")
    parser.add_argument("--registry", choices=["npm", "pypi"])
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--commit")
    args = parser.parse_args()
    if args.command == "version":
        print(version(tag=args.tag))
    elif args.command == "resolve":
        sha = resolve(args.tag)
        candidate = tag_version(args.tag)
        with open(os.environ["GITHUB_OUTPUT"], "a") as handle:
            handle.write(f"sha={sha}\nversion={candidate}\n")
        print(f"Resolved {args.tag} to {sha}")
    elif args.command == "available":
        available(args.registry, tag_version(args.tag))
        print(f"{args.registry}: version is currently absent")
    else:
        manifest(args.bundle, args.registry, args.tag, args.commit, args.command == "verify")


if __name__ == "__main__":
    main()
