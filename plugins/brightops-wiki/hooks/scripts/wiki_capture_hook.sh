#!/bin/bash
# Intentionally NOT using `set -e` / `set -u`:
# - Claude Code may pass empty or unset environment variables; unbound-var
#   errors would crash the hook on legitimate inputs.
# - The counter logic relies on jq/python silently returning 0 on empty or
#   partial transcripts; non-zero exits should not crash the hook.
# - A crashed hook breaks Claude Code's Stop event handling; we want this
#   script to always exit cleanly (with `{}` or a block decision).
# This mirrors mempalace/hooks/mempal_save_hook.sh which also does not use
# strict mode for the same reasons.
#
# WIKI CAPTURE HOOK — auto-capture session conclusions to global wiki inbox.
#
# Claude Code Stop hook. After every assistant response:
# 1. Counts user messages in the session transcript
# 2. Every CAPTURE_INTERVAL messages, BLOCKS the AI from stopping
# 3. Returns a reason telling the AI to write a "nugget" to the wiki inbox
# 4. AI writes a markdown nugget with frontmatter
# 5. Next Stop fires with stop_hook_active=true → lets AI stop normally
# 6. The /loop session later compiles nuggets into pages/<project>/
#
# The AI does the classification — it has the conversation context. The hook
# does ZERO LLM work. No regex. No filters. Mirrors mempal_save_hook.sh.
#
# === CONFIGURATION ===
#
# Override defaults via environment variables (typically in your shell rc):
#
#   BRIGHTOPS_WIKI_ROOT     — wiki location (default: $HOME/Documents/wiki)
#   BRIGHTOPS_WIKI_INTERVAL — fire every N user messages (default: 12)
#
# === RECURSION GUARDS ===
#
# 1. stop_hook_active=true (post-block second fire) → exit silently
# 2. CLAUDE_PROJECT_DIR == WIKI_ROOT (the dedicated /loop session is INSIDE
#    the wiki itself and must NOT capture itself) → exit silently
# 3. _just_captured flag (set by /wiki-capture slash command) → reset counter,
#    exit silently
#
# === REGISTERED VIA ===
#
# brightops-wiki plugin's hooks/hooks.json. The plugin auto-registers this
# hook on the Stop event when enabled. Restart Claude Code after install.

CAPTURE_INTERVAL="${BRIGHTOPS_WIKI_INTERVAL:-12}"
WIKI_ROOT="${BRIGHTOPS_WIKI_ROOT:-$HOME/Documents/wiki}"
INBOX_DIR="$WIKI_ROOT/inbox"
RAW_DIR="$INBOX_DIR/raw"
STATE_DIR="$INBOX_DIR/.session_state"
LOG_FILE="$STATE_DIR/hook.log"

# If the wiki dir doesn't exist yet, the user hasn't bootstrapped it.
# Exit silently rather than creating an orphan inbox/.
if [ ! -d "$WIKI_ROOT" ]; then
    echo "{}"
    exit 0
fi

mkdir -p "$RAW_DIR" "$STATE_DIR"

# Read JSON input from stdin
INPUT=$(cat)

# Parse fields from Claude Code's JSON
SESSION_ID=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('session_id','unknown'))" 2>/dev/null)
STOP_HOOK_ACTIVE=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('stop_hook_active', False))" 2>/dev/null)
TRANSCRIPT_PATH=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('transcript_path',''))" 2>/dev/null)

# Expand ~ in path
TRANSCRIPT_PATH="${TRANSCRIPT_PATH/#\~/$HOME}"

# === GUARD 1: stop_hook_active ===
if [ "$STOP_HOOK_ACTIVE" = "True" ] || [ "$STOP_HOOK_ACTIVE" = "true" ]; then
    echo "{}"
    exit 0
fi

# === GUARD 2: are we INSIDE the wiki itself? ===
if [ -n "$CLAUDE_PROJECT_DIR" ]; then
    ACTIVE_DIR="$(cd "$CLAUDE_PROJECT_DIR" 2>/dev/null && pwd -P)"
    WIKI_REAL="$(cd "$WIKI_ROOT" 2>/dev/null && pwd -P)"
    if [ "$ACTIVE_DIR" = "$WIKI_REAL" ]; then
        echo "{}"
        exit 0
    fi
fi

# Helper: count user messages from a transcript file path on stdin.
# Reads path from $1 (quoted). Safe for paths with special chars.
count_user_messages() {
    local transcript="$1"
    if [ ! -f "$transcript" ]; then
        echo 0
        return 0
    fi
    # Cap the read at 5 MB so we don't time out on long sessions.
    tail -c 5242880 "$transcript" 2>/dev/null | python3 -c '
import json, sys
count = 0
for line in sys.stdin:
    try:
        entry = json.loads(line)
        msg = entry.get("message", {})
        if isinstance(msg, dict) and msg.get("role") == "user":
            content = msg.get("content", "")
            if isinstance(content, str) and "<command-message>" in content:
                continue
            count += 1
    except Exception:
        pass
print(count)
' 2>/dev/null || echo 0
}

# === GUARD 3: _just_captured flag ===
JUST_CAPTURED_FLAG="$STATE_DIR/${SESSION_ID}_just_captured"
if [ -f "$JUST_CAPTURED_FLAG" ]; then
    rm -f "$JUST_CAPTURED_FLAG"
    EXCHANGE_NOW=$(count_user_messages "$TRANSCRIPT_PATH")
    echo "$EXCHANGE_NOW" > "$STATE_DIR/${SESSION_ID}_last_capture"
    echo "{}"
    exit 0
fi

# === COUNT EXCHANGES ===
EXCHANGE_COUNT=$(count_user_messages "$TRANSCRIPT_PATH")

# === COUNTER STATE ===
LAST_CAPTURE_FILE="$STATE_DIR/${SESSION_ID}_last_capture"
LAST_CAPTURE=0
if [ -f "$LAST_CAPTURE_FILE" ]; then
    LAST_CAPTURE=$(cat "$LAST_CAPTURE_FILE")
fi

SINCE_LAST=$((EXCHANGE_COUNT - LAST_CAPTURE))

echo "[$(date '+%Y-%m-%d %H:%M:%S')] sid=$SESSION_ID cwd=${CLAUDE_PROJECT_DIR:-?} count=$EXCHANGE_COUNT since=$SINCE_LAST" >> "$LOG_FILE"

# === FIRE? ===
if [ "$SINCE_LAST" -ge "$CAPTURE_INTERVAL" ] && [ "$EXCHANGE_COUNT" -gt 0 ]; then
    echo "$EXCHANGE_COUNT" > "$LAST_CAPTURE_FILE"

    # Generate a unique filename: session_id + nanos + 4 random hex chars
    NANOS=$(date +%s%N 2>/dev/null || python3 -c "import time; print(int(time.time()*1e9))")
    RAND4=$(python3 -c "import secrets; print(secrets.token_hex(2))")
    NUGGET_FILENAME="${SESSION_ID}-${NANOS}-${RAND4}.md"
    NUGGET_PATH="$RAW_DIR/$NUGGET_FILENAME"

    # Project name is the basename of the active project dir, normalized.
    if [ -n "$CLAUDE_PROJECT_DIR" ]; then
        PROJECT_RAW=$(basename "$CLAUDE_PROJECT_DIR")
    else
        PROJECT_RAW="unknown"
    fi
    PROJECT_NAME=$(echo "$PROJECT_RAW" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]/-/g' | sed 's/--*/-/g' | sed 's/^-//;s/-$//')
    [ -z "$PROJECT_NAME" ] && PROJECT_NAME="unknown"

    CAPTURED_AT=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

    echo "[$(date '+%Y-%m-%d %H:%M:%S')] FIRING capture sid=$SESSION_ID project=$PROJECT_NAME nugget=$NUGGET_FILENAME" >> "$LOG_FILE"

    cat <<HOOKJSON
{
  "decision": "block",
  "reason": "WIKI CAPTURE checkpoint. Before stopping, write a markdown nugget describing any durable conclusions, decisions, learnings, or research findings from this session. If the session was trivial (just file reads, clarifying questions, simple fixes), write a nugget that says exactly 'NONE — no durable conclusions in this session.' and nothing else.\n\nWrite the nugget to: $NUGGET_PATH\n\nFormat (YAML frontmatter + body):\n\n---\norigin_project: $PROJECT_NAME\norigin_session: $SESSION_ID\norigin_cwd: ${CLAUDE_PROJECT_DIR:-unknown}\ncaptured_at: $CAPTURED_AT\nexchange_count: $EXCHANGE_COUNT\n---\n\n# <one-line topic title>\n\n## Decisions\n- (one bullet per durable decision, with reasoning)\n\n## Findings\n- (one bullet per research finding or root cause)\n\n## Files touched\n- (relative paths, max 10)\n\n## Open questions\n- (anything left unresolved)\n\nKeep the nugget under ~200 lines. Be specific. Use verbatim quotes for important phrases. Then continue with whatever you were doing. The user can /exit normally after this."
}
HOOKJSON
else
    echo "{}"
fi
