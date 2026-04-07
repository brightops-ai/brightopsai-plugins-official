---
description: Show wiki state — pending inbox, recent log entries, current status, lint results
---

Show a snapshot of the wiki's current state. Use when you want a quick "where am I" without running the full compile loop.

Read `$BRIGHTOPS_WIKI_ROOT` from the environment. If unset, use `$HOME/Documents/wiki`.

## Step 1 — basic existence check

```bash
WIKI_ROOT="${BRIGHTOPS_WIKI_ROOT:-$HOME/Documents/wiki}"
if [ ! -d "$WIKI_ROOT/docs/wiki" ]; then
    echo "wiki not bootstrapped at $WIKI_ROOT"
    exit 1
fi
echo "wiki: $WIKI_ROOT"
```

## Step 2 — count pending nuggets

```bash
PENDING=$(ls "$WIKI_ROOT"/inbox/raw/*.md 2>/dev/null | wc -l | tr -d ' ')
echo "inbox: $PENDING pending"
```

If `$PENDING > 0`, list them briefly with their `origin_project` values so the user knows what's about to be compiled:

```bash
for f in "$WIKI_ROOT"/inbox/raw/*.md; do
    [ -f "$f" ] || continue
    project=$(grep -m1 '^origin_project:' "$f" | awk '{print $2}')
    ts=$(grep -m1 '^captured_at:' "$f" | awk '{print $2}')
    title=$(grep -m1 '^# ' "$f" | sed 's/^# //')
    echo "  [$project @ $ts] $title"
done
```

## Step 3 — last 3 log entries

```bash
tail -n 30 "$WIKI_ROOT/docs/wiki/log.md" | grep -E '^## \[' | tail -n 3
```

## Step 4 — page count by project

Walk `pages/**/*.md` and report counts per project subdir:

```bash
if [ -d "$WIKI_ROOT/docs/wiki/pages" ]; then
    echo "pages:"
    for dir in "$WIKI_ROOT"/docs/wiki/pages/*/; do
        [ -d "$dir" ] || continue
        project=$(basename "$dir")
        count=$(find "$dir" -name '*.md' -type f | wc -l | tr -d ' ')
        echo "  $project: $count"
    done
fi
```

## Step 5 — run lint checks silently, report only failures

```bash
cd "$WIKI_ROOT"
wiki_check_out=$(python3 scripts/wiki_check.py 2>&1 || true)
provenance_out=$(python3 scripts/provenance_check.py 2>&1 || true)

if echo "$wiki_check_out" | grep -q 'FAILED\|ERROR'; then
    echo "wiki_check: FAILED"
    echo "$wiki_check_out" | tail -20
else
    echo "wiki_check: OK"
fi

if echo "$provenance_out" | grep -q 'STALE\|FAILED\|unresolved'; then
    echo "provenance_check: issues"
    echo "$provenance_out" | tail -10
else
    echo "provenance_check: OK"
fi
```

## Step 6 — hook state

Report the number of active session counter files so the user knows which sessions have captured today:

```bash
SESSIONS=$(ls "$WIKI_ROOT"/inbox/.session_state/*_last_capture 2>/dev/null | wc -l | tr -d ' ')
echo "active session counters: $SESSIONS"
```

## Step 7 — final summary

Compose a short one-paragraph summary based on the data gathered above:

- If inbox is empty + all checks pass + recent log entries look normal → "wiki healthy, nothing pending."
- If inbox has pending nuggets → "N nuggets pending compile. Run `/wiki-process-inbox` or wait for the next `/loop` tick."
- If lint failures → "wiki has lint issues, investigate before committing new work."
- If no recent log entries → "wiki is quiet — no recent activity."

## What this command does NOT do

- Does NOT compile any nuggets. Use `/wiki-process-inbox` for that.
- Does NOT modify the wiki. Read-only inspection.
- Does NOT commit anything. No git operations.
- Does NOT run `stale_report.py` (too noisy for a quick snapshot). Run it manually if you want stale detection.
