"""scripts/install-hooks.sh — activates the hooks without displacing anyone's.

The installer writes git config, so every test runs it inside a throwaway
repository with a temp HOME and no global or system git config. This
checkout's own config is never read or written.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INSTALLER = ROOT / "scripts" / "install-hooks.sh"
HOOKS = ROOT / ".githooks"

ACTIVE = "hooks active in this worktree"
LIVE = "the scan is live"


class TestInstallHooks(unittest.TestCase):
    def setUp(self) -> None:
        tools = {name: shutil.which(name) for name in ("git", "bash", "chmod", "cat")}
        for name, found in tools.items():
            self.assertIsNotNone(found, f"{name} is required")
        self.git = str(tools["git"])
        self.bash = str(tools["bash"])

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(os.path.realpath(tmp.name))
        self.repo = self.base / "repo"
        self.bin = self.base / "bin"
        home = self.base / "home"
        for d in (self.repo, self.bin, home):
            d.mkdir()

        # PATH is this directory alone, so whether gitleaks exists is the
        # test's choice. git goes through a wrapper so it still finds its own
        # helper programs.
        (self.bin / "git").write_text(f'#!/bin/sh\nexec "{self.git}" "$@"\n', encoding="utf-8")
        (self.bin / "git").chmod(0o755)
        for name in ("chmod", "cat"):
            os.symlink(str(tools[name]), self.bin / name)

        self.env = {
            "PATH": str(self.bin),
            "HOME": str(home),
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_AUTHOR_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "test@example.invalid",
            "GIT_COMMITTER_NAME": "Test",
            "GIT_COMMITTER_EMAIL": "test@example.invalid",
        }
        self._git("init", "-q")
        (self.repo / "scripts").mkdir()
        shutil.copy(INSTALLER, self.repo / "scripts" / INSTALLER.name)
        shutil.copytree(HOOKS, self.repo / ".githooks")
        self._git("add", "-A")
        self._git("commit", "-q", "-m", "init")

    def _git(self, *args: str, cwd: Path | None = None, **env: str) -> str:
        result = subprocess.run(
            [self.git, *args],
            cwd=cwd or self.repo,
            env={**self.env, **env},
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def _value(self, *scope: str, cwd: Path | None = None, **env: str) -> str | None:
        """core.hooksPath in a scope (default: the effective value), or None."""
        result = subprocess.run(
            [self.git, "config", *scope, "--get", "core.hooksPath"],
            cwd=cwd or self.repo,
            env={**self.env, **env},
            capture_output=True,
            text=True,
            check=False,
        )
        return result.stdout.strip() if result.returncode == 0 else None

    def _install(
        self, *args: str, cwd: Path | None = None, **env: str
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [self.bash, "scripts/install-hooks.sh", *args],
            cwd=cwd or self.repo,
            env={**self.env, **env},
            capture_output=True,
            text=True,
            check=False,
        )

    def _gitleaks_stub(self, body: str) -> None:
        stub = self.bin / "gitleaks"
        stub.write_text("#!/bin/sh\n" + body, encoding="utf-8")
        stub.chmod(0o755)

    # -- activation -------------------------------------------------------

    def test_fresh_clone_is_activated(self) -> None:
        result = self._install()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self._value("--local"), ".githooks")
        self.assertIn(ACTIVE, result.stdout)

    def test_rerun_changes_nothing(self) -> None:
        self.assertEqual(self._install().returncode, 0)
        config = self.repo / ".git" / "config"
        before = (config.read_bytes(), config.stat().st_ino, config.stat().st_mtime_ns)
        for _ in range(2):
            result = self._install()
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(ACTIVE, result.stdout)
        after = (config.read_bytes(), config.stat().st_ino, config.stat().st_mtime_ns)
        self.assertEqual(after, before, "a repeat run rewrote the git config")

    def test_equivalent_spelling_counts_as_active(self) -> None:
        absolute = str(self.repo / ".githooks")
        self._git("config", "core.hooksPath", absolute)
        result = self._install()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(ACTIVE, result.stdout)
        self.assertEqual(self._value("--local"), absolute)

    def test_makes_both_hooks_executable(self) -> None:
        hooks = [self.repo / ".githooks" / name for name in ("pre-commit", "pre-merge-commit")]
        for hook in hooks:
            hook.chmod(0o644)
        self.assertEqual(self._install().returncode, 0)
        for hook in hooks:
            with self.subTest(hook=hook.name):
                self.assertTrue(os.access(hook, os.X_OK))

    def test_linked_worktree_is_activated(self) -> None:
        worktree = self.base / "wt"
        self._git("worktree", "add", "-q", str(worktree), "-b", "wt")
        result = self._install(cwd=worktree)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(ACTIVE, result.stdout)
        self.assertEqual(self._value(cwd=worktree), ".githooks")
        self.assertEqual(self._value(), ".githooks")

    def test_unknown_argument_is_refused(self) -> None:
        for args in (("--bogus",), ("--force", "extra")):
            with self.subTest(args=args):
                result = self._install(*args)
                self.assertEqual(result.returncode, 2)
                self.assertIsNone(self._value())

    # -- never displace someone else's hooks ------------------------------

    def test_existing_value_is_left_alone(self) -> None:
        self._git("config", "core.hooksPath", ".husky")
        result = self._install()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self._value("--local"), ".husky")
        self.assertIn("core.hooksPath is already '.husky'", result.stderr)
        self.assertIn("REPLACES", result.stderr)
        self.assertIn("Refusing", result.stderr)
        self.assertIn("NOT active", result.stderr)
        self.assertIn("--force", result.stderr)
        self.assertNotIn(ACTIVE, result.stdout + result.stderr)

    def test_force_replaces_an_existing_value(self) -> None:
        self._git("config", "core.hooksPath", ".husky")
        result = self._install("--force")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self._value("--local"), ".githooks")
        self.assertIn("replacing core.hooksPath '.husky'", result.stderr)
        self.assertIn(ACTIVE, result.stdout)

    def test_global_value_is_left_alone(self) -> None:
        elsewhere = self.base / "global-hooks"
        elsewhere.mkdir()
        global_config = self.base / "gitconfig"
        global_config.write_text(f"[core]\n\thooksPath = {elsewhere}\n", encoding="utf-8")
        before = global_config.read_bytes()
        env = {"GIT_CONFIG_GLOBAL": str(global_config)}
        result = self._install(**env)
        self.assertEqual(result.returncode, 1)
        self.assertIn(f"core.hooksPath is already '{elsewhere}'", result.stderr)
        self.assertIsNone(self._value("--local", **env))
        self.assertEqual(global_config.read_bytes(), before)
        self.assertNotIn(ACTIVE, result.stdout + result.stderr)

    def test_worktree_override_is_left_alone(self) -> None:
        self._git("config", "extensions.worktreeConfig", "true")
        self._git("config", "--worktree", "core.hooksPath", "other-hooks")
        result = self._install()
        self.assertEqual(result.returncode, 1)
        self.assertIn("core.hooksPath is already 'other-hooks'", result.stderr)
        self.assertIsNone(self._value("--local"))
        self.assertEqual(self._value(), "other-hooks")
        self.assertNotIn(ACTIVE, result.stdout + result.stderr)

    def test_activation_is_reported_only_when_effective(self) -> None:
        # --force writes the repository config, but a worktree-level value
        # still wins. The installer must report what git will really use.
        self._git("config", "extensions.worktreeConfig", "true")
        self._git("config", "--worktree", "core.hooksPath", "other-hooks")
        result = self._install("--force")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self._value(), "other-hooks")
        self.assertIn("effective value in this worktree is 'other-hooks'", result.stderr)
        self.assertIn("SKIP", result.stderr)
        self.assertIn("Not active", result.stderr)
        self.assertNotIn(ACTIVE, result.stdout + result.stderr)
        self.assertNotIn(LIVE, result.stdout + result.stderr)

    # -- what it says about gitleaks --------------------------------------

    def test_missing_gitleaks_is_a_warning_not_a_live_scan(self) -> None:
        result = self._install()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("WARNING: gitleaks is not on PATH", result.stderr)
        self.assertIn("BLOCK", result.stderr)
        self.assertIn("brew install gitleaks", result.stderr)
        self.assertNotIn(LIVE, result.stdout + result.stderr)

    def test_working_gitleaks_is_reported_live(self) -> None:
        self._gitleaks_stub('[ "$1" = "version" ] && echo 9.9.9\n')
        result = self._install()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("gitleaks 9.9.9 found", result.stdout)
        self.assertIn(LIVE, result.stdout)

    def test_broken_gitleaks_is_not_reported_live(self) -> None:
        for label, body in (("fails", "echo 9.9.9\nexit 1\n"), ("silent", "exit 0\n")):
            with self.subTest(gitleaks=label):
                self._gitleaks_stub(body)
                result = self._install()
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("`gitleaks version` failed", result.stderr)
                self.assertIn("BLOCK", result.stderr)
                self.assertNotIn(LIVE, result.stdout + result.stderr)

    def test_says_what_no_hook_covers(self) -> None:
        result = self._install()
        self.assertIn("rebase, cherry-pick and revert run no commit hook", result.stdout)
        self.assertIn("CI", result.stdout)
        self.assertNotIn("every commit", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
