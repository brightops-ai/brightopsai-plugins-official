#!/usr/bin/env python3
"""Read and update the CLI's workspace-trust entries.

The CLI records which directories it may operate in inside its own JSON
configuration file, under ``projects[<path>].hasTrustDialogAccepted``. Setting
that entry before launch is the CLI's own documented alternative to accepting
the dialog interactively, and it is what lets a session be started in a
not-yet-trusted directory without anything simulating keystrokes at a security
prompt.

Two rules govern every write here, and both exist because this file does not
belong to us:

* **Never rewrite it wholesale.** It holds unrelated state for every project on
  the machine. The update is a merge into the structure that is on disk at the
  moment of writing, re-read inside the caller's lock.
* **Replace it atomically.** The file is written to a temporary path in the same
  directory and renamed over the original, so a reader never observes a
  half-written file and a crash mid-write cannot truncate it.

Locking is the caller's job: the shell wrapper takes the same lock directory
the CLI takes, so a concurrent session's changes cannot be lost between our
read and our write.

Usage:
    trust-config.py check <config-file> <key>   exit 0 if trusted, 1 if not
    trust-config.py grant <config-file> <key>   add the entry, exit 0 on success
"""

import json
import os
import sys
import tempfile


def load(path):
    """Return the parsed config, or None if it cannot be read or parsed."""
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return None


def is_trusted(config, key):
    if not isinstance(config, dict):
        return False
    projects = config.get("projects")
    if not isinstance(projects, dict):
        return False
    entry = projects.get(key)
    # An entry present but false is a decision on record, not an absence: it
    # means trust was declined for this path, and treating it as "unknown"
    # would quietly overrule that.
    return isinstance(entry, dict) and entry.get("hasTrustDialogAccepted") is True


def grant(path, key):
    config = load(path)
    if config is None:
        # A missing file is an ordinary first run. An unparseable one is not
        # ours to repair — refusing leaves it for the CLI to handle rather
        # than replacing content we cannot read.
        if os.path.exists(path):
            print(
                "refusing to write: %s exists but could not be parsed" % path,
                file=sys.stderr,
            )
            return 1
        config = {}

    projects = config.setdefault("projects", {})
    if not isinstance(projects, dict):
        print("refusing to write: 'projects' is not an object", file=sys.stderr)
        return 1

    entry = projects.get(key)
    if not isinstance(entry, dict):
        entry = {}
    # Merge into the existing entry rather than replacing it: a project entry
    # also carries per-project tool permissions and server lists.
    entry["hasTrustDialogAccepted"] = True
    projects[key] = entry

    directory = os.path.dirname(os.path.abspath(path)) or "."
    try:
        os.makedirs(directory, exist_ok=True)
        handle = tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=directory,
            prefix=".spawn-session-",
            suffix=".json",
            delete=False,
        )
        try:
            with handle:
                json.dump(config, handle, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(handle.name, 0o600)
            os.replace(handle.name, path)
        except BaseException:
            try:
                os.unlink(handle.name)
            except OSError:
                pass
            raise
    except OSError as exc:
        print("could not write %s: %s" % (path, exc), file=sys.stderr)
        return 1

    return 0


def main(argv):
    if len(argv) != 4:
        print(__doc__, file=sys.stderr)
        return 2
    action, path, key = argv[1], argv[2], argv[3]

    if action == "check":
        return 0 if is_trusted(load(path), key) else 1
    if action == "grant":
        return grant(path, key)

    print("unknown action: %s" % action, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
