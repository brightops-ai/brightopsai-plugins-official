# shellcheck shell=bash
#
# Pure decision logic for spawn-session.
#
# Nothing here talks to tmux, the filesystem, the network or the clock. Every
# value arrives as an argument and every answer is returned on stdout. That is
# what makes these decisions testable without launching anything — the part of
# this skill most likely to be wrong is the reasoning, not the plumbing, and
# reasoning is only cheap to test when it is separated from effects.

# spawn_launch_command <session_name> <posture> <pre_launch>
#
# Echoes the shell line typed into the new pane. Kept separate from the typing
# so what gets launched is assertable without launching anything.
#
# This tool spawns; it never resumes. In particular it never emits --continue,
# which resolves to the most recently active conversation in the working
# directory rather than a named one — in a directory hosting two sessions that
# reattaches the wrong conversation and takes over its remote-control bridge.
spawn_launch_command() {
  local session_name="$1" posture="${2:-}" pre_launch="${3:-}"

  # A CLI launched from inside another CLI session inherits these and refuses
  # to start, believing itself nested. The pane inherits the environment of
  # whatever ran this script, so they must be cleared in the pane itself.
  local unset_nested="unset CLAUDECODE CLAUDE_CODE_CHILD_SESSION CLAUDE_CODE_SESSION_ID CLAUDE_CODE_ENTRYPOINT CLAUDE_CODE_EXECPATH CLAUDE_EFFORT"

  # Fail toward fewer privileges: exactly the token `bypass` launches
  # unattended, and every other value — a typo, a truncation, the empty
  # default — is acceptEdits. A corrupted posture must never grant more.
  local perm_flag="--permission-mode acceptEdits"
  [[ "$posture" == "bypass" ]] && perm_flag="--dangerously-skip-permissions"

  # The portability seam. This skill knows nothing about how any particular
  # machine injects environment — a credential helper, a version manager, a
  # secrets file — so the caller supplies that as a command run in the pane
  # before the CLI starts. Placed after the unset so it cannot be undone by
  # it, and before the CLI so it can actually affect it.
  local line="$unset_nested"
  [[ -n "$pre_launch" ]] && line="$line; $pre_launch"
  line="$line; claude $perm_flag --remote-control $session_name"

  printf '%s\n' "$line"
}

# valid_session_name <name>
#
# Returns 0 if the name is safe to hand to the multiplexer and to reuse for
# every later exact-match lookup.
#
# The rule that matters is the dot and the colon. Neither is rejected by the
# multiplexer — both are silently rewritten to an underscore, so a session
# asked for as `a.b` is created as `a_b`. Every subsequent exact-match lookup
# on the requested name then misses, and the fallback is prefix matching,
# which can resolve to a different session entirely. Accepting a character
# that triggers a silent rename means the caller does not have the session
# they asked for and has no way to notice.
#
# A leading dash is refused separately: the multiplexer's own argument parser
# reads it as an option rather than a name.
valid_session_name() {
  local name="$1"

  [[ -n "$name" ]] || return 1
  (( ${#name} <= 64 )) || return 1
  [[ "$name" != -* ]] || return 1
  # LC_ALL pins the ranges: under some locales a range like A-Z collates
  # loosely enough to admit characters the multiplexer will mangle, which
  # would make this check pass or fail by environment rather than by input.
  local LC_ALL=C
  [[ "$name" =~ ^[A-Za-z0-9_-]+$ ]] || return 1
}

# spawn_verdict <pid> <bridge_session_id>
#
# Classifies what was observed about a spawned session. Three outcomes,
# deliberately not two:
#
#   no_process   nothing is running under the session
#   bridge_dead  a live process whose remote-control bridge is absent
#   healthy      a live process with a live bridge
#
# `bridge_dead` exists because a dead bridge is invisible to a liveness check:
# the process and its session both survive it, so "is it running" answers yes
# while the session is unreachable from the web client. Collapsing it into
# either neighbour is what leads a caller to destroy a working session — one
# holding a real conversation — in order to repair connectivity.
spawn_verdict() {
  local pid="$1" bridge="$2"

  if [[ -z "$pid" ]]; then
    echo "no_process"
  elif [[ -z "$bridge" || "$bridge" == "null" ]]; then
    echo "bridge_dead"
  else
    echo "healthy"
  fi
}

# bridge_url <bridge_session_id>
#
# Renders the remote-control link for a session, or fails without printing.
#
# The identifier is minted per bridge, so this link is valid for the bridge
# that is live right now and not for the session in general: a restart mints a
# new one. It is a handoff line, never something to persist.
bridge_url() {
  local id="$1"
  [[ -n "$id" && "$id" != "null" ]] || return 1
  printf 'https://claude.ai/code/%s\n' "$id"
}

# ── the handshake ───────────────────────────────────────────────────────────
#
# A session is asked to identify itself before it is sent any work. The reply
# is read from the session's own transcript, so a reply arriving from anywhere
# else is not seen at all — which is what makes delivering a brief into the
# wrong pane impossible rather than merely unlikely.

# handshake_text <nonce>
#
# The message asking a new session to identify itself.
#
# Written so that the instruction can never be mistaken for the reply. Both
# land in the same transcript, and a literal well-formed acknowledgement
# inside the request would match on the way out — the spawner would confirm a
# session that had not yet said anything. The required parts are therefore
# listed rather than shown assembled.
handshake_text() {
  local nonce="$1"
  cat <<EOF
Before doing anything else, reply with a single line and then stop.

The line must contain, separated by single spaces and in this order:
  1. the word SPAWN-ACK
  2. the token $nonce
  3. cwd= immediately followed by your working directory, exactly as pwd reports it
  4. posture= immediately followed by one of: acceptEdits, bypass, unknown

Report the directory you are actually in, not the one you were told to expect.
Use unknown for posture if you cannot determine how you were launched; do not
guess. Send that one line, then wait for further instructions.
EOF
}

# ack_matches <nonce> <text>
#
# Returns 0 if the text contains an acknowledgement carrying this nonce.
#
# The separators are literal spaces rather than a general whitespace class:
# whitespace would match across newlines, letting the parts of a multi-line
# instruction join up into an accidental match.
ack_matches() {
  local nonce="$1" text="$2"
  [[ "$text" =~ SPAWN-ACK[' ']+"$nonce"[' ']+cwd=[^' ']+[' ']+posture=[A-Za-z]+ ]]
}

# parse_ack <field> <line>
#
# Echoes the value of cwd or posture from an acknowledgement line.
parse_ack() {
  local field="$1" line="$2"
  [[ "$line" =~ (^|[' '])"$field"=([^' ']+) ]] || return 1
  printf '%s\n' "${BASH_REMATCH[2]}"
}

# ack_verdict <expected_cwd> <reported_cwd> <expected_posture> <reported_posture>
#
# Decides whether the session that answered is the session that was launched.
#
#   ok                   identity confirmed
#   mismatch_cwd         answered from a different directory — not our session
#   mismatch_posture     running under permissions other than those requested
#   posture_unverified   identity confirmed, posture could not be checked
#
# A directory mismatch is the wrong-pane detector and is disqualifying. An
# unknown posture is a weaker answer, not a contradictory one: treating it as
# failure would reject every session unable to introspect its own launch
# flags, buying no safety.
ack_verdict() {
  local want_dir="$1" got_dir="$2" want_posture="$3" got_posture="$4"

  if [[ "$want_dir" != "$got_dir" ]]; then
    echo "mismatch_cwd"
  elif [[ "$got_posture" == "unknown" || -z "$got_posture" ]]; then
    echo "posture_unverified"
  elif [[ "$want_posture" != "$got_posture" ]]; then
    echo "mismatch_posture"
  else
    echo "ok"
  fi
}

# brief_source <inline> <file>
#
# Echoes which source the brief comes from: inline, file, or none.
#
# Two sources is an error rather than a precedence rule. A caller who passed
# both meant one of them, and silently picking either delivers a brief they
# did not intend — into a session that will act on it.
brief_source() {
  local inline="$1" file="$2"

  if [[ -n "$inline" && -n "$file" ]]; then
    return 1
  elif [[ -n "$inline" ]]; then
    echo "inline"
  elif [[ -n "$file" ]]; then
    echo "file"
  else
    echo "none"
  fi
}

# trust_key <resolved_dir> <git_root>
#
# Echoes the key under which workspace trust is recorded: the repository root
# when the directory is inside one, the directory itself otherwise.
#
# This mirrors the CLI's own derivation, and it has a consequence the caller
# must be told about rather than left to discover: granting trust for a
# directory inside a repository grants it for the whole repository. A flag
# that quietly authorises more than the path it was given is a flag that
# surprises someone eventually.
trust_key() {
  local dir="$1" git_root="$2"
  if [[ -n "$git_root" ]]; then
    printf '%s\n' "$git_root"
  else
    printf '%s\n' "$dir"
  fi
}

# ── naming what is holding a session ────────────────────────────────────────

# blocker_for <table_text> <pane_text>
#
# Echoes "id<TAB>what<TAB>remedy" for the first table entry whose pattern
# appears in the pane, or nothing.
#
# Matching is literal. Patterns come from a data file, and dialog text is full
# of characters that are meaningful in an expression — a dot, a bracket, a
# question mark. Interpreting them would let one entry match panes it was
# never written for, and the failure would be a confidently wrong diagnosis
# rather than a missing one.
blocker_for() {
  local table="$1" pane="$2"
  local line id pattern what remedy

  while IFS= read -r line; do
    # The table carries a long explanatory header; treating comment lines as
    # patterns would match almost anything.
    [[ -z "$line" || "$line" == '#'* ]] && continue

    IFS=$'\t' read -r id pattern what remedy <<< "$line"
    [[ -n "$pattern" ]] || continue

    # Quoting the pattern inside the bracket expression is what makes the
    # match literal: unquoted, it would be read as a glob.
    if [[ "$pane" == *"$pattern"* ]]; then
      printf '%s\t%s\t%s\n' "$id" "$what" "$remedy"
      return 0
    fi
  done <<< "$table"

  return 1
}

# version_verdict <installed> <pinned>
#
# Compares the CLI version present against the one this skill's dialog
# patterns were verified against: ok, drift, or unknown.
#
# Advisory by design. The dialog wording, option order and highlight glyph are
# all version-dependent, so a newer CLI may well hold a session at a dialog
# this table does not recognise — but refusing to spawn on a version bump
# would break the tool on every routine update, which is how a safety feature
# becomes the thing people disable.
version_verdict() {
  local installed="$1" pinned="$2"

  if [[ -z "$installed" || -z "$pinned" ]]; then
    echo "unknown"
  elif [[ "$installed" == "$pinned" ]]; then
    echo "ok"
  else
    echo "drift"
  fi
}

# trust_grantable <key> <home>
#
# Returns 0 if trust for this key can actually be recorded.
#
# The home directory is the exception. The CLI accepts trust there for the
# running session only and deliberately never persists it, so writing the
# configuration entry would succeed, change nothing the CLI consults, and let
# the next session stop at the same dialog. Reporting that as a grant would be
# worse than refusing: the caller would believe the problem was solved.
trust_grantable() {
  local key="$1" home="$2"
  [[ -n "$home" && "$key" == "$home" ]] && return 1
  return 0
}
