#!/usr/bin/env bash
#
# spawn-session — create a named Claude Code session under a terminal
# multiplexer, with remote control enabled, and report whether it came up.
#
# Effects live here; decisions live in lib/session-spawn.sh. This file talks
# to the multiplexer, the process table and the filesystem, and does as little
# reasoning as it can get away with.
#
# Every session target uses the "=" prefix, which forces an exact match.
# Without it the multiplexer falls back to prefix matching, so a lookup for
# "worker" resolves to "worker-2" — silently operating on a session the caller
# never named. Pane targets need the trailing colon as well: "=name:".

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
# shellcheck source=lib/session-spawn.sh
source "$SCRIPT_DIR/lib/session-spawn.sh"

# Where the CLI records the live state of each running session, one file per
# process id. Overridable so the suite can point at a fixture directory.
SESSIONS_DIR="${SPAWN_SESSIONS_DIR:-$HOME/.claude/sessions}"

# Where the CLI keeps per-conversation transcripts, one directory per working
# directory and one file per conversation. A session's reply is read from its
# own transcript rather than from the pane: a pane is a rendering, repainted
# and wrapped, while the transcript is the record.
PROJECTS_DIR="${SPAWN_PROJECTS_DIR:-$HOME/.claude/projects}"

# How long to wait before reporting that a session has not answered yet. Not a
# failure — a first turn loads configuration and starts external servers, so a
# healthy session can be slow. Inspecting early and failing late is the point.
INSPECT_AFTER="${SPAWN_INSPECT_AFTER:-30}"

# The CLI's own configuration file, where workspace trust is recorded.
CONFIG_FILE="${SPAWN_CONFIG_FILE:-$HOME/.claude.json}"
TRUST_TOOL="$SCRIPT_DIR/lib/trust-config.py"
BLOCKER_TABLE="$SCRIPT_DIR/startup-blockers.tsv"

# The CLI release this skill's dialog patterns were verified against. Advisory
# only — see version_verdict.
PINNED_CLI_VERSION="2.1.259"
CLI_BIN="${SPAWN_CLI_BIN:-claude}"

# Exit codes. Each names a distinct outcome a caller may need to act on
# differently; see docs in the skill's references.
readonly EXIT_OK=0
readonly EXIT_USAGE=2
readonly EXIT_BRIDGE_DEAD=3
readonly EXIT_NO_PROCESS=4
readonly EXIT_UNCONFIRMED=5

NAME=""
DIR=""
POSTURE=""
PRE_LAUNCH=""
PROMPT=""
PROMPT_FILE=""
BRIEF=""
BRIEF_DELIVERED=0
TRUST_FOLDER=0
TRUST_GRANTED=""
BLOCKER=""
RESUME=0
SOCKET=""
DRY_RUN=0
PORCELAIN=0
VERIFY=1
TIMEOUT=120

usage() {
  cat <<'USAGE'
usage: spawn-session.sh <name> [options]

  -C, --dir <dir>        directory to launch in (default: current directory)
  -p, --prompt <text>    starter brief, delivered once the session is confirmed
  -f, --prompt-file <p>  starter brief read from a file ('-' for standard input)
  -b, --bypass           launch with permissions bypassed (default: acceptEdits)
      --pre-launch <cmd> shell command run in the pane before the CLI starts
      --socket <name>    address a named multiplexer server instead of the default
      --resume           pick up a session that already exists instead of creating one
      --trust-folder     pre-authorize this workspace if it is not trusted yet
      --timeout <secs>   how long to wait for the session to come up (default 120)
      --no-verify        report as soon as the session is launched
  -n, --dry-run          report the plan and launch nothing
      --porcelain        emit tab-separated key/value pairs instead of prose
  -h, --help             this text

exit: 0 reachable · 2 usage or refusal · 3 alive but unreachable · 4 never started
USAGE
}

die() {
  echo "spawn-session: $1" >&2
  exit "${2:-$EXIT_USAGE}"
}

# tm <args...>
#
# Every multiplexer call goes through here so the server is addressed
# consistently. A named socket is passed explicitly on each invocation rather
# than through the environment: an inherited variable can be overridden by
# being inside a session, and a call that looks redirected but is not lands on
# the caller's real server.
tm() {
  if [[ -n "$SOCKET" ]]; then
    tmux -L "$SOCKET" "$@"
  else
    tmux "$@"
  fi
}

parse_args() {
  while (( $# > 0 )); do
    case "$1" in
      -C|--dir)        [[ -n "${2:-}" ]] || die "$1 needs a directory"; DIR="$2"; shift ;;
      -b|--bypass)     POSTURE="bypass" ;;
      --pre-launch)    [[ -n "${2:-}" ]] || die "$1 needs a command"; PRE_LAUNCH="$2"; shift ;;
      -p|--prompt)     [[ -n "${2:-}" ]] || die "$1 needs text"; PROMPT="$2"; shift ;;
      -f|--prompt-file) [[ -n "${2:-}" ]] || die "$1 needs a path"; PROMPT_FILE="$2"; shift ;;
      --socket)        [[ -n "${2:-}" ]] || die "$1 needs a socket name"; SOCKET="$2"; shift ;;
      --timeout)       [[ -n "${2:-}" ]] || die "$1 needs a number"; TIMEOUT="$2"; shift ;;
      --resume)        RESUME=1 ;;
      --trust-folder)  TRUST_FOLDER=1 ;;
      --no-verify)     VERIFY=0 ;;
      -n|--dry-run)    DRY_RUN=1 ;;
      --porcelain)     PORCELAIN=1 ;;
      -h|--help)       usage; exit "$EXIT_OK" ;;
      -*)              die "unknown option: $1" ;;
      *)
        [[ -z "$NAME" ]] || die "more than one name given: '$NAME' and '$1'"
        NAME="$1" ;;
    esac
    shift
  done
}

# claude_pid_in <session>
#
# Echoes the process id of the CLI running inside the named session, or
# nothing. Identified by the remote-control flag in its own argument list,
# read through ps rather than /proc so this works on any Unix.
claude_pid_in() {
  local session="$1" pane_pid child
  pane_pid=$(tm list-panes -t "=$session" -F '#{pane_pid}' 2>/dev/null | head -1) || return 0
  [[ -n "$pane_pid" ]] || return 0

  for child in $(pgrep -P "$pane_pid" 2>/dev/null || true); do
    if ps -o args= -p "$child" 2>/dev/null | grep -q -- '--remote-control'; then
      echo "$child"
      return 0
    fi
  done
}

# bridge_id_for <pid>
#
# Echoes the remote-control bridge identifier from the session's own state
# file, or nothing. The file is keyed by process id and is removed when the
# process exits, so absence is normal for a session that has only just
# started — and permanent for one that never did.
bridge_id_for() {
  local pid="$1"
  local file="$SESSIONS_DIR/$pid.json"
  [[ -r "$file" ]] || return 0
  sed -n 's/.*"bridgeSessionId"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$file" | head -1
}

# session_id_for <pid>
#
# Echoes the conversation identifier the session is working in. That id is
# also the name of its transcript file, which is what makes the reply
# locatable without guessing at how a directory name is encoded.
session_id_for() {
  local pid="$1"
  local file="$SESSIONS_DIR/$pid.json"
  [[ -r "$file" ]] || return 0
  sed -n 's/.*"sessionId"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$file" | head -1
}

# transcript_for <session_id>
#
# Echoes the path of the transcript for a conversation. Located by searching
# for the file named after the conversation rather than by rebuilding the
# directory name from the working directory: that encoding collapses several
# characters, so reconstructing it guesses, while the conversation id is
# unique and needs no decoding.
transcript_for() {
  local sid="$1"
  [[ -n "$sid" ]] || return 0
  find "$PROJECTS_DIR" -type f -name "$sid.jsonl" 2>/dev/null | head -1
}

# spawn_nonce
#
# A token unique to this spawn, so a reply left in a transcript by an earlier
# spawn cannot be mistaken for an answer to this one.
spawn_nonce() {
  local n=""
  # Reads a fixed number of bytes rather than filtering a stream into `head`:
  # closing that pipe early kills the producer with SIGPIPE, which under
  # `set -o pipefail` fails the assignment and takes the run down with it.
  if [[ -r /dev/urandom ]]; then
    n="$(od -An -tx1 -N6 /dev/urandom 2>/dev/null | tr -d ' \n')"
  fi
  [[ -n "$n" ]] || n="$(printf '%04x%04x%04x' "$RANDOM" "$RANDOM" "$RANDOM")"
  printf '%s\n' "$n"
}

# deliver_text <text>
#
# Send text to the session as a paste, then submit it.
#
# Typed input would submit at the first newline, truncating anything
# multi-line to its first line and delivering the remainder as separate
# messages. A paste is handled as one block, so newlines inside it are text
# rather than submissions, and exactly one submission follows.
deliver_text() {
  local text="$1"
  local buf="spawn-session-$$"
  local tmp
  tmp="$(mktemp)"
  printf '%s' "$text" > "$tmp"

  tm load-buffer -b "$buf" "$tmp"
  tm paste-buffer -p -d -b "$buf" -t "=$NAME:"
  rm -f "$tmp"

  # Let the paste be taken up before submitting; submitting into a composer
  # that has not finished receiving loses the tail.
  sleep 0.5
  tm send-keys -t "=$NAME:" Enter
}

# ack_line_in <transcript> <nonce>
#
# Echoes the acknowledgement carrying this nonce, or nothing.
ack_line_in() {
  local file="$1" nonce="$2"
  [[ -r "$file" ]] || return 0
  # `|| true` is load-bearing under `set -o pipefail`: grep exits 1 when it
  # finds nothing, which is the normal case on every poll before the session
  # answers. Without it the failing pipeline propagates out of the command
  # substitution and the whole run dies silently, mid-wait, with no output —
  # and it would do so only when the reply had not arrived yet, so a session
  # that answered quickly would pass and a slow one would "crash".
  grep -oE "SPAWN-ACK +$nonce +cwd=[^\" ]+ +posture=[A-Za-z]+" "$file" 2>/dev/null | head -1 || true
}

# git_root_of <dir>
#
# Echoes the repository root containing the directory, or nothing.
git_root_of() {
  git -C "$1" rev-parse --show-toplevel 2>/dev/null || true
}

# have_trust_tool
#
# Whether trust can be inspected at all. The check needs an interpreter that
# the rest of this script does not, so it is optional rather than required:
# a machine without it can still spawn sessions in directories that are
# already trusted, and only loses the ability to inspect or grant.
have_trust_tool() {
  command -v python3 >/dev/null 2>&1 && [[ -r "$TRUST_TOOL" ]]
}

# config_trusts <config_file> <key>
#
# Returns 0 if the workspace is recorded as trusted.
config_trusts() {
  have_trust_tool || return 1
  python3 "$TRUST_TOOL" check "$1" "$2"
}

# grant_trust <config_file> <key>
#
# Records the workspace as trusted, under the same lock the CLI takes.
#
# The lock is not optional. The configuration file holds state for every
# project on the machine and every running session writes it by reading,
# modifying and replacing the whole file. Writing without the lock is
# last-writer-wins against those sessions: anything they changed between our
# read and our write is silently discarded, and nothing reports it.
grant_trust() {
  local cfg="$1" key="$2"
  have_trust_tool || {
    echo "spawn-session: python3 is required to grant workspace trust" >&2
    return 1
  }

  local lock="$cfg.lock"
  local tries="${SPAWN_LOCK_RETRIES:-6}" attempt=0
  until mkdir "$lock" 2>/dev/null; do
    attempt=$(( attempt + 1 ))
    if (( attempt >= tries )); then
      echo "spawn-session: the configuration lock ($lock) is held by another session; nothing was written. Try again in a moment." >&2
      return 1
    fi
    sleep 0.3
  done

  local rc=0
  python3 "$TRUST_TOOL" grant "$cfg" "$key" || rc=$?
  rmdir "$lock" 2>/dev/null || true
  return "$rc"
}

# installed_cli_version
#
# Echoes the version of the CLI on PATH, or nothing if it cannot be asked.
installed_cli_version() {
  if [[ -n "${SPAWN_CLI_VERSION:-}" ]]; then
    printf '%s\n' "$SPAWN_CLI_VERSION"
    return 0
  fi
  command -v "$CLI_BIN" >/dev/null 2>&1 || return 0
  "$CLI_BIN" --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1 || true
}

# find_blocker <session>
#
# Echoes "id<TAB>what<TAB>remedy" if the pane shows a known startup dialog.
find_blocker() {
  local pane table
  pane="$(tm capture-pane -p -J -t "=$1:" 2>/dev/null || true)"
  [[ -n "$pane" ]] || return 1
  [[ -r "$BLOCKER_TABLE" ]] || return 1
  table="$(cat "$BLOCKER_TABLE")"
  blocker_for "$table" "$pane"
}

# report_blocker <blocker-row>
#
# Explains what is holding the session, and what settles it. Never acts on it:
# every remedy here is a decision recorded in configuration, deliberately, by
# a person — not a keypress sent at a dialog by this tool.
report_blocker() {
  local id what remedy
  IFS=$'\t' read -r id what remedy <<< "$1"
  echo "  blocked  $id"
  echo "           $what"
  echo "           $remedy"

  local installed verdict
  installed="$(installed_cli_version)"
  verdict="$(version_verdict "$installed" "$PINNED_CLI_VERSION")"
  if [[ "$verdict" == "drift" ]]; then
    echo "           (CLI $installed differs from $PINNED_CLI_VERSION, which these"
    echo "            dialog patterns were verified against — wording may have moved)"
  fi
}

report() {
  local verdict="$1" pid="$2" bridge="$3" identity="${4:-}" url=""
  url="$(bridge_url "$bridge" 2>/dev/null || true)"

  if (( PORCELAIN )); then
    printf 'name\t%s\n' "$NAME"
    printf 'directory\t%s\n' "$DIR"
    printf 'posture\t%s\n' "${POSTURE:-acceptEdits}"
    printf 'verdict\t%s\n' "$verdict"
    printf 'pid\t%s\n' "$pid"
    [[ -n "$identity" ]] && printf 'identity\t%s\n' "$identity"
    printf 'brief\t%s\n' "$( (( BRIEF_DELIVERED )) && echo delivered || echo none )"
    [[ -n "$url" ]] && printf 'url\t%s\n' "$url"
    return 0
  fi

  echo "session '$NAME' in $DIR (${POSTURE:-acceptEdits})"
  # Say exactly what was authorised: inside a repository the key is the
  # repository root, which is broader than the directory that was named.
  [[ -n "$TRUST_GRANTED" ]] && echo "  trusted  $TRUST_GRANTED (recorded now)"
  [[ -n "$pid" ]] && echo "  pid      $pid"
  case "$verdict" in
    healthy)
      echo "  bridge   live"
      # Valid for the bridge that is live now, not for the session in
      # general: the identifier is minted per bridge and a restart mints a
      # new one. A handoff line, never something to bookmark.
      echo "  url      $url  (this bridge only)" ;;
    bridge_dead)
      echo "  bridge   not established — the session is running but is not"
      echo "           reachable from the web client. It has been left alone." ;;
    launched)
      echo "  launched (not verified)" ;;
    unconfirmed)
      echo "  identity unconfirmed — the session did not answer in time."
      echo "           It is still running and has been left alone." ;;
    blocked)
      echo "  the session never got as far as reading its input."
      report_blocker "$BLOCKER" ;;
  esac

  # Reported from what actually happened, never from what was asked for: on
  # any path that stops before delivery, the brief was not sent, and a report
  # saying otherwise is worse than no report at all.
  (( BRIEF_DELIVERED )) && echo "  brief    delivered"

  case "$identity" in
    ok)                 echo "  identity confirmed" ;;
    posture_unverified) echo "  identity confirmed (the session could not report its posture)" ;;
  esac
}

main() {
  parse_args "$@"

  [[ -n "$NAME" ]] || { usage >&2; exit "$EXIT_USAGE"; }
  valid_session_name "$NAME" ||
    die "'$NAME' is not a usable session name: use letters, digits, underscore and dash only (a dot or colon is silently rewritten by the multiplexer, leaving a session under a name you did not choose)"

  local source
  source="$(brief_source "$PROMPT" "$PROMPT_FILE")" ||
    die "give either --prompt or --prompt-file, not both"
  case "$source" in
    inline) BRIEF="$PROMPT" ;;
    file)
      if [[ "$PROMPT_FILE" == "-" ]]; then
        BRIEF="$(cat)"
      else
        [[ -r "$PROMPT_FILE" ]] || die "cannot read brief file: $PROMPT_FILE"
        BRIEF="$(cat "$PROMPT_FILE")"
      fi
      [[ -n "$BRIEF" ]] || die "the brief is empty: $PROMPT_FILE"
      ;;
  esac

  DIR="${DIR:-$PWD}"
  [[ -d "$DIR" ]] || die "no such directory: $DIR"
  DIR="$(cd "$DIR" && pwd)"

  local launch_line
  launch_line="$(spawn_launch_command "$NAME" "$POSTURE" "$PRE_LAUNCH")"

  if (( DRY_RUN )); then
    echo "would spawn '$NAME' in $DIR"
    echo "  $launch_line"
    # Report the trust decision without acting on it. A dry run that wrote to
    # the CLI's configuration would not be a dry run.
    if have_trust_tool; then
      local dry_key
      dry_key="$(trust_key "$DIR" "$(git_root_of "$DIR")")"
      if config_trusts "$CONFIG_FILE" "$dry_key"; then
        echo "  workspace already trusted ($dry_key)"
      elif (( TRUST_FOLDER )) && trust_grantable "$dry_key" "$HOME"; then
        echo "  would record workspace trust for $dry_key"
      elif (( TRUST_FOLDER )); then
        echo "  workspace trust CANNOT be recorded for the home directory — the CLI"
        echo "  keeps that decision per-session and never writes it down"
      else
        echo "  workspace NOT trusted ($dry_key) — would refuse without --trust-folder"
      fi
    fi
    exit "$EXIT_OK"
  fi

  # Refuse rather than reuse. Sending anything into a session someone else is
  # working in delivers it into their conversation, and nothing undoes that.
  # Checked before the trust grant below so a refused spawn leaves no trace in
  # a configuration file this tool does not own.
  #
  # --resume is the deliberate exception: a spawn that stopped part-way — held
  # at a dialog, or confirmed but not yet briefed — is picked up rather than
  # started again. Nothing about that progress is stored anywhere; it is all
  # re-derived below from the session, its process and its transcript, because
  # a record of progress that disagrees with reality is worse than no record.
  if tm has-session -t "=$NAME" 2>/dev/null; then
    if (( ! RESUME )); then
      die "a session named '$NAME' is already running — stop it first, choose another name, or pass --resume to pick it up"
    fi
  elif (( RESUME )); then
    die "no session named '$NAME' to resume"
  fi

  # Workspace trust, settled before anything is launched. A session started in
  # an untrusted directory stops at a dialog nothing here will answer by
  # simulating input, so the choice is made explicitly, in advance, by a flag.
  if have_trust_tool; then
    local key
    key="$(trust_key "$DIR" "$(git_root_of "$DIR")")"
    if ! config_trusts "$CONFIG_FILE" "$key"; then
      if (( TRUST_FOLDER )); then
        trust_grantable "$key" "$HOME" ||
          die "workspace trust cannot be recorded for the home directory: the CLI accepts it for one session only and never writes it down. Launch in a subdirectory, or start the CLI here once by hand."
        grant_trust "$CONFIG_FILE" "$key" || die "could not record workspace trust"
        TRUST_GRANTED="$key"
      else
        die "$DIR is not a trusted workspace yet, so the session would stop at the trust prompt. Re-run with --trust-folder to record trust for '$key', or start the CLI there once by hand and accept the prompt."
      fi
    fi
  elif (( TRUST_FOLDER )); then
    die "--trust-folder needs python3, which was not found"
  fi


  if (( ! RESUME )); then
    tm new-session -d -s "$NAME" -c "$DIR"
    tm send-keys -t "=$NAME:" "$launch_line" Enter
  fi

  if (( ! VERIFY )); then
    report "launched" "" ""
    exit "$EXIT_OK"
  fi

  local waited=0 pid=""
  while (( waited < TIMEOUT )); do
    pid="$(claude_pid_in "$NAME")"
    [[ -n "$pid" ]] && break
    sleep 1
    (( waited += 1 ))
  done

  if [[ -z "$pid" ]]; then
    report "$(spawn_verdict "" "")" "" ""
    die "no CLI process appeared in '$NAME' within ${TIMEOUT}s" "$EXIT_NO_PROCESS"
  fi

  # ── identity ──────────────────────────────────────────────────────────
  #
  # Ask the session who it is before sending it anything else. Until this
  # answers, the handshake is the only thing that has been delivered — so a
  # handshake that reached the wrong pane costs a stray line, where a brief
  # would have landed in someone else's conversation.
  local sid=""
  while (( waited < TIMEOUT )); do
    sid="$(session_id_for "$pid")"
    [[ -n "$sid" ]] && break
    sleep 1
    (( waited += 1 ))
  done

  local nonce
  nonce="$(spawn_nonce)"
  deliver_text "$(handshake_text "$nonce")"

  local transcript="" ack="" noted=0
  while (( waited < TIMEOUT )); do
    [[ -n "$transcript" ]] || transcript="$(transcript_for "$sid")"
    if [[ -n "$transcript" ]]; then
      ack="$(ack_line_in "$transcript" "$nonce")"
      [[ -n "$ack" ]] && break
    fi
    # Say something at the inspection mark rather than sitting silent to the
    # ceiling: a first turn can legitimately be slow, and a caller needs to
    # tell "still starting" from "stuck" without waiting for the timeout.
    if (( ! noted )) && (( waited >= INSPECT_AFTER )); then
      local early
      early="$(find_blocker "$NAME" || true)"
      if [[ -n "$early" ]]; then
        echo "spawn-session: '$NAME' is held at a startup dialog (${early%%$'\t'*}); still waiting" >&2
      else
        echo "spawn-session: '$NAME' has not answered after ${waited}s, nothing obviously blocking it; still waiting" >&2
      fi
      noted=1
    fi
    sleep 1
    (( waited += 1 ))
  done

  local bridge
  bridge="$(bridge_id_for "$pid")"

  if [[ -z "$ack" ]]; then
    # No answer. Before reporting a bare timeout, look at the pane: if a known
    # startup dialog is holding the session, that is a diagnosis rather than an
    # unknown, and it has a remedy the caller can act on.
    BLOCKER="$(find_blocker "$NAME" || true)"
    if [[ -n "$BLOCKER" ]]; then
      report "blocked" "$pid" "$bridge" ""
      exit "$EXIT_NO_PROCESS"
    fi

    # Genuinely unknown: unconfirmed, not failed. The session is running and
    # may be perfectly healthy; what is missing is evidence, and destroying it
    # to tidy up an unknown would throw away a real conversation.
    report "unconfirmed" "$pid" "$bridge" ""
    exit "$EXIT_UNCONFIRMED"
  fi

  local got_dir got_posture identity
  got_dir="$(parse_ack cwd "$ack" || true)"
  got_posture="$(parse_ack posture "$ack" || true)"
  identity="$(ack_verdict "$DIR" "$got_dir" "${POSTURE:-acceptEdits}" "$got_posture")"

  case "$identity" in
    mismatch_cwd)
      die "'$NAME' answered from a different directory ($got_dir, expected $DIR): this is not the session that was launched. Nothing further has been sent to it." ;;
    mismatch_posture)
      die "'$NAME' reports posture '$got_posture' but was launched as '${POSTURE:-acceptEdits}'. Nothing further has been sent to it." ;;
  esac

  # Identity is settled; only now does anything the caller wrote get sent.
  if [[ -n "$BRIEF" ]]; then
    deliver_text "$BRIEF"
    BRIEF_DELIVERED=1
  fi

  local verdict
  verdict="$(spawn_verdict "$pid" "$bridge")"
  report "$verdict" "$pid" "$bridge" "$identity"

  if [[ "$verdict" == "healthy" ]]; then
    exit "$EXIT_OK"
  fi
  exit "$EXIT_BRIDGE_DEAD"
}

# Only run when executed. Sourcing the file gives a test direct access to the
# effectful helpers — the config writer in particular, which must be proven to
# preserve a file it does not own.
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  main "$@"
fi
