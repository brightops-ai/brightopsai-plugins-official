"""Distil raw session transcripts into a small set of candidate episodes.

Transcripts are far too large to read directly -- a single active project can
hold hundreds of megabytes -- so this script reduces them to the moments worth
judging, and the judgement happens elsewhere.

The division of labour is the whole point. This script finds *structure*: a run
that was interrupted, a command that failed the same way repeatedly, a
permission that was refused, a terse human turn landing right after an edit. It
never decides that an episode was a correction, and it never decides that two
episodes are the same correction. Those are judgements about meaning, and a
regular expression that tried to make them would be wrong in both directions --
measured against real transcripts, lexical correction markers matched barely
six percent of human turns and most of what they matched were not corrections
at all.

Secrets are redacted here rather than at delivery, so no artefact this suite
writes ever holds one.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

# Roughly four characters per token; used only to keep a digest inside budget.
CHARS_PER_TOKEN = 4
DEFAULT_TOKEN_BUDGET = 40_000
DEFAULT_WINDOW_DAYS = 7
QUICK_TURN_CHARS = 240
EDIT_TOOLS = frozenset({"Edit", "Write", "NotebookEdit", "MultiEdit"})

INTERRUPT_MARKER = "[Request interrupted by user"
DENIAL_MARKERS = (
    "user doesn't want to proceed",
    "user doesn't want to take this action",
    "requested permissions to use",
)

_REDACTIONS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b(sk-[A-Za-z0-9_-]{16,})"), "[redacted-api-key]"),
    (re.compile(r"\b(gh[pousr]_[A-Za-z0-9]{16,})"), "[redacted-token]"),
    (re.compile(r"\b(AKIA[0-9A-Z]{12,})"), "[redacted-aws-key]"),
    (re.compile(r"\b(xox[abposr]-[A-Za-z0-9-]{8,})"), "[redacted-token]"),
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{16,}"), "Bearer [redacted]"),
    (
        re.compile(
            r"(?i)\b(api[_-]?key|secret|token|password|passwd|pwd)"
            r"\s*[:=]\s*[\"']?[^\s\"',]{6,}"
        ),
        r"\1=[redacted]",
    ),
    (
        re.compile(r"-----BEGIN[^-]*PRIVATE KEY-----.*?-----END[^-]*PRIVATE KEY-----", re.S),
        "[redacted-private-key]",
    ),
    (re.compile(r"\b[a-z]+://[^\s/@]+:[^\s/@]+@"), "[redacted-credentials]@"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"), "[redacted-jwt]"),
)


def redact(text: str) -> str:
    """Remove credential-shaped substrings. Applied before anything is stored."""
    for pattern, replacement in _REDACTIONS:
        text = pattern.sub(replacement, text)
    return text


def _clip(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


@dataclass
class Episode:
    """One structurally notable moment, with enough context to be judged."""

    kind: str
    session: str
    timestamp: str
    summary: str
    detail: str = ""
    tool: str = ""
    target: str = ""
    preceding_action: str = ""
    occurrences: int = 1
    git_branch: str = ""

    def as_dict(self) -> dict:
        payload = {
            "kind": self.kind,
            "session": self.session,
            "timestamp": self.timestamp,
            "summary": self.summary,
        }
        for key in ("detail", "tool", "target", "preceding_action", "git_branch"):
            value = getattr(self, key)
            if value:
                payload[key] = value
        if self.occurrences > 1:
            payload["occurrences"] = self.occurrences
        return payload

    def cost(self) -> int:
        return max(1, len(json.dumps(self.as_dict())) // CHARS_PER_TOKEN)


@dataclass
class Digest:
    episodes: list[Episode] = field(default_factory=list)
    sessions_read: int = 0
    records_read: int = 0
    window_start: str = ""
    window_end: str = ""
    truncated: bool = False
    dropped: int = 0
    retention_gap: str = ""

    def as_dict(self) -> dict:
        counts: dict[str, int] = defaultdict(int)
        for episode in self.episodes:
            counts[episode.kind] += 1
        payload = {
            "window": {"start": self.window_start, "end": self.window_end},
            "sessions_read": self.sessions_read,
            "records_read": self.records_read,
            "episode_counts": dict(sorted(counts.items())),
            "truncated": self.truncated,
            "episodes": [e.as_dict() for e in self.episodes],
        }
        if self.dropped:
            payload["episodes_dropped_for_budget"] = self.dropped
        if self.retention_gap:
            payload["retention_gap"] = self.retention_gap
        return payload


def _text_of(content) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text":
            parts.append(block.get("text", ""))
    return "".join(parts)


def _tool_uses(content) -> list[tuple[str, dict]]:
    uses = []
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                uses.append((block.get("name", ""), block.get("input") or {}))
    return uses


def _tool_results(content) -> list[tuple[bool, str]]:
    results = []
    if isinstance(content, list):
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_result":
                continue
            raw = block.get("content")
            if isinstance(raw, list):
                raw = "".join(
                    b.get("text", "") for b in raw if isinstance(b, dict)
                )
            results.append((bool(block.get("is_error")), raw if isinstance(raw, str) else ""))
    return results


def _describe_action(name: str, params: dict) -> tuple[str, str]:
    """A short label for what a tool call was doing, and what it touched."""
    target = ""
    for key in ("file_path", "path", "notebook_path", "pattern", "url"):
        value = params.get(key)
        if isinstance(value, str) and value:
            target = Path(value).name if "/" in value else value
            break
    if not target and name == "Bash":
        command = params.get("command")
        if isinstance(command, str):
            target = _clip(command, 80)
    return name, target


def _error_signature(tool: str, text: str) -> str:
    first = _clip(text, 120)
    first = re.sub(r"\d+", "N", first)
    return f"{tool}:{first}"


def _parse_time(value) -> dt.datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)


def extract(
    transcripts_dir: Path,
    since: dt.datetime | None = None,
    now: dt.datetime | None = None,
    token_budget: int = DEFAULT_TOKEN_BUDGET,
    window_days: int = DEFAULT_WINDOW_DAYS,
) -> Digest:
    """Build a digest of candidate episodes from every transcript in scope."""
    now = dt.datetime.now(dt.timezone.utc) if now is None else now
    if since is None:
        since = now - dt.timedelta(days=window_days)

    digest = Digest(window_start=since.isoformat(), window_end=now.isoformat())
    transcripts_dir = Path(transcripts_dir)
    if not transcripts_dir.is_dir():
        digest.retention_gap = f"No transcript directory at {transcripts_dir}."
        return digest

    files = sorted(transcripts_dir.glob("*.jsonl"))
    if not files:
        digest.retention_gap = "No session transcripts found for this project."
        return digest

    oldest = min(dt.datetime.fromtimestamp(f.stat().st_mtime, dt.timezone.utc) for f in files)
    if oldest > since:
        digest.retention_gap = (
            f"Requested window opens {since.date()}, but the oldest surviving "
            f"transcript is from {oldest.date()}. Sessions before that were "
            "removed by transcript retention and could not be read."
        )

    collected: list[Episode] = []
    error_clusters: dict[str, Episode] = {}

    for path in files:
        digest.sessions_read += 1
        collected.extend(
            _scan_transcript(path, since, digest, error_clusters)
        )

    collected.extend(error_clusters.values())
    collected.sort(key=lambda e: e.timestamp, reverse=True)

    kept: list[Episode] = []
    spent = 0
    for episode in collected:
        cost = episode.cost()
        if spent + cost > token_budget:
            digest.truncated = True
            digest.dropped += 1
            continue
        kept.append(episode)
        spent += cost

    digest.episodes = kept
    return digest


def _scan_transcript(
    path: Path,
    since: dt.datetime,
    digest: Digest,
    error_clusters: dict[str, Episode],
) -> list[Episode]:
    episodes: list[Episode] = []
    session = path.stem
    last_action: tuple[str, str, str] | None = None  # (tool, target, timestamp)

    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if not isinstance(record, dict):
                continue
            digest.records_read += 1

            if record.get("isSidechain"):
                continue

            when = _parse_time(record.get("timestamp"))
            if when is None or when < since:
                continue
            stamp = when.isoformat()
            branch = record.get("gitBranch") or ""
            message = record.get("message")
            content = message.get("content") if isinstance(message, dict) else None
            kind = record.get("type")

            if kind == "assistant":
                for name, params in _tool_uses(content):
                    tool, target = _describe_action(name, params)
                    last_action = (tool, target, stamp)
                text = _text_of(content)
                if INTERRUPT_MARKER in text:
                    episodes.append(
                        _interrupt_episode(session, stamp, branch, last_action)
                    )
                continue

            if kind != "user":
                continue

            text = _text_of(content)
            if INTERRUPT_MARKER in text:
                episodes.append(
                    _interrupt_episode(session, stamp, branch, last_action)
                )
                continue

            handled = False
            for is_error, result_text in _tool_results(content):
                lowered = result_text.lower()
                if any(marker in lowered for marker in DENIAL_MARKERS):
                    episodes.append(
                        Episode(
                            kind="permission-denied",
                            session=session,
                            timestamp=stamp,
                            git_branch=branch,
                            tool=last_action[0] if last_action else "",
                            target=last_action[1] if last_action else "",
                            summary="A tool call was refused by the user.",
                            detail=redact(_clip(result_text, 200)),
                            preceding_action=_action_label(last_action),
                        )
                    )
                    handled = True
                elif is_error:
                    tool = last_action[0] if last_action else "unknown"
                    signature = _error_signature(tool, result_text)
                    existing = error_clusters.get(signature)
                    if existing is None:
                        error_clusters[signature] = Episode(
                            kind="tool-failure",
                            session=session,
                            timestamp=stamp,
                            git_branch=branch,
                            tool=tool,
                            target=last_action[1] if last_action else "",
                            summary=f"{tool} failed.",
                            detail=redact(_clip(result_text, 300)),
                            preceding_action=_action_label(last_action),
                        )
                    else:
                        existing.occurrences += 1
                        if stamp > existing.timestamp:
                            existing.timestamp = stamp
                    handled = True

            if handled or not text.strip():
                continue
            if text.lstrip().startswith("<"):
                continue

            if (
                last_action
                and last_action[0] in EDIT_TOOLS
                and len(text.strip()) <= QUICK_TURN_CHARS
            ):
                episodes.append(
                    Episode(
                        kind="quick-turn-after-edit",
                        session=session,
                        timestamp=stamp,
                        git_branch=branch,
                        tool=last_action[0],
                        target=last_action[1],
                        summary="A short human turn landed immediately after an edit.",
                        detail=redact(_clip(text, 240)),
                        preceding_action=_action_label(last_action),
                    )
                )
            last_action = None
    return episodes


def _action_label(last_action) -> str:
    if not last_action:
        return ""
    tool, target, _ = last_action
    return f"{tool} {target}".strip()


def _interrupt_episode(session, stamp, branch, last_action) -> Episode:
    return Episode(
        kind="interrupted",
        session=session,
        timestamp=stamp,
        git_branch=branch,
        tool=last_action[0] if last_action else "",
        target=last_action[1] if last_action else "",
        summary="The user interrupted the assistant mid-run.",
        preceding_action=_action_label(last_action),
    )
