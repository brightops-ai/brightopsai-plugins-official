#!/usr/bin/env python3
"""List the hidden Unicode in one file and, with --apply, remove it.

    strip_hidden_unicode.py <file>            list every position; change nothing
    strip_hidden_unicode.py <file> --apply    remove exactly the positions listed

It uses the same definition of "hidden" as the collector, so a zero-width
joiner inside an emoji sequence and a leading byte-order mark are kept. The
file is rewritten byte for byte apart from the removed characters: line
endings and the permission bits are preserved, and the replacement is atomic.

Exit status: 0 on success, 2 when the file cannot be handled (not found, a
symbolic link, not UTF-8). Standard library only; runs on Python 3.9+.
"""

from __future__ import annotations

import os
import stat
import sys
import tempfile
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from collect import hidden_codepoint  # noqa: E402 - sibling module, path set just above


def hidden_positions(text: str) -> list[tuple[int, int, int]]:
    """(index, line, column) of every hidden character, in file order."""
    found, index = [], 0
    for lineno, line in enumerate(text.split("\n"), 1):
        previous = 0
        for column, char in enumerate(line, 1):
            code = ord(char)
            leading_bom = code == 0xFEFF and index == 0
            if code > 0x7F and hidden_codepoint(code, previous) and not leading_bom:
                found.append((index, lineno, column))
            previous = code
            index += 1
        index += 1  # the newline that split() consumed
    return found


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    apply = "--apply" in args
    paths = [a for a in args if a != "--apply"]
    if len(paths) != 1:
        sys.stderr.write("usage: strip_hidden_unicode.py <file> [--apply]\n")
        return 2
    path = paths[0]
    if os.path.islink(path) or not os.path.isfile(path):
        sys.stderr.write(f"{path}: not a regular file (links are not followed); nothing changed\n")
        return 2
    with open(path, "rb") as handle:
        raw = handle.read()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        sys.stderr.write(f"{path}: not UTF-8; nothing changed\n")
        return 2
    positions = hidden_positions(text)
    for index, lineno, column in positions:
        code = ord(text[index])
        print(f"{path}:{lineno}:{column} U+{code:04X} {unicodedata.name(text[index], 'UNNAMED')}")
    if not apply or not positions:
        print(f"{path}: {len(positions)} hidden characters" + ("" if apply else "; nothing changed (pass --apply to remove them)"))
        return 0
    drop = {index for index, _, _ in positions}
    cleaned = "".join(char for index, char in enumerate(text) if index not in drop).encode("utf-8")
    descriptor, temp = tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(path)))
    try:
        with os.fdopen(descriptor, "wb") as out:
            out.write(cleaned)
        os.chmod(temp, stat.S_IMODE(os.stat(path).st_mode))
        os.replace(temp, path)  # atomic: the original is never left half-written
    except OSError:
        if os.path.exists(temp):
            os.unlink(temp)
        raise
    print(f"{path}: removed {len(positions)} hidden characters")
    return 0


if __name__ == "__main__":
    sys.exit(main())
