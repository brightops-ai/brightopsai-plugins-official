"""Which commit-creating git commands run the commit hooks, and what the docs say.

The guidance used to say that rebase, cherry-pick and revert run no commit
hook. Git runs `pre-commit` for some of the commits those commands make and
not for others, so the guidance now says the cautious thing (assume such a
commit was not scanned; CI is the scan that covers it) and lists what was
observed.

Two halves:

* a fixture that runs each command in a throwaway repository with recording
  hooks, so every case the guidance lists is checked against the git that is
  installed;
* checks that the guidance makes the cautious statement, lists the cases, and
  no longer carries a blanket "runs no hook" sentence.

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

    def test_rebase_picks_and_continue_run_no_hook(self) -> None:
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

    def test_edit_flag_on_a_clean_cherry_pick_or_revert_runs_no_hook(self) -> None:
        self._history()
        self._git("cherry-pick", "--edit", "side")
        self.assertEqual(self._subject(), "side adds g2")
        self.assertEqual(self._ran(), [], "cherry-pick --edit ran a hook")

        self._history()
        self._git("revert", "--edit", "HEAD")
        self.assertTrue(self._subject().startswith("Revert "))
        self.assertEqual(self._ran(), [], "revert --edit ran a hook")

    def _todo_editor(self, name: str, *, line: int | None = None, old: str, new: str) -> str:
        """A sequence editor that rewrites the todo list, so no editor opens.

        Replaces `old` with `new` at the start of todo line `line` (counted
        from 0), or wherever a line starts with it when `line` is None.
        """
        editor = self.base / name
        which = '[ "$n" = %d ] && ' % line if line is not None else ""
        editor.write_text(
            "#!/bin/sh\n"
            "n=0\n"
            'while IFS= read -r todo; do\n'
            f'  {which}case "$todo" in "{old}"*) todo="{new}${{todo#"{old}"}}" ;; esac\n'
            '  printf "%s\\n" "$todo"\n'
            "  n=$((n + 1))\n"
            'done < "$1" > "$1.new" && mv "$1.new" "$1"\n',
            encoding="utf-8",
        )
        editor.chmod(0o755)
        return str(editor)

    def test_squash_and_fixup_run_no_hook(self) -> None:
        for label, new in (("squash", "squash "), ("fixup -c", "fixup -c ")):
            with self.subTest(todo=label):
                editor = self._todo_editor(f"todo-{label.split()[0]}", line=1, old="pick ", new=new)
                self._history()
                self._git("checkout", "-q", "side")
                self._git("rebase", "-i", "main~1", GIT_SEQUENCE_EDITOR=editor)
                self.assertEqual(self._git("rev-list", "--count", "main~1..HEAD").stdout.strip(), "1")
                self.assertEqual(self._ran(), [], f"{label} ran a hook")

    def _merged_history(self) -> None:
        """main with a clean merge of a topic branch on top, for a rebase that keeps merges."""
        self._history()
        quiet = ("-c", "core.hooksPath=/dev/null")
        self._git("checkout", "-q", "-b", "topic", "main~1")
        self._write("t", "topic")
        self._git("add", "t")
        self._git(*quiet, "commit", "-q", "-m", "topic adds t")
        self._git("checkout", "-q", "main")
        self._git(*quiet, "merge", "--no-ff", "-q", "-m", "merge topic", "topic")
        self.log.write_text("", encoding="utf-8")

    def test_a_rebased_merge_runs_pre_commit_only_when_its_message_is_edited(self) -> None:
        # `merge -C` re-creates the merge commit with its message as it was;
        # `merge -c` opens the message for editing, and that commit is made
        # the way `git commit` makes one.
        for todo, ran in (("merge -C", []), ("merge -c", ["pre-commit"])):
            with self.subTest(todo=todo):
                editor = self._todo_editor("todo-merge", old="merge -C", new=todo)
                self._merged_history()
                self._git(
                    "rebase", "-i", "--force-rebase", "--rebase-merges", "HEAD~1",
                    GIT_SEQUENCE_EDITOR=editor,
                )
                self.assertEqual(self._subject(), "merge topic")
                self.assertEqual(self._git("rev-list", "--count", "--merges", "main~1..HEAD").stdout.strip(), "1")
                self.assertEqual(self._ran(), ran)

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
        editor = self._todo_editor("todo-reword", line=0, old="pick ", new="reword ")
        self._history()
        self._git("checkout", "-q", "side")
        self._git("rebase", "-i", "main~1", GIT_SEQUENCE_EDITOR=editor)
        self.assertEqual(self._ran(), ["pre-commit"])

    # -- what the CI scan can and cannot see ------------------------------------

    @unittest.skipUnless(shutil.which("gitleaks"), "gitleaks is not installed")
    def test_a_tree_scan_does_not_see_a_value_added_and_removed(self) -> None:
        # CI runs `gitleaks detect --no-git`. The guidance says that is a scan
        # of files, not of commits; this is the difference, with a rule and a
        # marker made up here so nothing credential-shaped is written down.
        marker = "FIXTURE" + "_MARKER_" + "0042"
        rules = self.base / "rules.toml"
        rules.write_text(
            '[[rules]]\nid = "fixture-marker"\ndescription = "fixture"\nregex = \'\'\'FIXTURE_MARKER_[0-9]+\'\'\'\n',
            encoding="utf-8",
        )
        self._history()
        quiet = ("-c", "core.hooksPath=/dev/null")
        self._write("notes", marker)
        self._git("add", "notes")
        self._git(*quiet, "commit", "-q", "-m", "add a marker")

        def scan(*mode: str) -> int:
            return subprocess.run(
                [str(shutil.which("gitleaks")), "detect", *mode, "--config", str(rules), "--redact", "--no-banner"],
                cwd=self.repo,
                env=self.env,
                capture_output=True,
                text=True,
                check=False,
            ).returncode

        self.assertEqual(scan("--no-git"), 1, "the tree scan missed a marker that is in the tree")
        self._write("notes", "nothing here")
        self._git("add", "notes")
        self._git(*quiet, "commit", "-q", "-m", "remove the marker")
        self.assertEqual(scan("--no-git"), 0, "the tree scan found a marker that is no longer in the tree")
        self.assertEqual(scan(), 1, "a history scan did not find the marker in an earlier commit")

    def test_guidance_does_not_say_ci_covers_what_the_hook_missed(self) -> None:
        overclaims = (
            re.compile(r"scan\s+that\s+covers", re.IGNORECASE),
            re.compile(r"\bbackstop\b", re.IGNORECASE),
            re.compile(r"CI\s+is\s+the\s+only\s+scan", re.IGNORECASE),
            re.compile(r"so\s+a\s+skipped\s+hook\s+is\s+caught\s+before\s+merge", re.IGNORECASE),
        )
        for name in GUIDANCE:
            flat = self._flat(name)
            for pattern in overclaims:
                with self.subTest(file=name, pattern=pattern.pattern):
                    found = pattern.search(flat)
                    self.assertIsNone(found, f"{name} says: ...{flat[found.start() - 60 : found.end() + 40] if found else ''}...")
        for name in ("CLAUDE.md", "CONTRIBUTING.md", "SECURITY.md"):
            flat = self._flat(name)
            for phrase in (
                "`gitleaks detect --no-git`",
                "the files in the tree it checks out, not history",
                "a commit added and a later commit removed",
            ):
                with self.subTest(file=name, phrase=phrase):
                    self.assertTrue(phrase in flat, f"{name} does not say: {phrase}")
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        self.assertIn("gitleaks detect --no-git", workflow, "the docs describe a scan the workflow no longer runs")

    # -- the guidance ----------------------------------------------------------

    @staticmethod
    def _flat(name: str) -> str:
        text = (ROOT / name).read_text(encoding="utf-8")
        return " ".join(line.lstrip("# ").strip() for line in text.splitlines())

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
                self.assertIsNone(
                    named_together.search(self._flat(name)),
                    f"{name} still says rebase, cherry-pick and revert all run no hook",
                )

    def test_guidance_makes_no_blanket_claim_about_rebase(self) -> None:
        # A rebase runs pre-commit for a `reword` and for a `merge -c`, so no
        # sentence may say that rebase as such runs no hook, or that reword is
        # the one exception.
        blanket = (
            re.compile(r"rebase`?\s+runs\s+no\s+(?:commit\s+)?hook", re.IGNORECASE),
            re.compile(r"rebase`?\s+creates\s+commits\s+without\s+running", re.IGNORECASE),
            re.compile(r"rebase`?,\s+and\s+a\s+`git cherry-pick`[^.]*still\s+run\s+no\s+hook", re.IGNORECASE),
            re.compile(r"the\s+one\s+exception\s+is", re.IGNORECASE),
            re.compile(r"the\s+only\s+rebase\s+commit\s+a\s+hook\s+sees", re.IGNORECASE),
        )
        for name in GUIDANCE:
            flat = self._flat(name)
            for pattern in blanket:
                with self.subTest(file=name, pattern=pattern.pattern):
                    found = pattern.search(flat)
                    self.assertIsNone(found, f"{name} says: ...{flat[found.start() - 40 : found.end() + 40] if found else ''}...")

    def test_guidance_says_the_cautious_thing(self) -> None:
        for name in ("CLAUDE.md", "CONTRIBUTING.md", "SECURITY.md"):
            flat = self._flat(name)
            for phrase in (
                # The statement to act on.
                "Assume a commit made by `git rebase`, `git cherry-pick` or `git revert` was not scanned",
                # What was observed, each pinned by a test above.
                "git cherry-pick --continue",
                "git revert --continue",
                "`reword`",
                "`merge -c`",
                "git rebase --continue",
                "git 2.56.1",
            ):
                with self.subTest(file=name, phrase=phrase):
                    self.assertTrue(phrase in flat, f"{name} does not say: {phrase}")
        with self.subTest(file="scripts/install-hooks.sh"):
            flat = self._flat("scripts/install-hooks.sh")
            self.assertIn("a commit made by rebase, cherry-pick or revert may not have been scanned", flat)
            self.assertIn("git runs pre-commit for only some of them", flat)


if __name__ == "__main__":
    unittest.main()
