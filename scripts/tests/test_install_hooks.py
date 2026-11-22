"""scripts/install-hooks.sh — activates the hooks without displacing anyone's.

The installer writes git config, so every test runs it inside a throwaway
repository with a temp HOME and no global or system git config. This
checkout's own config is never read or written.
"""

from __future__ import annotations

import os
import shutil
import stat
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
        # A worktree-level value outranks the repository config --force
        # writes. The installer must report what git will really use.
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

    def test_force_changes_nothing_under_a_linked_worktree_override(self) -> None:
        # The repository config is shared by every worktree. Writing it for a
        # worktree whose own value still wins would change the others and
        # leave this one as it was.
        worktree = self.base / "wt"
        self._git("worktree", "add", "-q", str(worktree), "-b", "wt")
        self._git("config", "extensions.worktreeConfig", "true")
        self._git("config", "--worktree", "core.hooksPath", "other-hooks", cwd=worktree)
        shared = self.repo / ".git" / "config"
        before = shared.read_bytes()

        result = self._install("--force", cwd=worktree)

        self.assertEqual(result.returncode, 1)
        self.assertEqual(shared.read_bytes(), before, "--force rewrote the shared config")
        self.assertIsNone(self._value("--local"))
        self.assertIsNone(self._value(), "the main worktree's hooks path changed")
        self.assertEqual(self._value(cwd=worktree), "other-hooks")
        self.assertIn("effective value in this worktree is 'other-hooks'", result.stderr)
        self.assertIn("config.worktree", result.stderr)
        self.assertIn("Nothing was changed", result.stderr)
        self.assertIn("git config --worktree --unset-all core.hooksPath", result.stderr)
        self.assertNotIn("replacing core.hooksPath", result.stderr)
        self.assertNotIn(ACTIVE, result.stdout + result.stderr)

    def test_force_changes_nothing_under_an_environment_override(self) -> None:
        env = {
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "core.hooksPath",
            "GIT_CONFIG_VALUE_0": "env-hooks",
        }
        self.assertEqual(self._value(**env), "env-hooks", "this git ignores GIT_CONFIG_COUNT")
        result = self._install("--force", **env)
        self.assertEqual(result.returncode, 1)
        self.assertIsNone(self._value("--local"))
        self.assertIn("effective value in this worktree is 'env-hooks'", result.stderr)
        self.assertIn("the command line or the environment", result.stderr)
        self.assertIn("Nothing was changed", result.stderr)
        self.assertNotIn(ACTIVE, result.stdout + result.stderr)

    def _git_without_show_scope(self) -> None:
        """Make the git on PATH behave like one older than 2.26."""
        (self.bin / "git").write_text(
            "#!/bin/sh\n"
            'for arg in "$@"; do\n'
            '  [ "$arg" = "--show-scope" ] && { echo "error: unknown option" >&2; exit 129; }\n'
            "done\n"
            f'exec "{self.git}" "$@"\n',
            encoding="utf-8",
        )

    def _snapshot(self, *extra: Path) -> tuple[list[bytes], dict[str, int]]:
        """The repository config, any other config file named, and the hook modes."""
        files = [self.repo / ".git" / "config", *extra]
        return [f.read_bytes() for f in files], self._modes()

    def _plain_hooks(self, mode: int = 0o644) -> None:
        for hook in (self.repo / ".githooks").iterdir():
            hook.chmod(mode)

    def test_force_refuses_when_git_cannot_name_the_scope(self) -> None:
        # git before 2.26 has no --show-scope, so the installer cannot tell
        # whether a write to the repository config would take effect. It used
        # to write and then report the failure; it now refuses first.
        self._git_without_show_scope()
        self._git("config", "extensions.worktreeConfig", "true")
        self._git("config", "--worktree", "core.hooksPath", "other-hooks")
        self._plain_hooks()
        before = self._snapshot()
        result = self._install("--force")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self._snapshot(), before)
        self.assertEqual(self._value(), "other-hooks")
        self.assertIn("effective value in this worktree is 'other-hooks'", result.stderr)
        self.assertIn("a level this git cannot name", result.stderr)
        self.assertIn("Not active", result.stderr)
        self.assertIn("Nothing was changed", result.stderr)
        self.assertNotIn(ACTIVE, result.stdout + result.stderr)

    def test_old_git_still_activates_a_fresh_clone(self) -> None:
        # With nothing set there is no scope to ask about.
        self._git_without_show_scope()
        result = self._install()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self._value("--local"), ".githooks")
        self.assertIn(ACTIVE, result.stdout)

    def test_force_refuses_an_empty_override_before_writing(self) -> None:
        # The decision goes by where the winning value comes from, not by
        # whether it is empty. An empty value outranks the repository config
        # like any other, and makes git run no hooks at all.
        worktree = self.base / "wt"
        self._git("worktree", "add", "-q", str(worktree), "-b", "wt")
        self._git("config", "extensions.worktreeConfig", "true")
        self._git("config", "--local", "core.hooksPath", "shared")
        self._git("config", "--worktree", "core.hooksPath", "", cwd=worktree)
        shared = self.repo / ".git" / "config"
        hooks = sorted((worktree / ".githooks").iterdir())
        for hook in hooks:
            hook.chmod(0o644)
        before = shared.read_bytes()

        result = self._install("--force", cwd=worktree)

        self.assertEqual(result.returncode, 1)
        self.assertEqual(shared.read_bytes(), before, "--force rewrote the shared config")
        self.assertEqual([stat.S_IMODE(h.stat().st_mode) for h in hooks], [0o644, 0o644])
        self.assertEqual(self._value("--local"), "shared")
        self.assertEqual(self._value(cwd=worktree), "")
        self.assertIn("effective value in this worktree is ''", result.stderr)
        self.assertIn("an empty value", result.stderr)
        self.assertIn("config.worktree", result.stderr)
        self.assertIn("Nothing was changed", result.stderr)
        self.assertNotIn("replacing core.hooksPath", result.stderr)
        self.assertNotIn(ACTIVE, result.stdout + result.stderr)

    def test_force_refuses_an_empty_environment_override_before_writing(self) -> None:
        env = {
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "core.hooksPath",
            "GIT_CONFIG_VALUE_0": "",
        }
        self.assertEqual(self._value(**env), "", "this git ignores GIT_CONFIG_COUNT")
        self._plain_hooks()
        before = self._snapshot()
        result = self._install("--force", **env)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self._snapshot(), before)
        self.assertIn("effective value in this worktree is ''", result.stderr)
        self.assertIn("the command line or the environment", result.stderr)
        self.assertIn("Nothing was changed", result.stderr)
        self.assertNotIn(ACTIVE, result.stdout + result.stderr)

    def test_an_empty_value_is_someone_elses_setting_too(self) -> None:
        # core.hooksPath set to nothing switches hooks off on purpose. It is
        # not "unset", and is not displaced without --force.
        self._git("config", "core.hooksPath", "")
        self._plain_hooks()
        before = self._snapshot()
        result = self._install()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self._snapshot(), before)
        self.assertIn("core.hooksPath is already ''", result.stderr)
        self.assertIn("Refusing", result.stderr)
        self.assertNotIn(ACTIVE, result.stdout + result.stderr)

        result = self._install("--force")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            self._git("config", "--local", "--get-all", "core.hooksPath").split("\n"), [".githooks"]
        )
        self.assertIn(ACTIVE, result.stdout)

    def test_force_refuses_a_value_an_included_file_sets(self) -> None:
        # --force edits the repository config and nothing else. A value that
        # arrives through include.path is not there to replace, and replacing
        # the direct one beside it would change the config and still fail.
        included = self.base / "included.gitconfig"
        for label, direct, body, winner in (
            ("include wins", "old", "[core]\n\thooksPath = other\n", "other"),
            ("include wins with an empty value", "old", "[core]\n\thooksPath =\n", ""),
            ("include only", None, "[core]\n\thooksPath = other\n", "other"),
        ):
            with self.subTest(case=label):
                if self._value("--local") is not None:
                    self._git("config", "--unset-all", "core.hooksPath")
                if "include.path" in self._git("config", "--local", "--list"):
                    self._git("config", "--unset-all", "include.path")
                if direct is not None:
                    self._git("config", "core.hooksPath", direct)
                included.write_text(body, encoding="utf-8")
                self._git("config", "include.path", str(included))
                self.assertEqual(self._value(), winner)
                self._plain_hooks()
                before = self._snapshot(included)

                result = self._install("--force")

                self.assertEqual(result.returncode, 1)
                self.assertEqual(self._snapshot(included), before)
                self.assertEqual(self._value(), winner)
                self.assertIn("a file the repository config includes", result.stderr)
                self.assertIn("Nothing was changed", result.stderr)
                self.assertNotIn("replacing core.hooksPath", result.stderr)
                self.assertNotIn(ACTIVE, result.stdout + result.stderr)

    def test_force_overrides_a_global_value(self) -> None:
        # A global value is outranked by the repository config, so here the
        # write is worth making. The global file is not touched.
        elsewhere = self.base / "global-hooks"
        elsewhere.mkdir()
        global_config = self.base / "gitconfig"
        global_config.write_text(f"[core]\n\thooksPath = {elsewhere}\n", encoding="utf-8")
        before = global_config.read_bytes()
        env = {"GIT_CONFIG_GLOBAL": str(global_config)}
        result = self._install("--force", **env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self._value("--local", **env), ".githooks")
        self.assertEqual(self._value(**env), ".githooks")
        self.assertEqual(global_config.read_bytes(), before)
        self.assertIn(ACTIVE, result.stdout)

    # -- an unsuccessful run leaves things as they were ---------------------

    def test_a_config_write_that_fails_changes_nothing(self) -> None:
        # Another git process holds the config lock. The modes were already
        # changed by then; they must not outlive the failure.
        for mode in (0o644, 0o600, 0o654):
            with self.subTest(mode=oct(mode)):
                self._plain_hooks(mode)
                lock = self.repo / ".git" / "config.lock"
                lock.touch()
                before = self._snapshot()
                result = self._install()
                lock.unlink()
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertEqual(self._snapshot(), before, "a failed run left changes behind")
                self.assertIn("could not write core.hooksPath", result.stderr)
                self.assertIn("SKIP", result.stderr)
                self.assertIn("Nothing was changed", result.stderr)
                self.assertNotIn(ACTIVE, result.stdout + result.stderr)

    def _git_reporting_another_hooks_dir(self) -> None:
        """git that answers `rev-parse --git-path hooks` with another directory.

        It stands for an override the checks before the write did not foresee:
        the config is written, and git still looks somewhere else.
        """
        (self.bin / "git").write_text(
            "#!/bin/sh\n"
            'if [ "$1 $2 $3" = "rev-parse --git-path hooks" ]; then echo elsewhere; exit 0; fi\n'
            f'exec "{self.git}" "$@"\n',
            encoding="utf-8",
        )

    def test_a_write_that_does_not_take_effect_is_undone(self) -> None:
        self._git_reporting_another_hooks_dir()
        self._plain_hooks()
        before = self._snapshot()
        result = self._install()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self._snapshot(), before, "a failed run left changes behind")
        self.assertIsNone(self._value("--local"))
        self.assertIn("git looks", result.stderr)
        self.assertIn("for hooks in 'elsewhere'", result.stderr)
        self.assertIn("SKIP", result.stderr)
        self.assertIn("Not active", result.stderr)
        self.assertIn("was undone", result.stderr)
        self.assertNotIn(ACTIVE, result.stdout + result.stderr)

    def test_a_forced_write_that_does_not_take_effect_puts_the_values_back(self) -> None:
        self._git_reporting_another_hooks_dir()
        values = [".husky", "", "other hooks"]
        for value in values:
            self._git("config", "--add", "core.hooksPath", value)
        self._plain_hooks()
        modes = self._modes()
        result = self._install("--force")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(
            self._git("config", "--local", "--get-all", "core.hooksPath").split("\n"), values
        )
        self.assertEqual(self._modes(), modes)
        self.assertIn("was undone", result.stderr)
        self.assertNotIn(ACTIVE, result.stdout + result.stderr)

    # -- what `git config` says is checked against what git does -------------

    def test_git_config_variable_cannot_fake_an_active_report(self) -> None:
        # GIT_CONFIG makes `git config` read one file and nothing else. No
        # other git command honours it, so a commit made in this environment
        # runs the hooks the repository config names.
        decoy = self.base / "decoy.gitconfig"
        decoy.write_text("[core]\n\thooksPath = .githooks\n", encoding="utf-8")
        hidden = self.repo / "hidden"
        hidden.mkdir()
        self._git("config", "core.hooksPath", "hidden")
        self._plain_hooks()
        before = self._snapshot(decoy)
        env = {"GIT_CONFIG": str(decoy)}

        result = self._install(**env)

        self.assertEqual(self._git("rev-parse", "--git-path", "hooks", **env), "hidden")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertEqual(self._snapshot(decoy), before)
        self.assertIn("core.hooksPath is already 'hidden'", result.stderr)
        self.assertNotIn(ACTIVE, result.stdout + result.stderr)
        self.assertNotIn(LIVE, result.stdout + result.stderr)

    def test_git_config_variable_does_not_redirect_the_write(self) -> None:
        # The other direction: the decoy says another directory, the
        # repository says nothing. The repository config is what gets written.
        decoy = self.base / "decoy.gitconfig"
        decoy.write_text("[core]\n\thooksPath = other\n", encoding="utf-8")
        before = decoy.read_bytes()
        env = {"GIT_CONFIG": str(decoy)}
        result = self._install(**env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(decoy.read_bytes(), before)
        self.assertEqual(self._value("--local"), ".githooks")
        self.assertEqual(self._git("rev-parse", "--git-path", "hooks", **env), ".githooks")
        self.assertIn(ACTIVE, result.stdout)

    # -- where it runs --------------------------------------------------------

    def test_a_checkout_whose_name_ends_in_a_newline(self) -> None:
        # A command substitution drops trailing newlines, so the checkout root
        # is reached by a relative path and never printed and read back.
        odd = self.base / "trailing-newline\n"
        shutil.copytree(self.repo, odd)
        (odd / "sub" / "dir").mkdir(parents=True)
        for cwd in (odd, odd / "sub" / "dir"):
            with self.subTest(cwd=cwd.name):
                if self._value("--local", cwd=odd) is not None:
                    self._git("config", "--unset-all", "core.hooksPath", cwd=odd)
                result = subprocess.run(
                    [self.bash, str(odd / "scripts" / "install-hooks.sh")],
                    cwd=cwd,
                    env=self.env,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(self._value("--local", cwd=odd), ".githooks")
                self.assertIn(ACTIVE, result.stdout)
                self.assertIsNone(self._value("--local"), "the other checkout was written to")

    def test_outside_a_work_tree_is_a_plain_refusal(self) -> None:
        nowhere = self.base / "nowhere"
        nowhere.mkdir()
        result = subprocess.run(
            [self.bash, str(self.repo / "scripts" / "install-hooks.sh")],
            cwd=nowhere,
            env={**self.env, "GIT_CEILING_DIRECTORIES": str(self.base)},
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("not inside a git work tree", result.stderr)
        self.assertNotIn(ACTIVE, result.stdout + result.stderr)

    def test_force_replaces_several_local_values(self) -> None:
        for value in (".husky", "other-hooks"):
            self._git("config", "--add", "core.hooksPath", value)
        self.assertEqual(
            self._git("config", "--local", "--get-all", "core.hooksPath").split(),
            [".husky", "other-hooks"],
        )
        refused = self._install()
        self.assertEqual(refused.returncode, 1)
        self.assertIn("core.hooksPath is already 'other-hooks'", refused.stderr)

        result = self._install("--force")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            self._git("config", "--local", "--get-all", "core.hooksPath").split(), [".githooks"]
        )
        self.assertIn(ACTIVE, result.stdout)

    # -- a refusal changes nothing ----------------------------------------

    def _modes(self) -> dict[str, int]:
        return {
            hook.name: stat.S_IMODE(hook.stat().st_mode)
            for hook in sorted((self.repo / ".githooks").iterdir())
        }

    def test_a_refusal_leaves_the_hook_modes_alone(self) -> None:
        for hook in (self.repo / ".githooks").iterdir():
            hook.chmod(0o644)
        before = self._modes()
        self.assertEqual(set(before.values()), {0o644})

        self._git("config", "core.hooksPath", ".husky")
        result = self._install()
        self.assertEqual(result.returncode, 1)
        self.assertIn("Nothing was changed", result.stderr)
        self.assertEqual(self._modes(), before, "a refused run changed file modes")

        self._git("config", "--unset-all", "core.hooksPath")
        self._git("config", "extensions.worktreeConfig", "true")
        self._git("config", "--worktree", "core.hooksPath", "other-hooks")
        result = self._install("--force")
        self.assertEqual(result.returncode, 1)
        self.assertIn("Nothing was changed", result.stderr)
        self.assertEqual(self._modes(), before, "a refused --force run changed file modes")

    # -- the hook files themselves ----------------------------------------

    def test_missing_hook_files_are_not_reported_active(self) -> None:
        self._gitleaks_stub('[ "$1" = "version" ] && echo 9.9.9\n')
        names = ("pre-commit", "pre-merge-commit")
        for label, removed in (("pre-commit", names[:1]), ("pre-merge-commit", names[1:]), ("both", names)):
            for preset in (False, True):
                with self.subTest(missing=label, hooks_path_already_set=preset):
                    shutil.rmtree(self.repo / ".githooks")
                    shutil.copytree(HOOKS, self.repo / ".githooks")
                    for name in removed:
                        (self.repo / ".githooks" / name).unlink()
                    if self._value("--local") is not None:
                        self._git("config", "--unset-all", "core.hooksPath")
                    if preset:
                        self._git("config", "core.hooksPath", ".githooks")
                    result = self._install()
                    said = result.stdout + result.stderr
                    self.assertEqual(result.returncode, 1, said)
                    self.assertNotIn(ACTIVE, said)
                    self.assertNotIn(LIVE, said)
                    self.assertIn("WARNING: missing hook file(s):", result.stderr)
                    for name in removed:
                        self.assertIn(f".githooks/{name}", result.stderr)
                    self.assertIn("SKIP", result.stderr)
                    self.assertIn("Not active", result.stderr)
                    self.assertEqual(self._value("--local"), ".githooks" if preset else None)

    def test_a_hook_that_stays_non_executable_is_not_reported_active(self) -> None:
        # chmod that changes nothing stands in for a tree where modes cannot
        # be set (a read-only checkout, a filesystem without them).
        self._gitleaks_stub('[ "$1" = "version" ] && echo 9.9.9\n')
        (self.bin / "chmod").unlink()
        (self.bin / "chmod").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        os.chmod(self.bin / "chmod", 0o755)
        (self.repo / ".githooks" / "pre-commit").chmod(0o644)
        result = self._install()
        said = result.stdout + result.stderr
        self.assertEqual(result.returncode, 1, said)
        self.assertNotIn(ACTIVE, said)
        self.assertNotIn(LIVE, said)
        self.assertIn("not executable", result.stderr)
        self.assertIn(".githooks/pre-commit", result.stderr)
        self.assertNotIn(".githooks/pre-merge-commit", result.stderr)
        self.assertIn("SKIP", result.stderr)
        self.assertIsNone(self._value("--local"))

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
        # Which of these commits git runs pre-commit for depends on how they
        # are made, so the installer says the cautious thing and no more.
        self.assertIn(
            "a commit made by rebase, cherry-pick or revert may not have been scanned",
            result.stdout,
        )
        self.assertIn("git runs pre-commit for only some of them", result.stdout)
        self.assertNotIn("rebase, cherry-pick and revert run no commit hook", result.stdout)
        self.assertNotIn("rebase runs no commit hook", result.stdout)
        self.assertIn("CI", result.stdout)
        self.assertNotIn("every commit", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
