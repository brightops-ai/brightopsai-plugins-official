""".claude/settings.json — what the Bash deny rules refuse, and the hook command.

Claude Code, not this repository, evaluates the deny rules, so the first half
is a model: `matches` implements the matching the permissions documentation
describes (https://code.claude.com/docs/en/permissions, "Wildcard patterns",
read 2026-11-22 against Claude Code 2.1.330):

* a `*` stands for any text, spaces included, and the rule must match the
  whole command;
* a rule with no `*` matches one exact command;
* a rule whose only `*` is a trailing one after a space also matches the
  command with nothing after it (`Bash(ls *)` matches `ls`);
* a trailing `:*` is another spelling of a trailing ` *`.

It does not model compound commands, stripped wrappers, leading variable
assignments or quoting; every command below is a single plain one.

The model is not Claude Code. Every command in REFUSED, ALLOWED, KNOWN_MISSES
and FALSE_POSITIVES was also put to the real matcher, Claude Code 2.1.330
started with these deny rules as its only settings, a local stand-in for the
API that asks for one Bash call, and stand-ins on PATH for git, gh, env,
printenv, cat, claude, codex and gemini, so a command that was not refused ran
a stub and nothing else. The real matcher and the model agreed on every row
of those four lists. REAL_MATCHER_ONLY holds the spellings where they differ:
the real matcher refuses them and the model does not.

The second half runs the registered SessionStart command in a throwaway
repository. Nothing here reads or writes the real git or Claude configuration.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SETTINGS = ROOT / ".claude" / "settings.json"


def bash_rules(settings: dict) -> list[str]:
    """The text inside each `Bash(...)` deny rule."""
    rules = []
    for rule in settings["permissions"]["deny"]:
        if rule.startswith("Bash(") and rule.endswith(")"):
            rules.append(rule[len("Bash(") : -1])
    return rules


def matches(rule: str, command: str) -> bool:
    """Whether one Bash rule body matches one plain command."""
    if rule.endswith(":*"):
        rule = rule[:-2] + " *"
    if "*" not in rule:
        return command == rule
    pattern = ".*".join(re.escape(part) for part in rule.split("*"))
    if re.fullmatch(pattern, command, flags=re.DOTALL):
        return True
    return rule.count("*") == 1 and rule.endswith(" *") and command == rule[:-2]


def refusing(rules: list[str], command: str) -> list[str]:
    return [rule for rule in rules if matches(rule, command)]


# Every spelling the Guardrails table in CLAUDE.md says is refused, and the
# probes recorded when the rules were written. `live` marks the ones run
# against the real matcher for this change.
REFUSED = (
    # No push to main.
    "git push origin main",
    "git push origin main --dry-run",
    "git push --dry-run origin main",
    "git push -u origin main",
    "git -C . push origin main",
    "git -C some/dir push --dry-run origin main --tags",
    "git push origin HEAD:main",
    "git push origin HEAD:main --dry-run",
    "git push origin feature:main",
    "git push origin refs/heads/main",
    "git push --dry-run origin refs/heads/main --tags",
    "git push origin HEAD:refs/heads/main",
    "git push --dry-run origin HEAD:refs/heads/main --tags",
    "git push origin refs/heads/main:refs/heads/main",
    "git push origin +refs/heads/main",
    "git push origin +refs/heads/main --dry-run",
    "git push origin +HEAD:refs/heads/main",
    "git push refs/heads/main",
    "git push refs/heads/main --dry-run",
    # The same words first, with no remote before them. A rule shaped
    # `* <word>` needs something in front; each needs a `<word> *` twin.
    "git push +refs/heads/main",
    "git push +refs/heads/main --dry-run",
    "git push main",
    "git push main --dry-run",
    "git -C . push main",
    "git -C some/dir push main --tags",
    "git push --all",
    "git push origin --all",
    "git push --all origin",
    "git push --mirror",
    "git push origin --mirror",
    # No force push.
    "git push --force",
    "git push --force origin fix/x",
    "git push origin fix/x --force",
    "git push origin --force fix/x",
    "git push -f",
    "git push -f origin fix/x",
    "git push origin fix/x -f",
    "git push origin -f fix/x",
    # No commit that skips the secret scan.
    "git commit --no-verify",
    "git commit --no-verify -m x",
    "git commit -m x --no-verify",
    "git -C . commit --no-verify",
    "git -C . commit -m x --no-verify",
    "git commit -n",
    "git commit -n -m x",
    "git commit -m x -n",
    "git commit -a -n -m x",
    # No agent started with a permission-bypass flag.
    "claude --dangerously-skip-permissions",
    "claude --dangerously-skip-permissions --version",
    "claude --permission-mode bypassPermissions --version",
    "codex --yolo",
    "codex --yolo --version",
    "codex exec --dangerously-bypass-approvals-and-sandbox x",
    "gemini --yolo",
    "gemini --approval-mode=yolo --version",
    "gemini -y",
    "gemini -y --version",
    "gemini --version -y",
    "gemini -p x -y --version",
    # No printing the environment or a token.
    "env",
    "env -0",
    "env --null",
    "printenv",
    "printenv HOME",
    "gh auth token",
    "gh auth token --hostname github.com",
    "gh auth status --show-token",
    "gh auth status --help --show-token",
    "gh auth status --show-token --hostname github.com",
    "gh auth status -t",
    "gh auth status -t --help",
    "gh auth status --help -t",
    "gh auth status --hostname github.com -t",
    "gh auth status --hostname github.com -t --active",
    "gh auth status --hostname git-t -t",
)

# Commands that must stay runnable. The first block is the two false positives
# this file was written for: a boundary is now required before the word.
ALLOWED = (
    "git push origin feature/refs/heads/main",
    "git push --dry-run origin feature/refs/heads/main --tags",
    "git push origin HEAD:feature/refs/heads/main",
    "git push -u origin feature/refs/heads/main",
    "gh auth status --hostname git-t",
    "gh auth status --help --hostname git-t",
    "gh auth status --hostname git-t --active",
    "gh auth status --hostname=git-t",
    # The safe commands the table names, and ordinary neighbours.
    "git push",
    "git push -u origin fix/review-followups-94",
    "git push origin fix/x",
    "git push --force-with-lease origin fix/x",
    "git push origin zz-probe--force",
    "git push origin feature/main",
    "git push origin maintenance",
    "git push origin refs/heads/maintenance",
    "git push origin HEAD:refs/heads/main-backup",
    "git commit",
    "git commit -m x",
    "git commit -F message.txt",
    "gh auth status",
    "gh auth status --active",
    "gh auth status --hostname github.com",
    "env VAR=1 true",
    "claude --version",
    "codex --version",
    "gemini --version",
)


# The "Known misses" list in CLAUDE.md, as commands. None is matched, and the
# list says so; a rule that starts catching one should move it to REFUSED and
# out of the list. Not here: `set` and `export -p`, which no rule could name.
KNOWN_MISSES = (
    # Inside another shell, or with options before the subcommand.
    "bash -c 'git push origin main'",
    "sh -c 'git commit --no-verify'",
    "git -c push.default=current push origin main",
    # Pushes.
    "git push",
    "git push origin +main",
    "git push origin +main --dry-run",
    "git -C . push origin HEAD:main",
    "git -C . push origin refs/heads/main",
    "git -C . push --all",
    "git -C . push --mirror",
    "git -C . push --force origin fix/x",
    "git -C . push -f origin fix/x",
    # Short flags joined to others.
    "git push -fu origin fix/x",
    "git commit -nm x",
    "gh auth status -at",
    "gh auth status -at --help",
    "git -C . commit -n",
    "git -C . commit -n -m x",
    # The environment.
    "env -u NAME true",
    # Environment files under other names.
    "cat .env.qa",
    "cat .envrc",
)

# The "Known false positives" list: refused although harmless.
FALSE_POSITIVES = (
    "git commit -m 'mentions --no-verify in passing'",
    "git commit -m 'flag -n explained'",
    "git push origin fix/contains--all",
    "git push origin fix/contains--mirror-in-name",
    # `main` as the first word after `push` is refused whatever it names.
    "git push main fix/x",
    "git -C . push main fix/x",
)


# Refused by the real matcher (Claude Code 2.1.330) and not by the model: it
# looks past a path in front of the program and past quotes. The permissions
# documentation says a command run by path is not matched, so this is recorded
# as observed, and CLAUDE.md does not promise it.
REAL_MATCHER_ONLY = (
    "/usr/bin/git push origin main",
    "/usr/bin/git commit --no-verify",
    "git push origin 'HEAD:refs/heads/main'",
    "git push origin HEAD:'refs/heads/main'",
)


class TestBashDenyRules(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.settings = json.loads(SETTINGS.read_text(encoding="utf-8"))
        cls.rules = bash_rules(cls.settings)

    def test_the_model_matches_the_documented_examples(self) -> None:
        # The table under "Wildcard patterns", row for row.
        documented = (
            ("npm run *", ("npm run build", "npm run test --watch", "npm run"), ("npm install",)),
            (
                "git log * main",
                ("git log --oneline main", "git log -5 main"),
                ("git log main", "git push origin main"),
            ),
            ("git * main", ("git merge main", "git push origin main"), ("git log",)),
            ("* --version", ("node --version",), ("node -v",)),
            ("ls *", ("ls -la", "ls"), ("lsof",)),
            ("ls*", ("ls -la", "lsof"), ()),
            ("* --help *", ("npm --help x",), ("npm --help",)),
            ("ls:*", ("ls -la", "ls"), ("lsof",)),
            ("npm test", ("npm test",), ("npm test --watch", "npm")),
        )
        for rule, yes, no in documented:
            for command in yes:
                with self.subTest(rule=rule, matches=command):
                    self.assertTrue(matches(rule, command))
            for command in no:
                with self.subTest(rule=rule, does_not_match=command):
                    self.assertFalse(matches(rule, command))

    def test_refused_commands_are_refused(self) -> None:
        for command in REFUSED:
            with self.subTest(command=command):
                self.assertTrue(refusing(self.rules, command), f"no deny rule matches: {command}")

    def test_allowed_commands_are_not_refused(self) -> None:
        for command in ALLOWED:
            with self.subTest(command=command):
                self.assertEqual(refusing(self.rules, command), [])

    def test_known_misses_are_not_matched(self) -> None:
        for command in KNOWN_MISSES:
            with self.subTest(command=command):
                self.assertEqual(refusing(self.rules, command), [])

    def test_the_model_is_narrower_than_the_real_matcher_where_recorded(self) -> None:
        # If the model starts matching one of these, it has grown a rule the
        # real matcher's behaviour was only observed to have: move the row.
        for command in REAL_MATCHER_ONLY:
            with self.subTest(command=command):
                self.assertEqual(refusing(self.rules, command), [])

    def test_known_false_positives_are_refused(self) -> None:
        for command in FALSE_POSITIVES:
            with self.subTest(command=command):
                self.assertTrue(refusing(self.rules, command), f"no deny rule matches: {command}")

    def test_a_word_refused_after_a_remote_is_refused_first_too(self) -> None:
        # `Bash(git push * main)` needs text between `push` and `main`, so the
        # same word straight after `push` slips through unless a rule that
        # starts with it exists. Checked for every word a push rule ends in.
        checked = 0
        for rule in self.rules:
            for lead, start in (("git push * ", "git push "), ("git -C * push * ", "git -C . push ")):
                word = rule[len(lead) :]
                if not rule.startswith(lead) or "*" in word:
                    continue
                checked += 1
                for command in (start + word, start + word + " --dry-run"):
                    with self.subTest(rule=rule, command=command):
                        self.assertTrue(refusing(self.rules, command), f"no deny rule matches: {command}")
        self.assertGreaterEqual(checked, 6)

    def test_no_rule_matches_inside_a_word(self) -> None:
        # A `*` written straight against `refs/heads/main` or `-t` lets the
        # rule match the tail of a longer word. Each such rule needs a
        # boundary first: a space, or the `:` or `+` of a refspec.
        for rule in self.rules:
            with self.subTest(rule=rule):
                self.assertNotRegex(rule, r"\*refs/heads/main")
                self.assertNotRegex(rule, r"\*-t( \*)?$")

    def test_guardrails_table_describes_the_rules_as_shipped(self) -> None:
        text = " ".join((ROOT / "CLAUDE.md").read_text(encoding="utf-8").split())
        for phrase in (
            # What the table says is refused.
            "`main` as its own word, first or after a remote",
            "`refs/heads/main` as its own word, first or after a remote, or straight after a `:`",
            "`+refs/heads/main` as its own word",
            "`-t` as its own word",
            # Known misses.
            "inside `bash -c` or `sh -c`",
            "`gh auth status -at`",
            "`git -C <dir> push` with a refspec",
            # Known false positives.
            "a remote or a directory named `main`",
        ):
            with self.subTest(phrase=phrase):
                self.assertTrue(phrase in text, f"CLAUDE.md (Guardrails) does not say: {phrase}")


class TestSessionStartCommand(unittest.TestCase):
    """The registered command finds the hook from wherever the session starts."""

    def setUp(self) -> None:
        self.git = shutil.which("git")
        self.assertIsNotNone(self.git, "git is required")
        settings = json.loads(SETTINGS.read_text(encoding="utf-8"))
        entries = settings["hooks"]["SessionStart"]
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["matcher"], "startup")
        self.assertEqual(len(entries[0]["hooks"]), 1)
        self.command = entries[0]["hooks"][0]["command"]

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(os.path.realpath(tmp.name))
        self.repo = self.base / "repo"
        self.marker = self.base / "ran.txt"
        home = self.base / "home"
        home.mkdir()
        self.env = {
            "PATH": os.environ["PATH"],
            "HOME": str(home),
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "MARKER": str(self.marker),
        }
        self._project(self.repo, "repo")
        (self.repo / "plugins" / "deep" / "er").mkdir(parents=True)

    def _project(self, root: Path, label: str, repository: bool = True) -> None:
        """A directory with a stand-in hook that records `label` when it runs."""
        (root / ".claude" / "hooks").mkdir(parents=True)
        (root / ".claude" / "hooks" / "install-plugins.sh").write_text(
            f'echo "{label}" >> "$MARKER"\n', encoding="utf-8"
        )
        if repository:
            subprocess.run(
                [str(self.git), "init", "-q"], cwd=root, env=self.env, check=True, capture_output=True
            )

    def _start(self, shell: str, cwd: Path, **env: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [shell, "-c", self.command],
            cwd=cwd,
            env={**self.env, **env},
            capture_output=True,
            text=True,
            check=False,
        )

    def _ran(self) -> list[str]:
        """Which stand-in hooks ran since the last call."""
        if not self.marker.exists():
            return []
        ran = self.marker.read_text(encoding="utf-8").splitlines()
        self.marker.unlink()
        return ran

    def _shells(self) -> list[str]:
        shells = [shell for shell in ("/bin/sh", "sh", "bash") if shutil.which(shell)]
        self.assertTrue(shells)
        return shells

    def test_runs_from_a_subdirectory_without_claude_project_dir(self) -> None:
        for shell in self._shells():
            for sub in ("plugins", "plugins/deep/er", ".claude/hooks"):
                with self.subTest(shell=shell, cwd=sub):
                    result = self._start(shell, self.repo / sub)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(self._ran(), ["repo"], result.stderr)

    def test_runs_from_the_root_without_claude_project_dir(self) -> None:
        for shell in self._shells():
            with self.subTest(shell=shell):
                result = self._start(shell, self.repo)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(self._ran(), ["repo"])
                self.assertEqual(result.stderr, "")

    def test_claude_project_dir_wins_when_set(self) -> None:
        # Started somewhere else entirely, in another repository with a hook
        # of its own: the variable, not the directory, names the project.
        other = self.base / "other"
        self._project(other, "other")
        for shell in self._shells():
            with self.subTest(shell=shell):
                result = self._start(shell, other, CLAUDE_PROJECT_DIR=str(self.repo))
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(self._ran(), ["repo"])

    def test_an_empty_claude_project_dir_falls_back_too(self) -> None:
        result = self._start(self._shells()[0], self.repo / "plugins", CLAUDE_PROJECT_DIR="")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self._ran(), ["repo"])

    def test_a_checkout_whose_name_ends_in_a_newline(self) -> None:
        # A command substitution drops trailing newlines. The root is reached
        # by a relative path, so its absolute path never passes through one.
        odd = self.base / "trailing-newline\n"
        self._project(odd, "newline")
        (odd / "sub" / "dir").mkdir(parents=True)
        for shell in self._shells():
            for cwd in (odd, odd / "sub", odd / "sub" / "dir"):
                with self.subTest(shell=shell, cwd=str(cwd.relative_to(self.base))):
                    result = self._start(shell, cwd)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(self._ran(), ["newline"], result.stderr)
                    self.assertEqual(result.stderr, "")
        with self.subTest(case="named by CLAUDE_PROJECT_DIR"):
            result = self._start(self._shells()[0], self.base, CLAUDE_PROJECT_DIR=str(odd))
            self.assertEqual(self._ran(), ["newline"], result.stderr)

    def test_a_hook_in_the_starting_directory_is_the_one_that_runs(self) -> None:
        # As it was before the fallback existed: a directory inside the
        # checkout that carries the hook itself is launched as its own root.
        nested = self.repo / "snapshot"
        self._project(nested, "snapshot", repository=False)
        for shell in self._shells():
            with self.subTest(shell=shell):
                result = self._start(shell, nested)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(self._ran(), ["snapshot"])

    def test_a_root_launch_needs_neither_git_nor_a_repository(self) -> None:
        plain = self.base / "plain"
        self._project(plain, "plain", repository=False)
        (plain / "sub").mkdir()
        # A PATH with bash on it and no git.
        bindir = self.base / "bin"
        bindir.mkdir()
        os.symlink(str(shutil.which("bash")), bindir / "bash")
        for shell in self._shells():
            for label, env in (
                ("not a repository", {"GIT_CEILING_DIRECTORIES": str(self.base)}),
                ("git not installed", {"PATH": str(bindir)}),
            ):
                with self.subTest(shell=shell, case=label):
                    shell_path = shutil.which(shell) or shell
                    result = self._start(shell_path, plain, **env)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(self._ran(), ["plain"], result.stderr)
                    # And a subdirectory there has no root to find: nothing
                    # runs, and the session still starts.
                    result = self._start(shell_path, plain / "sub", **env)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(self._ran(), [])
                    self.assertEqual(result.stdout, "")
        with self.subTest(case="a repository, git not installed, root launch"):
            result = self._start(str(shutil.which("bash")), self.repo, PATH=str(bindir))
            self.assertEqual(self._ran(), ["repo"], result.stderr)

    def test_never_fails_the_session(self) -> None:
        # Outside any repository there is no hook to find; the session still
        # starts. So does one whose hook exits non-zero.
        nowhere = self.base / "nowhere"
        nowhere.mkdir()
        for shell in self._shells():
            with self.subTest(shell=shell, case="no repository"):
                result = self._start(shell, nowhere, GIT_CEILING_DIRECTORIES=str(self.base))
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(self._ran(), [])
                self.assertEqual(result.stdout, "")
        (self.repo / ".claude" / "hooks" / "install-plugins.sh").write_text("exit 7\n", encoding="utf-8")
        result = self._start(self._shells()[0], self.repo / "plugins")
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
