"""Mechanical defect checks over an auto memory directory.

Every check here is decidable without judgement: a link either resolves or it
does not, an index either fits its load limit or it does not. Anything needing
an opinion about meaning -- whether two memories contradict, whether a rule
should be retired -- is deliberately absent, and belongs to the model reading
this report.

The index limit check is the reason this module exists. Content past 200 lines
or 25KB of ``MEMORY.md`` is dropped when the index loads, silently: memories
stop reaching the session and nothing anywhere reports an error.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from pathlib import Path

INDEX_NAME = "MEMORY.md"
INDEX_LINE_LIMIT = 200
INDEX_BYTE_LIMIT = 25 * 1024
VALID_TYPES = ("user", "feedback", "project", "reference")
DEFAULT_STALE_DAYS = 180

_MARKDOWN_LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
_WIKI_LINK = re.compile(r"\[\[([^\]]+)\]\]")


@dataclass
class Finding:
    """One defect, in terms a reader can act on."""

    check: str
    detail: str
    file: str = ""
    auto_fixable: bool = False

    def as_dict(self) -> dict:
        return {
            "check": self.check,
            "detail": self.detail,
            "file": self.file,
            "auto_fixable": self.auto_fixable,
        }


@dataclass
class MemoryFile:
    path: Path
    frontmatter: dict[str, str] = field(default_factory=dict)
    has_frontmatter: bool = False


def parse_frontmatter(text: str) -> tuple[dict[str, str], bool]:
    """Read leading YAML frontmatter as scalar key/value pairs.

    Deliberately not a YAML parser: the fields that matter here (``type``,
    ``modified``, ``name``) are scalars, and depending on a third-party parser
    would make this script unrunnable on a stock Python.

    Handles one level of nesting, because written memory files put ``type`` and
    ``modified`` under a ``metadata:`` block rather than at the top level.
    Nested keys are recorded both bare and dotted, so ``metadata.type`` is also
    reachable as ``type``; a top-level key always wins over a nested one.
    """
    if not text.startswith("---"):
        return {}, False
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, False

    fields: dict[str, str] = {}
    nested: dict[str, str] = {}
    parent: str | None = None
    closed = False

    for line in lines[1:]:
        if line.strip() == "---":
            closed = True
            break
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indented = line.startswith((" ", "\t"))
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip().strip("'\"")
        if indented:
            if parent is not None and value:
                nested.setdefault(key, value)
                fields[f"{parent}.{key}"] = value
            continue
        parent = key if not value else None
        if value:
            fields[key] = value

    if not closed:
        return {}, False

    for key, value in nested.items():
        fields.setdefault(key, value)
    return fields, True


def _referenced_targets(index_text: str) -> set[str]:
    targets: set[str] = set()
    for match in _MARKDOWN_LINK.findall(index_text):
        target = match.split("#", 1)[0].strip()
        if target:
            targets.add(Path(target).name)
    for match in _WIKI_LINK.findall(index_text):
        name = match.split("|", 1)[0].strip()
        if name:
            targets.add(name if name.endswith(".md") else f"{name}.md")
    return targets


def _parse_modified(value: str) -> dt.datetime | None:
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed


def audit(
    memory_dir: Path,
    now: dt.datetime | None = None,
    stale_days: int = DEFAULT_STALE_DAYS,
) -> list[Finding]:
    """Report every mechanical defect in ``memory_dir``. Writes nothing."""
    now = dt.datetime.now(dt.timezone.utc) if now is None else now
    memory_dir = Path(memory_dir)
    findings: list[Finding] = []

    if not memory_dir.is_dir():
        return [
            Finding(
                check="memory-directory-missing",
                detail=(
                    "No auto memory directory at the resolved location. This is "
                    "not a clean result: nothing could be checked."
                ),
                file=str(memory_dir),
            )
        ]

    index_path = memory_dir / INDEX_NAME
    topic_files = sorted(
        p for p in memory_dir.glob("*.md") if p.name != INDEX_NAME
    )

    if not index_path.exists():
        findings.append(
            Finding(
                check="index-missing",
                detail=(
                    f"No {INDEX_NAME}. Topic files are never loaded without an "
                    f"index entry, so all {len(topic_files)} are unreachable."
                ),
                file=str(index_path),
            )
        )
        index_text = ""
    else:
        index_text = index_path.read_text(encoding="utf-8", errors="replace")
        findings.extend(_check_index_limits(index_path, index_text))

    findings.extend(_check_duplicate_entries(index_path, index_text))

    referenced = _referenced_targets(index_text)
    present = {p.name for p in topic_files}

    for missing in sorted(referenced - present):
        findings.append(
            Finding(
                check="dead-index-entry",
                detail=f"Index links to {missing}, which does not exist.",
                file=str(index_path),
                auto_fixable=True,
            )
        )

    for orphan in sorted(present - referenced):
        findings.append(
            Finding(
                check="unreachable-memory",
                detail=(
                    f"{orphan} has no index entry, so it is never loaded and "
                    "cannot be recalled."
                ),
                file=str(memory_dir / orphan),
                auto_fixable=True,
            )
        )

    for path in topic_files:
        findings.extend(_check_topic_file(path, now, stale_days))

    return findings


def _check_duplicate_entries(index_path: Path, text: str) -> list[Finding]:
    """Identical index lines: redundant, and they count against the line limit."""
    seen: set[str] = set()
    duplicated: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith(("-", "*")):
            continue
        if stripped in seen and stripped not in duplicated:
            duplicated.append(stripped)
        seen.add(stripped)
    return [
        Finding(
            check="duplicate-index-entry",
            detail=f"Index repeats an entry verbatim: {entry[:70]}",
            file=str(index_path),
            auto_fixable=True,
        )
        for entry in duplicated
    ]


def _check_index_limits(index_path: Path, text: str) -> list[Finding]:
    findings: list[Finding] = []
    lines = text.splitlines()
    size = len(text.encode("utf-8"))

    if len(lines) > INDEX_LINE_LIMIT:
        dropped = len(lines) - INDEX_LINE_LIMIT
        findings.append(
            Finding(
                check="index-over-line-limit",
                detail=(
                    f"Index is {len(lines)} lines; only the first "
                    f"{INDEX_LINE_LIMIT} load. {dropped} line(s) are dropped "
                    "at session start, starting at line "
                    f"{INDEX_LINE_LIMIT + 1}."
                ),
                file=str(index_path),
                auto_fixable=True,
            )
        )

    if size > INDEX_BYTE_LIMIT:
        findings.append(
            Finding(
                check="index-over-byte-limit",
                detail=(
                    f"Index is {size} bytes; only the first {INDEX_BYTE_LIMIT} "
                    "load. The remainder is dropped at session start."
                ),
                file=str(index_path),
                auto_fixable=True,
            )
        )
    return findings


def _check_topic_file(path: Path, now: dt.datetime, stale_days: int) -> list[Finding]:
    findings: list[Finding] = []
    text = path.read_text(encoding="utf-8", errors="replace")
    fields, has_frontmatter = parse_frontmatter(text)

    if not has_frontmatter:
        findings.append(
            Finding(
                check="missing-frontmatter",
                detail=(
                    "No frontmatter, so the memory declares no type and never "
                    "receives a modified timestamp."
                ),
                file=str(path),
            )
        )
        return findings

    declared = fields.get("type")
    if declared is None:
        findings.append(
            Finding(
                check="missing-type",
                detail=(
                    "Frontmatter declares no type. Expected one of: "
                    + ", ".join(VALID_TYPES)
                ),
                file=str(path),
            )
        )
    elif declared not in VALID_TYPES:
        findings.append(
            Finding(
                check="invalid-type",
                detail=(
                    f"Frontmatter type {declared!r} is outside the documented "
                    "set: " + ", ".join(VALID_TYPES)
                ),
                file=str(path),
            )
        )

    modified = fields.get("modified")
    if modified:
        parsed = _parse_modified(modified)
        if parsed is None:
            findings.append(
                Finding(
                    check="unreadable-modified",
                    detail=f"modified value {modified!r} is not an ISO 8601 timestamp.",
                    file=str(path),
                )
            )
        else:
            age = (now - parsed).days
            if age > stale_days:
                findings.append(
                    Finding(
                        check="stale-memory",
                        detail=(
                            f"Last written {age} days ago, past the "
                            f"{stale_days}-day threshold. Confirm it still holds."
                        ),
                        file=str(path),
                    )
                )
    return findings
