"""Render and re-read the memory improvement overview.

The overview is the seam between the two runs. The analysing run writes it with
applied changes recorded and proposals left unticked; a person ticks what they
agree with; the applying run reads back only the ticked items.

Sign-off is a checkbox rather than a prompt because the applying run has to work
with nobody watching -- an interactive confirmation cannot be answered by a
scheduled task.

A proposal nobody ticks is not carried forever. Each item records how many runs
have seen it, and one that goes unticked past the threshold is reported as
declined and dropped, so the document stays readable rather than becoming a
growing list of things the reader has already decided against.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

OVERVIEW_NAME = "memory-improvement-overview.md"
DEFAULT_EXPIRE_AFTER_RUNS = 3

APPLIED_HEADING = "## Applied"
PENDING_HEADING = "## Awaiting sign-off"
DECLINED_HEADING = "## Declined"

_ITEM = re.compile(
    r"^- \[(?P<tick>[ xX])\]\s+(?P<body>.*?)\s*<!--\s*dream:"
    r"id=(?P<id>[A-Za-z0-9]+)\s+seen=(?P<seen>\d+)\s*-->\s*$"
)


def item_id(*parts: str) -> str:
    """A stable id for a proposal, so the same proposal keeps its identity."""
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()
    return digest[:10]


@dataclass
class Item:
    """One proposal awaiting a decision."""

    title: str
    detail: str = ""
    identifier: str = ""
    seen: int = 1
    ticked: bool = False

    def __post_init__(self):
        if not self.identifier:
            self.identifier = item_id(self.title, self.detail)

    def render(self) -> str:
        body = f"**{self.title}**"
        if self.detail:
            body += f" — {self.detail}"
        mark = "x" if self.ticked else " "
        return f"- [{mark}] {body} <!-- dream:id={self.identifier} seen={self.seen} -->"


@dataclass
class Overview:
    applied: list[str] = field(default_factory=list)
    pending: list[Item] = field(default_factory=list)
    declined: list[Item] = field(default_factory=list)
    generated_at: str = ""
    project_root: str = ""
    memory_dir: str = ""
    snapshot: str = ""
    notes: list[str] = field(default_factory=list)


def render(overview: Overview) -> str:
    """Write the overview as markdown a person can tick."""
    lines = ["# Memory improvement overview", ""]
    for label, value in (
        ("Generated", overview.generated_at),
        ("Project", overview.project_root),
        ("Memory directory", overview.memory_dir),
        ("Snapshot", overview.snapshot),
    ):
        if value:
            lines.append(f"- {label}: {value}")
    lines.append("")

    for note in overview.notes:
        lines.append(f"> {note}")
    if overview.notes:
        lines.append("")

    lines.append(APPLIED_HEADING)
    lines.append("")
    if overview.applied:
        lines.append(
            "Already made. Restore the snapshot above to undo all of them."
        )
        lines.append("")
        lines.extend(f"- {entry}" for entry in overview.applied)
    else:
        lines.append("Nothing was applied automatically in this run.")
    lines.append("")

    lines.append(PENDING_HEADING)
    lines.append("")
    if overview.pending:
        lines.append(
            "Tick an item to have the apply-fixes run make the change. "
            "Leave it unticked to decline."
        )
        lines.append("")
        lines.extend(item.render() for item in overview.pending)
    else:
        lines.append("Nothing is waiting on a decision.")
    lines.append("")

    if overview.declined:
        lines.append(DECLINED_HEADING)
        lines.append("")
        lines.append(
            "Left unticked long enough to be treated as declined, and dropped."
        )
        lines.append("")
        lines.extend(f"- {item.title}" for item in overview.declined)
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def parse(text: str) -> Overview:
    """Read back an overview, recovering each proposal and whether it is ticked."""
    overview = Overview()
    section = ""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            section = stripped
            continue
        if section == PENDING_HEADING:
            match = _ITEM.match(stripped)
            if match:
                body = match.group("body")
                title, _, detail = body.partition(" — ")
                overview.pending.append(
                    Item(
                        title=title.strip().strip("*"),
                        detail=detail.strip(),
                        identifier=match.group("id"),
                        seen=int(match.group("seen")),
                        ticked=match.group("tick").lower() == "x",
                    )
                )
        elif section == APPLIED_HEADING and stripped.startswith("- "):
            overview.applied.append(stripped[2:])
    return overview


def approved(text: str) -> list[Item]:
    """Only the items a person actually ticked."""
    return [item for item in parse(text).pending if item.ticked]


def carry_forward(
    previous: list[Item],
    fresh: list[Item],
    expire_after_runs: int = DEFAULT_EXPIRE_AFTER_RUNS,
) -> tuple[list[Item], list[Item]]:
    """Age untouched proposals into the next run, expiring the stale ones.

    Returns the items still pending and the items now declined. A proposal that
    reappears keeps its identity and its sighting count, so ignoring it for long
    enough is itself a decision.
    """
    by_id = {item.identifier: item for item in previous}
    still_pending: list[Item] = []
    declined: list[Item] = []

    for item in fresh:
        seen_before = by_id.pop(item.identifier, None)
        if seen_before is None:
            still_pending.append(item)
            continue
        if seen_before.ticked:
            # Already approved; the applying run owns it, not this one.
            continue
        item.seen = seen_before.seen + 1
        if item.seen > expire_after_runs:
            declined.append(item)
        else:
            still_pending.append(item)

    return still_pending, declined


def write(path: Path, overview: Overview) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(overview), encoding="utf-8")
    return path


def now_stamp(now: dt.datetime | None = None) -> str:
    now = dt.datetime.now(dt.timezone.utc) if now is None else now
    return now.isoformat()
