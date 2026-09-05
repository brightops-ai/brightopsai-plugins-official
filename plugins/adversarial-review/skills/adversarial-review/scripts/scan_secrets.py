#!/usr/bin/env python3
"""Bundled high-confidence secret scan used when gitleaks is unavailable.

Patterns live here so SKILL.md cannot drift from the scanner. This is a
fallback, not a replacement for gitleaks.
"""

from __future__ import annotations

import os
import re
import sys

Finding = tuple[str, str, int]

# Each pattern is (rule id, compiled regex). Keep these high-confidence:
# a match should be enough to refuse an upload, not a topic-word in prose.
_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "private-key",
        re.compile(r"-----BEGIN (?:[A-Z0-9]+ )?PRIVATE KEY-----"),
    ),
    (
        "aws-access-key-id",
        re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    ),
    (
        "github-token",
        re.compile(
            r"\b(?:ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{20,}"
            r"|gho_[A-Za-z0-9]{36}|ghs_[A-Za-z0-9]{36}|ghu_[A-Za-z0-9]{36})\b"
        ),
    ),
    (
        "openai-api-key",
        re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b"),
    ),
    (
        "slack-token",
        re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    ),
    (
        "stripe-access-token",
        re.compile(r"\b(?:sk|rk)_(?:live|test)_[0-9a-zA-Z]{24,}\b"),
    ),
    (
        "jwt",
        re.compile(
            r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"
        ),
    ),
    (
        "generic-credential",
        re.compile(
            r"(?i)\b(password|secret|api_key)\b\s*[=:]\s*"
            r"(?:['\"][^'\"]{8,}['\"]|\S{12,})"
        ),
    ),
)

FALLBACK_NOTICE = (
    "FALLBACK: gitleaks is not available; using bundled high-confidence "
    "patterns. Install gitleaks for broader coverage."
)


def _line_of(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def findings_from_text(text: str, path: str) -> list[Finding]:
    """Return (rule, file, line) for each high-confidence match in text."""
    hits: list[Finding] = []
    seen: set[Finding] = set()
    for rule, pattern in _PATTERNS:
        for match in pattern.finditer(text):
            finding = (rule, path, _line_of(text, match.start()))
            if finding not in seen:
                seen.add(finding)
                hits.append(finding)
    hits.sort(key=lambda item: (item[2], item[0]))
    return hits


def scan_file(path: str) -> list[Finding]:
    with open(path, encoding="utf-8", errors="replace") as fh:
        return findings_from_text(fh.read(), path)


def format_finding(rule: str, file: str, line: int) -> str:
    return f"rule: {rule}  file: {file}  line: {line}"


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: scan_secrets.py <file>", file=sys.stderr)
        return 2
    path = argv[1]
    if not os.path.isfile(path):
        print(f"scan_secrets.py: not a file: {path}", file=sys.stderr)
        return 2
    print(FALLBACK_NOTICE)
    hits = scan_file(path)
    for rule, file, line in hits:
        print(format_finding(rule, file, line))
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
