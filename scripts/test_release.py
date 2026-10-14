"""Run without publication credentials: python scripts/test_release.py."""

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError

import release
import yaml


class ReleaseChecks(unittest.TestCase):
    def test_metadata_and_tag(self):
        self.assertEqual(release.version(tag="v0.3.0"), "0.3.0")
        with self.assertRaisesRegex(ValueError, "versions differ"):
            release.version(tag="v99.0.0")
        for tag in ["main", "v1.2", "v01.2.3", "v1.2.3; echo bad", "v1.2.3\n"]:
            with self.subTest(tag=tag), self.assertRaises(ValueError):
                release.tag_version(tag)

    def test_only_main_tags_resolve(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def git(*args):
                return subprocess.run(
                    ["git", "-C", str(root), *args],
                    check=True,
                    capture_output=True,
                )

            git("init", "-b", "main")
            git(
                "-c",
                "user.name=Test",
                "-c",
                "user.email=test@example.invalid",
                "commit",
                "--allow-empty",
                "-m",
                "main",
            )
            git("update-ref", "refs/remotes/origin/main", "HEAD")
            git("tag", "v0.2.0")
            self.assertEqual(len(release.resolve("v0.2.0", root, "refs/heads/main")), 40)
            with self.assertRaises(ValueError):
                release.resolve("v0.2.0", root, "refs/heads/feature")
            with self.assertRaises(subprocess.CalledProcessError):
                release.resolve("v0.3.0", root, "refs/heads/main")
            git("checkout", "-b", "feature")
            git(
                "-c",
                "user.name=Test",
                "-c",
                "user.email=test@example.invalid",
                "commit",
                "--allow-empty",
                "-m",
                "feature",
            )
            git("tag", "v0.3.0")
            with self.assertRaises(subprocess.CalledProcessError):
                release.resolve("v0.3.0", root, "refs/heads/main")

    def test_registry_fails_closed(self):
        for registry in ["npm", "pypi"]:
            for status in [404, 403, 429, 500]:
                error = HTTPError("https://example.invalid", status, "test", {}, None)
                with patch("release.urllib.request.urlopen", side_effect=error):
                    if status == 404:
                        release.available(registry, "0.2.0")
                    else:
                        with self.assertRaises(HTTPError):
                            release.available(registry, "0.2.0")
            with (
                patch("release.urllib.request.urlopen"),
                self.assertRaisesRegex(ValueError, "already has"),
            ):
                release.available(registry, "0.2.0")
            with (
                patch("release.urllib.request.urlopen", side_effect=URLError("offline")),
                self.assertRaises(URLError),
            ):
                release.available(registry, "0.2.0")

    def test_artifact_bytes_and_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory)
            packages = bundle / "packages"
            packages.mkdir()
            package = packages / "cld-reducer-0.3.0.tgz"
            package.write_bytes(b"candidate")
            args = (bundle, "npm", "v0.3.0", "a" * 40)
            release.manifest(*args)
            release.manifest(*args, verify=True)
            with self.assertRaises(ValueError):
                release.manifest(bundle, "npm", "v0.3.0", "b" * 40, verify=True)
            package.write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "mismatch"):
                release.manifest(*args, verify=True)
            (packages / "unexpected.tgz").write_bytes(b"extra")
            with self.assertRaisesRegex(ValueError, "expected"):
                release.manifest(*args, verify=True)

    def test_workflows_keep_authority_in_publish_job(self):
        # BaseLoader keeps GitHub's "on" key as text instead of YAML 1.1 boolean.
        for name, registry in [("npm", "npm"), ("python", "pypi")]:
            path = release.ROOT / f".github/workflows/publish-{name}.yaml"
            workflow = yaml.load(path.read_text(), Loader=yaml.BaseLoader)
            self.assertEqual(set(workflow["on"]), {"workflow_dispatch"})
            inputs = workflow["on"]["workflow_dispatch"]["inputs"]
            self.assertEqual(inputs["dry_run"]["default"], "true")
            self.assertEqual(workflow["permissions"], {"contents": "read"})
            self.assertEqual(workflow["concurrency"]["cancel-in-progress"], "false")
            jobs = workflow["jobs"]
            for name in ["resolve", "build"]:
                self.assertNotIn("environment", jobs[name])
                self.assertNotIn("permissions", jobs[name])
            publish = jobs["publish"]
            self.assertEqual(publish["if"], "${{ !inputs.dry_run }}")
            self.assertEqual(publish["needs"], ["resolve", "build"])
            self.assertEqual(publish["environment"], registry)
            self.assertEqual(publish["permissions"]["id-token"], "write")
            for job in ["build", "publish"]:
                checkout = jobs[job]["steps"][0]
                self.assertEqual(checkout["with"]["ref"], "${{ needs.resolve.outputs.sha }}")
            steps = json.dumps(publish["steps"])
            self.assertIn("release.py verify", steps)
            self.assertIn("release.py available", steps)
            self.assertNotIn("npm pack", steps)
            self.assertNotIn("uv build", steps)


if __name__ == "__main__":
    unittest.main()
