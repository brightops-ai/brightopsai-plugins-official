#!/usr/bin/env bash
#
# A stand-in for the CLI, used by every live spec. No spec launches the real
# binary: doing so would mint a session upstream, spend tokens, and on a
# developer's machine could collide with sessions they are working in.
#
# This is a fixture file rather than a string generated inside a spec. An
# earlier version built it with nested here-documents — a spec writing a shell
# script that writes a shell script — and the quoting collapsed silently: the
# stub was syntactically invalid, the session never started, and the failure
# surfaced as a timeout somewhere else entirely. A file that can be read and
# syntax-checked on its own cannot fail that way.
#
# Behaviour is set entirely through the environment, so one fixture covers
# every case:
#
#   FAKE_EXIT=<n>         exit immediately with this status (a CLI that never starts)
#   FAKE_SILENT=1         read input but never answer the handshake
#   FAKE_BRIDGE_NULL=1    publish a null bridge id (alive but unreachable)
#   FAKE_BRIDGE_ID=<id>   publish this bridge id
#   FAKE_SESSION_ID=<id>  use this conversation id (and transcript filename)
#   FAKE_REPORT_CWD=<dir> answer with this directory instead of the real one
#   FAKE_POSTURE=<word>   answer with this posture
#   FAKE_RECORD=<file>    append every line received to this file
#   FAKE_BRACKETED=0      do not enable bracketed paste
#   FAKE_PANE_TEXT=<text> print this to the pane, then behave as if silent
#                         (models a session held at a startup dialog)
#
# Requires SPAWN_SESSIONS_DIR and SPAWN_PROJECTS_DIR, which the spec passes in
# through the launcher's own pre-launch hook.

set -u

if [[ -n "${FAKE_EXIT:-}" ]]; then
  exit "$FAKE_EXIT"
fi

# The real terminal interface enables bracketed paste on entering raw mode.
# Enabling it here is what makes the multiplexer wrap pasted text in paste
# markers, so a spec can tell a single pasted block from a run of keystrokes.
if [[ "${FAKE_BRACKETED:-1}" == "1" ]]; then
  printf '\033[?2004h'
fi

sid="${FAKE_SESSION_ID:-11111111-2222-3333-4444-555555555555}"

if [[ "${FAKE_BRIDGE_NULL:-0}" == "1" ]]; then
  bridge="null"
else
  bridge="\"${FAKE_BRIDGE_ID:-session_fake}\""
fi

# The state file, keyed by process id, exactly as the real CLI publishes it.
printf '{"pid":%s,"sessionId":"%s","bridgeSessionId":%s}\n' "$$" "$sid" "$bridge" \
  > "$SPAWN_SESSIONS_DIR/$$.json"

# The transcript, named after the conversation. The directory name is
# deliberately not derived from the working directory: the launcher locates
# this file by searching for the conversation id, and a fixture that encoded
# the directory the same way the launcher does would test nothing.
proj="$SPAWN_PROJECTS_DIR/encoded-dir"
mkdir -p "$proj"
transcript="$proj/$sid.jsonl"
: > "$transcript"

record="${FAKE_RECORD:-}"
if [[ -n "$record" ]]; then
  : > "$record"
fi

if [[ -n "${FAKE_PANE_TEXT:-}" ]]; then
  printf '%s\n' "$FAKE_PANE_TEXT"
fi

report_cwd="${FAKE_REPORT_CWD:-$PWD}"
posture="${FAKE_POSTURE:-acceptEdits}"

while IFS= read -r line; do
  if [[ -n "$record" ]]; then
    printf '%s\n' "$line" >> "$record"
  fi

  [[ "${FAKE_SILENT:-0}" == "1" ]] && continue

  # The handshake lists its parts rather than showing them assembled, so the
  # token is identified by the words introducing it.
  case "$line" in
    *"the token "*)
      nonce="${line##*the token }"
      nonce="${nonce%%[![:alnum:]]*}"
      printf '{"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"SPAWN-ACK %s cwd=%s posture=%s"}]}}\n' \
        "$nonce" "$report_cwd" "$posture" >> "$transcript"
      ;;
  esac
done
