"""Which commit-creating git commands run the commit hooks, and what the docs say.

The guidance used to say that rebase, cherry-pick and revert run no commit
hook. That is true of rebase and of a cherry-pick or revert that applies
cleanly. After a conflict, `git cherry-pick --continue` and
`git revert --continue` run `pre-commit`.

Two halves:

* a fixture that runs each command in a throwaway repository with recording
  hooks, so the statement is checked against the git that is installed;
* a check that no tracked guidance still carries the unqualified sentence.

The repository is built under a temp directory with a temp HOME and no global
or system git config. This checkout's own config is never read or written.
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

# Every file that tells a reader what the hooks cover.
GUIDANCE = (
    "CLAUDE.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "CHANGELOG.md",
    "scripts/install-hooks.sh",
)


class TestCommitHookCoverage(unittest.TestCase):
    def setUp(self) -> None:
        git = shutil.which("git")
        self.assertIsNotNone(git, "git is required")
        self.git = str(git)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(os.path.realpath(tmp.name))
        self.repo = self.base / "repo"
        self.log = self.base / "hooks.log"
        home = self.base / "home"
        home.mkdir()
        self.env = {
            "PATH": os.environ["PATH"],
            "HOME": str(home),
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_AUTHOR_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "test@example.invalid",
            "GIT_COMMITTER_NAME": "Test",
            "GIT_COMMITTER_EMAIL": "test@example.invalid",
            "GIT_EDITOR": "true",
            "GIT_SEQUENCE_EDITOR": "true",
            "HOOK_LOG": str(self.log),
        }

    # -- fixture ------------------------------------------------------------

    def _git(self, *args: str, ok: bool = True, **env: str) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [self.git, *args],
            cwd=self.repo,
            env={**self.env, **env},
            capture_output=True,
            text=True,
            check=False,
        )
        if ok:
            self.assertEqual(result.returncode, 0, f"git {' '.join(args)}\n{result.stdout}{result.stderr}")
        return result

    def _write(self, name: str, text: str) -> None:
        (self.repo / name).write_text(text + "\n", encoding="utf-8")

    def _history(self) -> None:
        """main and side both change f (a conflict); side also adds g2 (none).

        The history is made with the hooks switched off, so the log holds only
        what the command under test ran.
        """
        if self.repo.exists():
            shutil.rmtree(self.repo)
        self.repo.mkdir()
        self._git("init", "-q")
        self._git("checkout", "-q", "-b", "main")
        hooks = self.repo / "hooks"
        hooks.mkdir()
        for name in ("pre-commit", "pre-merge-commit"):
            (hooks / name).write_text(f'#!/bin/sh\necho {name} >> "$HOOK_LOG"\n', encoding="utf-8")
            (hooks / name).chmod(0o755)

        def commit(message: str) -> None:
            self._git("add", "-A")
            self._git("-c", "core.hooksPath=/dev/null", "commit", "-q", "-m", message)

        self._write("f", "base")
        commit("base")
        self._git("checkout", "-q", "-b", "side")
        self._write("f", "side")
        commit("side changes f")
        self._write("g2", "side")
        commit("side adds g2")
        self._git("checkout", "-q", "main")
        self._write("f", "main")
        commit("main changes f")
        self._git("config", "core.hooksPath", "hooks")
        self.log.write_text("", encoding="utf-8")

    def _ran(self) -> list[str]:
        return self.log.read_text(encoding="utf-8").split()

    def _resolve(self) -> None:
        self._write("f", "resolved")
        self._git("add", "f")

    def _subject(self) -> str:
        return self._git("log", "-1", "--format=%s").stdout.strip()

    # -- the baseline: the hooks do run on an ordinary commit -----------------

    def test_commit_and_merge_run_the_hooks(self) -> None:
        self._history()
        self._write("new", "x")
        self._git("add", "new")
        self._git("commit", "-q", "-m", "plain")
        self.assertEqual(self._ran(), ["pre-commit"])

        self._history()
        self._git("checkout", "-q", "-b", "other", "main~1")
        self._write("other", "x")
        self._git("add", "other")
        self._git("-c", "core.hooksPath=/dev/null", "commit", "-q", "-m", "other")
        self._git("merge", "--no-edit", "main")
        self.assertEqual(self._ran(), ["pre-merge-commit"])

    # -- no hook ---------------------------------------------------------------

    def test_clean_cherry_pick_and_revert_run_no_hook(self) -> None:
        self._history()
        self._git("cherry-pick", "side")
        self.assertEqual(self._subject(), "side adds g2")
        self.assertEqual(self._ran(), [], "a clean cherry-pick ran a hook")

        self._history()
        self._git("revert", "--no-edit", "HEAD")
        self.assertTrue(self._subject().startswith("Revert "))
        self.assertEqual(self._ran(), [], "a clean revert ran a hook")

    def test_rebase_runs_no_hook_with_or_without_a_conflict(self) -> None:
        self._history()
        self._git("checkout", "-q", "-b", "clean", "main~1")
        self._write("c", "x")
        self._git("add", "c")
        self._git("-c", "core.hooksPath=/dev/null", "commit", "-q", "-m", "clean")
        self._git("rebase", "main")
        self.assertEqual(self._ran(), [], "a clean rebase ran a hook")

        for backend in ("--merge", "--apply"):
            with self.subTest(backend=backend):
                self._history()
                self._git("checkout", "-q", "side")
                stopped = self._git("rebase", backend, "main", ok=False)
                self.assertNotEqual(stopped.returncode, 0, "the rebase was expected to stop on f")
                self._resolve()
                self._git("rebase", "--continue")
                self.assertEqual(self._subject(), "side adds g2")
                self.assertEqual(self._ran(), [], "rebase --continue ran a hook")

    # -- pre-commit does run ---------------------------------------------------

    def test_cherry_pick_continue_after_a_conflict_runs_pre_commit(self) -> None:
        self._history()
        stopped = self._git("cherry-pick", "side~1", ok=False)
        self.assertNotEqual(stopped.returncode, 0, "the cherry-pick was expected to stop on f")
        self.assertEqual(self._ran(), [])
        self._resolve()
        self._git("cherry-pick", "--continue")
        self.assertEqual(self._subject(), "side changes f")
        self.assertEqual(self._ran(), ["pre-commit"])

    def test_revert_continue_after_a_conflict_runs_pre_commit(self) -> None:
        self._history()
        self._write("f", "main again")
        self._git("-c", "core.hooksPath=/dev/null", "commit", "-q", "-am", "main changes f again")
        stopped = self._git("revert", "--no-edit", "HEAD~1", ok=False)
        self.assertNotEqual(stopped.returncode, 0, "the revert was expected to stop on f")
        self.assertEqual(self._ran(), [])
        self._resolve()
        self._git("revert", "--continue")
        self.assertTrue(self._subject().startswith("Revert "))
        self.assertEqual(self._ran(), ["pre-commit"])

    def test_interactive_reword_runs_pre_commit(self) -> None:
        # The todo list is edited by a script, so no editor opens.
        editor = self.base / "reword-first"
        editor.write_text(
            "#!/bin/sh\n"
            'first=1\nwhile IFS= read -r line; do\n'
            '  if [ "$first" = 1 ]; then first=0; line="reword ${line#pick }"; fi\n'
            '  printf "%s\\n" "$line"\n'
            'done < "$1" > "$1.new" && mv "$1.new" "$1"\n',
            encoding="utf-8",
        )
        editor.chmod(0o755)
        self._history()
        self._git("checkout", "-q", "side")
        self._git("rebase", "-i", "main~1", GIT_SEQUENCE_EDITOR=str(editor))
        self.assertEqual(self._ran(), ["pre-commit"])

    # -- the guidance ----------------------------------------------------------

    def test_guidance_no_longer_says_all_three_run_no_hook(self) -> None:
        # The unqualified sentence, in any of the forms it was written in:
        # the three commands named together, then a blanket "no hook".
        named_together = re.compile(
            r"rebase`?,\s+(?:`git )?cherry-pick`?\s+and\s+(?:`git )?revert`?\s+"
            r"(?:still\s+)?(?:run\s+no|create\s+commits\s+without)",
            re.IGNORECASE,
        )
        for name in GUIDANCE:
            with self.subTest(file=name):
                text = (ROOT / name).read_text(encoding="utf-8")
                flat = " ".join(line.lstrip("# ").strip() for line in text.splitlines())
                self.assertIsNone(
                    named_together.search(flat),
                    f"{name} still says rebase, cherry-pick and revert all run no hook",
                )

    def test_guidance_names_the_continue_exception(self) -> None:
        for name in ("CLAUDE.md", "CONTRIBUTING.md", "SECURITY.md", "scripts/install-hooks.sh"):
            with self.subTest(file=name):
                text = (ROOT / name).read_text(encoding="utf-8")
                flat = " ".join(line.lstrip("# ").strip() for line in text.splitlines())
                self.assertIn("git cherry-pick --continue", flat)
                self.assertIn("git revert --continue", flat)
                self.assertRegex(flat, r"run(?:s)? (?:it|`pre-commit`)")


if __name__ == "__main__":
    unittest.main()
