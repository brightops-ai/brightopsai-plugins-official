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

``install()`` changes the whole process: it rewrites ``os.environ`` and wraps
``unittest.TestCase.run``. In order, it:

1. Works out which directories count as temp, and refuses when the answer
   would prove nothing (see ``temp_roots``).
2. Refuses an override inherited from the caller that is not a clean absolute
   path resolving under a temp directory. The caller set it on purpose; it is
   not quietly ignored.
3. Points ``HOME`` at a fresh temp directory and gives every unset override a
   default beside it.
4. Checks, then and again before every test, that every guarded variable is
   set and safe.

``HOME`` is replaced without asking because every process has one and it says
nothing about intent. The overrides exist only when somebody exported them.

``CLAUDE_CODE_PROJECT_DIR_NAME`` is guarded as a name, not a path:
``lib/dream/claude_env.py`` joins it onto the config directory as written, so
a value with a slash or ``..`` leaves the sandbox the path variables built. It
is left unset when unset and refused when it is not a plain name.

The bats suites enforce the same lists from ``sandbox-guard.bash``, beside
this file, which also names the script that reads each variable. A variable
added to one belongs in the other.

Not caught: a test that passes its own ``env=`` to a child process, a test
that points a variable at a real path and restores it before it returns, a
test file run by path instead of through its package, and anything the code
under test reads without going through one of these variables (the
repository's own ``.claude/settings*.json`` and the managed-policy settings
file, which ``claude_env.py`` reads).
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

NAME_VARIABLE = "CLAUDE_CODE_PROJECT_DIR_NAME"

# _CS_DARWIN_USER_TEMP_DIR. os.confstr_names does not list it on every build.
_CS_DARWIN_USER_TEMP_DIR = 65537


class SandboxRefusal(RuntimeError):
    """A guarded variable would let a test reach outside the temp directory."""


def one_line(text: str) -> str:
    """The text on one line, with every control character written out.

    Every value printed here comes from the environment. Printed raw, a value
    holding a newline followed by ``WARNING: ...`` forges a second warning,
    and one holding an escape sequence repaints the line that mattered.
    """
    out = []
    for ch in text:
        if ch == "\\":
            out.append("\\\\")  # doubled, so a rendering cannot pass for the real thing
        elif ch == " " or ch.isprintable():
            out.append(ch)
        else:
            out.append({"\n": "\\n", "\t": "\\t", "\r": "\\r"}.get(ch, f"\\x{ord(ch):02x}"))
    return "".join(out)


def has_control(text: str) -> bool:
    """Whether the text holds a control character: U+0000 to U+001F, U+007F,
    or U+0080 to U+009F. The same set ``sandbox-guard.bash`` refuses."""
    return any(ord(ch) < 0x20 or 0x7F <= ord(ch) <= 0x9F for ch in text)


def _refusal(fact: str, remedy: str = "") -> SandboxRefusal:
    # The repo's warning shape: the fact read at run time, the consequence as
    # one capitalised verb, then the refusal. Always one line.
    return SandboxRefusal(one_line(f"WARNING: {fact} Refusing.{' ' + remedy if remedy else ''}"))


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


def darwin_user_temp_dir() -> str | None:
    """The per-user temp directory on macOS, where ``mktemp -d`` puts things
    whatever ``TMPDIR`` says. ``None`` anywhere else."""
    if sys.platform != "darwin":
        return None
    try:
        return os.confstr(_CS_DARWIN_USER_TEMP_DIR) or None
    except (OSError, ValueError):
        return None


def _usable_root(root: str, home: str | None, config: str | None) -> bool:
    if home and within(home, root):
        return False
    return not (config and (within(root, config) or within(config, root)))


def temp_roots(
    primary: str | None = None, home: str | None = None, extras: list | None = None
) -> list[str]:
    """Resolved directories a guarded variable may point under.

    "Under a temp directory" proves nothing when that directory contains the
    home directory, or is, is inside, or contains the real Claude config
    directory, so the temp directory in use is refused then rather than
    believed. A temp directory elsewhere under the home directory is fine.

    ``/tmp`` and the macOS per-user temp directory are added when they exist
    and are usable by the same rule.
    """
    primary = os.path.realpath(tempfile.gettempdir() if primary is None else primary)
    home = passwd_home() if home is None else os.path.realpath(home)
    config = os.path.realpath(os.path.join(home, ".claude")) if home else None
    if home and within(home, primary):
        raise _refusal(
            f"the temp directory {primary} contains the home directory {home}, so a path "
            "under it proves nothing; this test could WRITE into the real Claude config.",
            "Set TMPDIR to a directory that does not contain the home directory.",
        )
    if config and within(primary, config):
        raise _refusal(
            f"the temp directory {primary} is inside the real Claude config directory "
            f"{config}; this test would WRITE its sandbox into the real Claude config.",
            f"Set TMPDIR to a directory outside {config}.",
        )
    if config and within(config, primary):
        raise _refusal(
            f"the temp directory {primary} contains the real Claude config directory "
            f"{config}, so a path under it proves nothing; this test could WRITE into the "
            "real Claude config.",
            f"Set TMPDIR to a directory that does not contain {config}.",
        )
    roots = [primary]
    for candidate in ["/tmp", darwin_user_temp_dir()] if extras is None else extras:
        if not candidate or not os.path.isabs(candidate) or not os.path.isdir(candidate):
            continue
        extra = os.path.realpath(candidate)
        if extra not in roots and not has_control(extra) and _usable_root(extra, home, config):
            roots.append(extra)
    return roots


def check_variable(name: str, environ=None, roots: list[str] | None = None) -> None:
    """Raise ``SandboxRefusal`` unless ``name`` holds a clean absolute path
    that resolves under a temp directory."""
    environ = os.environ if environ is None else environ
    roots = temp_roots() if roots is None else roots
    noun, real = next((entry[1], entry[2]) for entry in GUARDED if entry[0] == name)
    remedy = f"Unset {name} to get a fresh temp directory, or point it under {roots[0]}."
    value = environ.get(name)
    if not value:
        raise _refusal(
            f"{name} is {'unset' if value is None else 'empty'}; this test would WRITE into {real}.",
            "The sandbox guard set it before the first test; something has unset it since.",
        )
    if has_control(value):
        raise _refusal(
            f"{name} holds a control character ({value}); this test would WRITE {noun} to a "
            "path nobody checked.",
            remedy,
        )
    # A relative value depends on the working directory at the moment it is
    # used, and the code under test expands a leading "~", including "~user".
    if not os.path.isabs(value):
        raise _refusal(
            f"{name} is {value}, which is not an absolute path; this test would WRITE {noun} "
            "to a path nobody checked.",
            remedy,
        )
    resolved = os.path.realpath(value)
    if has_control(resolved):
        raise _refusal(
            f"{name} is {value}, which cannot be resolved to a real path; this test would "
            f"WRITE {noun} to a path nobody checked.",
            remedy,
        )
    if not any(within(resolved, root) for root in roots):
        raise _refusal(
            f"{name} resolves to {resolved}, outside the temp directory {roots[0]}; "
            f"this test would WRITE {noun} there.",
            remedy,
        )


def check_name(environ=None) -> None:
    """Raise ``SandboxRefusal`` unless the project directory name is unset or
    a plain name."""
    environ = os.environ if environ is None else environ
    value = environ.get(NAME_VARIABLE)
    if not value:
        return
    if has_control(value) or "/" in value or "\\" in value or ".." in value or value == ".":
        raise _refusal(
            f"{NAME_VARIABLE} is {value}, which is a path and not a directory name; this test "
            "would WRITE session transcripts and memory outside the sandboxed Claude config "
            "directory.",
            f"Unset {NAME_VARIABLE}, or set it to a plain name.",
        )


def check(environ=None, roots: list[str] | None = None) -> None:
    """Raise ``SandboxRefusal`` unless every guarded variable is safe."""
    roots = temp_roots() if roots is None else roots
    for name, _noun, _real in GUARDED:
        check_variable(name, environ, roots)
    check_name(environ)


def _guard_every_test(roots: list[str]) -> None:
    """Re-check before each test, and stop the run on a refusal.

    One process runs the whole suite, so a variable one test leaves pointing
    at a real path is still there for every test after it. The check is not
    cached on the values: a link one test retargets leaves every string as it
    was and still moves where the next test writes.
    """
    original = unittest.TestCase.run

    def run(self, result=None):
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
        return original(self, result)

    run._sandbox_guard = True  # type: ignore[attr-defined]
    unittest.TestCase.run = run  # type: ignore[method-assign]


def install() -> None:
    """Sandbox this process and refuse to run tests outside the sandbox."""
    if getattr(unittest.TestCase.run, "_sandbox_guard", False):
        return  # another tests package in this process already did

    roots = temp_roots()

    # What the caller exported is honoured only when it is safe.
    check_name()
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
