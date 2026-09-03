"""Locate the Claude Code directories the dream skills read and write.

This module answers "where does this live" and nothing else: it reads no user
content and writes nothing. It exists because getting the location wrong fails
silently -- a skill that looks in the wrong place finds an empty directory and
reports nothing to do, which is indistinguishable from a clean result.

Resolution follows the documented rules rather than assuming a layout:

* the config directory honours ``CLAUDE_CONFIG_DIR``
* the auto memory directory honours the ``autoMemoryDirectory`` setting, read
  from every settings scope in precedence order
* project identity derives from the git repository root, so every worktree and
  subdirectory of one repository resolves to the same project
* ``CLAUDE_CODE_PROJECT_DIR_NAME`` overrides the derived project directory name
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

# Settings scopes lowest precedence first; the last scope that defines a key wins.
_SCOPE_ORDER = ("user", "project", "local", "policy")

_UNSAFE_SLUG_CHARS = re.compile(r"[^A-Za-z0-9-]")


def config_dir(env: dict[str, str] | None = None) -> Path:
    """The Claude Code configuration directory."""
    env = os.environ if env is None else env
    override = env.get("CLAUDE_CONFIG_DIR")
    if override:
        return Path(override).expanduser()
    return Path(env.get("HOME", "~")).expanduser() / ".claude"


def policy_settings_path() -> Path:
    """Managed-policy settings location for the running platform."""
    if sys.platform == "darwin":
        return Path("/Library/Application Support/ClaudeCode/managed-settings.json")
    if sys.platform.startswith("win"):
        return Path("C:/ProgramData/ClaudeCode/managed-settings.json")
    return Path("/etc/claude-code/managed-settings.json")


def settings_paths(
    project_root: Path, env: dict[str, str] | None = None
) -> list[tuple[str, Path]]:
    """Every settings file that may define a key, lowest precedence first."""
    return [
        ("user", config_dir(env) / "settings.json"),
        ("project", project_root / ".claude" / "settings.json"),
        ("local", project_root / ".claude" / "settings.local.json"),
        ("policy", policy_settings_path()),
    ]


def _load_json(path: Path) -> dict:
    try:
        with path.open(encoding="utf-8") as handle:
            loaded = json.load(handle)
    except (OSError, ValueError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def read_setting(
    key: str, project_root: Path, env: dict[str, str] | None = None
) -> tuple[object | None, str | None]:
    """Read ``key`` from the highest-precedence scope that defines it.

    Returns the value and the scope it came from, or ``(None, None)``.
    """
    found: tuple[object | None, str | None] = (None, None)
    for scope, path in settings_paths(project_root, env):
        value = _load_json(path).get(key)
        if value is not None:
            found = (value, scope)
    return found


def project_root(start: Path | None = None) -> Path:
    """The git repository root containing ``start``, or ``start`` itself.

    Worktrees and subdirectories of one repository resolve to the same root,
    which is what makes them share a single auto memory directory.
    """
    start = Path.cwd() if start is None else Path(start)
    try:
        result = subprocess.run(
            ["git", "-C", str(start), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return start
    if result.returncode == 0 and result.stdout.strip():
        return Path(result.stdout.strip())
    return start


def slugify(path: Path | str) -> str:
    """Encode an absolute path the way Claude Code names its project directory."""
    return _UNSAFE_SLUG_CHARS.sub("-", str(path))


def project_dir_name(root: Path, env: dict[str, str] | None = None) -> str:
    """The project directory name, honouring the explicit override."""
    env = os.environ if env is None else env
    override = env.get("CLAUDE_CODE_PROJECT_DIR_NAME")
    if override:
        return override
    return slugify(root)


def _expand(value: str, env: dict[str, str] | None = None) -> Path:
    env = os.environ if env is None else env
    if value.startswith("~"):
        home = env.get("HOME")
        if home:
            return Path(home) / value.lstrip("~/")
    return Path(value).expanduser()


@dataclass(frozen=True)
class Locations:
    """Where one project's memory and transcripts live."""

    project_root: Path
    project_dir: Path
    memory_dir: Path
    transcripts_dir: Path
    memory_source: str
    memory_exists: bool
    transcripts_exist: bool

    def as_dict(self) -> dict:
        return {
            "project_root": str(self.project_root),
            "project_dir": str(self.project_dir),
            "memory_dir": str(self.memory_dir),
            "transcripts_dir": str(self.transcripts_dir),
            "memory_source": self.memory_source,
            "memory_exists": self.memory_exists,
            "transcripts_exist": self.transcripts_exist,
        }


def resolve(cwd: Path | None = None, env: dict[str, str] | None = None) -> Locations:
    """Resolve every location the dream skills need for one project."""
    env = os.environ if env is None else env
    root = project_root(cwd)
    project_dir = config_dir(env) / "projects" / project_dir_name(root, env)

    configured, scope = read_setting("autoMemoryDirectory", root, env)
    if isinstance(configured, str) and configured.strip():
        memory = _expand(configured.strip(), env)
        source = f"autoMemoryDirectory ({scope} settings)"
    else:
        memory = project_dir / "memory"
        source = "default layout"

    return Locations(
        project_root=root,
        project_dir=project_dir,
        memory_dir=memory,
        transcripts_dir=project_dir,
        memory_source=source,
        memory_exists=memory.is_dir(),
        transcripts_exist=project_dir.is_dir(),
    )
