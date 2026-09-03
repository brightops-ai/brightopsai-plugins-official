"""Apply only the memory changes that are mechanically certain.

The dividing line is whether a change requires an opinion about meaning. Adding
an index entry for a file that has none restores a memory that was already
written and simply could not be reached; removing an entry that points at a
deleted file removes a link that resolves to nothing. Neither decides anything.

Resolving a contradiction, retiring a rule, or shortening an index by choosing
which entries matter least are judgements, and they are proposed instead. A
wrongly merged memory does not error -- it quietly misinforms every later
session -- so the cost of being wrong here is paid slowly and invisibly, which
is exactly the case for keeping a person in the loop.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from . import memory_audit

_INDEX_ENTRY = re.compile(r"^\s*[-*]\s+")


@dataclass
class FixResult:
    applied: list[str]
    proposals: list[tuple[str, str]]


def _index_lines(index_path: Path) -> list[str]:
    if not index_path.exists():
        return []
    return index_path.read_text(encoding="utf-8", errors="replace").splitlines()


def _entry_targets(line: str) -> set[str]:
    targets = set()
    for match in memory_audit._MARKDOWN_LINK.findall(line):
        target = match.split("#", 1)[0].strip()
        if target:
            targets.add(Path(target).name)
    for match in memory_audit._WIKI_LINK.findall(line):
        name = match.split("|", 1)[0].strip()
        if name:
            targets.add(name if name.endswith(".md") else f"{name}.md")
    return targets


def _safe_link_text(text: str) -> str:
    """Strip characters that would break the markdown link being generated."""
    return re.sub(r"[\[\]()]", "", text).strip()


def _describe(path: Path) -> str:
    """A one-line description for an index entry, taken from the file itself."""
    text = path.read_text(encoding="utf-8", errors="replace")
    fields, _ = memory_audit.parse_frontmatter(text)
    described = fields.get("description")
    if described:
        return described
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith(("-", "#")) and ":" not in stripped[:20]:
            return stripped[:100]
    return "recovered memory"


def apply_safe_fixes(memory_dir: Path, dry_run: bool = False) -> FixResult:
    """Make the mechanically certain repairs; propose everything else."""
    memory_dir = Path(memory_dir)
    applied: list[str] = []
    proposals: list[tuple[str, str]] = []

    if not memory_dir.is_dir():
        return FixResult(applied, [("Memory directory missing", str(memory_dir))])

    index_path = memory_dir / memory_audit.INDEX_NAME
    lines = _index_lines(index_path)
    present = {p.name for p in memory_dir.glob("*.md") if p.name != memory_audit.INDEX_NAME}

    kept: list[str] = []
    seen_entries: set[str] = set()
    referenced: set[str] = set()

    for line in lines:
        targets = _entry_targets(line)
        if targets and not (targets & present):
            applied.append(
                f"Removed dead index entry pointing at {', '.join(sorted(targets))}"
            )
            continue
        missing_in_line = targets - present if targets else set()
        if missing_in_line:
            # The line also links something that still exists, so removing it
            # would lose a live entry. Left alone -- but say so, or the audit
            # reports this dead link on every run and the fix silently never
            # resolves it.
            proposals.append(
                (
                    "Index entry mixes a live and a dead link",
                    f"The entry {line.strip()[:70]!r} links to "
                    f"{', '.join(sorted(missing_in_line))}, which no longer "
                    "exists, alongside a file that does. Removing the whole "
                    "entry would lose the live link, so this needs a decision.",
                )
            )
        if _INDEX_ENTRY.match(line) and line.strip() in seen_entries:
            applied.append(f"Removed duplicate index entry: {line.strip()[:60]}")
            continue
        if _INDEX_ENTRY.match(line):
            seen_entries.add(line.strip())
        referenced |= targets
        kept.append(line)

    for orphan in sorted(present - referenced):
        path = memory_dir / orphan
        title = _safe_link_text(path.stem.replace("_", " ").replace("-", " "))
        kept.append(f"- [{title}]({orphan}) — {_safe_link_text(_describe(path))}")
        applied.append(f"Linked unreachable memory {orphan} into the index")

    collapsed: list[str] = []
    for line in kept:
        if not line.strip() and collapsed and not collapsed[-1].strip():
            continue
        collapsed.append(line)
    if len(collapsed) < len(kept):
        applied.append("Collapsed repeated blank lines in the index")

    text = "\n".join(collapsed).rstrip() + "\n" if collapsed else ""
    over_lines = len(collapsed) > memory_audit.INDEX_LINE_LIMIT
    over_bytes = len(text.encode("utf-8")) > memory_audit.INDEX_BYTE_LIMIT
    if over_lines or over_bytes:
        proposals.append(
            (
                "Shorten the memory index",
                f"The index is still {len(collapsed)} lines / "
                f"{len(text.encode('utf-8'))} bytes after mechanical cleanup, so "
                "content past the load limit is still dropped at session start. "
                "Deciding which entries to merge or move into topic files needs "
                "a judgement about what matters.",
            )
        )

    if applied and not dry_run:
        index_path.write_text(text, encoding="utf-8")

    return FixResult(applied, proposals)
