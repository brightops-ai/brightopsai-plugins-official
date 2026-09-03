#!/usr/bin/env python3
"""One entrypoint for every deterministic step the dream skills need.

Skills call this rather than embedding logic in prose: what a machine can decide
exactly should not be re-derived by a model on every run.

    resolve     where this project's memory and transcripts live
    audit       mechanical defects in the memory directory
    extract     candidate episodes distilled from session transcripts
    snapshot    copy the memory directory before changing it
    restore     put a snapshot's files back
    prune       drop all but the newest snapshots
    fix         apply the mechanically certain repairs
    approved    read the ticked items back out of an overview
    deliver     send a summary to the configured destination

Every subcommand prints JSON on stdout and exits non-zero on failure.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

if __package__ in (None, ""):  # invoked as a file path rather than a module
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dream import claude_env, delivery, extract_sessions, fixes, memory_audit, overview, snapshot


def _emit(payload) -> int:
    json.dump(payload, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")
    return 0


def _locations(args) -> claude_env.Locations:
    return claude_env.resolve(Path(args.cwd) if args.cwd else None)


def _since(args) -> dt.datetime | None:
    if args.since:
        parsed = dt.datetime.fromisoformat(args.since.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)
    return None


def cmd_resolve(args) -> int:
    return _emit(_locations(args).as_dict())


def cmd_audit(args) -> int:
    found = _locations(args)
    memory_dir = Path(args.memory_dir) if args.memory_dir else found.memory_dir
    findings = memory_audit.audit(memory_dir, stale_days=args.stale_days)
    return _emit(
        {
            "memory_dir": str(memory_dir),
            "memory_source": found.memory_source,
            "finding_count": len(findings),
            "findings": [f.as_dict() for f in findings],
        }
    )


def cmd_extract(args) -> int:
    found = _locations(args)
    directory = Path(args.transcripts_dir) if args.transcripts_dir else found.transcripts_dir
    digest = extract_sessions.extract(
        directory,
        since=_since(args),
        token_budget=args.token_budget,
        window_days=args.window_days,
    )
    payload = digest.as_dict()
    payload["transcripts_dir"] = str(directory)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return _emit(
            {
                "written": str(out),
                "episode_counts": payload["episode_counts"],
                "truncated": payload["truncated"],
                "retention_gap": payload.get("retention_gap", ""),
            }
        )
    return _emit(payload)


def cmd_snapshot(args) -> int:
    found = _locations(args)
    memory_dir = Path(args.memory_dir) if args.memory_dir else found.memory_dir
    taken = snapshot.create(memory_dir)
    return _emit(
        {"snapshot": str(taken.path), "files": taken.file_count, "taken_at": taken.taken_at}
    )


def cmd_restore(args) -> int:
    found = _locations(args)
    memory_dir = Path(args.memory_dir) if args.memory_dir else found.memory_dir
    restored = snapshot.restore(memory_dir, Path(args.snapshot) if args.snapshot else None)
    return _emit({"memory_dir": str(memory_dir), "restored": restored})


def cmd_prune(args) -> int:
    found = _locations(args)
    memory_dir = Path(args.memory_dir) if args.memory_dir else found.memory_dir
    removed = snapshot.prune(memory_dir, keep=args.keep)
    return _emit({"removed": [str(p) for p in removed], "kept": args.keep})


def cmd_fix(args) -> int:
    found = _locations(args)
    memory_dir = Path(args.memory_dir) if args.memory_dir else found.memory_dir
    taken = None
    if not args.dry_run:
        taken = snapshot.create(memory_dir)
    result = fixes.apply_safe_fixes(memory_dir, dry_run=args.dry_run)
    return _emit(
        {
            "memory_dir": str(memory_dir),
            "snapshot": str(taken.path) if taken else "",
            "dry_run": args.dry_run,
            "applied": result.applied,
            "proposals": [
                {"title": title, "detail": detail} for title, detail in result.proposals
            ],
        }
    )


def cmd_approved(args) -> int:
    text = Path(args.overview).read_text(encoding="utf-8")
    items = overview.approved(text)
    return _emit(
        {
            "overview": args.overview,
            "approved": [
                {"id": i.identifier, "title": i.title, "detail": i.detail} for i in items
            ],
        }
    )


def cmd_deliver(args) -> int:
    summary = (
        Path(args.summary_file).read_text(encoding="utf-8")
        if args.summary_file
        else sys.stdin.read()
    )
    try:
        result = delivery.deliver(summary, destination=args.destination)
    except delivery.DeliveryError as error:
        json.dump({"ok": False, "error": str(error)}, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 2
    return _emit(result.as_dict())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dream", description=__doc__)
    parser.add_argument("--cwd", help="Directory to resolve the project from.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add(name, handler, memory=False):
        sub = subparsers.add_parser(name)
        sub.set_defaults(handler=handler)
        if memory:
            sub.add_argument("--memory-dir", help="Override the resolved memory directory.")
        return sub

    add("resolve", cmd_resolve)

    audit = add("audit", cmd_audit, memory=True)
    audit.add_argument(
        "--stale-days", type=int, default=memory_audit.DEFAULT_STALE_DAYS
    )

    extract = add("extract", cmd_extract)
    extract.add_argument("--transcripts-dir")
    extract.add_argument("--since", help="ISO 8601 start of the window.")
    extract.add_argument(
        "--window-days", type=int, default=extract_sessions.DEFAULT_WINDOW_DAYS
    )
    extract.add_argument(
        "--token-budget", type=int, default=extract_sessions.DEFAULT_TOKEN_BUDGET
    )
    extract.add_argument("--out", help="Write the digest here instead of stdout.")

    add("snapshot", cmd_snapshot, memory=True)

    restore = add("restore", cmd_restore, memory=True)
    restore.add_argument("--snapshot", help="Defaults to the newest snapshot.")

    prune = add("prune", cmd_prune, memory=True)
    prune.add_argument("--keep", type=int, default=snapshot.DEFAULT_KEEP)

    fix = add("fix", cmd_fix, memory=True)
    fix.add_argument("--dry-run", action="store_true")

    approved = add("approved", cmd_approved)
    approved.add_argument("overview")

    deliver = add("deliver", cmd_deliver)
    deliver.add_argument("--summary-file")
    deliver.add_argument("--destination", choices=("file", "command"))

    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.handler(args)
    except (FileNotFoundError, ValueError) as error:
        json.dump({"ok": False, "error": str(error)}, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
