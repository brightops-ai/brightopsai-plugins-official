#!/usr/bin/env bash
#
# SessionStart hook — activate the tracked git hooks, then make sure the
# plugins this repo enables are installed. .claude/settings.json registers it
# with the `startup` matcher, so it runs for a new session and not on resume,
# /clear or compaction. Every step is idempotent in case it runs again.
#
# Git hooks: git never clones hooks, so a fresh clone commits with no local
# secret scan until scripts/install-hooks.sh has pointed core.hooksPath at
# .githooks/.
#
# Plugins: a plugin that only project settings enable does not load until it
# is installed on the machine, and Claude Code does not download it for that
# entry alone; it does so only when user settings, .claude/settings.local.json,
# --settings or managed settings enable it. An Anthropic-hosted cloud session
# does not add the marketplaces listed under extraKnownMarketplaces either. So
# a fresh container starts with the plugin enabled and missing
# (https://code.claude.com/docs/en/plugins/loading).
#
# What this hook does about it:
#   - Installs a plugin only when `claude plugin list --json` exits 0, is a
#     well-formed listing, and has no row for the plugin that applies to this
#     project. The Python program further down reads the listing as
#     untrusted input: strict JSON (no NaN, no duplicate keys, bounded size
#     and nesting), and in every row each field the CLI is known to emit has
#     to have that field's shape when it is there. Fields it does not know
#     are left alone. If the listing fails, does not answer in time, is
#     malformed in any row, or python3 is missing, the answer is unknown and
#     the hook warns and skips the install.
#   - Never updates an installed plugin, and prints the installed version to
#     stderr so a change of version is visible.
#
# What it cannot do: pin. `claude plugin install` takes no version or commit
# (checked on Claude Code 2.1.330), and a commit `ref` is refused for a
# reserved marketplace name such as claude-plugins-official. Marketplace
# auto-update is a separate path; .claude/settings.json turns it off for this
# marketplace (`autoUpdate: false`) in sessions that read that file.
#
# A plugin installed here is on disk, not loaded: it is available from the
# next session, or in this one after /reload-plugins.
#
# Everything this hook prints goes to stderr: SessionStart stdout is added to
# the model's context. It never fails the session: a broken step costs you the
# pre-commit gate or the skills, not the session.

set -uo pipefail

PLUGINS=(
  "mattpocock-skills@claude-plugins-official"
)

# Paths are built from where this file is and used as they are. They are never
# printed and read back, because a command substitution drops a trailing
# newline and a checkout directory may be named with one.
hook_dir="${BASH_SOURCE[0]%/*}"
if [ "$hook_dir" = "${BASH_SOURCE[0]}" ]; then
  hook_dir="."
fi
# A relative path that begins with a dash would be read as an option by cd.
case "$hook_dir" in
  /* | ./* | ../* | .) ;;
  *) hook_dir="./$hook_dir" ;;
esac
repo_root="$hook_dir/../.."

if ! (cd "$repo_root" && bash scripts/install-hooks.sh) >&2; then
  echo "WARNING: scripts/install-hooks.sh failed; commits in this clone SKIP the gitleaks pre-commit scan. Run ./scripts/install-hooks.sh by hand." >&2
fi

# The program that reads the plugin listing. It lives in this file so the hook
# is one file: there is no helper to go missing. scripts/tests reads it from
# here, between the two PLUGIN_STATUS_PY lines, and tests it directly.
PLUGIN_STATUS_PY=""
IFS= read -r -d '' PLUGIN_STATUS_PY <<'PLUGIN_STATUS_PY' || true
"""Whether a plugin is installed for this project, from `claude plugin list --json`.

    python3 -I -c <this program> <plugin-id> <project-root>

install-plugins.sh carries this program and installs a plugin when it says the
plugin is not installed, so the one answer that must never be given by mistake
is "not installed". The listing is treated as untrusted input: it is parsed
strictly, every row is validated, and the answer is "unknown" unless the whole
listing is well-formed.

Exit status and output:

    0   the listing is well-formed. stdout holds what was found for the plugin
        in this project, such as "1.2.3 (user scope)", or nothing when it is
        not installed here.
    2   `claude plugin list --json` could not be run, or exited non-zero.
    3   the listing is not well-formed, so the answer is unknown.
    4   `claude plugin list --json` did not answer in time and was stopped.

A row applies to this project when its scope is user or managed, or project or
local with a projectPath that is this project.

Nothing here depends on how one Python version parses: size, nesting depth and
the length of a number are bounded before the parser sees the text, so the
answer is the same on 3.9 and on a version with a deeper or no recursion
limit. Standard library only.
"""

import json
import os
import re
import signal
import subprocess
import sys
import unicodedata

EXIT_OK = 0
EXIT_LISTING_FAILED = 2
EXIT_MALFORMED = 3
EXIT_LISTING_TIMED_OUT = 4

# Far above any real listing; bounds on what is parsed at all. A real listing
# is a list of flat objects: depth 2.
MAX_LISTING_BYTES = 4 * 1024 * 1024
MAX_DEPTH = 16
MAX_NUMBER_CHARS = 32
MAX_PATH_CHARS = 4096

# How long the listing may take. The real one answers in well under a second.
LIST_TIMEOUT_SECONDS = 20.0
LIST_TIMEOUT_VARIABLE = "INSTALL_PLUGINS_LIST_TIMEOUT"

# "<name>@<marketplace>", each part a letter or digit first and last.
_PART = r"[A-Za-z0-9](?:[A-Za-z0-9._-]{0,126}[A-Za-z0-9])?"
PLUGIN_ID = re.compile(_PART + "@" + _PART)
SCOPE = re.compile(r"[a-z][a-z-]{0,31}")
VERSION = re.compile(r"[0-9A-Za-z][0-9A-Za-z.+_-]{0,63}")
TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?(?:Z|[+-]\d{2}:\d{2})")

# Scopes whose rows apply everywhere, and scopes whose rows name one project.
EVERYWHERE = ("user", "managed")
ONE_PROJECT = ("project", "local")


class Malformed(Exception):
    """The listing is not something this hook can base an install on."""


def _reject_constant(name):
    # NaN, Infinity and -Infinity are not JSON.
    raise Malformed("non-standard constant %s" % name)


def _finite_float(text):
    if len(text) > MAX_NUMBER_CHARS:
        raise Malformed("number too long")
    value = float(text)
    if value != value or value in (float("inf"), float("-inf")):
        raise Malformed("number out of range")
    return value


def _bounded_int(text):
    # Bounded here, not by the interpreter: some versions refuse to convert a
    # very long run of digits and some do not.
    if len(text) > MAX_NUMBER_CHARS:
        raise Malformed("number too long")
    return int(text)


def _check_depth(text):
    """Raise Malformed if arrays and objects nest deeper than MAX_DEPTH.

    A plain scan, so that the bound does not depend on a recursion limit. For
    text the parser would accept, the count is exact. For text it would
    reject, the count is never lower than what the parser sees before it
    stops, because both read strings the same way up to that point.
    """
    depth = 0
    in_string = False
    escaped = False
    for char in text:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char in "[{":
            depth += 1
            if depth > MAX_DEPTH:
                raise Malformed("nested too deeply")
        elif char in "]}":
            depth -= 1


def _unique_keys(pairs):
    # A parser that keeps the last of two "id" keys and one that keeps the
    # first read different listings. Neither reading is trusted.
    found = {}
    for key, value in pairs:
        if key in found:
            raise Malformed("duplicate key")
        found[key] = value
    return found


def parse(raw):
    """Return the listing's rows, or raise Malformed. `raw` is bytes."""
    if not isinstance(raw, bytes):
        raise Malformed("not bytes")
    if len(raw) > MAX_LISTING_BYTES:
        raise Malformed("listing too large")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise Malformed("not UTF-8")
    _check_depth(text)
    try:
        listing = json.loads(
            text,
            parse_constant=_reject_constant,
            parse_float=_finite_float,
            parse_int=_bounded_int,
            object_pairs_hook=_unique_keys,
        )
    except Malformed:
        raise
    except (ValueError, RecursionError, MemoryError, OverflowError):
        raise Malformed("not JSON")
    if not isinstance(listing, list):
        raise Malformed("top level is not a list")
    return listing


def _clean_path(value):
    """An absolute path with nothing in it that could be read two ways."""
    if not isinstance(value, str) or not value or len(value) > MAX_PATH_CHARS:
        return False
    for char in value:
        # Controls, lone surrogates, line and paragraph separators.
        if unicodedata.category(char) in ("Cc", "Cs", "Zl", "Zp"):
            return False
    return os.path.isabs(value)


def _is_bool(value):
    return value is True or value is False


def _is_timestamp(value):
    return isinstance(value, str) and TIMESTAMP.fullmatch(value) is not None


# Every field `claude plugin list --json` is known to emit (Claude Code
# 2.1.330), and the shape each has there. A row need not carry all of them,
# but one that is present has to look like the CLI wrote it: null is not a
# shape any of them has. A field that is not in this table is left alone, so
# a new CLI field does not switch the hook off.
KNOWN_FIELDS = {
    "id": lambda v: isinstance(v, str) and PLUGIN_ID.fullmatch(v) is not None,
    "scope": lambda v: isinstance(v, str) and SCOPE.fullmatch(v) is not None,
    "version": lambda v: isinstance(v, str) and VERSION.fullmatch(v) is not None,
    "enabled": _is_bool,
    "projectEnabled": _is_bool,
    "installPath": _clean_path,
    "projectPath": _clean_path,
    "installedAt": _is_timestamp,
    "lastUpdated": _is_timestamp,
}
REQUIRED_FIELDS = ("id", "scope")


def check_row(row):
    """Raise Malformed unless the row is shaped like one the CLI writes."""
    if not isinstance(row, dict):
        raise Malformed("row is not an object")
    for name in REQUIRED_FIELDS:
        if name not in row:
            raise Malformed("row without %s" % name)
    for name, has_shape in KNOWN_FIELDS.items():
        if name in row and not has_shape(row[name]):
            raise Malformed("%s does not have its shape" % name)
    # Absolute or unknown: an empty or relative path would resolve against the
    # directory this runs in, which is this project.
    if row["scope"] in ONE_PROJECT and "projectPath" not in row:
        raise Malformed("a project row without a projectPath")


def _same_directory(path, root):
    # The directories themselves, not their spellings: on a filesystem that
    # ignores capitalization two spellings name one project. A path that does
    # not exist is not this project, which does.
    try:
        return os.path.samefile(path, root)
    except (OSError, ValueError):
        return False


def decide(raw, plugin, root):
    """What the listing says about `plugin` in the project at `root`.

    Returns "" when it is not installed for this project, or a description of
    each install that applies. Raises Malformed when the listing cannot be
    relied on.
    """
    rows = parse(raw)
    # Every row is checked before any is filtered out. A row this hook cannot
    # identify may be the plugin it is looking for.
    for row in rows:
        check_row(row)

    found = []
    for row in rows:
        if row["id"] != plugin:
            continue
        scope = row["scope"]
        if scope in ONE_PROJECT:
            if not _same_directory(row["projectPath"], root):
                continue
        elif scope not in EVERYWHERE:
            raise Malformed("a scope this hook does not know")
        found.append("%s (%s scope)" % (row.get("version") or "unknown version", scope))
    return ", ".join(found)


def _timeout():
    try:
        seconds = float(os.environ.get(LIST_TIMEOUT_VARIABLE, ""))
    except ValueError:
        return LIST_TIMEOUT_SECONDS
    return seconds if 0 < seconds <= 600 else LIST_TIMEOUT_SECONDS


class ListingTimedOut(Exception):
    pass


def read_listing():
    """The bytes `claude plugin list --json` prints, or None if it failed.

    The CLI runs in a process group of its own so that, when it does not
    answer in time, everything it started can be stopped with it; a process it
    left behind would keep the hook's output open and whoever waits for that.
    A signal that stops this program stops that group first, so stopping the
    hook does not leave the listing running either.
    """
    try:
        child = subprocess.Popen(
            ["claude", "plugin", "list", "--json"], stdout=subprocess.PIPE, start_new_session=True
        )
    except OSError:
        return None

    def stop_listing(signum=None, _frame=None):
        try:
            os.killpg(child.pid, signal.SIGKILL)
        except OSError:
            pass
        if signum is not None:
            sys.exit(128 + signum)

    for name in ("SIGTERM", "SIGINT", "SIGHUP"):
        signal.signal(getattr(signal, name), stop_listing)
    try:
        out, _ = child.communicate(timeout=_timeout())
    except subprocess.TimeoutExpired:
        stop_listing()
        child.stdout.close()
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        raise ListingTimedOut()
    if child.returncode != 0:
        return None
    return out


def main(argv):
    if len(argv) != 3 or not PLUGIN_ID.fullmatch(argv[1]):
        return EXIT_MALFORMED
    try:
        raw = read_listing()
    except ListingTimedOut:
        return EXIT_LISTING_TIMED_OUT
    if raw is None:
        return EXIT_LISTING_FAILED
    try:
        found = decide(raw, argv[1], argv[2])
    except Malformed:
        return EXIT_MALFORMED
    except Exception:  # noqa: BLE001 - any surprise means "unknown", never "missing"
        return EXIT_MALFORMED
    if found:
        print(found)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv))
PLUGIN_STATUS_PY

# Decides whether plugin $1 is installed for this project. Sets plugin_state
# to installed, missing or unknown, and plugin_detail to the versions found or
# to the reason the answer is unknown. The program above runs the listing and
# judges it; anything but a clean "found" or "not found" from it is unknown.
plugin_state="unknown"
plugin_detail=""
plugin_status() {
  local rc=0
  plugin_state="unknown"
  if ! command -v python3 >/dev/null 2>&1; then
    plugin_detail="python3 is not on PATH, so the plugin listing cannot be read"
    return
  fi
  plugin_detail="$(python3 -I -c "$PLUGIN_STATUS_PY" "$1" "$repo_root")" || rc=$?
  case "$rc" in
    0)
      if [ -n "$plugin_detail" ]; then
        plugin_state="installed"
      else
        plugin_state="missing"
      fi
      ;;
    2) plugin_detail="claude plugin list --json failed" ;;
    4) plugin_detail="claude plugin list --json did not answer in time and was stopped" ;;
    *) plugin_detail="the plugin listing is not the JSON this hook expects" ;;
  esac
}

if ! command -v claude >/dev/null 2>&1; then
  echo "warning: claude is not on PATH — skipping the plugin check; plugin skills may be unavailable this session" >&2
  exit 0
fi

for plugin in "${PLUGINS[@]}"; do
  plugin_status "$plugin"
  case "$plugin_state" in
    installed)
      echo "install-plugins: $plugin is installed: $plugin_detail — not updating" >&2
      ;;
    missing)
      echo "WARNING: $plugin is not installed; this INSTALLS the version its marketplace serves right now." >&2
      if claude plugin install "$plugin" -y >&2; then
        plugin_status "$plugin"
        if [ "$plugin_state" != "installed" ]; then
          plugin_detail="version not confirmed"
        fi
        echo "install-plugins: installed $plugin: $plugin_detail. It loads in the next session, or in this one after /reload-plugins." >&2
      else
        echo "warning: could not install $plugin — its skills will be unavailable this session" >&2
      fi
      ;;
    *)
      echo "WARNING: cannot tell whether $plugin is installed ($plugin_detail); this SKIPS the install. Check with: claude plugin list" >&2
      ;;
  esac
done

exit 0
