"""scripts/evict-plugin-cache.sh — guarded eviction of one cached plugin version.

Every test points CLAUDE_CONFIG_DIR and HOME at a temp directory, so neither
the real plugin cache nor the real home directory is ever a target.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "evict-plugin-cache.sh"
MARKETPLACE = "brightopsai-plugins-official"


def _files(root: Path) -> list[str]:
    return sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file())


class TestEvictPluginCache(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        # Resolved, because the script prints symlink-free paths and the system
        # temp directory is itself behind a symlink on macOS.
        self.base = Path(os.path.realpath(tmp.name))
        self.home = self.base / "home"
        self.config = self.base / "config"
        self.outside = self.base / "outside"
        self.cache = self.config / "plugins" / "cache" / MARKETPLACE
        self._seed(self.cache)
        self.outside.mkdir()
        (self.outside / "keep.txt").write_text("keep\n", encoding="utf-8")
        self.home.mkdir()
        self.before = _files(self.base)

    @staticmethod
    def _seed(cache: Path) -> None:
        for rel in (
            "alpha/1.0.0/plugin.json",
            "alpha/1.0.0/skills/demo/SKILL.md",
            "alpha/1.1.0/plugin.json",
            "beta/1.0.0/plugin.json",
        ):
            path = cache / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("x\n", encoding="utf-8")

    def _run(self, *args: str, **env: str) -> subprocess.CompletedProcess[str]:
        full_env = os.environ.copy()
        full_env.pop("DRY_RUN", None)
        full_env["HOME"] = str(self.home)
        full_env["CLAUDE_CONFIG_DIR"] = str(self.config)
        # The realpath fallback runs python3; keep its bytecode cache out of
        # the sandbox so the before/after file lists stay comparable.
        full_env["PYTHONDONTWRITEBYTECODE"] = "1"
        full_env.update(env)
        return subprocess.run(
            ["bash", str(SCRIPT), *args],
            env=full_env,
            capture_output=True,
            text=True,
            check=False,
        )

    def _assert_refused(self, result: subprocess.CompletedProcess[str]) -> None:
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(_files(self.base), self.before, "a refused run deleted files")

    def test_refuses_missing_and_empty_arguments(self) -> None:
        for args in ((), ("alpha",), ("", "1.0.0"), ("alpha", ""), ("", ""), ("alpha", "1.0.0", "extra")):
            with self.subTest(args=args):
                self._assert_refused(self._run(*args))

    def test_refuses_traversal_and_malformed_arguments(self) -> None:
        cases = (
            ("../..", "1.0.0"),
            ("alpha", "../.."),
            ("..", ".."),
            ("alpha/../beta", "1.0.0"),
            ("alpha", "1.0.0/../../beta"),
            (str(self.outside), "1.0.0"),
            ("Alpha", "1.0.0"),
            ("alpha", "1.0"),
            ("alpha", "latest"),
            ("alpha", "*"),
            ("*", "1.0.0"),
            ("-rf", "1.0.0"),
            ("alpha", "1.0.0\n"),
        )
        for args in cases:
            with self.subTest(args=args):
                result = self._run(*args)
                self._assert_refused(result)
                self.assertIn("Refusing", result.stderr)

    def test_dry_run_prints_target_and_count_and_deletes_nothing(self) -> None:
        target = self.cache / "alpha" / "1.0.0"
        for args, env in (
            (("--dry-run", "alpha", "1.0.0"), {}),
            (("alpha", "1.0.0"), {"DRY_RUN": "1"}),
            (("alpha", "1.0.0"), {"DRY_RUN": "true"}),
        ):
            with self.subTest(args=args, env=env):
                result = self._run(*args, **env)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(f"would delete {target} (2 files)", result.stdout)
                self.assertEqual(_files(self.base), self.before)

    def test_eviction_removes_only_the_target(self) -> None:
        target = self.cache / "alpha" / "1.0.0"
        result = self._run("alpha", "1.0.0")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(target.exists())
        self.assertEqual(
            _files(self.base),
            [f for f in self.before if "alpha/1.0.0/" not in f],
        )
        # The warning names the target and the consequence.
        self.assertIn("WARNING", result.stderr)
        self.assertIn(f"DELETES {target} (2 files)", result.stderr)

    def test_prerelease_version_is_accepted(self) -> None:
        path = self.cache / "alpha" / "2.0.0-rc.1" / "plugin.json"
        path.parent.mkdir(parents=True)
        path.write_text("x\n", encoding="utf-8")
        result = self._run("alpha", "2.0.0-rc.1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(path.parent.exists())
        self.assertEqual(_files(self.base), self.before)

    def test_absent_version_is_a_no_op(self) -> None:
        result = self._run("alpha", "9.9.9")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("nothing to evict", result.stdout)
        self.assertEqual(_files(self.base), self.before)

    def test_refuses_a_symlinked_version_directory(self) -> None:
        os.symlink(self.outside, self.cache / "alpha" / "3.0.0")
        result = self._run("alpha", "3.0.0")
        self._assert_refused(result)
        self.assertIn("WARNING", result.stderr)
        self.assertIn("Refusing", result.stderr)

    def test_refuses_a_plugin_directory_that_resolves_outside_the_cache(self) -> None:
        elsewhere = self.outside / "gamma" / "1.0.0"
        elsewhere.mkdir(parents=True)
        (elsewhere / "precious.txt").write_text("keep\n", encoding="utf-8")
        os.symlink(self.outside / "gamma", self.cache / "gamma")
        self.before = _files(self.base)
        result = self._run("gamma", "1.0.0")
        self._assert_refused(result)
        self.assertIn("WARNING", result.stderr)
        self.assertIn("DELETES", result.stderr)
        self.assertIn("Refusing", result.stderr)

    def test_refuses_a_plugin_directory_aliased_to_another_plugin(self) -> None:
        os.symlink(self.cache / "beta", self.cache / "delta")
        result = self._run("delta", "1.0.0")
        self._assert_refused(result)

    def test_default_config_dir_is_under_home(self) -> None:
        cache = self.home / ".claude" / "plugins" / "cache" / MARKETPLACE
        self._seed(cache)
        before = _files(self.base)
        result = self._run("alpha", "1.0.0", CLAUDE_CONFIG_DIR="")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((cache / "alpha" / "1.0.0").exists())
        self.assertEqual(
            _files(self.base),
            [f for f in before if "home/.claude/" not in f or "alpha/1.0.0/" not in f],
        )

    def test_works_without_a_realpath_binary(self) -> None:
        # PATH holds only what the script needs, minus realpath, so the
        # python3 fallback is the code path under test.
        bindir = self.base / "bin"
        bindir.mkdir()
        for tool in ("bash", "find", "wc", "tr", "rm"):
            found = shutil.which(tool)
            self.assertIsNotNone(found, f"{tool} is required")
            os.symlink(str(found), bindir / tool)
        wrapper = bindir / "python3"
        wrapper.write_text(f'#!/bin/sh\nexec "{sys.executable}" "$@"\n', encoding="utf-8")
        wrapper.chmod(0o755)
        elsewhere = self.outside / "gamma" / "1.0.0"
        elsewhere.mkdir(parents=True)
        (elsewhere / "precious.txt").write_text("keep\n", encoding="utf-8")
        os.symlink(self.outside / "gamma", self.cache / "gamma")
        self.before = _files(self.base)

        refused = self._run("gamma", "1.0.0", PATH=str(bindir))
        self._assert_refused(refused)
        self.assertIn("Refusing", refused.stderr)

        result = self._run("alpha", "1.0.0", PATH=str(bindir))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.cache / "alpha" / "1.0.0").exists())
        self.assertTrue((self.cache / "alpha" / "1.1.0" / "plugin.json").is_file())


if __name__ == "__main__":
    unittest.main()
