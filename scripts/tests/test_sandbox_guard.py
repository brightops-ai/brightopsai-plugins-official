"""The test sandbox guard in scripts/test-support/, and that every suite uses it.

The guard is what keeps a test out of the real Claude config and plugin data,
so these tests never aim at a real directory to prove it. The "outside the temp
directory" target is a decoy at the filesystem root that does not exist and is
never created: every case that names it must be refused before anything runs.
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

DECOY = "/claude-sandbox-decoy-never-created"

SKIP_DIRS = {".git", "node_modules", "__pycache__"}


def _load_guard():
    spec = importlib.util.spec_from_file_location("sandbox_guard_under_test", PY_GUARD)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _caller_env(**extra: str) -> dict[str, str]:
    """The environment of a caller who exported none of the overrides."""
    env = {k: v for k, v in os.environ.items() if k not in OVERRIDES}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.update(extra)
    return env


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


class _DecoyNeverCreated(unittest.TestCase):
    def setUp(self) -> None:
        self.assertFalse(os.path.lexists(DECOY), f"{DECOY} exists; these tests need it absent")
        self.addCleanup(
            lambda: self.assertFalse(os.path.lexists(DECOY), f"a refused run created {DECOY}")
        )
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(os.path.realpath(tmp.name))

    def assertRefused(self, text: str, name: str) -> None:
        lines = [line for line in text.splitlines() if "WARNING: " in line]
        self.assertTrue(lines, f"no WARNING line in:\n{text}")
        warning = lines[0][lines[0].index("WARNING: "):]
        self.assertTrue(warning.startswith(f"WARNING: {name} "), warning)
        self.assertIn("; this test would WRITE ", warning)
        self.assertIn(" Refusing.", warning)


class TestPythonGuardRules(_DecoyNeverCreated):
    """The checks themselves, called directly with a made-up environment."""

    def setUp(self) -> None:
        super().setUp()
        self.guard = _load_guard()
        self.roots = [str(self.tmp)]
        self.env = {name: str(self.tmp / name.lower()) for name in GUARDED}

    def test_every_variable_under_the_temp_directory_passes(self) -> None:
        self.guard.check(self.env, self.roots)

    def test_each_variable_is_refused_outside_the_temp_directory(self) -> None:
        for name in GUARDED:
            with self.subTest(name=name):
                env = dict(self.env, **{name: f"{DECOY}/{name.lower()}"})
                with self.assertRaises(self.guard.SandboxRefusal) as caught:
                    self.guard.check(env, self.roots)
                self.assertRefused(str(caught.exception), name)
                self.assertIn(f"resolves to {DECOY}/", str(caught.exception))

    def test_each_variable_is_refused_when_unset_or_empty(self) -> None:
        for name in GUARDED:
            for missing in (None, ""):
                with self.subTest(name=name, missing=missing):
                    env = dict(self.env)
                    if missing is None:
                        del env[name]
                    else:
                        env[name] = missing
                    with self.assertRaises(self.guard.SandboxRefusal) as caught:
                        self.guard.check(env, self.roots)
                    self.assertRefused(str(caught.exception), name)
                    state = "unset" if missing is None else "empty"
                    self.assertIn(f"{name} is {state}; this test would WRITE into the real ",
                                  str(caught.exception))

    def test_the_documented_example_is_the_message(self) -> None:
        env = dict(self.env)
        del env["CLAUDE_PLUGIN_DATA"]
        with self.assertRaises(self.guard.SandboxRefusal) as caught:
            self.guard.check(env, self.roots)
        self.assertTrue(str(caught.exception).startswith(
            "WARNING: CLAUDE_PLUGIN_DATA is unset; this test would WRITE into the real "
            "plugin data directory. Refusing."
        ), str(caught.exception))

    def test_a_link_out_of_the_temp_directory_is_followed(self) -> None:
        link = self.tmp / "looks-safe"
        link.symlink_to("/")
        env = dict(self.env, CLAUDE_PLUGIN_DATA=str(link / DECOY.lstrip("/")))
        with self.assertRaises(self.guard.SandboxRefusal) as caught:
            self.guard.check(env, self.roots)
        self.assertRefused(str(caught.exception), "CLAUDE_PLUGIN_DATA")

    def test_dot_dot_cannot_climb_out_of_the_temp_directory(self) -> None:
        climb = "/".join([".."] * (len(self.tmp.parts) + 2))
        env = dict(self.env, CLAUDE_CONFIG_DIR=f"{self.tmp}/not-there/{climb}{DECOY}")
        with self.assertRaises(self.guard.SandboxRefusal) as caught:
            self.guard.check(env, self.roots)
        self.assertRefused(str(caught.exception), "CLAUDE_CONFIG_DIR")

    def test_a_sibling_whose_name_starts_like_the_temp_directory_is_outside(self) -> None:
        self.assertTrue(self.guard.within("/t/a", "/t"))
        self.assertTrue(self.guard.within("/t", "/t"))
        self.assertFalse(self.guard.within("/t-other/a", "/t"))

    def test_a_temp_directory_that_contains_the_home_directory_is_refused(self) -> None:
        for primary, home in (("/made-up", "/made-up/person"), ("/made-up/person", "/made-up/person")):
            with self.subTest(primary=primary):
                with self.assertRaises(self.guard.SandboxRefusal) as caught:
                    self.guard.temp_roots(primary=primary, home=home)
                message = str(caught.exception)
                self.assertTrue(message.startswith("WARNING: the temp directory /made-up"), message)
                self.assertIn("contains the home directory", message)
                self.assertIn("could WRITE into the real Claude config. Refusing.", message)

    def test_a_temp_directory_beside_the_home_directory_is_accepted(self) -> None:
        roots = self.guard.temp_roots(primary="/made-up/tmp", home="/made-up/person")
        self.assertEqual(roots[0], "/made-up/tmp")


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

            NAMES = {GUARDED!r}

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

    def test_a_caller_who_exported_nothing_gets_a_sandbox(self) -> None:
        result = self.run_suite()
        self.assertEqual(result.returncode, 0, result.stderr)
        seen = json.loads(self.first.read_text(encoding="utf-8"))
        temp = os.path.realpath(tempfile.gettempdir())
        for name in GUARDED:
            with self.subTest(name=name):
                self.assertTrue(os.path.realpath(seen[name]).startswith(temp + os.sep), seen[name])
        self.assertNotEqual(seen["HOME"], os.environ["HOME"])
        self.assertTrue(self.second.exists())

    def test_the_sandbox_is_removed_when_the_run_ends(self) -> None:
        self.run_suite()
        seen = json.loads(self.first.read_text(encoding="utf-8"))
        self.assertFalse(os.path.exists(os.path.dirname(seen["HOME"])))

    def test_an_override_under_the_temp_directory_is_kept(self) -> None:
        mine = str(self.tmp / "my-config")
        result = self.run_suite(CLAUDE_CONFIG_DIR=mine)
        self.assertEqual(result.returncode, 0, result.stderr)
        seen = json.loads(self.first.read_text(encoding="utf-8"))
        self.assertEqual(seen["CLAUDE_CONFIG_DIR"], mine)
        self.assertEqual(seen["SPAWN_SESSIONS_DIR"], os.path.join(mine, "sessions"))

    def test_each_override_outside_the_temp_directory_stops_the_run_before_any_test(self) -> None:
        for name in OVERRIDES:
            with self.subTest(name=name):
                result = self.run_suite(**{name: f"{DECOY}/{name.lower()}"})
                self.assertNotEqual(result.returncode, 0)
                self.assertRefused(result.stderr, name)
                self.assertFalse(self.first.exists(), "a test ran after the refusal")
                self.assertFalse(self.second.exists(), "a test ran after the refusal")

    def test_a_variable_repointed_before_the_first_test_stops_the_run(self) -> None:
        for name in GUARDED:
            with self.subTest(name=name):
                result = self.run_suite(PROBE_AT_IMPORT=f"{name}={DECOY}/{name.lower()}")
                self.assertNotEqual(result.returncode, 0)
                self.assertRefused(result.stderr, name)
                self.assertFalse(self.first.exists(), "a test ran after the refusal")
                self.assertFalse(self.second.exists(), "a test ran after the refusal")

    def test_a_variable_unset_before_the_first_test_stops_the_run(self) -> None:
        result = self.run_suite(PROBE_AT_IMPORT="CLAUDE_PLUGIN_DATA")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "WARNING: CLAUDE_PLUGIN_DATA is unset; this test would WRITE into the real "
            "plugin data directory. Refusing.",
            result.stderr,
        )
        self.assertFalse(self.first.exists(), "a test ran after the refusal")

    def test_a_variable_one_test_leaves_repointed_stops_the_next_test(self) -> None:
        result = self.run_suite(PROBE_LEAK=f"{DECOY}/leaked")
        self.assertNotEqual(result.returncode, 0)
        self.assertRefused(result.stderr, "CLAUDE_PLUGIN_DATA")
        self.assertTrue(self.first.exists())
        self.assertFalse(self.second.exists(), "the test after the leak ran")


class TestBashGuard(_DecoyNeverCreated):
    """sandbox-guard.bash sourced by plain bash, with the variables bats would set."""

    PRINT = 'for n in %s; do printf "%%s=%%s\\n" "$n" "${!n}"; done' % " ".join(GUARDED)

    def source(self, after: str = "", **env: str) -> subprocess.CompletedProcess[str]:
        bats_tmp = self.tmp / "bats-test"
        bats_tmp.mkdir(exist_ok=True)
        env.setdefault("BATS_TEST_TMPDIR", str(bats_tmp))
        env = {k: v for k, v in _caller_env(**env).items() if v != "<unset>"}
        return subprocess.run(
            ["bash", "-c", f'source "$1" || exit 9\n{after}\n{self.PRINT}', "bash", str(BASH_GUARD)],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

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
                self.assertFalse((self.tmp / "bats-test" / ".claude-sandbox").exists())

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

    @unittest.skipUnless(_load_guard().passwd_home(), "no home directory in the user database")
    def test_a_temp_directory_that_contains_the_home_directory_is_refused(self) -> None:
        # TMPDIR=/ contains every home directory. Nothing is written there: the
        # refusal comes first, and the sandbox would be built under
        # BATS_TEST_TMPDIR in any case.
        result = self.source(TMPDIR="/")
        self.assertEqual(result.returncode, 9, result.stderr)
        self.assertIn("WARNING: the temp directory / contains the home directory ", result.stderr)
        self.assertIn("could WRITE into the real Claude config. Refusing.", result.stderr)

    def test_no_bats_temp_directory_is_refused(self) -> None:
        result = self.source(BATS_TEST_TMPDIR="<unset>", BATS_FILE_TMPDIR="<unset>")
        self.assertEqual(result.returncode, 9, result.stderr)
        self.assertIn("WARNING: neither BATS_TEST_TMPDIR nor BATS_FILE_TMPDIR is set", result.stderr)
        self.assertIn(" Refusing.", result.stderr)


class TestEverySuiteIsGuarded(_DecoyNeverCreated):
    """Each real suite, started with an override aimed at the decoy, must refuse."""

    def test_every_python_suite_refuses_an_override_outside_the_temp_directory(self) -> None:
        suites = _python_suites()
        self.assertGreaterEqual(len(suites), 5, suites)
        for directory, top in suites:
            with self.subTest(suite=str(directory.relative_to(ROOT))):
                result = subprocess.run(
                    [sys.executable, "-m", "unittest", "discover",
                     "-s", str(directory.relative_to(top)), "-t", "."],
                    cwd=top,
                    env=_caller_env(CLAUDE_PLUGIN_DATA=f"{DECOY}/plugin-data"),
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertRefused(result.stderr, "CLAUDE_PLUGIN_DATA")
                # The one "test" is unittest reporting that the package would not import.
                self.assertIn("Ran 1 test", result.stderr)
                self.assertIn("FAILED (errors=1)", result.stderr)

    def test_every_bats_file_loads_the_guard_first_in_setup(self) -> None:
        files = _bats_files()
        self.assertGreaterEqual(len(files), 4, files)
        first_in_setup = re.compile(
            r"^setup\(\) \{\n[ \t]*load '((?:\.\./)+scripts/test-support/sandbox-guard)'\n", re.M
        )
        for path in files:
            with self.subTest(file=str(path.relative_to(ROOT))):
                found = first_in_setup.search(path.read_text(encoding="utf-8"))
                self.assertIsNotNone(
                    found,
                    "the first line of setup() must load scripts/test-support/sandbox-guard",
                )
                loaded = (path.parent / (found.group(1) + ".bash")).resolve()
                self.assertEqual(loaded, BASH_GUARD.resolve())

    @unittest.skipUnless(shutil.which("bats"), "bats not on PATH")
    def test_every_bats_file_refuses_an_override_outside_the_temp_directory(self) -> None:
        for path in _bats_files():
            with self.subTest(file=str(path.relative_to(ROOT))):
                result = subprocess.run(
                    ["bats", str(path)],
                    cwd=ROOT,
                    env=_caller_env(CLAUDE_PLUGIN_DATA=f"{DECOY}/plugin-data"),
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
                    len(re.findall(r"^# WARNING: CLAUDE_PLUGIN_DATA resolves to ", output, re.M)),
                    planned,
                    output,
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


if __name__ == "__main__":
    unittest.main()
