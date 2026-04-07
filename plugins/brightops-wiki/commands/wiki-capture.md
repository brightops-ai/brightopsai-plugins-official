---
description: Manually force a wiki capture for this session — bypasses the exchange-count threshold
---

Force a wiki capture for the current session right now, regardless of how many exchanges have passed since the last automatic capture. Use when a session hits a durable conclusion before the 12-exchange threshold and shouldn't wait for the next auto-fire.

## What this does

1. Checks whether the wiki exists at `$BRIGHTOPS_WIKI_ROOT` (default `$HOME/Documents/wiki`). If not, report that the wiki hasn't been bootstrapped and stop.
2. Reads the current session's context and writes a nugget to `$WIKI_ROOT/inbox/raw/` using the same format as the automatic capture hook.
3. Touches a flag file at `$WIKI_ROOT/inbox/.session_state/<session_id>_just_captured` so the Stop hook's guard #3 resets its counter on the next fire instead of immediately re-firing. This prevents a capture-then-auto-capture feedback loop on the next exchange.

## Step 1 — locate the wiki

```bash
WIKI_ROOT="${BRIGHTOPS_WIKI_ROOT:-$HOME/Documents/wiki}"
if [ ! -d "$WIKI_ROOT/inbox" ]; then
    echo "wiki not bootstrapped at $WIKI_ROOT — run /wiki-bootstrap first"
    exit 1
fi
```

If the wiki doesn't exist, tell the user to run the `wiki-bootstrap` skill first, and stop.

## Step 2 — determine session identity

You need `session_id` and `CLAUDE_PROJECT_DIR` to write a well-formed nugget. The `session_id` can be derived from Claude Code's environment or from the transcript file path (which Claude Code sets per session). If neither is available, fall back to generating a UUID and logging that this was a manual-session capture.

```bash
SESSION_ID="${CLAUDE_SESSION_ID:-$(uuidgen 2>/dev/null | tr '[:upper:]' '[:lower:]' || python3 -c 'import uuid; print(uuid.uuid4())')}"
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"
```

## Step 3 — generate the nugget path

Same filename scheme as the automatic hook: `<session_id>-<nanos>-<rand4>.md`.

```bash
NANOS=$(date +%s%N 2>/dev/null || python3 -c 'import time; print(int(time.time()*1e9))')
RAND4=$(python3 -c 'import secrets; print(secrets.token_hex(2))')
NUGGET_PATH="$WIKI_ROOT/inbox/raw/${SESSION_ID}-${NANOS}-${RAND4}.md"
```

## Step 4 — normalize project name

Same rule as the hook: lowercase, non-alphanumeric → `-`, collapse repeats, trim.

```bash
PROJECT_RAW=$(basename "$PROJECT_DIR")
PROJECT_NAME=$(echo "$PROJECT_RAW" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]/-/g' | sed 's/--*/-/g' | sed 's/^-//;s/-$//')
[ -z "$PROJECT_NAME" ] && PROJECT_NAME="unknown"
CAPTURED_AT=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
```

## Step 5 — write the nugget

You (the active Claude session) have the conversation context. Write a nugget file at `$NUGGET_PATH` with this frontmatter (fill in the actual values) plus a body containing the session's durable conclusions:

```yaml
---
origin_project: <PROJECT_NAME>
origin_session: <SESSION_ID>
origin_cwd: <PROJECT_DIR>
captured_at: <CAPTURED_AT>
exchange_count: manual
capture_type: manual-override
---

# <one-line topic title describing what happened in this session>

## Decisions
- (durable decisions with reasoning)

## Findings
- (research findings or root causes)

## Files touched
- (relative paths, max 10)

## Open questions
- (anything left unresolved)
```

Keep the nugget under ~200 lines. If the session was trivial and there's nothing durable to capture, write a single-line nugget: `NONE — no durable conclusions in this session.` and stop.

## Step 6 — set the just-captured flag

Touch the flag file so the Stop hook's guard #3 fires on the next Stop event, resets the counter, and exits silently instead of triggering a second capture:

```bash
touch "$WIKI_ROOT/inbox/.session_state/${SESSION_ID}_just_captured"
```

This flag is consumed by the hook and deleted after the next Stop. It does NOT persist across multiple Stops.

## Step 7 — report

Print a one-line confirmation:

```
captured manually → <NUGGET_PATH>
  project=<PROJECT_NAME> session=<SESSION_ID> at <CAPTURED_AT>
```

Then continue with whatever the user asked next. Do not block the session.

## When NOT to use this

- **Right after the automatic hook fires**: the counter was just updated; another capture 2 minutes later would be redundant. Wait for real new content.
- **In the dedicated wiki processing session**: the hook's recursion guard #2 prevents auto-capture there, but this slash command has no equivalent guard. Calling `/wiki-capture` inside the wiki session itself will write a nugget about the loop session, which is almost certainly noise.
- **When the session hasn't produced anything durable**: just write the `NONE` nugget and stop; don't fabricate content.
