"""Local secret-scan gate: the pre-commit hook fails closed, and says how to proceed.

Each test commits in a throwaway repository with a scrubbed environment: a
temp HOME, no global or system git config, and a PATH holding only what the
hook needs. The hook is switched on with `git -c core.hooksPath=...`, so no git
config file is written anywhere, including in this checkout.
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
HOOK = ROOT / ".githooks" / "pre-commit"
INSTALLER = ROOT / "scripts" / "install-hooks.sh"
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
GITIGNORE = ROOT / ".gitignore"

ESCAPE_HATCH = "ALLOW_UNSCANNED_PUBLIC_COMMIT"

# Records its arguments, then exits with the status the test asked for.
GITLEAKS_STUB = """#!/bin/sh
printf '%s\\n' "$*" > "$GITLEAKS_STUB_LOG"
exit "${GITLEAKS_STUB_EXIT:-0}"
"""


class _TempRepo(unittest.TestCase):
    def setUp(self) -> None:
        git = shutil.which("git")
        cat = shutil.which("cat")
        self.assertIsNotNone(git, "git is required for the hook tests")
        self.assertIsNotNone(cat, "cat is required for the hook tests")
        self.git = str(git)

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        self.repo = base / "repo"
        self.bin = base / "bin"
        home = base / "home"
        for d in (self.repo, self.bin, home):
            d.mkdir()

        # PATH is this directory alone: the hook's own needs and nothing else,
        # so a gitleaks installed on the machine is not found.
        os.symlink(str(cat), self.bin / "cat")
        self.stub_log = base / "gitleaks-args"
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

    def _has_commit(self) -> bool:
        return self._git("rev-parse", "--verify", "-q", "HEAD").returncode == 0


class TestPreCommitHook(_TempRepo):
    def setUp(self) -> None:
        super().setUp()
        hooks = self.repo / ".githooks"
        hooks.mkdir()
        shutil.copy(HOOK, hooks / "pre-commit")
        (hooks / "pre-commit").chmod(0o755)
        (self.repo / "note.txt").write_text("hello\n", encoding="utf-8")
        self.assertEqual(self._git("add", "note.txt").returncode, 0)

    def _commit(self, **env: str) -> subprocess.CompletedProcess[str]:
        return self._git(
            "-c", "core.hooksPath=.githooks", "commit", "-q", "-m", "test", **env
        )

    def _install_gitleaks_stub(self) -> None:
        stub = self.bin / "gitleaks"
        stub.write_text(GITLEAKS_STUB, encoding="utf-8")
        stub.chmod(0o755)

    def test_missing_gitleaks_blocks_the_commit(self) -> None:
        result = self._commit()
        self.assertNotEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self._has_commit(), "the commit landed unscanned")
        # Names the hazard and the consequence, then how to proceed.
        self.assertIn("BLOCKED", result.stderr)
        self.assertIn("WARNING: gitleaks is not on PATH", result.stderr)
        self.assertIn("PUBLIC", result.stderr)
        self.assertIn("unscanned. Refusing.", result.stderr)
        self.assertIn("brew install gitleaks", result.stderr)
        self.assertIn("sha256sum -c", result.stderr)

    def test_escape_hatch_allows_the_commit_and_says_so(self) -> None:
        result = self._commit(**{ESCAPE_HATCH: "1"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self._has_commit())
        self.assertIn("WARNING", result.stderr)
        self.assertIn(f"{ESCAPE_HATCH}=1", result.stderr)
        self.assertIn("UNSCANNED", result.stderr)

    def test_escape_hatch_needs_the_exact_value(self) -> None:
        for value in ("", "0", "true", "yes"):
            with self.subTest(value=value):
                result = self._commit(**{ESCAPE_HATCH: value})
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(self._has_commit())

    def test_clean_scan_allows_the_commit(self) -> None:
        self._install_gitleaks_stub()
        result = self._commit(GITLEAKS_STUB_EXIT="0")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self._has_commit())
        self.assertEqual(
            self.stub_log.read_text(encoding="utf-8").strip(),
            "protect --staged --redact --config .gitleaks.toml",
        )

    def test_finding_blocks_even_with_the_escape_hatch(self) -> None:
        # The hatch covers a missing scanner. It never overrides a finding.
        self._install_gitleaks_stub()
        result = self._commit(GITLEAKS_STUB_EXIT="1", **{ESCAPE_HATCH: "1"})
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self._has_commit())
        self.assertIn("BLOCKED", result.stderr)
        self.assertIn("PUBLIC", result.stderr)


class TestInstallAdvice(unittest.TestCase):
    """What the hook and the installer print is the likeliest next command."""

    def setUp(self) -> None:
        self.texts = {
            path.name: path.read_text(encoding="utf-8") for path in (HOOK, INSTALLER)
        }

    def test_hook_is_valid_posix_sh(self) -> None:
        result = subprocess.run(
            ["sh", "-n", str(HOOK)], capture_output=True, text=True, check=False
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.texts[HOOK.name].startswith("#!/bin/sh\n"))
        self.assertNotIn("pipefail", self.texts[HOOK.name])

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
                self.assertIn(f"/download/v{version.group(1)}/{archive}", text)
                self.assertIn(f"{digest.group(1)}  {archive}", text)
                self.assertIn("sha256sum -c", text)
                self.assertIn("brew install gitleaks", text)


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
