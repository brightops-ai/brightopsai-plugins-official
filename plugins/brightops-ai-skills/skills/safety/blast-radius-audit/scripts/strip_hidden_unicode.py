#!/usr/bin/env python3
"""List the hidden Unicode in one file and, with --apply, remove it.

    strip_hidden_unicode.py <file>            list every position; change nothing
    strip_hidden_unicode.py <file> --apply    remove exactly the positions listed

Run it from the repository root with a path inside the repository. The file
must be a regular file reached without passing through any link: the path you
approve is then the file that changes.

It uses the same definition of "hidden" as the collector, so a zero-width
joiner inside an emoji sequence, the tag characters of a flag emoji and a
leading byte-order mark are kept. Apart from the removed characters the file
is unchanged: same bytes, same line endings, and it is rewritten in place, so
its permissions, ownership and extended attributes stay as they were. A copy
of the original sits beside it until the rewrite has succeeded.

Exit status: 0 on success, 2 when the file cannot be handled (not found, an
absolute path or one containing `..`, reached through a link, hard-linked
elsewhere, not UTF-8).
Standard library only; runs on Python 3.9+.
"""

from __future__ import annotations

import os
import re
import stat
import sys
import tempfile
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from collect import hidden_columns  # noqa: E402 - sibling module, path set just above


def hidden_positions(text: str) -> list[tuple[int, int, int]]:
    """(index, line, column) of every hidden character, in file order."""
    found, offset = [], 0
    for lineno, line in enumerate(text.split("\n"), 1):
        for column, code in hidden_columns(line):
            index = offset + column - 1
            if not (code == 0xFEFF and index == 0):
                found.append((index, lineno, column))
        offset += len(line) + 1  # the newline that split() consumed
    return found


def checked_path(path: str) -> tuple[str, str]:
    """(the real path to operate on, "") or ("", why this path may not be rewritten).

    The path is walked one component at a time from the working directory, so
    what is checked is what is opened. `..` is refused outright: collapsing it
    as text hides a link that the filesystem would still follow.
    """
    if os.path.isabs(path):
        return "", "is an absolute path; give a path relative to the repository root"
    separators = "[" + re.escape(os.sep + (os.altsep or "")) + "]"  # both kinds, where a platform has two
    parts = [part for part in re.split(separators, path) if part not in ("", os.curdir)]
    if not parts or os.pardir in parts:
        return "", "contains '..' or names no file; give a plain path under the repository root"
    current = os.path.realpath(os.getcwd())
    for part in parts:
        current = os.path.join(current, part)
        if os.path.islink(current):
            return "", "is reached through a link; links are not followed"
    try:
        info = os.lstat(current)
    except OSError:
        return "", "does not exist"
    if not stat.S_ISREG(info.st_mode):
        return "", "is not a regular file"
    if info.st_nlink > 1:
        return "", "has other hard links, so rewriting it in place would change those files too"
    return current, ""


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    apply = "--apply" in args
    paths = [a for a in args if a != "--apply"]
    if len(paths) != 1:
        sys.stderr.write("usage: strip_hidden_unicode.py <file> [--apply]\n")
        return 2
    path = paths[0]
    shown = "".join(ch if ch.isprintable() else f"\\x{ord(ch):02x}" for ch in path)
    real, problem = checked_path(path)
    if problem:
        sys.stderr.write(f"{shown}: {problem}; nothing changed\n")
        return 2
    path = real  # from here on, only the path that was checked is used
    with open(path, "rb") as handle:
        raw = handle.read()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        sys.stderr.write(f"{shown}: not UTF-8; nothing changed\n")
        return 2
    positions = hidden_positions(text)
    for index, lineno, column in positions:
        code = ord(text[index])
        print(f"{shown}:{lineno}:{column} U+{code:04X} {unicodedata.name(text[index], 'UNNAMED')}")
    if not apply or not positions:
        print(f"{shown}: {len(positions)} hidden characters" + ("" if apply else "; nothing changed (pass --apply to remove them)"))
        return 0
    drop = {index for index, _, _ in positions}
    cleaned = "".join(char for index, char in enumerate(text) if index not in drop).encode("utf-8")
    # Keep the original beside the file until the in-place rewrite is done. Writing in
    # place, rather than swapping in a new file, is what keeps the file's metadata.
    descriptor, backup = tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(path)), prefix=".hidden-unicode-backup-")
    with os.fdopen(descriptor, "wb") as saved:
        saved.write(raw)
    try:
        with open(path, "r+b") as handle:
            handle.write(cleaned)
            handle.truncate()
            handle.flush()
            os.fsync(handle.fileno())
    except OSError:
        sys.stderr.write(f"{shown}: rewrite failed; the original is saved as {os.path.basename(backup)}\n")
        raise
    os.unlink(backup)
    print(f"{shown}: removed {len(positions)} hidden characters")
    return 0


if __name__ == "__main__":
    sys.exit(main())
