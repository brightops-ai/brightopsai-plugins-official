"""Sandbox guard for every Python test suite in this repository.

The code under test falls back to the real Claude Code directories when its
override variables are unset, so a test that forgets one override reads and
writes the config of every session on the machine, with no error. Installing
this guard is what makes "tests never touch the real Claude config or plugin
data" hold without any test having to remember it.

Each tests package installs it from ``__init__.py``, which runs before any
test module is imported:

    <load scripts/test-support/sandbox_guard.py by path>.install()

``scripts/tests/test_sandbox_guard.py`` fails when a tests package does not.

``install()`` does three things, in this order:

1. Refuses an override inherited from the caller that resolves outside the
   temp directory. The caller set it on purpose; it is not quietly ignored.
2. Points ``HOME`` at a fresh temp directory and gives every unset override a
   default beside it.
3. Checks, then and again before every test, that every guarded variable is
   set and resolves under the temp directory.

``HOME`` is replaced without asking because every process has one and it says
nothing about intent. The overrides exist only when somebody exported them.

The bats suites enforce the same list from ``sandbox-guard.bash``, beside this
file, which also names the script that reads each variable. A variable added
to one belongs in the other.

Not caught: a test that passes its own ``env=`` to a child process, a test
that points a variable at a real path and restores it before it returns, and a
test file run by path instead of through its package.
"""

from __future__ import annotations

import atexit
import os
import shutil
import sys
import tempfile
import unittest

# unittest leaves frames from modules that define this out of a traceback, so
# a refusal prints as its one WARNING line.
__unittest = True

# (variable, what a test writes through it, where the code falls back to)
GUARDED = (
    ("HOME", "Claude config and plugin data", "the real home directory"),
    ("CLAUDE_CONFIG_DIR", "Claude config", "the real Claude config directory"),
    ("CLAUDE_PLUGIN_DATA", "plugin data", "the real plugin data directory"),
    ("SPAWN_SESSIONS_DIR", "session state", "the real Claude sessions directory"),
    ("SPAWN_PROJECTS_DIR", "session transcripts", "the real Claude transcripts directory"),
    ("SPAWN_CONFIG_FILE", "the Claude config file", "the real Claude config file"),
)


class SandboxRefusal(RuntimeError):
    """A guarded variable would let a test reach outside the temp directory."""


def _refusal(fact: str, remedy: str = "") -> SandboxRefusal:
    # The repo's warning shape: the fact read at run time, the consequence as
    # one capitalised verb, then the refusal.
    return SandboxRefusal(f"WARNING: {fact} Refusing.{' ' + remedy if remedy else ''}")


def within(path: str, root: str) -> bool:
    """Whether the resolved ``path`` is ``root`` or inside it."""
    return path == root or path.startswith(root.rstrip(os.sep) + os.sep)


def passwd_home() -> str | None:
    """The home directory from the user database, never from ``HOME``."""
    try:
        import pwd

        return os.path.realpath(pwd.getpwuid(os.getuid()).pw_dir)
    except (ImportError, KeyError, OSError):
        return None


def temp_roots(primary: str | None = None, home: str | None = None) -> list[str]:
    """Resolved directories a guarded variable may point under.

    "Under the temp directory" proves nothing when the temp directory contains
    the home directory, so that is refused rather than believed.
    """
    primary = os.path.realpath(tempfile.gettempdir() if primary is None else primary)
    home = passwd_home() if home is None else os.path.realpath(home)
    if home and within(home, primary):
        raise _refusal(
            f"the temp directory {primary} contains the home directory {home}, so a path "
            "under it proves nothing; this test could WRITE into the real Claude config.",
            "Set TMPDIR to a directory outside the home directory.",
        )
    roots = [primary]
    fallback = os.path.realpath("/tmp")
    if os.path.isdir(fallback) and fallback != primary and not (home and within(home, fallback)):
        roots.append(fallback)
    return roots


def check_variable(name: str, environ=None, roots: list[str] | None = None) -> None:
    """Raise ``SandboxRefusal`` unless ``name`` is set and resolves under temp."""
    environ = os.environ if environ is None else environ
    roots = temp_roots() if roots is None else roots
    noun, real = next((entry[1], entry[2]) for entry in GUARDED if entry[0] == name)
    value = environ.get(name)
    if not value:
        raise _refusal(
            f"{name} is {'unset' if value is None else 'empty'}; this test would WRITE into {real}.",
            "The sandbox guard set it before the first test; something has unset it since.",
        )
    resolved = os.path.realpath(value)
    if not any(within(resolved, root) for root in roots):
        raise _refusal(
            f"{name} resolves to {resolved}, outside the temp directory {roots[0]}; "
            f"this test would WRITE {noun} there.",
            f"Unset {name} to get a fresh temp directory, or point it under {roots[0]}.",
        )


def check(environ=None, roots: list[str] | None = None) -> None:
    """Raise ``SandboxRefusal`` unless every guarded variable is sandboxed."""
    roots = temp_roots() if roots is None else roots
    for name, _noun, _real in GUARDED:
        check_variable(name, environ, roots)


def _guard_every_test(roots: list[str]) -> None:
    """Re-check before each test, and stop the run on a refusal.

    One process runs the whole suite, so a variable one test leaves pointing
    at a real path is still there for every test after it.
    """
    original = unittest.TestCase.run
    seen: list[tuple] = []

    def run(self, result=None):
        state = tuple(os.environ.get(name) for name, _noun, _real in GUARDED)
        if seen != [state]:
            try:
                check(roots=roots)
            except SandboxRefusal:
                if result is None:
                    raise
                result.startTest(self)
                result.addError(self, sys.exc_info())
                result.stopTest(self)
                result.stop()
                return result
            seen[:] = [state]
        return original(self, result)

    run._sandbox_guard = True  # type: ignore[attr-defined]
    unittest.TestCase.run = run  # type: ignore[method-assign]


def install() -> None:
    """Sandbox this process and refuse to run tests outside the sandbox."""
    if getattr(unittest.TestCase.run, "_sandbox_guard", False):
        return  # another tests package in this process already did

    roots = temp_roots()

    # What the caller exported is honoured only under the temp directory.
    for name, _noun, _real in GUARDED:
        if name != "HOME" and os.environ.get(name):
            check_variable(name, roots=roots)

    sandbox = tempfile.mkdtemp(prefix="claude-test-sandbox-")
    atexit.register(shutil.rmtree, sandbox, ignore_errors=True)
    home = os.path.join(sandbox, "home")
    os.mkdir(home)

    def default(name: str, value: str) -> str:
        if not os.environ.get(name):
            os.environ[name] = value
        return os.environ[name]

    os.environ["HOME"] = home
    config = default("CLAUDE_CONFIG_DIR", os.path.join(home, ".claude"))
    default("CLAUDE_PLUGIN_DATA", os.path.join(sandbox, "plugin-data"))
    default("SPAWN_SESSIONS_DIR", os.path.join(config, "sessions"))
    default("SPAWN_PROJECTS_DIR", os.path.join(config, "projects"))
    default("SPAWN_CONFIG_FILE", os.path.join(home, ".claude.json"))

    check(roots=roots)
    _guard_every_test(roots)
