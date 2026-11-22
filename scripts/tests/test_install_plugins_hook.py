""".claude/hooks/install-plugins.sh — installs a plugin only on a sure "missing".

The hook runs `claude plugin list --json` and installs when no row for the
plugin applies to this project. A listing it cannot read must make the answer
"unknown" (warn, install nothing), never "missing".

Every test runs a copy of the hook in a throwaway repository, with a stand-in
`claude` first on PATH that serves a canned listing and records its calls. The
real CLI is never run, and the real git and Claude configuration are never
read or written: HOME and the git config variables point into the temp
directory.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HOOK = ROOT / ".claude" / "hooks" / "install-plugins.sh"
PLUGIN = "mattpocock-skills@claude-plugins-official"

INSTALL = f"claude plugin install {PLUGIN} -y"
UNKNOWN = f"WARNING: cannot tell whether {PLUGIN} is installed"


class TestInstallPluginsHook(unittest.TestCase):
    def setUp(self) -> None:
        for tool in ("git", "bash", "python3"):
            self.assertIsNotNone(shutil.which(tool), f"{tool} is required")
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(os.path.realpath(tmp.name))
        self.repo = self.base / "repo"
        self.other = self.base / "other-project"
        self.bin = self.base / "bin"
        self.calls = self.base / "calls.txt"
        self.listing = self.base / "listing.json"
        home = self.base / "home"
        for d in (self.repo, self.other, self.bin, home):
            d.mkdir()

        (self.repo / ".claude" / "hooks").mkdir(parents=True)
        shutil.copy(HOOK, self.repo / ".claude" / "hooks" / HOOK.name)
        (self.repo / "scripts").mkdir()
        shutil.copy(ROOT / "scripts" / "install-hooks.sh", self.repo / "scripts")
        shutil.copytree(ROOT / ".githooks", self.repo / ".githooks")

        # The stand-in CLI. `plugin list` prints the canned listing; `plugin
        # install` succeeds and, as the real one does, makes the next listing
        # show the plugin.
        (self.bin / "claude").write_text(
            "#!/bin/sh\n"
            'echo "claude $*" >> "$STUB_CALLS"\n'
            'case "$1 $2" in\n'
            '  "plugin list") cat "$STUB_LISTING"; exit "${STUB_LIST_RC:-0}" ;;\n'
            '  "plugin install") cp "$STUB_INSTALLED" "$STUB_LISTING" ;;\n'
            "esac\n",
            encoding="utf-8",
        )
        (self.bin / "claude").chmod(0o755)
        installed = self.base / "installed.json"
        installed.write_text(json.dumps([self._row(version="9.9.9")]), encoding="utf-8")

        self.env = {
            "PATH": str(self.bin) + os.pathsep + os.environ["PATH"],
            "HOME": str(home),
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "STUB_CALLS": str(self.calls),
            "STUB_LISTING": str(self.listing),
            "STUB_INSTALLED": str(installed),
        }
        subprocess.run(
            ["git", "init", "-q"], cwd=self.repo, env=self.env, check=True, capture_output=True
        )

    @staticmethod
    def _row(**fields: object) -> dict[str, object]:
        row: dict[str, object] = {"id": PLUGIN, "version": "1.2.3", "scope": "user", "enabled": True}
        row.update(fields)
        return {key: value for key, value in row.items() if value is not ...}

    def _hook(self, rows: object, cwd: Path | None = None, **env: str) -> subprocess.CompletedProcess[str]:
        text = rows if isinstance(rows, str) else json.dumps(rows)
        self.listing.write_text(text, encoding="utf-8")
        self.calls.write_text("", encoding="utf-8")
        result = subprocess.run(
            ["bash", str(self.repo / ".claude" / "hooks" / HOOK.name)],
            cwd=cwd or self.repo,
            env={**self.env, **env},
            capture_output=True,
            text=True,
            check=False,
        )
        # Never fails the session, and never writes to the model's context.
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        return result

    def _installs(self) -> int:
        return self.calls.read_text(encoding="utf-8").splitlines().count(INSTALL)

    def _assert_unknown(self, result: subprocess.CompletedProcess[str]) -> None:
        self.assertEqual(self._installs(), 0, f"installed on an unreadable listing\n{result.stderr}")
        self.assertIn(UNKNOWN, result.stderr)
        self.assertIn("SKIPS the install", result.stderr)
        self.assertNotIn("is installed:", result.stderr)

    # -- the two defects ----------------------------------------------------

    def test_a_row_without_a_usable_id_makes_the_answer_unknown(self) -> None:
        # Such a row may be the plugin asked about. Skipping it used to leave
        # "no row found", which is the one answer that installs.
        for label, row in (
            ("no id", self._row(id=...)),
            ("null id", self._row(id=None)),
            ("empty id", self._row(id="")),
            ("numeric id", self._row(id=7)),
            ("id in a list", self._row(id=[PLUGIN])),
        ):
            for others in ([], [self._row(id="another@marketplace")]):
                with self.subTest(row=label, other_rows=len(others)):
                    self._assert_unknown(self._hook([*others, row]))

    def test_a_project_row_needs_an_absolute_project_path(self) -> None:
        # An empty or relative path resolves against the directory the hook
        # runs in. Run from the repository, that made a row for nowhere in
        # particular count as installed for this project.
        for scope in ("project", "local"):
            for label, path in (("empty", ""), ("dot", "."), ("relative", "repo"), ("missing", ...), ("null", None)):
                for cwd in (self.repo, self.base):
                    with self.subTest(scope=scope, project_path=label, cwd=cwd.name):
                        result = self._hook([self._row(scope=scope, projectPath=path)], cwd=cwd)
                        self._assert_unknown(result)

    # -- what must keep working ---------------------------------------------

    def test_installed_rows_are_reported_and_not_updated(self) -> None:
        link = self.base / "repo-link"
        os.symlink(self.repo, link)
        for label, rows, said in (
            ("user", [self._row()], "1.2.3 (user scope)"),
            ("managed, no version", [self._row(scope="managed", version=...)], "unknown version (managed scope)"),
            ("project, here", [self._row(scope="project", projectPath=str(self.repo))], "1.2.3 (project scope)"),
            ("local, via a link", [self._row(scope="local", projectPath=str(link))], "1.2.3 (local scope)"),
            (
                "two scopes",
                [self._row(), self._row(scope="project", projectPath=str(self.repo), version="2.0.0")],
                "1.2.3 (user scope), 2.0.0 (project scope)",
            ),
            (
                "beside another plugin's odd row",
                [self._row(id="another@marketplace", scope="synced", projectPath=""), self._row()],
                "1.2.3 (user scope)",
            ),
        ):
            with self.subTest(rows=label):
                result = self._hook(rows)
                self.assertEqual(self._installs(), 0)
                self.assertIn(f"{PLUGIN} is installed: {said}", result.stderr)
                self.assertIn("not updating", result.stderr)

    def test_a_sure_missing_installs_once(self) -> None:
        for label, rows in (
            ("empty listing", []),
            ("another plugin only", [self._row(id="another@marketplace")]),
            ("an id that shares a suffix", [self._row(id="x" + PLUGIN)]),
            ("a row for another project", [self._row(scope="project", projectPath=str(self.other))]),
            (
                "another plugin's row with a scope this hook does not know",
                [self._row(id="another@marketplace", scope="synced")],
            ),
        ):
            with self.subTest(rows=label):
                result = self._hook(rows)
                self.assertEqual(self._installs(), 1, result.stderr)
                self.assertIn(f"WARNING: {PLUGIN} is not installed; this INSTALLS", result.stderr)
                self.assertIn(f"installed {PLUGIN}: 9.9.9 (user scope)", result.stderr)

    def test_other_unreadable_listings_stay_unknown(self) -> None:
        for label, listing in (
            ("not JSON", "plugins: none"),
            ("empty output", ""),
            ("an object", {"plugins": []}),
            ("a row that is not an object", [PLUGIN]),
            ("a scope this hook does not know", [self._row(scope="synced")]),
            ("no scope", [self._row(scope=...)]),
        ):
            with self.subTest(listing=label):
                self._assert_unknown(self._hook(listing))
        with self.subTest(listing="the listing command failed"):
            self._assert_unknown(self._hook([self._row()], STUB_LIST_RC="1"))


if __name__ == "__main__":
    unittest.main()
