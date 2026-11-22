""".claude/hooks/install-plugins.sh — installs a plugin only on a sure "missing".

The hook carries a Python program that reads `claude plugin list --json`, and
installs when no row for the plugin applies to this project. The
listing is untrusted input: anything but a well-formed listing must make the
answer "unknown" (warn, install nothing), never "missing".

Two layers:

* `TestListingDecision` loads that program out of the hook file and calls its
  `decide` in this process, which is what lets it try thousands of malformed
  listings: wrong types at every
  level, non-standard JSON, oversized values, and seeded random damage checked
  against a validator written separately in this file.
* `TestInstallPluginsHook` runs a copy of the hook in a throwaway repository,
  with a stand-in `claude` first on PATH that serves a canned listing and
  records its calls.

The real CLI is never run, and the real git and Claude configuration are never
read or written: HOME and the git config variables point into the temp
directory.
"""

from __future__ import annotations

import json
import os
import random
import shutil
import subprocess
import tempfile
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HOOKS = ROOT / ".claude" / "hooks"
HOOK = HOOKS / "install-plugins.sh"
PLUGIN = "mattpocock-skills@claude-plugins-official"
OTHER = "another@marketplace"

INSTALL = f"claude plugin install {PLUGIN} -y"
UNKNOWN = f"WARNING: cannot tell whether {PLUGIN} is installed"


def _load_helper() -> types.ModuleType:
    """The program between the hook's two PLUGIN_STATUS_PY lines, as a module."""
    lines = HOOK.read_text(encoding="utf-8").split("\n")
    opens = [i for i, line in enumerate(lines) if "<<'PLUGIN_STATUS_PY'" in line]
    closes = [i for i, line in enumerate(lines) if line == "PLUGIN_STATUS_PY"]
    if len(opens) != 1 or len(closes) != 1 or closes[0] <= opens[0]:
        raise AssertionError(f"expected one PLUGIN_STATUS_PY heredoc in {HOOK.name}: {opens}, {closes}")
    source = "\n".join(lines[opens[0] + 1 : closes[0]]) + "\n"
    module = types.ModuleType("plugin_status")
    exec(compile(source, f"{HOOK.name}:PLUGIN_STATUS_PY", "exec"), module.__dict__)  # noqa: S102 - this repo's own hook
    return module


def _row(**fields: object) -> dict[str, object]:
    """A well-formed user-scope row for PLUGIN; `...` as a value drops the key."""
    row: dict[str, object] = {"id": PLUGIN, "version": "1.2.3", "scope": "user", "enabled": True}
    row.update(fields)
    return {key: value for key, value in row.items() if value is not ...}


# Values no field of a row should hold. Each field also has its own list below.
JUNK = (
    None,
    True,
    False,
    0,
    7,
    1.5,
    "",
    " ",
    "    ",
    "\t",
    "\n",
    [],
    {},
    [PLUGIN],
    {"id": PLUGIN},
    [[PLUGIN]],
    "x" * 100_000,
    "line\nbreak",
    "esc\x1b[2K",
    "nul\x00byte",
    "\ud800",
    " ",
)

BAD_IDS = JUNK + (
    "mattpocock-skills",  # no marketplace
    "@claude-plugins-official",
    "mattpocock-skills@",
    "a@b@c",
    " " + PLUGIN,
    PLUGIN + " ",
    PLUGIN + "\n",
    "matt pocock@claude-plugins-official",
    "-leading@marketplace",
    "name@marketplace/",
    "../x@marketplace",
    "ñame@marketplace",
)

BAD_SCOPES = JUNK + ("User", "user ", " user", "us er", "user\n", "1user", "-user", "x" * 33)

# A version may be absent or null; anything else has to look like one.
BAD_VERSIONS = tuple(v for v in JUNK if v is not None) + (
    "1.2.3 ",
    " 1.2.3",
    "1.2.3\n",
    "1.2.3 (user scope), 9.9.9",
    "-1",
    "x" * 65,
)

# For a project or local row. Absent and null are bad there too.
BAD_PATHS = JUNK + (
    ...,
    ".",
    "..",
    "repo",
    "./repo",
    "~/repo",
    "/tmp/no\x00such",
    "/tmp/line\nbreak",
    "/tmp/esc\x1b",
    "/tmp/\ud800",
    "/tmp/c1\u009b",
    "/tmp/sep ",
    "/" + "x" * 5000,
)

# Text that is not one strict JSON document holding a list.
NOT_A_LISTING = {
    "empty": "",
    "whitespace": " \n\t ",
    "truncated": "[",
    "truncated row": '[{"id":',
    "trailing junk": "[] garbage",
    "two documents": "[][]",
    "trailing comma": '[{"id":"a@b","scope":"user"},]',
    "single quotes": "[{'id':'a@b','scope':'user'}]",
    "comment": '[] // none',
    "NaN": '[{"id":"another@example","scope":"user","version":NaN}]',
    "Infinity": '[{"id":"another@example","scope":"user","n":Infinity}]',
    "-Infinity": '[{"id":"another@example","scope":"user","n":-Infinity}]',
    "bare NaN": "NaN",
    "float out of range": '[{"id":"another@example","scope":"user","n":1e999}]',
    "duplicate id, target first": f'[{{"id":"{PLUGIN}","id":"other@example","scope":"user"}}]',
    "duplicate id, target last": f'[{{"id":"other@example","id":"{PLUGIN}","scope":"user"}}]',
    "duplicate scope": '[{"id":"other@example","scope":"user","scope":"user"}]',
    "duplicate key in a field we ignore": '[{"id":"other@example","scope":"user","x":{"a":1,"a":2}}]',
    "byte order mark": "﻿[]",
    "raw control character in a string": '[{"id":"other@example","scope":"user","note":"a\tb"}]',
    "null": "null",
    "true": "true",
    "number": "0",
    "string": f'"{PLUGIN}"',
    "object": "{}",
    "object holding the list": '{"plugins":[]}',
    "object keyed by id": json.dumps({PLUGIN: {"scope": "user"}}),
    "list in a list": "[[]]",
    "row in a list in a list": json.dumps([[_row()]]),
    "string row": json.dumps([PLUGIN]),
    "null row": "[null]",
    "number row": "[0]",
    "a good row then a bad one": json.dumps([_row(id=OTHER), None]),
    "deep nesting": "[" * 100_000,
    "deep nesting, closed": "[" * 100_000 + "]" * 100_000,
    "deep nesting in an ignored field": '[{"id":"other@example","scope":"user","x":'
    + "[" * 100_000
    + "]" * 100_000
    + "}]",
}

NOT_A_LISTING_BYTES = {
    "invalid UTF-8": b'[{"id":"other@example","scope":"user","note":"\xff"}]',
    "UTF-16": "[]".encode("utf-16"),
    "raw NUL between the brackets": b"[\x00]",
    "raw NUL after the listing": b"[]\x00",
    "larger than the cap": b"[" + b" " * (4 * 1024 * 1024) + b"]",
}


def well_formed(text: str) -> bool:
    """This file's own reading of "a listing the hook may act on".

    Written separately from the hook's program, with a different parser set-up
    and plain string checks, so the random test below compares two
    implementations rather than one with itself.
    """

    def refuse(_):
        raise ValueError

    def pairs(items):
        keys = [key for key, _ in items]
        if len(keys) != len(set(keys)):
            raise ValueError
        return dict(items)

    def finite(text_):
        if float(text_) in (float("inf"), float("-inf")):
            raise ValueError
        return float(text_)

    try:
        # The listing arrives as bytes; text that is not UTF-8 is not a listing.
        text.encode("utf-8")
        rows = json.loads(text, parse_constant=refuse, object_pairs_hook=pairs, parse_float=finite)
    except (ValueError, RecursionError):
        return False
    if type(rows) is not list:
        return False
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")
    alnum = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")
    for row in rows:
        if type(row) is not dict:
            return False
        ident = row.get("id")
        if type(ident) is not str or ident.count("@") != 1:
            return False
        for part in ident.split("@"):
            if not 1 <= len(part) <= 128 or not set(part) <= allowed:
                return False
            if part[0] not in alnum or part[-1] not in alnum:
                return False
        scope = row.get("scope")
        if type(scope) is not str or not 1 <= len(scope) <= 32:
            return False
        if not set(scope) <= set("abcdefghijklmnopqrstuvwxyz-") or scope[0] == "-":
            return False
        version = row.get("version")
        if version is not None:
            if type(version) is not str or not 1 <= len(version) <= 64:
                return False
            if not set(version) <= allowed | {"+"} or version[0] not in alnum:
                return False
        path = row.get("projectPath")
        if scope in ("project", "local") or path is not None:
            if type(path) is not str or not path.startswith("/") or len(path) > 4096:
                return False
            if any(ord(c) < 32 or 127 <= ord(c) < 160 or 0xD800 <= ord(c) <= 0xDFFF for c in path):
                return False
            if " " in path or " " in path:
                return False
        if ident == PLUGIN and scope not in ("user", "managed", "project", "local"):
            return False
    return True


class TestListingDecision(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.helper = _load_helper()

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(os.path.realpath(tmp.name))
        self.root = self.base / "repo"
        self.root.mkdir()
        self.elsewhere = str(self.base / "other-project")

    def decide(self, listing: object) -> str:
        if isinstance(listing, bytes):
            raw = listing
        elif isinstance(listing, str):
            raw = listing.encode("utf-8", "surrogatepass")
        else:
            raw = json.dumps(listing).encode("utf-8")
        return self.helper.decide(raw, PLUGIN, str(self.root))

    def assert_unknown(self, listing: object) -> None:
        with self.assertRaises(self.helper.Malformed):
            self.decide(listing)

    # -- answers it must still give -------------------------------------------

    def test_well_formed_listings_are_answered(self) -> None:
        here = str(self.root)
        for label, rows, want in (
            ("empty", [], ""),
            ("another plugin", [_row(id=OTHER)], ""),
            ("an id that shares a suffix", [_row(id="x" + PLUGIN)], ""),
            ("another project", [_row(scope="project", projectPath=self.elsewhere)], ""),
            ("another plugin, scope not known here", [_row(id=OTHER, scope="synced")], ""),
            ("user", [_row()], "1.2.3 (user scope)"),
            ("no version", [_row(scope="managed", version=...)], "unknown version (managed scope)"),
            ("null version", [_row(version=None)], "unknown version (user scope)"),
            ("a git revision as version", [_row(version="0a1b2c3d4e5f")], "0a1b2c3d4e5f (user scope)"),
            ("this project", [_row(scope="local", projectPath=here)], "1.2.3 (local scope)"),
            ("this project, trailing slash", [_row(scope="project", projectPath=here + "/")], "1.2.3 (project scope)"),
            (
                "two scopes",
                [_row(), _row(scope="project", projectPath=here, version="2.0.0")],
                "1.2.3 (user scope), 2.0.0 (project scope)",
            ),
            (
                "fields this hook does not read",
                [_row(installPath="/x", installedAt="2026-01-01", nested={"a": [1, 2.5, None, True]})],
                "1.2.3 (user scope)",
            ),
        ):
            with self.subTest(listing=label):
                self.assertEqual(self.decide(rows), want)

    # -- the four listings the review found, and their neighbours -------------

    def test_listings_that_used_to_trigger_an_install(self) -> None:
        for label, listing in (
            ("whitespace-only id", [{"id": "    ", "scope": "user", "version": "1.0.0"}]),
            ("NUL in a project path", [_row(scope="project", projectPath="/tmp/no\x00such")]),
            ("lone surrogate in a project path", [_row(scope="project", projectPath="/tmp/\ud800")]),
            ("duplicate id keys", NOT_A_LISTING["duplicate id, target first"]),
            ("NaN", NOT_A_LISTING["NaN"]),
        ):
            with self.subTest(listing=label):
                self.assert_unknown(listing)

    # -- wrong types and shapes, field by field --------------------------------

    def test_every_field_is_checked_in_every_row(self) -> None:
        here = str(self.root)
        cases = [("id", bad, _row(id=bad)) for bad in BAD_IDS]
        cases += [("id", "absent", _row(id=...))]
        cases += [("scope", bad, _row(scope=bad)) for bad in BAD_SCOPES]
        cases += [("scope", "absent", _row(scope=...))]
        cases += [("version", bad, _row(version=bad)) for bad in BAD_VERSIONS]
        cases += [("projectPath", bad, _row(scope="project", projectPath=bad)) for bad in BAD_PATHS]
        cases += [("projectPath", bad, _row(scope="local", projectPath=bad)) for bad in BAD_PATHS]
        # A path on a row that needs none still has to be a path.
        cases += [
            ("projectPath on a user row", bad, _row(projectPath=bad))
            for bad in BAD_PATHS
            if bad is not ... and bad is not None
        ]
        for field, bad, row in cases:
            shown = repr(bad)[:40]
            # As the only row, beside a good row for the plugin, and on a row
            # for another plugin: the whole listing is unknown each time.
            bystander = dict(row)
            if field != "id":
                bystander["id"] = OTHER
            for where, rows in (
                ("alone", [row]),
                ("after an installed row", [_row(), row]),
                ("before an installed row", [row, _row()]),
                ("on another plugin's row", [bystander, _row(scope="local", projectPath=here)]),
            ):
                with self.subTest(field=field, value=shown, where=where):
                    self.assert_unknown(rows)

    def test_a_scope_this_hook_does_not_know(self) -> None:
        # On the plugin's own row the answer is unknown. On another plugin's
        # row the scope is not this hook's business, so long as it is one.
        self.assert_unknown([_row(scope="synced")])
        self.assert_unknown([_row(scope="future-scope")])
        self.assertEqual(self.decide([_row(id=OTHER, scope="synced"), _row()]), "1.2.3 (user scope)")

    # -- not strict JSON, or not a list ----------------------------------------

    def test_text_that_is_not_a_strict_json_list(self) -> None:
        for label, text in NOT_A_LISTING.items():
            with self.subTest(listing=label):
                self.assert_unknown(text)
        for label, raw in NOT_A_LISTING_BYTES.items():
            with self.subTest(listing=label):
                self.assert_unknown(raw)

    def test_a_large_well_formed_listing_is_still_answered(self) -> None:
        rows = [_row(id=f"plugin-{n}@marketplace", installPath="/x" * 200) for n in range(5000)]
        self.assertEqual(self.decide(rows), "")
        self.assertEqual(self.decide(rows + [_row()]), "1.2.3 (user scope)")

    # -- random damage, judged by a second implementation ---------------------

    def _mutate(self, rng: random.Random, text: str) -> str:
        fragments = (
            '"', "\\", "{", "}", "[", "]", ",", ":", " ", "\n", "\x00", "\x1b", "\ud800",
            "NaN", "Infinity", "null", "true", "1e999", "-", '"id"', '"scope"', '"version"',
            '"projectPath"', '""', '" "', '"/"', '"."', "user", "synced", "@", "//", "﻿",
            f'"id":"{PLUGIN}",', '"id":"   ",', '"scope":"user",',
        )
        for _ in range(rng.randint(1, 3)):
            at = rng.randrange(len(text) + 1)
            kind = rng.randrange(4)
            if kind == 0:
                text = text[:at] + rng.choice(fragments) + text[at:]
            elif kind == 1 and text:
                end = min(len(text), at + rng.randint(1, 12))
                text = text[:at] + text[end:]
            elif kind == 2 and text:
                end = min(len(text), at + rng.randint(1, 20))
                text = text[:at] + text[at:end] * 2 + text[end:]
            else:
                text = text[:at] + chr(rng.choice((0, 9, 10, 27, 32, 34, 44, 58, 92, 127, 0x9B))) + text[at:]
        return text

    def test_random_damage_never_yields_an_answer_from_a_bad_listing(self) -> None:
        rng = random.Random(94)
        here = str(self.root)
        seeds = [
            json.dumps([]),
            json.dumps([_row(id=OTHER)]),
            json.dumps([_row(id=OTHER, scope="synced"), _row(id="third@marketplace", version=...)]),
            json.dumps([_row(scope="project", projectPath=self.elsewhere), _row(id=OTHER)]),
            json.dumps([_row()], indent=2),
            json.dumps([_row(scope="local", projectPath=here), _row(scope="managed", version=None)]),
        ]
        answered = refused = 0
        for round_ in range(6000):
            text = self._mutate(rng, rng.choice(seeds))
            try:
                answer = self.decide(text)
            except self.helper.Malformed:
                refused += 1
                # The other direction: what this file calls well-formed must
                # not be refused, or the hook would never install anything.
                self.assertFalse(well_formed(text), f"round {round_}: refused a well-formed listing: {text!r}")
                continue
            answered += 1
            self.assertTrue(well_formed(text), f"round {round_}: answered {answer!r} for: {text!r}")
        # The test means something only if both outcomes were exercised.
        self.assertGreater(answered, 200, (answered, refused))
        self.assertGreater(refused, 2000, (answered, refused))

    def test_random_well_formed_listings_are_answered_correctly(self) -> None:
        rng = random.Random(97)
        here = str(self.root)
        names = ("alpha", "beta-2", "g.amma", "d_elta", "mattpocock-skills")
        markets = ("marketplace", "claude-plugins-official", "x")
        for round_ in range(500):
            rows, expect = [], []
            for _ in range(rng.randint(0, 6)):
                ident = f"{rng.choice(names)}@{rng.choice(markets)}"
                scope = rng.choice(("user", "managed", "project", "local") + (("synced",) if ident != PLUGIN else ()))
                row: dict[str, object] = {"id": ident, "scope": scope, "enabled": rng.random() < 0.5}
                version = rng.choice(("1.0.0", "2.3.4-rc.1+build", "abc1234", None, ...))
                if version is not ...:
                    row["version"] = version
                if scope in ("project", "local"):
                    row["projectPath"] = rng.choice((here, self.elsewhere, "/"))
                rows.append(row)
                applies = scope in ("user", "managed") or row.get("projectPath") == here
                if ident == PLUGIN and applies:
                    expect.append(f"{row.get('version') or 'unknown version'} ({scope} scope)")
            with self.subTest(round=round_):
                self.assertTrue(well_formed(json.dumps(rows)))
                self.assertEqual(self.decide(rows), ", ".join(expect))


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
        for d in (self.other, self.bin, home):
            d.mkdir()
        self._checkout(self.repo)

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
        installed.write_text(json.dumps([_row(version="9.9.9")]), encoding="utf-8")

        self.env = {
            "PATH": str(self.bin) + os.pathsep + os.environ["PATH"],
            "HOME": str(home),
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "STUB_CALLS": str(self.calls),
            "STUB_LISTING": str(self.listing),
            "STUB_INSTALLED": str(installed),
        }
        self._git_init(self.repo)

    def _checkout(self, repo: Path) -> None:
        """A copy of what the hook needs, laid out as in this repository."""
        (repo / ".claude" / "hooks").mkdir(parents=True)
        shutil.copy(HOOK, repo / ".claude" / "hooks" / HOOK.name)
        (repo / "scripts").mkdir()
        shutil.copy(ROOT / "scripts" / "install-hooks.sh", repo / "scripts")
        shutil.copytree(ROOT / ".githooks", repo / ".githooks")

    def _git_init(self, repo: Path) -> None:
        subprocess.run(["git", "init", "-q"], cwd=repo, env=self.env, check=True, capture_output=True)

    def _hook(
        self, listing: object, cwd: Path | None = None, repo: Path | None = None, **env: str
    ) -> subprocess.CompletedProcess[str]:
        if isinstance(listing, bytes):
            self.listing.write_bytes(listing)
        elif isinstance(listing, str):
            self.listing.write_bytes(listing.encode("utf-8", "surrogatepass"))
        else:
            self.listing.write_text(json.dumps(listing), encoding="utf-8")
        self.calls.write_text("", encoding="utf-8")
        repo = repo or self.repo
        result = subprocess.run(
            ["bash", str(repo / ".claude" / "hooks" / HOOK.name)],
            cwd=cwd or repo,
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
        self.assertNotIn("Traceback", result.stderr)

    # -- malformed listings, end to end ----------------------------------------

    def test_a_row_without_a_usable_id_makes_the_answer_unknown(self) -> None:
        # Such a row may be the plugin asked about. Skipping it used to leave
        # "no row found", which is the one answer that installs.
        for label, row in (
            ("no id", _row(id=...)),
            ("null id", _row(id=None)),
            ("empty id", _row(id="")),
            ("whitespace id", _row(id="    ")),
            ("numeric id", _row(id=7)),
            ("id in a list", _row(id=[PLUGIN])),
        ):
            for others in ([], [_row(id=OTHER)]):
                with self.subTest(row=label, other_rows=len(others)):
                    self._assert_unknown(self._hook([*others, row]))

    def test_a_project_row_needs_a_clean_absolute_project_path(self) -> None:
        # An empty or relative path resolves against the directory the hook
        # runs in. Run from the repository, that made a row for nowhere in
        # particular count as installed for this project.
        for scope in ("project", "local"):
            for label, path in (
                ("empty", ""),
                ("dot", "."),
                ("relative", "repo"),
                ("missing", ...),
                ("null", None),
                ("NUL", "/tmp/no\x00such"),
                ("lone surrogate", "/tmp/\ud800"),
                ("newline", "/tmp/a\nb"),
            ):
                for cwd in (self.repo, self.base):
                    with self.subTest(scope=scope, project_path=label, cwd=cwd.name):
                        result = self._hook([_row(scope=scope, projectPath=path)], cwd=cwd)
                        self._assert_unknown(result)

    def test_listings_that_are_not_strict_json_install_nothing(self) -> None:
        for label in (
            "empty",
            "truncated",
            "trailing junk",
            "NaN",
            "Infinity",
            "float out of range",
            "duplicate id, target first",
            "duplicate id, target last",
            "duplicate key in a field we ignore",
            "byte order mark",
            "object",
            "object holding the list",
            "string row",
            "row in a list in a list",
            "deep nesting",
        ):
            with self.subTest(listing=label):
                self._assert_unknown(self._hook(NOT_A_LISTING[label]))
        for label, raw in NOT_A_LISTING_BYTES.items():
            with self.subTest(listing=label):
                self._assert_unknown(self._hook(raw))

    def test_other_unreadable_listings_stay_unknown(self) -> None:
        for label, listing in (
            ("a scope this hook does not know", [_row(scope="synced")]),
            ("no scope", [_row(scope=...)]),
            ("a version that is a sentence", [_row(version="1.2.3 (user scope), 9.9.9")]),
            ("another plugin's row with an empty project path", [_row(id=OTHER, projectPath=""), _row()]),
        ):
            with self.subTest(listing=label):
                self._assert_unknown(self._hook(listing))
        with self.subTest(listing="the listing command failed"):
            result = self._hook([_row()], STUB_LIST_RC="1")
            self._assert_unknown(result)
            self.assertIn("claude plugin list --json failed", result.stderr)

    def test_the_hook_is_one_file(self) -> None:
        # Copied somewhere on its own, it still decides: nothing it needs
        # lives beside it.
        alone = self.base / "alone"
        (alone / ".claude" / "hooks").mkdir(parents=True)
        shutil.copy(HOOK, alone / ".claude" / "hooks" / HOOK.name)
        self.assertEqual([p.name for p in HOOKS.iterdir() if p.is_file()], [HOOK.name])
        result = self._hook([_row()], repo=alone)
        self.assertIn(f"{PLUGIN} is installed: 1.2.3 (user scope)", result.stderr)
        result = self._hook([], repo=alone)
        self.assertEqual(self._installs(), 1, result.stderr)
        self._assert_unknown(self._hook(NOT_A_LISTING["NaN"], repo=alone))

    def test_without_python_the_answer_is_unknown(self) -> None:
        # A PATH with the tools the hook itself needs and no python3.
        bindir = self.base / "nopython"
        bindir.mkdir()
        for tool in ("bash", "git", "dirname", "cat", "chmod"):
            os.symlink(str(shutil.which(tool)), bindir / tool)
        os.symlink(self.bin / "claude", bindir / "claude")
        result = self._hook([], PATH=str(bindir))
        self._assert_unknown(result)
        self.assertIn("python3 is not on PATH", result.stderr)

    # -- what must keep working -------------------------------------------------

    def test_installed_rows_are_reported_and_not_updated(self) -> None:
        link = self.base / "repo-link"
        os.symlink(self.repo, link)
        for label, rows, said in (
            ("user", [_row()], "1.2.3 (user scope)"),
            ("managed, no version", [_row(scope="managed", version=...)], "unknown version (managed scope)"),
            ("project, here", [_row(scope="project", projectPath=str(self.repo))], "1.2.3 (project scope)"),
            ("local, via a link", [_row(scope="local", projectPath=str(link))], "1.2.3 (local scope)"),
            (
                "two scopes",
                [_row(), _row(scope="project", projectPath=str(self.repo), version="2.0.0")],
                "1.2.3 (user scope), 2.0.0 (project scope)",
            ),
            (
                "beside another plugin's row with a scope not known here",
                [_row(id=OTHER, scope="synced"), _row()],
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
            ("another plugin only", [_row(id=OTHER)]),
            ("an id that shares a suffix", [_row(id="x" + PLUGIN)]),
            ("a row for another project", [_row(scope="project", projectPath=str(self.other))]),
            ("another plugin's row with a scope not known here", [_row(id=OTHER, scope="synced")]),
        ):
            with self.subTest(rows=label):
                result = self._hook(rows)
                self.assertEqual(self._installs(), 1, result.stderr)
                self.assertIn(f"WARNING: {PLUGIN} is not installed; this INSTALLS", result.stderr)
                self.assertIn(f"installed {PLUGIN}: 9.9.9 (user scope)", result.stderr)

    def test_runs_from_anywhere_including_a_checkout_named_with_a_newline(self) -> None:
        # The hook finds the checkout from its own location. Nothing is
        # printed and read back, so a directory name ending in a newline
        # works like any other.
        odd = self.base / "trailing-newline\n"
        self._checkout(odd)
        self._git_init(odd)
        (odd / "sub").mkdir()
        for repo in (self.repo, odd):
            for cwd in (repo, repo / ".claude", self.base):
                with self.subTest(repo=repo.name, cwd=cwd.name):
                    result = self._hook([_row()], cwd=cwd, repo=repo)
                    self.assertNotIn("install-hooks.sh failed", result.stderr)
                    self.assertIn("hooks active in this worktree", result.stderr)
                    self.assertIn(f"{PLUGIN} is installed: 1.2.3 (user scope)", result.stderr)
                    hooks_path = subprocess.run(
                        ["git", "config", "--local", "--get", "core.hooksPath"],
                        cwd=repo,
                        env=self.env,
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    self.assertEqual(hooks_path.stdout.strip(), ".githooks")


if __name__ == "__main__":
    unittest.main()
