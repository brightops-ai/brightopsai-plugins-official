"""Copy a memory directory before anything changes it.

Snapshots live beside the memory directory they protect, never in per-plugin
data. Per-plugin data is removed when a plugin is uninstalled from its last
scope, and a safety copy whose lifetime is tied to the plugin's installation is
not a safety copy: uninstalling the tool would destroy the only record of what
memory looked like before the tool touched it.
"""

from __future__ import annotations

import datetime as dt
import shutil
from dataclasses import dataclass
from pathlib import Path

SNAPSHOT_DIR_NAME = "dream-snapshots"
DEFAULT_KEEP = 10


def snapshot_root(memory_dir: Path) -> Path:
    """Where snapshots for ``memory_dir`` live: beside it, not inside it."""
    return Path(memory_dir).parent / SNAPSHOT_DIR_NAME


@dataclass(frozen=True)
class Snapshot:
    path: Path
    taken_at: str
    file_count: int


def create(memory_dir: Path, now: dt.datetime | None = None) -> Snapshot:
    """Copy every markdown file in ``memory_dir`` into a timestamped snapshot."""
    memory_dir = Path(memory_dir)
    if not memory_dir.is_dir():
        raise FileNotFoundError(f"No memory directory at {memory_dir}")

    now = dt.datetime.now(dt.timezone.utc) if now is None else now
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    destination = snapshot_root(memory_dir) / stamp
    suffix = 1
    while destination.exists():
        suffix += 1
        destination = snapshot_root(memory_dir) / f"{stamp}-{suffix}"
    destination.mkdir(parents=True)

    count = 0
    for source in sorted(memory_dir.glob("*.md")):
        shutil.copy2(source, destination / source.name)
        count += 1

    return Snapshot(path=destination, taken_at=now.isoformat(), file_count=count)


def list_snapshots(memory_dir: Path) -> list[Path]:
    """Every snapshot for ``memory_dir``, oldest first."""
    root = snapshot_root(memory_dir)
    if not root.is_dir():
        return []
    return sorted(p for p in root.iterdir() if p.is_dir())


def restore(memory_dir: Path, snapshot: Path | None = None) -> list[str]:
    """Put a snapshot's files back, replacing what is there now.

    Files created since the snapshot are left alone rather than deleted: this
    restores what was captured, it does not reset the directory.
    """
    memory_dir = Path(memory_dir)
    if snapshot is None:
        available = list_snapshots(memory_dir)
        if not available:
            raise FileNotFoundError(f"No snapshots for {memory_dir}")
        snapshot = available[-1]

    snapshot = Path(snapshot)
    if not snapshot.is_dir():
        raise FileNotFoundError(f"No snapshot at {snapshot}")

    memory_dir.mkdir(parents=True, exist_ok=True)
    restored = []
    for source in sorted(snapshot.glob("*.md")):
        shutil.copy2(source, memory_dir / source.name)
        restored.append(source.name)
    return restored


def prune(memory_dir: Path, keep: int = DEFAULT_KEEP) -> list[Path]:
    """Delete all but the newest ``keep`` snapshots. Returns what was removed."""
    if keep < 1:
        raise ValueError("keep must be at least 1")
    available = list_snapshots(memory_dir)
    removed = []
    for path in available[:-keep] if len(available) > keep else []:
        shutil.rmtree(path)
        removed.append(path)
    return removed
