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

It does not model compound commands, stripped wrappers or leading variable
assignments; every command below is a single plain one. The rows marked
"live" in REFUSED and ALLOWED were also run against the real matcher in a
Claude Code 2.1.330 session with these rules loaded, and agreed with the
model. The real matcher refuses at least one spelling the model does not (a
refspec in quotes, `'HEAD:refs/heads/main'`), so an ALLOWED row that is not
marked live is the model's answer only.

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
    "git push origin refs/heads/main",  # live
    "git push --dry-run origin refs/heads/main --tags",
    "git push origin HEAD:refs/heads/main",  # live
    "git push --dry-run origin HEAD:refs/heads/main --tags",
    "git push origin refs/heads/main:refs/heads/main",
    "git push origin +refs/heads/main",  # live
    "git push origin +refs/heads/main --dry-run",
    "git push origin +HEAD:refs/heads/main",
    "git push refs/heads/main",  # live
    "git push refs/heads/main --dry-run",
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
    "gh auth status -t --help",  # live
    "gh auth status --help -t",  # live
    "gh auth status --hostname github.com -t",
    "gh auth status --hostname github.com -t --active",
    "gh auth status --hostname git-t -t",
)

# Commands that must stay runnable. The first block is the two false positives
# this file was written for: a boundary is now required before the word.
ALLOWED = (
    "git push origin feature/refs/heads/main",  # live
    "git push --dry-run origin feature/refs/heads/main --tags",
    "git push origin HEAD:feature/refs/heads/main",  # live
    "git push -u origin feature/refs/heads/main",
    "gh auth status --hostname git-t",
    "gh auth status --help --hostname git-t",  # live
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
        self.assertIn("`refs/heads/main` as its own word or straight after a `:` or `+`", text)
        self.assertIn("`-t` as its own word", text)
        self.assertIn("`gh auth status -at`", text)


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
        (self.repo / ".claude" / "hooks").mkdir(parents=True)
        (self.repo / "plugins" / "deep" / "er").mkdir(parents=True)
        home.mkdir()
        # A stand-in for the hook: it records where it was found.
        (self.repo / ".claude" / "hooks" / "install-plugins.sh").write_text(
            'cd "$(dirname "$0")/../.." && pwd -P >> "$MARKER"\n', encoding="utf-8"
        )
        self.env = {
            "PATH": os.environ["PATH"],
            "HOME": str(home),
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "MARKER": str(self.marker),
        }
        subprocess.run(
            [str(self.git), "init", "-q"], cwd=self.repo, env=self.env, check=True, capture_output=True
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

    def _found(self) -> list[str]:
        if not self.marker.exists():
            return []
        found = self.marker.read_text(encoding="utf-8").split("\n")[:-1]
        self.marker.unlink()
        return found

    def _shells(self) -> list[str]:
        shells = [shell for shell in ("sh", "bash") if shutil.which(shell)]
        self.assertTrue(shells)
        return shells

    def test_runs_from_a_subdirectory_without_claude_project_dir(self) -> None:
        for shell in self._shells():
            for sub in ("plugins", "plugins/deep/er", ".claude/hooks"):
                with self.subTest(shell=shell, cwd=sub):
                    result = self._start(shell, self.repo / sub)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(self._found(), [str(self.repo)], result.stderr)

    def test_runs_from_the_root_without_claude_project_dir(self) -> None:
        for shell in self._shells():
            with self.subTest(shell=shell):
                result = self._start(shell, self.repo)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(self._found(), [str(self.repo)])

    def test_claude_project_dir_wins_when_set(self) -> None:
        # Started somewhere else entirely, in another repository: the
        # variable, not the directory, names the project.
        other = self.base / "other"
        other.mkdir()
        subprocess.run(
            [str(self.git), "init", "-q"], cwd=other, env=self.env, check=True, capture_output=True
        )
        for shell in self._shells():
            with self.subTest(shell=shell):
                result = self._start(shell, other, CLAUDE_PROJECT_DIR=str(self.repo))
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(self._found(), [str(self.repo)])

    def test_an_empty_claude_project_dir_falls_back_too(self) -> None:
        result = self._start(self._shells()[0], self.repo / "plugins", CLAUDE_PROJECT_DIR="")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self._found(), [str(self.repo)])

    def test_never_fails_the_session(self) -> None:
        # Outside any repository there is no hook to find; the session still
        # starts. So does one whose hook exits non-zero.
        nowhere = self.base / "nowhere"
        nowhere.mkdir()
        for shell in self._shells():
            with self.subTest(shell=shell, case="no repository"):
                result = self._start(shell, nowhere, GIT_CEILING_DIRECTORIES=str(self.base))
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(self._found(), [])
                self.assertEqual(result.stdout, "")
        (self.repo / ".claude" / "hooks" / "install-plugins.sh").write_text("exit 7\n", encoding="utf-8")
        result = self._start(self._shells()[0], self.repo / "plugins")
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
