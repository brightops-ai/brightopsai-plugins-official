"""Local secret-scan gate: the hooks fail closed, and say how to proceed.

Each test commits in a throwaway repository with a scrubbed environment: a
temp HOME, no global or system git config, and a PATH holding only what the
hook needs. The hooks are switched on with `git -c core.hooksPath=...`, so no
git config file is written anywhere, including in this checkout.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HOOKS = ROOT / ".githooks"
HOOK = HOOKS / "pre-commit"
MERGE_HOOK = HOOKS / "pre-merge-commit"
INSTALLER = ROOT / "scripts" / "install-hooks.sh"
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
GITIGNORE = ROOT / ".gitignore"

ESCAPE_HATCH = "ALLOW_UNSCANNED_PUBLIC_COMMIT"
FINDING_STATUS = "42"
SCAN_ARGS = f"protect --staged --redact --config .gitleaks.toml --exit-code {FINDING_STATUS}"

FINDING_TEXT = "Something staged matches"
INCOMPLETE_TEXT = "the gitleaks scan did not complete"

# Records its arguments, then exits with the status the test asked for.
GITLEAKS_STUB = """#!/bin/sh
printf '%s\\n' "$*" > "$GITLEAKS_STUB_LOG"
exit "${GITLEAKS_STUB_EXIT:-0}"
"""

# The Linux install commands, as printed: from the opening subshell to the
# closing parenthesis after the install step.
_INSTALL_BLOCK = re.compile(
    r'^ {4}(\(tmp="\$\(mktemp -d\)".*?~/\.local/bin/gitleaks\))$',
    re.MULTILINE | re.DOTALL,
)


def _install_block(text: str) -> str:
    match = _INSTALL_BLOCK.search(text)
    assert match is not None, "no Linux install block found"
    return match.group(1)


def _wrapper(path: Path, target: str) -> None:
    """An executable that runs `target`, for a PATH that must not hold more."""
    path.write_text(f'#!/bin/sh\nexec "{target}" "$@"\n', encoding="utf-8")
    path.chmod(0o755)


class _TempRepo(unittest.TestCase):
    def setUp(self) -> None:
        git = shutil.which("git")
        cat = shutil.which("cat")
        self.assertIsNotNone(git, "git is required for the hook tests")
        self.assertIsNotNone(cat, "cat is required for the hook tests")
        self.git = str(git)

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        self.repo = self.base / "repo"
        self.bin = self.base / "bin"
        home = self.base / "home"
        for d in (self.repo, self.bin, home):
            d.mkdir()

        # PATH is this directory alone: the hook's own needs and nothing else,
        # so a gitleaks installed on the machine is not found.
        os.symlink(str(cat), self.bin / "cat")
        self.stub_log = self.base / "gitleaks-args"
        self.env = {
            "PATH": str(self.bin),
            "HOME": str(home),
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_AUTHOR_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "test@example.invalid",
            "GIT_COMMITTER_NAME": "Test",
            "GIT_COMMITTER_EMAIL": "test@example.invalid",
            "GITLEAKS_STUB_LOG": str(self.stub_log),
        }
        self._git("init", "-q")

    def _git(self, *args: str, **env: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [self.git, *args],
            cwd=self.repo,
            env={**self.env, **env},
            capture_output=True,
            text=True,
            check=False,
        )

    def _ok(self, *args: str) -> str:
        result = self._git(*args)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def _has_commit(self) -> bool:
        return self._git("rev-parse", "--verify", "-q", "HEAD").returncode == 0

    def _install_hooks(self) -> None:
        hooks = self.repo / ".githooks"
        hooks.mkdir()
        for hook in (HOOK, MERGE_HOOK):
            shutil.copy(hook, hooks / hook.name)
            (hooks / hook.name).chmod(0o755)

    def _install_gitleaks_stub(self) -> None:
        stub = self.bin / "gitleaks"
        stub.write_text(GITLEAKS_STUB, encoding="utf-8")
        stub.chmod(0o755)

    def _stub_args(self) -> str:
        return self.stub_log.read_text(encoding="utf-8").strip()


class TestPreCommitHook(_TempRepo):
    def setUp(self) -> None:
        super().setUp()
        self._install_hooks()
        (self.repo / "note.txt").write_text("hello\n", encoding="utf-8")
        self.assertEqual(self._git("add", "note.txt").returncode, 0)

    def _commit(self, **env: str) -> subprocess.CompletedProcess[str]:
        return self._git(
            "-c", "core.hooksPath=.githooks", "commit", "-q", "-m", "test", **env
        )

    def test_missing_gitleaks_blocks_the_commit(self) -> None:
        result = self._commit()
        self.assertNotEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self._has_commit(), "the commit landed unscanned")
        # Names the hazard and the consequence, then how to proceed.
        self.assertIn("pre-commit: BLOCKED", result.stderr)
        self.assertIn("WARNING: gitleaks is not on PATH", result.stderr)
        self.assertIn("PUBLIC", result.stderr)
        self.assertIn("unscanned. Refusing.", result.stderr)
        self.assertIn("brew install gitleaks", result.stderr)
        self.assertIn(_install_block(HOOK.read_text(encoding="utf-8")), result.stderr)
        # How to check the result, and what to do when it is not found.
        self.assertIn("command -v gitleaks", result.stderr)
        self.assertIn('export PATH="$HOME/.local/bin:$PATH"', result.stderr)

    def test_escape_hatch_allows_the_commit_and_says_so(self) -> None:
        result = self._commit(**{ESCAPE_HATCH: "1"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self._has_commit())
        self.assertIn("WARNING", result.stderr)
        self.assertIn(f"{ESCAPE_HATCH}=1", result.stderr)
        self.assertIn("UNSCANNED", result.stderr)

    def test_escape_hatch_needs_the_exact_value(self) -> None:
        # Values a numeric or truthy comparison would accept are refused.
        for value in ("", "0", "true", "yes", "01", " 1", "1 ", "+1", "1.0"):
            with self.subTest(value=value):
                result = self._commit(**{ESCAPE_HATCH: value})
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(self._has_commit())
                self.assertIn("BLOCKED", result.stderr)

    def test_clean_scan_allows_the_commit(self) -> None:
        self._install_gitleaks_stub()
        result = self._commit(GITLEAKS_STUB_EXIT="0")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self._has_commit())
        self.assertEqual(self._stub_args(), SCAN_ARGS)

    def test_finding_blocks_even_with_the_escape_hatch(self) -> None:
        # The hatch covers a missing scanner. It never overrides a finding.
        self._install_gitleaks_stub()
        for hatch in ({}, {ESCAPE_HATCH: "1"}):
            with self.subTest(hatch=hatch):
                result = self._commit(GITLEAKS_STUB_EXIT=FINDING_STATUS, **hatch)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(self._has_commit())
                self.assertIn("pre-commit: BLOCKED", result.stderr)
                self.assertIn("PUBLIC", result.stderr)
                self.assertIn(FINDING_TEXT, result.stderr)
                self.assertNotIn(INCOMPLETE_TEXT, result.stderr)

    def test_scanner_failure_is_not_reported_as_a_finding(self) -> None:
        # Any status other than the finding status means the scan did not
        # complete. It blocks, says so, and the hatch does not apply.
        self._install_gitleaks_stub()
        for status in ("1", "2", "126", "137"):
            for hatch in ({}, {ESCAPE_HATCH: "1"}):
                with self.subTest(status=status, hatch=hatch):
                    result = self._commit(GITLEAKS_STUB_EXIT=status, **hatch)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertFalse(self._has_commit())
                    self.assertIn("pre-commit: BLOCKED", result.stderr)
                    self.assertIn(f"{INCOMPLETE_TEXT} (gitleaks exited {status})", result.stderr)
                    self.assertIn(".gitleaks.toml is missing, unreadable or malformed", result.stderr)
                    self.assertIn("unscanned. Refusing.", result.stderr)
                    self.assertNotIn(FINDING_TEXT, result.stderr)


class TestPreMergeCommitHook(_TempRepo):
    """`git merge` runs pre-merge-commit, not pre-commit."""

    def setUp(self) -> None:
        super().setUp()
        self._install_hooks()
        # History is built with no hooks active: one commit, then one more on
        # each of two branches, so the merge needs a real merge commit.
        self._commit_file("base.txt")
        self.main = self._ok("symbolic-ref", "--short", "HEAD")
        self._ok("checkout", "-q", "-b", "side")
        self._commit_file("side.txt")
        self._ok("checkout", "-q", self.main)
        self._commit_file("main.txt")
        self.head = self._ok("rev-parse", "HEAD")

    def _commit_file(self, name: str) -> None:
        (self.repo / name).write_text(name + "\n", encoding="utf-8")
        self._ok("add", name)
        self._ok("commit", "-q", "-m", name)

    def _merge(self, **env: str) -> subprocess.CompletedProcess[str]:
        return self._git(
            "-c", "core.hooksPath=.githooks", "merge", "--no-ff", "-m", "merge", "side", **env
        )

    def _merged(self) -> bool:
        return self._ok("rev-list", "--count", "--merges", "HEAD") != "0"

    def test_tracked_hooks_are_executable(self) -> None:
        # A hook without its exec bit is "no hook" to git, not an error.
        for hook in (HOOK, MERGE_HOOK):
            with self.subTest(hook=hook.name):
                self.assertTrue(os.access(hook, os.X_OK), f"{hook.name} is not executable")

    def test_merge_hook_shares_the_gate(self) -> None:
        text = MERGE_HOOK.read_text(encoding="utf-8")
        self.assertIn('exec "$dir/pre-commit" pre-merge-commit', text)
        self.assertNotIn("gitleaks protect", text)

    def test_missing_gitleaks_blocks_the_merge_commit(self) -> None:
        result = self._merge()
        self.assertNotEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self._ok("rev-parse", "HEAD"), self.head)
        self.assertFalse(self._merged(), "the merge commit landed unscanned")
        self.assertIn("pre-merge-commit: BLOCKED", result.stderr)
        self.assertIn("WARNING: gitleaks is not on PATH", result.stderr)

    def test_escape_hatch_allows_the_merge_and_says_so(self) -> None:
        result = self._merge(**{ESCAPE_HATCH: "1"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self._merged())
        self.assertIn("pre-merge-commit: WARNING", result.stderr)
        self.assertIn("UNSCANNED", result.stderr)

    def test_clean_scan_allows_the_merge(self) -> None:
        self._install_gitleaks_stub()
        result = self._merge(GITLEAKS_STUB_EXIT="0")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self._merged())
        self.assertEqual(self._stub_args(), SCAN_ARGS)

    def test_finding_and_scanner_failure_block_the_merge(self) -> None:
        self._install_gitleaks_stub()
        for status, expected in ((FINDING_STATUS, FINDING_TEXT), ("1", INCOMPLETE_TEXT)):
            with self.subTest(status=status):
                result = self._merge(GITLEAKS_STUB_EXIT=status, **{ESCAPE_HATCH: "1"})
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(self._merged())
                self.assertIn("pre-merge-commit: BLOCKED", result.stderr)
                self.assertIn(expected, result.stderr)
                self._git("merge", "--abort")

    def test_merge_hook_fails_closed_without_the_gate(self) -> None:
        (self.repo / ".githooks" / "pre-commit").unlink()
        self._install_gitleaks_stub()
        result = self._merge(GITLEAKS_STUB_EXIT="0")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self._merged())


@unittest.skipUnless(shutil.which("gitleaks"), "gitleaks is not installed")
class TestRealGitleaksContract(_TempRepo):
    """The exit statuses the hook relies on, against the real binary.

    A stub cannot show that gitleaks really exits 42 for a finding and with
    something else for a broken config. The rule and the matching text are
    invented here, so no secret-shaped string exists anywhere.
    """

    CONFIG = "title = \"test\"\n\n[[rules]]\nid = \"canary\"\nregex = '''CANARY_[0-9]{6}'''\n"

    def setUp(self) -> None:
        super().setUp()
        self._install_hooks()
        _wrapper(self.bin / "gitleaks", str(shutil.which("gitleaks")))
        _wrapper(self.bin / "git", self.git)  # gitleaks shells out to git

    def _commit(self, body: str, config: str | None) -> subprocess.CompletedProcess[str]:
        (self.repo / "note.txt").write_text(body, encoding="utf-8")
        if config is not None:
            (self.repo / ".gitleaks.toml").write_text(config, encoding="utf-8")
        self._ok("add", "note.txt")
        return self._git("-c", "core.hooksPath=.githooks", "commit", "-q", "-m", "test")

    def test_clean_content_commits(self) -> None:
        result = self._commit("nothing to see\n", self.CONFIG)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self._has_commit())

    def test_finding_is_reported_as_a_finding(self) -> None:
        result = self._commit("CANARY_" + "123456\n", self.CONFIG)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self._has_commit())
        self.assertIn(FINDING_TEXT, result.stderr)
        self.assertNotIn(INCOMPLETE_TEXT, result.stderr)

    def test_missing_or_malformed_config_is_a_scanner_failure(self) -> None:
        for label, config in (("missing", None), ("malformed", "not [ toml\n")):
            with self.subTest(config=label):
                result = self._commit("nothing to see\n", config)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(self._has_commit())
                self.assertIn(INCOMPLETE_TEXT, result.stderr)
                self.assertNotIn(FINDING_TEXT, result.stderr)


class TestInstallAdvice(unittest.TestCase):
    """What the hook and the installer print is the likeliest next command."""

    def setUp(self) -> None:
        self.texts = {
            path.name: path.read_text(encoding="utf-8") for path in (HOOK, INSTALLER)
        }

    def test_hooks_are_valid_posix_sh(self) -> None:
        for hook in (HOOK, MERGE_HOOK):
            with self.subTest(hook=hook.name):
                result = subprocess.run(
                    ["sh", "-n", str(hook)], capture_output=True, text=True, check=False
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                text = hook.read_text(encoding="utf-8")
                self.assertTrue(text.startswith("#!/bin/sh\n"))
                self.assertNotIn("pipefail", text)

    def test_no_piped_installer_and_no_bypass_advice(self) -> None:
        for name, text in self.texts.items():
            with self.subTest(file=name):
                self.assertIsNone(re.search(r"\|\s*(ba)?sh\b", text))
                self.assertNotIn("/master/", text)
                self.assertNotIn("--no-verify", text)

    def test_pinned_install_matches_ci(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        version = re.search(r'GITLEAKS_VERSION: "([0-9.]+)"', workflow)
        digest = re.search(r'GITLEAKS_SHA256: "([0-9a-f]{64})"', workflow)
        self.assertIsNotNone(version, "ci.yml no longer pins GITLEAKS_VERSION")
        self.assertIsNotNone(digest, "ci.yml no longer pins GITLEAKS_SHA256")
        assert version is not None and digest is not None
        archive = f"gitleaks_{version.group(1)}_linux_x64.tar.gz"
        for name, text in self.texts.items():
            with self.subTest(file=name):
                block = _install_block(text)
                self.assertIn(f"/download/v{version.group(1)}/{archive}", block)
                self.assertIn(f"{digest.group(1)}  {archive}", block)
                self.assertIn("sha256sum -c", block)
                self.assertIn("brew install gitleaks", text)
                self.assertIn("command -v gitleaks", text)

    def test_hook_and_installer_print_the_same_commands(self) -> None:
        self.assertEqual(
            _install_block(self.texts[HOOK.name]),
            _install_block(self.texts[INSTALLER.name]),
        )


class TestPrintedLinuxInstall(unittest.TestCase):
    """Runs the printed Linux commands with stub curl, sha256sum and tar.

    Nothing is downloaded and the real home directory is never the target:
    HOME and TMPDIR are temp directories and PATH holds only the stubs plus
    mktemp, mkdir and install.
    """

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        self.bin = base / "bin"
        self.home = base / "home"
        self.cwd = base / "cwd"
        self.tmpdir = base / "tmp"
        self.log = base / "log"
        for d in (self.bin, self.home, self.cwd, self.tmpdir):
            d.mkdir()
        for tool in ("mktemp", "mkdir", "install", "cat"):
            found = shutil.which(tool)
            self.assertIsNotNone(found, f"{tool} is required")
            os.symlink(str(found), self.bin / tool)
        stubs = {
            # Creates the file the URL names, as a download would.
            "curl": 'echo "curl $*" >> "$STUB_LOG"\n'
            '[ "${CURL_EXIT:-0}" = "0" ] || exit "$CURL_EXIT"\n'
            'for arg in "$@"; do last="$arg"; done\n: > "${last##*/}"\n',
            "sha256sum": 'echo "sha256sum $* <- $(cat)" >> "$STUB_LOG"\nexit "${SHA_EXIT:-0}"\n',
            "tar": 'echo "tar $*" >> "$STUB_LOG"\necho fake > gitleaks\n',
        }
        for name, body in stubs.items():
            path = self.bin / name
            path.write_text("#!/bin/sh\n" + body, encoding="utf-8")
            path.chmod(0o755)
        self.block = _install_block(HOOK.read_text(encoding="utf-8"))
        self.installed = self.home / ".local" / "bin" / "gitleaks"

    def _run(self, **env: str) -> subprocess.CompletedProcess[str]:
        sh = shutil.which("sh")
        self.assertIsNotNone(sh)
        return subprocess.run(
            [str(sh), "-c", self.block],
            cwd=self.cwd,
            env={
                "PATH": str(self.bin),
                "HOME": str(self.home),
                "TMPDIR": str(self.tmpdir),
                "STUB_LOG": str(self.log),
                **env,
            },
            capture_output=True,
            text=True,
            check=False,
        )

    def _log(self) -> str:
        return self.log.read_text(encoding="utf-8") if self.log.exists() else ""

    def test_good_checksum_installs_and_leaves_the_current_directory_clean(self) -> None:
        result = self._run()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(os.access(self.installed, os.X_OK))
        self.assertEqual(list(self.cwd.iterdir()), [], "files were left in the current directory")
        log = self._log()
        self.assertRegex(log, r"curl -fsSLO https://github\.com/gitleaks/gitleaks/releases/download/v")
        self.assertRegex(log, r"sha256sum -c - <- [0-9a-f]{64}  gitleaks_[0-9.]+_linux_x64\.tar\.gz")
        self.assertIn("tar -xzf", log)

    def test_failed_checksum_stops_before_extract_and_install(self) -> None:
        result = self._run(SHA_EXIT="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("sha256sum -c -", self._log())
        self.assertNotIn("tar ", self._log(), "extraction ran after a failed checksum")
        self.assertFalse(self.installed.exists(), "installed after a failed checksum")
        self.assertEqual(list(self.cwd.iterdir()), [])

    def test_failed_download_stops_everything(self) -> None:
        result = self._run(CURL_EXIT="22")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("sha256sum", self._log())
        self.assertNotIn("tar ", self._log())
        self.assertFalse(self.installed.exists())


class TestGitignore(_TempRepo):
    def setUp(self) -> None:
        super().setUp()
        shutil.copy(GITIGNORE, self.repo / ".gitignore")

    def _ignored(self, path: str) -> bool:
        result = self._git("check-ignore", "-q", path)
        self.assertIn(result.returncode, (0, 1), result.stderr)
        return result.returncode == 0

    def test_credential_files_are_ignored(self) -> None:
        for path in (".env", ".env.local", "app/.env.production", "tls/server.pem", "id.key"):
            with self.subTest(path=path):
                self.assertTrue(self._ignored(path))

    def test_env_example_stays_trackable(self) -> None:
        self.assertFalse(self._ignored(".env.example"))
        self.assertFalse(self._ignored("app/.env.example"))


if __name__ == "__main__":
    unittest.main()
