"""The test sandbox guard in scripts/test-support/, and that every suite uses it.

The guard is what keeps a test out of the real Claude config and plugin data,
so these tests never aim at a real directory to prove it. The "outside the temp
directory" target is a decoy at the filesystem root that does not exist and is
never created: every case that names it must be refused before anything runs.
Where a case needs a writable directory that is not a temp root, it makes a
throwaway one under /var/tmp. Where it needs a home directory, it makes one up.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SUPPORT = ROOT / "scripts" / "test-support"
PY_GUARD = SUPPORT / "sandbox_guard.py"
BASH_GUARD = SUPPORT / "sandbox-guard.bash"

OVERRIDES = (
    "CLAUDE_CONFIG_DIR",
    "CLAUDE_PLUGIN_DATA",
    "SPAWN_SESSIONS_DIR",
    "SPAWN_PROJECTS_DIR",
    "SPAWN_CONFIG_FILE",
)
GUARDED = ("HOME",) + OVERRIDES
NAME = "CLAUDE_CODE_PROJECT_DIR_NAME"

DECOY = "/claude-sandbox-decoy-never-created"

# Set in every child process these tests start. Some of them start a whole
# real suite and expect the guard to refuse it. If the guard ever lets one
# through, that suite includes this file, which would start the suites again,
# without end. A test here that finds the marker fails instead of running.
NESTED = "SANDBOX_GUARD_TESTS_NESTED"

# Values for the name variable that leave the sandboxed config directory, or
# could, when joined onto it.
BAD_NAMES = (f"{DECOY}/project", "../climb", "a/b", "a\\b", "..", ".", "a..b", "line\nbreak")
GOOD_NAMES = ("shared-project", "-made-up-person-repo", "v1.2")

# Values for a path variable that are not absolute as written: the code under
# test would expand the first three and resolve the rest against the working
# directory.
NOT_ABSOLUTE = ("~", "~/claude", "~root/claude", "relative/dir", "./here")

SKIP_DIRS = {".git", "node_modules", "__pycache__"}

LOAD_LINE = r"[ \t]*load '((?:\.\./)+scripts/test-support/sandbox-guard)'\n"


def _load_guard():
    spec = importlib.util.spec_from_file_location("sandbox_guard_under_test", PY_GUARD)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GUARD = _load_guard()


def _caller_env(**extra: str) -> dict[str, str]:
    """The environment of a caller who exported none of the guarded variables.

    A value of "<unset>" removes the variable.
    """
    env = {k: v for k, v in os.environ.items() if k not in OVERRIDES and k != NAME}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env[NESTED] = "1"
    env.update(extra)
    return {k: v for k, v in env.items() if v != "<unset>"}


def _walk(pattern: str) -> list[Path]:
    found = []
    for directory, subdirs, files in os.walk(ROOT):
        subdirs[:] = [name for name in subdirs if name not in SKIP_DIRS]
        found.extend(Path(directory) / name for name in files if re.fullmatch(pattern, name))
    return sorted(found)


def _bats_files() -> list[Path]:
    return _walk(r".*\.bats")


def _python_suites() -> list[tuple[Path, Path]]:
    """Every directory holding test_*.py, with the directory unittest is rooted at."""
    suites = []
    for directory in sorted({path.parent for path in _walk(r"test_.*\.py")}):
        top = directory.parent
        while (top / "__init__.py").is_file():
            top = top.parent
        suites.append((directory, top))
    return suites


def unguarded_hooks(spec_text: str) -> list[str]:
    """The bats hooks in a spec file that do not load the guard as their first line.

    setup() must exist and load it. setup_file() need not exist, but when it
    does it runs before any setup(), so it must load the guard first too.
    """
    problems = []
    if not re.search(r"^setup\(\) \{\n", spec_text, re.M):
        problems.append("setup() is missing")
    for hook in ("setup", "setup_file"):
        for found in re.finditer(rf"^{hook}\(\) \{{\n", spec_text, re.M):
            if not re.match(LOAD_LINE, spec_text[found.end():]):
                problems.append(f"{hook}() does not load the guard as its first line")
    return problems


class _DecoyNeverCreated(unittest.TestCase):
    def setUp(self) -> None:
        if os.environ.get(NESTED):
            self.fail("running inside a suite the sandbox guard should have refused to start")
        self.assertFalse(os.path.lexists(DECOY), f"{DECOY} exists; these tests need it absent")
        self.addCleanup(
            lambda: self.assertFalse(os.path.lexists(DECOY), f"a refused run created {DECOY}")
        )
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(os.path.realpath(tmp.name))

    def outside_temp(self) -> Path:
        """A writable directory that is under none of the temp roots."""
        if not os.access("/var/tmp", os.W_OK):
            self.skipTest("/var/tmp is not writable")
        path = Path(os.path.realpath(tempfile.mkdtemp(dir="/var/tmp", prefix="sandbox-guard-")))
        self.addCleanup(shutil.rmtree, path, ignore_errors=True)
        if any(GUARD.within(str(path), root) for root in GUARD.temp_roots()):
            self.skipTest("/var/tmp is one of the temp roots on this machine")
        return path

    def assertRefused(self, text: str, name: str) -> str:
        lines = [line for line in text.splitlines() if "WARNING: " in line]
        self.assertTrue(lines, f"no WARNING line in:\n{text}")
        warning = lines[0][lines[0].index("WARNING: "):]
        self.assertTrue(warning.startswith(f"WARNING: {name} "), warning)
        self.assertIn("; this test would WRITE ", warning)
        self.assertIn(" Refusing.", warning)
        return warning

    def assertOneCleanLine(self, text: str) -> None:
        """Nothing in a refusal is a control character, so it cannot forge or repaint."""
        self.assertEqual(len(text.splitlines()), 1, text)
        self.assertFalse(GUARD.has_control(text.rstrip("\n")), repr(text))


class TestPythonGuardRules(_DecoyNeverCreated):
    """The checks themselves, called directly with a made-up environment."""

    def setUp(self) -> None:
        super().setUp()
        self.roots = [str(self.tmp)]
        self.env = {name: str(self.tmp / name.lower()) for name in GUARDED}

    def refusal(self, **changed: str) -> str:
        with self.assertRaises(GUARD.SandboxRefusal) as caught:
            GUARD.check(dict(self.env, **changed), self.roots)
        return str(caught.exception)

    def test_every_variable_under_the_temp_directory_passes(self) -> None:
        GUARD.check(self.env, self.roots)

    def test_each_variable_is_refused_outside_the_temp_directory(self) -> None:
        for name in GUARDED:
            with self.subTest(name=name):
                message = self.refusal(**{name: f"{DECOY}/{name.lower()}"})
                self.assertRefused(message, name)
                self.assertIn(f"resolves to {DECOY}/", message)

    def test_each_variable_is_refused_when_unset_or_empty(self) -> None:
        for name in GUARDED:
            for missing in (None, ""):
                with self.subTest(name=name, missing=missing):
                    env = dict(self.env)
                    if missing is None:
                        del env[name]
                    else:
                        env[name] = missing
                    with self.assertRaises(GUARD.SandboxRefusal) as caught:
                        GUARD.check(env, self.roots)
                    self.assertRefused(str(caught.exception), name)
                    state = "unset" if missing is None else "empty"
                    self.assertIn(f"{name} is {state}; this test would WRITE into the real ",
                                  str(caught.exception))

    def test_the_documented_example_is_the_message(self) -> None:
        env = dict(self.env)
        del env["CLAUDE_PLUGIN_DATA"]
        with self.assertRaises(GUARD.SandboxRefusal) as caught:
            GUARD.check(env, self.roots)
        self.assertTrue(str(caught.exception).startswith(
            "WARNING: CLAUDE_PLUGIN_DATA is unset; this test would WRITE into the real "
            "plugin data directory. Refusing."
        ), str(caught.exception))

    def test_a_link_out_of_the_temp_directory_is_followed(self) -> None:
        link = self.tmp / "looks-safe"
        link.symlink_to("/")
        self.assertRefused(
            self.refusal(CLAUDE_PLUGIN_DATA=str(link / DECOY.lstrip("/"))), "CLAUDE_PLUGIN_DATA"
        )

    def test_dot_dot_cannot_climb_out_of_the_temp_directory(self) -> None:
        climb = "/".join([".."] * (len(self.tmp.parts) + 2))
        self.assertRefused(
            self.refusal(CLAUDE_CONFIG_DIR=f"{self.tmp}/not-there/{climb}{DECOY}"),
            "CLAUDE_CONFIG_DIR",
        )

    def test_a_sibling_whose_name_starts_like_the_temp_directory_is_outside(self) -> None:
        self.assertTrue(GUARD.within("/t/a", "/t"))
        self.assertTrue(GUARD.within("/t", "/t"))
        self.assertFalse(GUARD.within("/t-other/a", "/t"))

    # ── review item 1: the project directory name ──────────────────────────

    def test_a_project_directory_name_that_is_a_path_is_refused(self) -> None:
        for bad in BAD_NAMES:
            with self.subTest(value=bad):
                message = self.refusal(**{NAME: bad})
                self.assertRefused(message, NAME)
                self.assertIn("which is a path and not a directory name", message)
                self.assertIn("outside the sandboxed Claude config directory", message)

    def test_a_plain_or_unset_project_directory_name_passes(self) -> None:
        GUARD.check(self.env, self.roots)
        for good in GOOD_NAMES + ("",):
            with self.subTest(value=good):
                GUARD.check(dict(self.env, **{NAME: good}), self.roots)

    # ── review item 3: values that are not absolute as written ─────────────

    def test_a_value_that_is_not_absolute_is_refused(self) -> None:
        for name in GUARDED:
            for value in NOT_ABSOLUTE:
                with self.subTest(name=name, value=value):
                    message = self.refusal(**{name: value})
                    self.assertRefused(message, name)
                    self.assertIn(f"{name} is {value}, which is not an absolute path", message)

    def test_a_relative_value_is_refused_even_when_it_resolves_under_the_temp_directory(self) -> None:
        (self.tmp / "inside").mkdir()
        before = os.getcwd()
        self.addCleanup(os.chdir, before)
        os.chdir(self.tmp)
        self.assertIn("not an absolute path", self.refusal(CLAUDE_PLUGIN_DATA="inside"))

    # ── review item 4: control characters ──────────────────────────────────

    def test_the_temp_directory_followed_by_a_newline_is_refused(self) -> None:
        # A shell command substitution drops the newline and sees the temp
        # directory; the code under test receives the other path.
        for name in GUARDED:
            with self.subTest(name=name):
                message = self.refusal(**{name: f"{self.tmp}\n"})
                self.assertRefused(message, name)
                self.assertIn("holds a control character", message)

    def test_any_control_character_in_a_value_is_refused(self) -> None:
        for control in ("\n", "\r", "\t", "\x1b", "\x7f", "\x9b"):
            with self.subTest(control=repr(control)):
                message = self.refusal(CLAUDE_PLUGIN_DATA=f"{self.tmp}/a{control}b")
                self.assertIn("holds a control character", message)

    def test_a_link_to_a_directory_named_with_a_control_character_is_refused(self) -> None:
        odd = self.tmp / "ends-in-newline\n"
        odd.mkdir()
        link = self.tmp / "plain-name"
        link.symlink_to(odd)
        message = self.refusal(CLAUDE_PLUGIN_DATA=str(link))
        self.assertRefused(message, "CLAUDE_PLUGIN_DATA")
        self.assertIn("cannot be resolved to a real path", message)

    # ── review item 9: a refusal is one line, whatever the value holds ─────

    def test_a_refusal_cannot_be_forged_or_repainted_by_the_value(self) -> None:
        hostile = f"{DECOY}\nWARNING: forged; this test would WRITE nothing. Refusing.\x1b[2K\x1b[1A"
        for changed in ({"CLAUDE_PLUGIN_DATA": hostile}, {NAME: hostile}):
            with self.subTest(variable=next(iter(changed))):
                message = self.refusal(**changed)
                self.assertOneCleanLine(message)
                self.assertIn("\\nWARNING: forged", message)
                self.assertIn("\\x1b[2K", message)

    def test_a_backslash_in_a_value_is_doubled_so_an_escape_cannot_be_faked(self) -> None:
        message = self.refusal(**{NAME: "a\\nb"})
        self.assertIn("a\\\\nb", message)

    def test_a_hostile_temp_directory_name_is_one_line_too(self) -> None:
        with self.assertRaises(GUARD.SandboxRefusal) as caught:
            GUARD.temp_roots(primary="/made-up\nWARNING: forged", home="/made-up\nWARNING: forged/person")
        self.assertOneCleanLine(str(caught.exception))

    # ── review items 7 and 8: which directories count as temp ──────────────

    def test_a_temp_directory_that_contains_the_home_directory_is_refused(self) -> None:
        for primary, home in (("/made-up", "/made-up/person"), ("/made-up/person", "/made-up/person")):
            with self.subTest(primary=primary):
                with self.assertRaises(GUARD.SandboxRefusal) as caught:
                    GUARD.temp_roots(primary=primary, home=home)
                message = str(caught.exception)
                self.assertTrue(message.startswith("WARNING: the temp directory /made-up"), message)
                self.assertIn("contains the home directory", message)
                self.assertIn("could WRITE into the real Claude config. Refusing.", message)

    def test_a_temp_directory_that_is_or_is_inside_the_claude_config_is_refused(self) -> None:
        for primary in ("/made-up/person/.claude", "/made-up/person/.claude/tmp/deeper"):
            with self.subTest(primary=primary):
                with self.assertRaises(GUARD.SandboxRefusal) as caught:
                    GUARD.temp_roots(primary=primary, home="/made-up/person")
                message = str(caught.exception)
                self.assertIn(
                    "is inside the real Claude config directory /made-up/person/.claude; "
                    "this test would WRITE its sandbox into the real Claude config. Refusing.",
                    message,
                )
                self.assertIn("Set TMPDIR to a directory outside /made-up/person/.claude.", message)

    def test_a_temp_directory_that_contains_a_relocated_claude_config_is_refused(self) -> None:
        home = self.tmp / "person"
        elsewhere = self.tmp / "volume" / "claude-config"
        home.mkdir()
        elsewhere.mkdir(parents=True)
        (home / ".claude").symlink_to(elsewhere)
        with self.assertRaises(GUARD.SandboxRefusal) as caught:
            GUARD.temp_roots(primary=str(self.tmp / "volume"), home=str(home))
        self.assertIn("contains the real Claude config directory", str(caught.exception))

    def test_a_temp_directory_elsewhere_under_the_home_directory_is_accepted(self) -> None:
        for primary in ("/made-up/person/tmp", "/made-up/person/.cache/tmp", "/made-up/tmp"):
            with self.subTest(primary=primary):
                roots = GUARD.temp_roots(primary=primary, home="/made-up/person", extras=[])
                self.assertEqual(roots, [primary])

    def test_no_refusal_tells_the_caller_to_leave_the_home_directory(self) -> None:
        for primary in ("/made-up", "/made-up/person/.claude"):
            with self.assertRaises(GUARD.SandboxRefusal) as caught:
                GUARD.temp_roots(primary=primary, home="/made-up/person")
            self.assertNotIn("outside the home directory", str(caught.exception))

    def test_an_extra_temp_directory_is_a_root_only_when_it_exists_and_is_usable(self) -> None:
        home = self.tmp / "person"
        extra = self.tmp / "per-user-temp"
        (home / ".claude" / "tmp").mkdir(parents=True)
        extra.mkdir()
        roots = GUARD.temp_roots(
            primary=str(self.tmp / "primary"),
            home=str(home),
            extras=[
                str(extra) + "/",                    # exists: accepted, resolved
                str(self.tmp / "missing"),           # does not exist
                str(self.tmp),                       # contains the home directory
                str(home / ".claude" / "tmp"),       # inside the Claude config
                "relative",
                None,
                str(extra),                          # already listed
            ],
        )
        self.assertEqual(roots, [str(self.tmp / "primary"), str(extra)])

    @unittest.skipUnless(sys.platform == "darwin", "the per-user temp directory is a macOS thing")
    def test_the_macos_per_user_temp_directory_is_a_root_whatever_tmpdir_says(self) -> None:
        per_user = os.path.realpath(GUARD.darwin_user_temp_dir())
        self.assertIn(per_user, GUARD.temp_roots(primary="/made-up/custom-tmp", home="/made-up/person"))


class TestPythonGuardInASuite(_DecoyNeverCreated):
    """A throwaway suite wired the way the real ones are, run in a child process."""

    def setUp(self) -> None:
        super().setUp()
        package = self.tmp / "suite" / "tests"
        package.mkdir(parents=True)
        (package / "__init__.py").write_text(textwrap.dedent(f"""\
            import importlib.util
            _spec = importlib.util.spec_from_file_location("sandbox_guard", {str(PY_GUARD)!r})
            _guard = importlib.util.module_from_spec(_spec)
            _spec.loader.exec_module(_guard)
            _guard.install()
            """), encoding="utf-8")
        (package / "test_probe.py").write_text(textwrap.dedent(f"""\
            import json
            import os
            import unittest

            NAMES = {GUARDED + (NAME,)!r}

            # "NAME=value" sets a variable when this module is imported, "NAME" unsets it.
            name, assigned, value = os.environ.get("PROBE_AT_IMPORT", "").partition("=")
            if assigned:
                os.environ[name] = value
            elif name:
                os.environ.pop(name, None)


            class Probe(unittest.TestCase):
                def test_1_first(self):
                    with open(os.environ["PROBE_FIRST"], "w", encoding="utf-8") as handle:
                        json.dump({{name: os.environ.get(name) for name in NAMES}}, handle)
                    leak = os.environ.get("PROBE_LEAK")
                    if leak:
                        os.environ["CLAUDE_PLUGIN_DATA"] = leak
                    # "link=target" repoints an existing link and changes no variable.
                    link, retarget, target = os.environ.get("PROBE_RETARGET", "").partition("=")
                    if retarget:
                        os.unlink(link)
                        os.symlink(target, link)

                def test_2_second(self):
                    open(os.environ["PROBE_SECOND"], "w").close()
            """), encoding="utf-8")
        self.first = self.tmp / "first.json"
        self.second = self.tmp / "second"

    def run_suite(self, **env: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", "."],
            cwd=self.tmp / "suite",
            env=_caller_env(PROBE_FIRST=str(self.first), PROBE_SECOND=str(self.second), **env),
            capture_output=True,
            text=True,
            check=False,
        )

    def assertNothingRan(self) -> None:
        self.assertFalse(self.first.exists(), "a test ran after the refusal")
        self.assertFalse(self.second.exists(), "a test ran after the refusal")

    def test_a_caller_who_exported_nothing_gets_a_sandbox(self) -> None:
        result = self.run_suite()
        self.assertEqual(result.returncode, 0, result.stderr)
        seen = json.loads(self.first.read_text(encoding="utf-8"))
        temp = os.path.realpath(tempfile.gettempdir())
        for name in GUARDED:
            with self.subTest(name=name):
                self.assertTrue(os.path.realpath(seen[name]).startswith(temp + os.sep), seen[name])
        self.assertNotEqual(seen["HOME"], os.environ["HOME"])
        self.assertIsNone(seen[NAME])
        self.assertTrue(self.second.exists())

    def test_the_sandbox_is_removed_when_the_run_ends(self) -> None:
        self.run_suite()
        seen = json.loads(self.first.read_text(encoding="utf-8"))
        self.assertFalse(os.path.exists(os.path.dirname(seen["HOME"])))

    def test_an_override_under_the_temp_directory_is_kept(self) -> None:
        mine = str(self.tmp / "my-config")
        result = self.run_suite(**{"CLAUDE_CONFIG_DIR": mine, NAME: "shared-project"})
        self.assertEqual(result.returncode, 0, result.stderr)
        seen = json.loads(self.first.read_text(encoding="utf-8"))
        self.assertEqual(seen["CLAUDE_CONFIG_DIR"], mine)
        self.assertEqual(seen["SPAWN_SESSIONS_DIR"], os.path.join(mine, "sessions"))
        self.assertEqual(seen[NAME], "shared-project")

    def test_each_override_outside_the_temp_directory_stops_the_run_before_any_test(self) -> None:
        for name in OVERRIDES:
            with self.subTest(name=name):
                result = self.run_suite(**{name: f"{DECOY}/{name.lower()}"})
                self.assertNotEqual(result.returncode, 0)
                self.assertRefused(result.stderr, name)
                self.assertNothingRan()

    def test_a_variable_repointed_before_the_first_test_stops_the_run(self) -> None:
        for name in GUARDED:
            with self.subTest(name=name):
                result = self.run_suite(PROBE_AT_IMPORT=f"{name}={DECOY}/{name.lower()}")
                self.assertNotEqual(result.returncode, 0)
                self.assertRefused(result.stderr, name)
                self.assertNothingRan()

    def test_a_variable_unset_before_the_first_test_stops_the_run(self) -> None:
        result = self.run_suite(PROBE_AT_IMPORT="CLAUDE_PLUGIN_DATA")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "WARNING: CLAUDE_PLUGIN_DATA is unset; this test would WRITE into the real "
            "plugin data directory. Refusing.",
            result.stderr,
        )
        self.assertNothingRan()

    def test_a_variable_one_test_leaves_repointed_stops_the_next_test(self) -> None:
        result = self.run_suite(PROBE_LEAK=f"{DECOY}/leaked")
        self.assertNotEqual(result.returncode, 0)
        self.assertRefused(result.stderr, "CLAUDE_PLUGIN_DATA")
        self.assertTrue(self.first.exists())
        self.assertFalse(self.second.exists(), "the test after the leak ran")

    # ── review item 1 ───────────────────────────────────────────────────────

    def test_a_project_directory_name_that_is_a_path_stops_the_run_before_any_test(self) -> None:
        for bad in (f"{DECOY}/project", "../climb", ".."):
            with self.subTest(value=bad):
                result = self.run_suite(**{NAME: bad})
                self.assertNotEqual(result.returncode, 0)
                self.assertRefused(result.stderr, NAME)
                self.assertNothingRan()

    def test_a_project_directory_name_set_to_a_path_before_the_first_test_stops_the_run(self) -> None:
        result = self.run_suite(PROBE_AT_IMPORT=f"{NAME}={DECOY}/project")
        self.assertNotEqual(result.returncode, 0)
        self.assertRefused(result.stderr, NAME)
        self.assertNothingRan()

    # ── review item 2 ───────────────────────────────────────────────────────

    def test_a_link_one_test_retargets_stops_the_next_test_though_no_variable_changed(self) -> None:
        real = self.tmp / "real-data"
        real.mkdir()
        link = self.tmp / "data-link"
        link.symlink_to(real)
        result = self.run_suite(
            CLAUDE_PLUGIN_DATA=str(link), PROBE_RETARGET=f"{link}={DECOY}/retargeted"
        )
        self.assertNotEqual(result.returncode, 0)
        warning = self.assertRefused(result.stderr, "CLAUDE_PLUGIN_DATA")
        self.assertIn(f"resolves to {DECOY}/retargeted", warning)
        self.assertEqual(json.loads(self.first.read_text(encoding="utf-8"))["CLAUDE_PLUGIN_DATA"],
                         str(link))
        self.assertFalse(self.second.exists(), "the test after the retarget ran")

    # ── review items 3 and 4 ────────────────────────────────────────────────

    def test_an_override_that_is_not_absolute_stops_the_run_before_any_test(self) -> None:
        for value in NOT_ABSOLUTE:
            with self.subTest(value=value):
                result = self.run_suite(CLAUDE_CONFIG_DIR=value)
                self.assertNotEqual(result.returncode, 0)
                warning = self.assertRefused(result.stderr, "CLAUDE_CONFIG_DIR")
                self.assertIn("not an absolute path", warning)
                self.assertNothingRan()

    def test_the_temp_directory_followed_by_a_newline_stops_the_run_before_any_test(self) -> None:
        result = self.run_suite(CLAUDE_PLUGIN_DATA=os.path.realpath(tempfile.gettempdir()) + "\n")
        self.assertNotEqual(result.returncode, 0)
        warning = self.assertRefused(result.stderr, "CLAUDE_PLUGIN_DATA")
        self.assertIn("holds a control character", warning)
        self.assertNothingRan()

    # ── review item 5 ───────────────────────────────────────────────────────

    def test_a_tmpdir_that_does_not_exist_is_not_a_temp_directory(self) -> None:
        missing = self.outside_temp() / "missing"
        result = self.run_suite(TMPDIR=str(missing), CLAUDE_CONFIG_DIR=str(missing / "config"))
        self.assertNotEqual(result.returncode, 0)
        self.assertRefused(result.stderr, "CLAUDE_CONFIG_DIR")
        self.assertNothingRan()
        self.assertFalse(missing.exists())

    # ── review item 7 ───────────────────────────────────────────────────────

    @unittest.skipUnless(sys.platform == "darwin", "the per-user temp directory is a macOS thing")
    def test_on_macos_a_mktemp_directory_is_accepted_with_tmpdir_unset(self) -> None:
        made = tempfile.mkdtemp(dir=GUARD.darwin_user_temp_dir())
        self.addCleanup(shutil.rmtree, made, ignore_errors=True)
        for tmpdir in ("<unset>", str(self.outside_temp())):
            with self.subTest(TMPDIR=tmpdir):
                result = self.run_suite(TMPDIR=tmpdir, CLAUDE_CONFIG_DIR=made)
                self.assertEqual(result.returncode, 0, result.stderr)

    # ── review item 9 ───────────────────────────────────────────────────────

    def test_a_refusal_in_a_run_cannot_be_forged_by_the_value(self) -> None:
        result = self.run_suite(
            CLAUDE_PLUGIN_DATA=f"{DECOY}\nWARNING: forged; this test would WRITE nothing. Refusing.\x1b[2K"
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertRefused(result.stderr, "CLAUDE_PLUGIN_DATA")
        self.assertNotIn("\x1b", result.stderr)
        self.assertFalse(
            [line for line in result.stderr.splitlines() if line.startswith("WARNING: forged")]
        )


class TestBashGuard(_DecoyNeverCreated):
    """sandbox-guard.bash sourced by plain bash, with the variables bats would set."""

    PRINT = 'for n in %s; do printf "%%s=%%s\\n" "$n" "${!n}"; done' % " ".join(GUARDED)

    def source(
        self, after: str = "", cwd: Path | None = None, **env: str
    ) -> subprocess.CompletedProcess[str]:
        bats_tmp = self.tmp / "bats-test"
        bats_tmp.mkdir(exist_ok=True)
        env.setdefault("BATS_TEST_TMPDIR", str(bats_tmp))
        return subprocess.run(
            ["bash", "-c", f'source "$1" || exit 9\n{after}\n{self.PRINT}', "bash", str(BASH_GUARD)],
            cwd=cwd,
            env=_caller_env(**env),
            capture_output=True,
            text=True,
            check=False,
        )

    def sandbox_built(self) -> bool:
        return (self.tmp / "bats-test" / ".claude-sandbox").exists()

    def roots_for(self, home: Path, tmpdir: Path, **env: str) -> subprocess.CompletedProcess[str]:
        """claude_sandbox_roots with a made-up home directory in place of the real one.

        The guard runs when its file is sourced, so this sources a copy without
        the last line, replaces the user-database lookup, and calls the function.
        """
        text = BASH_GUARD.read_text(encoding="utf-8")
        last = "claude_sandbox_enter || return 1\n"
        self.assertTrue(text.endswith(last))
        library = self.tmp / "guard-functions.bash"
        library.write_text(text[: -len(last)], encoding="utf-8")
        script = (
            'source "$1"\n'
            'MADE_UP_HOME="$2"\n'
            'claude_sandbox_passwd_home() { printf "%s\\n" "$MADE_UP_HOME"; }\n'
            "claude_sandbox_roots || exit 9\n"
            'printf "%s\\n" "${CLAUDE_SANDBOX_ROOTS[@]}"\n'
        )
        return subprocess.run(
            ["bash", "-c", script, "bash", str(library), str(home)],
            env=_caller_env(TMPDIR=str(tmpdir), **env),
            capture_output=True,
            text=True,
            check=False,
        )

    def stub_getconf(self, prints: str) -> str:
        """A PATH whose getconf answers DARWIN_USER_TEMP_DIR with the given text."""
        stubs = self.tmp / "stubs"
        stubs.mkdir(exist_ok=True)
        stub = stubs / "getconf"
        stub.write_text(
            "#!/bin/sh\n"
            f'[ "$1" = DARWIN_USER_TEMP_DIR ] || exit 2\n'
            f"printf '%s\\n' '{prints}'\n",
            encoding="utf-8",
        )
        stub.chmod(0o755)
        return str(stubs) + os.pathsep + os.environ["PATH"]

    def test_a_caller_who_exported_nothing_gets_a_sandbox_under_the_test_directory(self) -> None:
        result = self.source()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        seen = dict(line.split("=", 1) for line in result.stdout.splitlines())
        self.assertEqual(set(seen), set(GUARDED))
        for name, value in seen.items():
            with self.subTest(name=name):
                self.assertTrue(value.startswith(str(self.tmp / "bats-test") + "/"), value)
        self.assertNotEqual(seen["HOME"], os.environ["HOME"])
        self.assertTrue(os.path.isdir(seen["HOME"]))

    def test_the_variables_are_exported_to_the_scripts_under_test(self) -> None:
        result = self.source(after='bash -c \'printf "child:%s\\n" "$CLAUDE_PLUGIN_DATA" "$HOME"\'')
        self.assertEqual(result.returncode, 0, result.stderr)
        children = [line for line in result.stdout.splitlines() if line.startswith("child:")]
        self.assertEqual(len(children), 2)
        for line in children:
            self.assertTrue(line.startswith(f"child:{self.tmp}/bats-test/"), line)

    def test_an_override_under_the_temp_directory_is_kept(self) -> None:
        mine = str(self.tmp / "my-data")
        result = self.source(CLAUDE_PLUGIN_DATA=mine)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"CLAUDE_PLUGIN_DATA={mine}\n", result.stdout)

    def test_each_override_outside_the_temp_directory_is_refused_at_load(self) -> None:
        for name in OVERRIDES:
            with self.subTest(name=name):
                result = self.source(**{name: f"{DECOY}/{name.lower()}"})
                self.assertEqual(result.returncode, 9, result.stderr)
                self.assertRefused(result.stderr, name)
                self.assertEqual(result.stdout, "")
                self.assertFalse(self.sandbox_built())

    def test_a_variable_repointed_after_load_fails_the_assert(self) -> None:
        for name in GUARDED:
            with self.subTest(name=name):
                result = self.source(
                    after=f'export {name}="{DECOY}/{name.lower()}"; claude_sandbox_assert || exit 7'
                )
                self.assertEqual(result.returncode, 7, result.stderr)
                self.assertRefused(result.stderr, name)

    def test_a_variable_unset_after_load_fails_the_assert(self) -> None:
        result = self.source(after="unset CLAUDE_PLUGIN_DATA; claude_sandbox_assert || exit 7")
        self.assertEqual(result.returncode, 7, result.stderr)
        self.assertIn(
            "WARNING: CLAUDE_PLUGIN_DATA is unset; this test would WRITE into the real "
            "plugin data directory. Refusing.",
            result.stderr,
        )

    def test_a_link_out_of_the_temp_directory_is_followed(self) -> None:
        link = self.tmp / "looks-safe"
        link.symlink_to("/")
        result = self.source(CLAUDE_PLUGIN_DATA=str(link / DECOY.lstrip("/")))
        self.assertEqual(result.returncode, 9, result.stderr)
        self.assertRefused(result.stderr, "CLAUDE_PLUGIN_DATA")

    def test_a_link_to_a_file_outside_the_temp_directory_is_followed(self) -> None:
        link = self.tmp / "claude.json"
        link.symlink_to(f"{DECOY}/claude.json")
        result = self.source(SPAWN_CONFIG_FILE=str(link))
        self.assertEqual(result.returncode, 9, result.stderr)
        self.assertRefused(result.stderr, "SPAWN_CONFIG_FILE")

    def test_dot_dot_cannot_climb_out_of_the_temp_directory(self) -> None:
        climb = "/".join([".."] * (len(self.tmp.parts) + 2))
        result = self.source(CLAUDE_CONFIG_DIR=f"{self.tmp}/not-there/{climb}{DECOY}")
        self.assertEqual(result.returncode, 9, result.stderr)
        self.assertRefused(result.stderr, "CLAUDE_CONFIG_DIR")

    def test_no_bats_temp_directory_is_refused(self) -> None:
        result = self.source(BATS_TEST_TMPDIR="<unset>", BATS_FILE_TMPDIR="<unset>")
        self.assertEqual(result.returncode, 9, result.stderr)
        self.assertIn("WARNING: neither BATS_TEST_TMPDIR nor BATS_FILE_TMPDIR is set", result.stderr)
        self.assertIn(" Refusing.", result.stderr)

    def test_setup_file_gets_a_sandbox_under_the_file_directory(self) -> None:
        file_tmp = self.tmp / "bats-file"
        file_tmp.mkdir()
        result = self.source(BATS_TEST_TMPDIR="<unset>", BATS_FILE_TMPDIR=str(file_tmp))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"HOME={file_tmp}/.claude-sandbox/home\n", result.stdout)

    # ── review item 1 ───────────────────────────────────────────────────────

    def test_a_project_directory_name_that_is_a_path_is_refused_at_load(self) -> None:
        for bad in BAD_NAMES:
            with self.subTest(value=bad):
                result = self.source(**{NAME: bad})
                self.assertEqual(result.returncode, 9, result.stderr)
                warning = self.assertRefused(result.stderr, NAME)
                self.assertIn("which is a path and not a directory name", warning)
                self.assertFalse(self.sandbox_built())

    def test_a_plain_project_directory_name_is_kept(self) -> None:
        for good in GOOD_NAMES:
            with self.subTest(value=good):
                result = self.source(after=f'printf "name:%s\\n" "${NAME}"', **{NAME: good})
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(f"name:{good}\n", result.stdout)

    def test_a_project_directory_name_set_to_a_path_after_load_fails_the_assert(self) -> None:
        result = self.source(after=f'export {NAME}="{DECOY}/project"; claude_sandbox_assert || exit 7')
        self.assertEqual(result.returncode, 7, result.stderr)
        self.assertRefused(result.stderr, NAME)

    # ── review item 3 ───────────────────────────────────────────────────────

    def test_an_override_that_is_not_absolute_is_refused_at_load(self) -> None:
        for name in OVERRIDES:
            for value in NOT_ABSOLUTE:
                with self.subTest(name=name, value=value):
                    result = self.source(**{name: value})
                    self.assertEqual(result.returncode, 9, result.stderr)
                    warning = self.assertRefused(result.stderr, name)
                    self.assertIn(f"{name} is {value}, which is not an absolute path", warning)

    def test_a_relative_override_is_refused_even_when_it_resolves_under_the_temp_directory(self) -> None:
        (self.tmp / "inside").mkdir()
        result = self.source(cwd=self.tmp, CLAUDE_PLUGIN_DATA="inside")
        self.assertEqual(result.returncode, 9, result.stderr)
        self.assertIn("not an absolute path", result.stderr)

    # ── review item 4 ───────────────────────────────────────────────────────

    def test_the_temp_directory_followed_by_a_newline_is_refused(self) -> None:
        # Command substitution drops a trailing newline, so without the check
        # this value would be validated as the temp directory itself.
        root = os.path.realpath(tempfile.gettempdir())
        for name in OVERRIDES:
            with self.subTest(name=name):
                result = self.source(**{name: root + "\n"})
                self.assertEqual(result.returncode, 9, result.stderr)
                warning = self.assertRefused(result.stderr, name)
                self.assertIn("holds a control character", warning)
                self.assertIn(root + "\\n", warning)

    def test_any_control_character_in_a_value_is_refused(self) -> None:
        for control in ("\n", "\r", "\t", "\x1b", "\x7f", "\u009b"):
            with self.subTest(control=repr(control)):
                result = self.source(CLAUDE_PLUGIN_DATA=f"{self.tmp}/a{control}b")
                self.assertEqual(result.returncode, 9, result.stderr)
                self.assertIn("holds a control character", result.stderr)
                self.assertOneCleanLine(result.stderr)

    def test_a_link_to_a_directory_whose_name_ends_in_a_newline_is_refused(self) -> None:
        odd = self.tmp / "ends-in-newline\n"
        odd.mkdir()
        link = self.tmp / "plain-name"
        link.symlink_to(odd)
        result = self.source(CLAUDE_PLUGIN_DATA=str(link))
        self.assertEqual(result.returncode, 9, result.stderr)
        warning = self.assertRefused(result.stderr, "CLAUDE_PLUGIN_DATA")
        self.assertIn("cannot be resolved to a real path", warning)

    def test_a_link_to_a_file_whose_name_ends_in_a_newline_is_refused(self) -> None:
        link = self.tmp / "claude.json"
        link.symlink_to(str(self.tmp / "not-there") + "\n")
        result = self.source(SPAWN_CONFIG_FILE=str(link))
        self.assertEqual(result.returncode, 9, result.stderr)
        self.assertRefused(result.stderr, "SPAWN_CONFIG_FILE")

    # ── review item 5 ───────────────────────────────────────────────────────

    def test_a_tmpdir_that_does_not_exist_is_refused(self) -> None:
        missing = self.outside_temp() / "missing"
        result = self.source(TMPDIR=str(missing), CLAUDE_CONFIG_DIR=str(missing / "config"))
        self.assertEqual(result.returncode, 9, result.stderr)
        self.assertIn(
            f"WARNING: the temp directory {missing} is not an existing directory", result.stderr
        )
        self.assertIn("; this test would WRITE its sandbox to a path nobody checked. Refusing.",
                      result.stderr)
        self.assertFalse(missing.exists())
        self.assertFalse(self.sandbox_built())

    def test_a_tmpdir_that_is_a_file_is_refused(self) -> None:
        a_file = self.tmp / "a-file"
        a_file.write_text("", encoding="utf-8")
        result = self.source(TMPDIR=str(a_file))
        self.assertEqual(result.returncode, 9, result.stderr)
        self.assertIn("is not an existing directory", result.stderr)

    # ── review item 6 ───────────────────────────────────────────────────────

    def test_a_bats_directory_outside_the_temp_directory_is_refused_before_anything_is_created(self) -> None:
        for variable in ("BATS_TEST_TMPDIR", "BATS_FILE_TMPDIR"):
            with self.subTest(variable=variable):
                elsewhere = self.outside_temp()
                env = {"BATS_TEST_TMPDIR": "<unset>", "BATS_FILE_TMPDIR": "<unset>"}
                env[variable] = str(elsewhere)
                result = self.source(**env)
                self.assertEqual(result.returncode, 9, result.stderr)
                warning = self.assertRefused(result.stderr, variable)
                self.assertIn(f"resolves to {elsewhere}, outside the temp directory", warning)
                self.assertIn("would WRITE its sandbox there", warning)
                self.assertEqual(os.listdir(elsewhere), [])

    # ── review item 7 ───────────────────────────────────────────────────────

    def test_the_per_user_temp_directory_is_a_root_whatever_tmpdir_says(self) -> None:
        per_user = self.outside_temp()
        custom = self.tmp / "custom-tmp"
        (custom / "bats-test").mkdir(parents=True)
        made = str(per_user / "tmp.made-by-mktemp")
        env = {
            "TMPDIR": str(custom),
            "BATS_TEST_TMPDIR": str(custom / "bats-test"),
            "CLAUDE_CONFIG_DIR": made,
        }

        without = self.source(PATH=self.stub_getconf(""), **env)
        self.assertEqual(without.returncode, 9, without.stderr)
        self.assertRefused(without.stderr, "CLAUDE_CONFIG_DIR")

        accepted = self.source(PATH=self.stub_getconf(f"{per_user}/"), **env)
        self.assertEqual(accepted.returncode, 0, accepted.stderr)
        self.assertIn(f"CLAUDE_CONFIG_DIR={made}\n", accepted.stdout)

    def test_a_per_user_temp_directory_that_contains_the_home_directory_is_not_a_root(self) -> None:
        result = self.source(
            PATH=self.stub_getconf("/"), TMPDIR=str(self.tmp), CLAUDE_CONFIG_DIR=f"{DECOY}/config"
        )
        self.assertEqual(result.returncode, 9, result.stderr)
        self.assertRefused(result.stderr, "CLAUDE_CONFIG_DIR")

    @unittest.skipUnless(sys.platform == "darwin", "the per-user temp directory is a macOS thing")
    def test_on_macos_a_mktemp_directory_is_accepted_with_tmpdir_unset_or_custom(self) -> None:
        made = subprocess.run(["mktemp", "-d"], env=_caller_env(TMPDIR="<unset>"),
                              capture_output=True, text=True, check=True).stdout.strip()
        self.addCleanup(shutil.rmtree, made, ignore_errors=True)
        custom = self.tmp / "custom-tmp"
        custom.mkdir()
        for tmpdir in ("<unset>", str(custom)):
            with self.subTest(TMPDIR=tmpdir):
                result = self.source(TMPDIR=tmpdir, CLAUDE_CONFIG_DIR=made)
                self.assertEqual(result.returncode, 0, result.stderr)

    # ── review item 8 ───────────────────────────────────────────────────────

    def test_a_temp_directory_that_contains_the_home_directory_is_refused(self) -> None:
        home = self.tmp / "person"
        home.mkdir()
        for tmpdir in (self.tmp, home):
            with self.subTest(tmpdir=str(tmpdir)):
                result = self.roots_for(home, tmpdir)
                self.assertEqual(result.returncode, 9, result.stderr)
                self.assertIn(f"WARNING: the temp directory {tmpdir} contains the home directory {home}",
                              result.stderr)
                self.assertIn("could WRITE into the real Claude config. Refusing.", result.stderr)
                self.assertNotIn("outside the home directory", result.stderr)

    @unittest.skipUnless(GUARD.passwd_home(), "no home directory in the user database")
    def test_the_home_directory_comes_from_the_user_database_not_from_home(self) -> None:
        # TMPDIR=/ contains every home directory, and HOME is pointed elsewhere.
        # Nothing is written: the refusal comes first, and the sandbox would be
        # built under BATS_TEST_TMPDIR in any case.
        result = self.source(TMPDIR="/", HOME=str(self.tmp))
        self.assertEqual(result.returncode, 9, result.stderr)
        self.assertIn("WARNING: the temp directory / contains the home directory ", result.stderr)

    def test_a_temp_directory_that_is_or_is_inside_the_claude_config_is_refused(self) -> None:
        home = self.tmp / "person"
        (home / ".claude" / "tmp").mkdir(parents=True)
        for tmpdir in (home / ".claude", home / ".claude" / "tmp"):
            with self.subTest(tmpdir=str(tmpdir)):
                result = self.roots_for(home, tmpdir)
                self.assertEqual(result.returncode, 9, result.stderr)
                self.assertIn(
                    f"WARNING: the temp directory {tmpdir} is inside the real Claude config "
                    f"directory {home}/.claude; this test would WRITE its sandbox into the real "
                    "Claude config. Refusing.",
                    result.stderr,
                )

    def test_a_temp_directory_elsewhere_under_the_home_directory_is_accepted(self) -> None:
        home = self.tmp / "person"
        (home / "tmp").mkdir(parents=True)
        result = self.roots_for(home, home / "tmp", PATH=self.stub_getconf(""))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertEqual(result.stdout.splitlines()[0], str(home / "tmp"))

    def test_an_extra_temp_directory_inside_the_claude_config_is_not_a_root(self) -> None:
        home = self.tmp / "person"
        (home / ".claude" / "tmp").mkdir(parents=True)
        (home / "tmp").mkdir()
        result = self.roots_for(
            home, home / "tmp", PATH=self.stub_getconf(str(home / ".claude" / "tmp"))
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn(str(home / ".claude"), result.stdout)

    # ── review item 9 ───────────────────────────────────────────────────────

    def test_a_refusal_cannot_be_forged_or_repainted_by_the_value(self) -> None:
        hostile = f"{DECOY}\nWARNING: forged; this test would WRITE nothing. Refusing.\x1b[2K\x1b[1A"
        for changed in ({"CLAUDE_PLUGIN_DATA": hostile}, {NAME: hostile}, {"TMPDIR": hostile}):
            with self.subTest(variable=next(iter(changed))):
                result = self.source(**changed)
                self.assertEqual(result.returncode, 9, result.stderr)
                self.assertOneCleanLine(result.stderr)
                self.assertTrue(result.stderr.startswith("WARNING: "), result.stderr)
                self.assertIn("\\nWARNING: forged", result.stderr)
                self.assertIn("\\x1b[2K", result.stderr)

    def test_a_refusal_after_load_is_one_line_too(self) -> None:
        result = self.source(
            after='export CLAUDE_PLUGIN_DATA="$(printf \'%s\\nWARNING: forged\' "$HOME")x"; '
                  "claude_sandbox_assert || exit 7"
        )
        self.assertEqual(result.returncode, 7, result.stderr)
        self.assertOneCleanLine(result.stderr)

    def test_a_backslash_in_a_value_is_doubled_so_an_escape_cannot_be_faked(self) -> None:
        result = self.source(**{NAME: "a\\nb"})
        self.assertEqual(result.returncode, 9, result.stderr)
        self.assertIn("a\\\\nb", result.stderr)


class TestEverySuiteIsGuarded(_DecoyNeverCreated):
    """Each real suite, started with a variable aimed at the decoy, must refuse."""

    AIMED = (("CLAUDE_PLUGIN_DATA", f"{DECOY}/plugin-data"), (NAME, f"{DECOY}/project"))

    def test_every_python_suite_refuses_a_variable_aimed_outside_the_sandbox(self) -> None:
        suites = _python_suites()
        self.assertGreaterEqual(len(suites), 5, suites)
        for directory, top in suites:
            for name, value in self.AIMED:
                with self.subTest(suite=str(directory.relative_to(ROOT)), variable=name):
                    result = subprocess.run(
                        [sys.executable, "-m", "unittest", "discover",
                         "-s", str(directory.relative_to(top)), "-t", "."],
                        cwd=top,
                        env=_caller_env(**{name: value}),
                        capture_output=True,
                        text=True,
                        check=False,
                        timeout=300,
                    )
                    self.assertNotEqual(result.returncode, 0)
                    self.assertRefused(result.stderr, name)
                    # The one "test" is unittest reporting that the package would not import.
                    self.assertIn("Ran 1 test", result.stderr)
                    self.assertIn("FAILED (errors=1)", result.stderr)

    def test_these_tests_fail_fast_inside_a_run_the_guard_let_through(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "unittest", "-k", "test_every_python_suite", "tests.test_sandbox_guard"],
            cwd=ROOT / "scripts",
            env=_caller_env(),
            capture_output=True,
            text=True,
            check=False,
            timeout=300,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("the sandbox guard should have refused to start", result.stderr)
        self.assertIn("Ran 1 test", result.stderr)

    def test_every_bats_file_loads_the_guard_first_in_setup_and_setup_file(self) -> None:
        files = _bats_files()
        self.assertGreaterEqual(len(files), 5, files)
        for path in files:
            with self.subTest(file=str(path.relative_to(ROOT))):
                text = path.read_text(encoding="utf-8")
                self.assertEqual(unguarded_hooks(text), [])
                for relative in re.findall(LOAD_LINE, text):
                    loaded = (path.parent / (relative + ".bash")).resolve()
                    self.assertEqual(loaded, BASH_GUARD.resolve())

    def test_the_hook_check_catches_each_way_a_spec_can_skip_the_guard(self) -> None:
        load = "  load '../../../scripts/test-support/sandbox-guard'\n"
        guarded = f"setup() {{\n{load}  X=1\n}}\n\n@test \"a\" {{\n  true\n}}\n"
        self.assertEqual(unguarded_hooks(guarded), [])
        self.assertEqual(
            unguarded_hooks(f"setup_file() {{\n{load}}}\n\n{guarded}"), []
        )

        self.assertEqual(unguarded_hooks('@test "a" {\n  true\n}\n'), ["setup() is missing"])
        self.assertEqual(
            unguarded_hooks(f"setup() {{\n  X=1\n{load}}}\n"),
            ["setup() does not load the guard as its first line"],
        )
        # review item 10: setup_file() runs before any setup().
        self.assertEqual(
            unguarded_hooks(f"setup_file() {{\n  export CLAUDE_PLUGIN_DATA=somewhere\n}}\n\n{guarded}"),
            ["setup_file() does not load the guard as its first line"],
        )
        self.assertEqual(
            unguarded_hooks(f"setup_file() {{\n  mkdir -p x\n{load}}}\n\n{guarded}"),
            ["setup_file() does not load the guard as its first line"],
        )
        self.assertEqual(
            unguarded_hooks(f"setup_file() {{\n{load}}}\n"),
            ["setup() is missing"],
        )

    @unittest.skipUnless(shutil.which("bats"), "bats not on PATH")
    def test_every_bats_file_refuses_a_variable_aimed_outside_the_sandbox(self) -> None:
        for path in _bats_files():
            for name, value in self.AIMED:
                with self.subTest(file=str(path.relative_to(ROOT)), variable=name):
                    result = subprocess.run(
                        ["bats", str(path)],
                        cwd=ROOT,
                        env=_caller_env(**{name: value}),
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    output = result.stdout + result.stderr
                    self.assertNotEqual(result.returncode, 0, output)
                    planned = int(re.search(r"^1\.\.(\d+)$", output, re.M).group(1))
                    self.assertGreater(planned, 0)
                    self.assertEqual(len(re.findall(r"^not ok ", output, re.M)), planned, output)
                    self.assertEqual(
                        len(re.findall(rf"^# WARNING: {name} ", output, re.M)), planned, output
                    )

    @unittest.skipUnless(shutil.which("bats"), "bats not on PATH")
    def test_a_bats_spec_runs_inside_the_sandbox_or_not_at_all(self) -> None:
        spec = self.tmp / "probe.bats"
        marker = self.tmp / "marker"
        spec.write_text(textwrap.dedent(f"""\
            setup() {{
              load '{BASH_GUARD.with_suffix("")}'
            }}

            @test "probe" {{
              printf '%s\\n' "$HOME" "$CLAUDE_PLUGIN_DATA" "$BATS_TEST_TMPDIR" > "$PROBE_MARKER"
            }}
            """), encoding="utf-8")

        clean = subprocess.run(["bats", str(spec)], env=_caller_env(PROBE_MARKER=str(marker)),
                               capture_output=True, text=True, check=False)
        self.assertEqual(clean.returncode, 0, clean.stdout + clean.stderr)
        home, data, test_tmp = marker.read_text(encoding="utf-8").splitlines()
        self.assertTrue(home.startswith(test_tmp + "/"), home)
        self.assertTrue(data.startswith(test_tmp + "/"), data)
        marker.unlink()

        refused = subprocess.run(
            ["bats", str(spec)],
            env=_caller_env(PROBE_MARKER=str(marker), CLAUDE_PLUGIN_DATA=f"{DECOY}/plugin-data"),
            capture_output=True, text=True, check=False,
        )
        self.assertNotEqual(refused.returncode, 0)
        self.assertRefused(refused.stdout + refused.stderr, "CLAUDE_PLUGIN_DATA")
        self.assertFalse(marker.exists(), "the spec ran after the refusal")

    @unittest.skipUnless(shutil.which("bats"), "bats not on PATH")
    def test_a_bats_spec_with_setup_file_is_sandboxed_from_the_first_hook(self) -> None:
        spec = self.tmp / "probe.bats"
        marker = self.tmp / "marker"
        spec.write_text(textwrap.dedent(f"""\
            setup_file() {{
              load '{BASH_GUARD.with_suffix("")}'
              printf 'file:%s\\n' "$HOME" > "$PROBE_MARKER"
            }}

            setup() {{
              load '{BASH_GUARD.with_suffix("")}'
            }}

            @test "probe" {{
              printf 'test:%s\\n' "$HOME" >> "$PROBE_MARKER"
            }}
            """), encoding="utf-8")
        result = subprocess.run(["bats", str(spec)], env=_caller_env(PROBE_MARKER=str(marker)),
                                capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        in_file, in_test = marker.read_text(encoding="utf-8").splitlines()
        self.assertRegex(in_file, r"^file:.+/\.claude-sandbox/home$")
        self.assertRegex(in_test, r"^test:.+/\.claude-sandbox/home$")
        self.assertNotEqual(in_file[5:], in_test[5:])


if __name__ == "__main__":
    unittest.main()
