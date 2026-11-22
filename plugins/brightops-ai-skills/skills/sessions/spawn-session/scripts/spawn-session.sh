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
READY_TABLE="$SCRIPT_DIR/ready-prompts.tsv"

# The CLI release this skill's dialog patterns were verified against. Advisory
# only — see version_verdict.
PINNED_CLI_VERSION="2.1.259"
# The CLI release the prompt patterns in the ready table were taken from. A
# separate fact from the pin above, and advisory in the same way.
READY_CLI_VERSION="2.1.330"
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
DIR_PHYSICAL=""
GIT_ROOT=""
EXACT=""
POSTURE=""
PRE_LAUNCH=""
PROMPT=""
PROMPT_FILE=""
BRIEF=""
BRIEF_DELIVERED=0
TRUST_FOLDER=0
TRUST_GRANTED=""
BLOCKER=""
BLOCKER_ROWS=""
READY_ROWS=""
# What the last look at the pane found: ready, blocked or waiting.
GATE="waiting"
# How far the handshake got on a verified run: not_sent, not_submitted (pasted,
# Enter withheld) or sent. Empty when no handshake is attempted at all.
HANDSHAKE=""
# How far the brief got when it stopped short of delivered: empty, or
# not_submitted.
BRIEF_HELD=""
NOTED=0
RESUME=0
SOCKET=""
DRY_RUN=0
PORCELAIN=0
VERIFY=1
TIMEOUT=120

usage() {
  cat <<'USAGE'
usage: spawn-session.sh <name> [options]

  -C, --dir <dir>        directory to launch in (default: current directory);
                         refused when its path holds a control character or
                         is not valid UTF-8
  -p, --prompt <text>    starter brief, delivered once the session is confirmed
  -f, --prompt-file <p>  starter brief read from a file ('-' for standard input)
  -b, --bypass           launch with permissions bypassed (default: acceptEdits);
                         prints a warning on stderr; refused with --trust-folder,
                         and when workspace trust cannot be checked (no python3)
      --pre-launch <cmd> shell command run in the pane before the CLI starts
      --socket <name>    address a named multiplexer server instead of the default
      --resume           pick up a session that already exists instead of creating one
      --trust-folder     pre-authorize this workspace if it is not trusted yet
                         (the whole repository, when the directory is inside one)
      --timeout <secs>   how long to wait for the session to come up (default 120)
      --no-verify        report as soon as the session is launched
  -n, --dry-run          report the plan and launch nothing
      --porcelain        emit tab-separated key/value pairs instead of prose
  -h, --help             this text; wins over every other argument, exit 0

exit: 0 reachable · 2 usage or refusal · 3 alive but unreachable · 4 never started
      5 running but unconfirmed
USAGE
}

# die <message> [exit-code]
#
# The message is rendered through `visible` as a whole. It usually quotes
# something the caller supplied — a name, a path, an option — and a refusal
# that can be split across lines or repainted by its own argument is a refusal
# that can be made to say something else.
die() {
  # printf, not echo: with xpg_echo set, echo would interpret the escapes that
  # `visible` has just written out and turn them back into control bytes.
  printf '%s\n' "spawn-session: $(visible "$1")" >&2
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

# look
#
# Looks at the pane once and sets GATE (ready, blocked or waiting) and, when
# blocked, BLOCKER. One capture decides both, so the dialog that is reported
# is the one that was seen.
#
# A capture that fails says nothing about the pane, whatever it printed
# before failing: readiness is unknown, which is not ready.
look() {
  local pane verdict
  GATE="waiting"
  BLOCKER=""
  pane="$(tm capture-pane -p -J -t "=$NAME:" 2>/dev/null)" || return 0
  verdict="$(pane_verdict "$BLOCKER_ROWS" "$READY_ROWS" "$pane")"
  GATE="${verdict%%$'\t'*}"
  if [[ "$GATE" == "blocked" ]]; then
    BLOCKER="${verdict#*$'\t'}"
  fi
  return 0
}

# look_settled
#
# Returns 0 once the pane shows the input box. A look that finds nothing
# recognisable is repeated a few times over a second, because a capture can
# land while the interface is redrawing; a known dialog ends it at once.
look_settled() {
  local tries=0
  while true; do
    look
    [[ "$GATE" == "ready" ]] && return 0
    [[ "$GATE" == "blocked" ]] && return 1
    tries=$(( tries + 1 ))
    (( tries >= 5 )) && return 1
    sleep 0.2
  done
}

# deliver_text <text>
#
# Send text to the session as a paste, then submit it. Returns 0 when both
# went, 1 when nothing was sent, 2 when the paste went and Enter did not.
#
# Typed input would submit at the first newline, truncating anything
# multi-line to its first line and delivering the remainder as separate
# messages. A paste is handled as one block, so newlines inside it are text
# rather than submissions, and exactly one submission follows.
#
# The paste and the Enter are two separate things sent to the pane, and each
# is preceded by its own look: the input box has to be there for both. What
# is on the pane can still change between a look and the send that follows
# it. That window is one multiplexer call wide and cannot be closed from
# here, so a send is held back when the box is seen to be gone, not
# guaranteed never to reach anything else.
deliver_text() {
  local text="$1"
  local buf="spawn-session-$$"
  local tmp
  tmp="$(mktemp)"
  printf '%s' "$text" > "$tmp"

  # Loading fills the multiplexer's own buffer and sends the pane nothing, so
  # it is done first and the look is the last thing before the paste.
  tm load-buffer -b "$buf" "$tmp"
  rm -f "$tmp"

  if ! look_settled; then
    tm delete-buffer -b "$buf" 2>/dev/null || true
    return 1
  fi
  tm paste-buffer -p -d -b "$buf" -t "=$NAME:"

  # Let the paste be taken up before submitting; submitting into a composer
  # that has not finished receiving loses the tail.
  sleep 0.5
  look_settled || return 2
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

# logical_dir <dir>
#
# Echoes the directory as an absolute path, symbolic links kept as named.
logical_dir() {
  # CDPATH is cleared so a relative name is looked up here and nowhere else;
  # with it set, cd may go somewhere else and print where it went.
  (CDPATH="" && cd -- "$1" 2>/dev/null && pwd)
}

# physical_dir <dir>
#
# Echoes the directory with symbolic links resolved, which is the form the
# repository root is reported in.
physical_dir() {
  (CDPATH="" && cd -- "$1" 2>/dev/null && pwd -P)
}

# kernel_dir <dir>
#
# Echoes where the name leads when every symbolic link is followed before
# every `..`, which is how the kernel reads it and how `[[ -d ]]` just did.
# logical_dir reads `link/..` as the directory holding the link; the kernel
# reads it as the parent of whatever the link points to. The launcher uses
# the first, as it always has, and checks the second too, so a name cannot be
# accepted for a place the argument does not lead to by either reading.
kernel_dir() {
  (CDPATH="" && cd -P -- "$1" 2>/dev/null && pwd -P)
}

# exact <command...>
#
# Runs the command and sets EXACT to the line it printed, less the one newline
# that ends it. Fails, with EXACT empty, if the command fails.
#
# Every path here is read through this rather than a bare command
# substitution. A substitution drops all trailing newlines, so a directory
# whose name ends in one comes back as a different, shorter path: its sibling.
# The sentinel keeps them, and the check that refuses such a directory can
# then see what it is refusing.
exact() {
  EXACT="$("$@" && printf x)" || { EXACT=""; return 1; }
  EXACT="${EXACT%x}"
  EXACT="${EXACT%$'\n'}"
}

# refuse_control_in <subject> <path>
#
# Refuses, as usage, a path holding a control character or a byte that is
# not UTF-8. Called before the path is used for anything: a trust lookup, a
# trust record, the multiplexer.
refuse_control_in() {
  has_control "$2" || return 0
  die "$1 has a control character, or a byte that is not valid UTF-8, in its path, written out here as text: '$2'. Refused: a path with one in it is not carried intact. A newline at the end is dropped when the path is resolved, which names a different directory for the session to start in and for trust to be recorded against. Rename the directory, or launch somewhere else."
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
      echo "spawn-session: the configuration lock ($(visible "$lock")) is held by another session; nothing was written. Try again in a moment." >&2
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

# load_tables
#
# Reads the dialog table and the prompt table once, so a look costs one
# multiplexer call and nothing else. A table that cannot be read contributes
# no rows: no ready table means "never ready", not "always ready".
load_tables() {
  if [[ -r "$BLOCKER_TABLE" ]]; then
    BLOCKER_ROWS="$(cat "$BLOCKER_TABLE")"
  fi
  if [[ -r "$READY_TABLE" ]]; then
    READY_ROWS="$(cat "$READY_TABLE")"
  fi
}

# drift_note <patterns> <cli-version> <how-they-relate>
#
# Echoes the advisory for a CLI other than the one a table's patterns come
# from, or nothing.
drift_note() {
  local installed verdict
  installed="$(installed_cli_version)"
  verdict="$(version_verdict "$installed" "$2")"
  if [[ "$verdict" == "drift" ]]; then
    echo "           (CLI $installed differs from $2, which these"
    echo "            $1 were $3 — wording may have moved)"
  fi
}

# still_waiting_note <waited>
#
# Says something once, at the inspection mark, rather than sitting silent to
# the ceiling: a first turn can legitimately be slow, and a caller needs to
# tell "still starting" from "stuck" without waiting for the timeout. Speaks
# from the last look.
still_waiting_note() {
  local waited="$1"
  (( NOTED )) && return 0
  (( waited >= INSPECT_AFTER )) || return 0
  NOTED=1

  if [[ -n "$BLOCKER" ]]; then
    echo "spawn-session: '$NAME' is held at a startup dialog (${BLOCKER%%$'\t'*}); still waiting" >&2
  elif [[ "$HANDSHAKE" == "sent" ]]; then
    echo "spawn-session: '$NAME' has not answered after ${waited}s, nothing obviously blocking it; still waiting" >&2
  else
    echo "spawn-session: '$NAME' has not shown its input prompt after ${waited}s, and no known dialog; nothing has been sent to it; still waiting" >&2
  fi
}

# held_back <identity>
#
# Echoes what a run that stopped short did and did not send. Said from what
# happened: a paste that went out is reported as a paste, including when the
# Enter after it was held back.
held_back() {
  local identity="$1"
  case "$HANDSHAKE" in
    not_sent)
      echo "  nothing was sent to it." ;;
    not_submitted)
      echo "  the handshake was pasted, and Enter was not sent: the input prompt"
      echo "  was gone by then. The paste may have reached what replaced it."
      echo "  Clear the session's input box before using --resume." ;;
    sent)
      [[ -n "$BRIEF" && -n "$identity" ]] || return 0
      if [[ "$BRIEF_HELD" == "not_submitted" ]]; then
        echo "  identity was confirmed. The brief was pasted, and Enter was not"
        echo "  sent: the input prompt was gone by then. The paste may have"
        echo "  reached what replaced it. Clear the input box before --resume."
      else
        echo "  identity was confirmed. The brief was not sent: the input prompt"
        echo "  was gone by then."
      fi ;;
  esac
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
  drift_note "dialog patterns" "$PINNED_CLI_VERSION" "verified against"
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
    if (( BRIEF_DELIVERED )); then
      printf 'brief\tdelivered\n'
    else
      printf 'brief\t%s\n' "${BRIEF_HELD:-none}"
    fi
    # On every run that verifies: how far the handshake got. With not_sent,
    # nothing at all was sent to the session.
    [[ -n "$HANDSHAKE" ]] && printf 'handshake\t%s\n' "$HANDSHAKE"
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
    not_ready)
      if [[ "$HANDSHAKE" == "not_sent" ]]; then
        echo "  identity unconfirmed — the input prompt never appeared, so the"
        echo "           handshake was not sent."
      else
        echo "  the input prompt is not showing, and no known dialog is."
      fi
      held_back "$identity"
      echo "  It is still running and has been left alone. Look at it"
      echo "  (tmux attach -t \"=$NAME\"), then re-run with --resume."
      echo "  If it is at its prompt, this CLI draws its input box or status line"
      echo "  in a way scripts/ready-prompts.tsv does not describe yet."
      drift_note "prompt patterns" "$READY_CLI_VERSION" "taken from" ;;
    blocked)
      if [[ -n "$identity" ]]; then
        echo "  a startup dialog came up after the session identified itself."
      else
        echo "  the session never got as far as reading its input."
      fi
      held_back "$identity"
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

# stop_short <pid> <identity>
#
# Ends a run whose next send was held back, from the last look: a known
# dialog is a diagnosis with a remedy, anything else is an unknown and is
# reported as one. Either way the session is left as it is.
stop_short() {
  local pid="$1" identity="$2" bridge
  bridge="$(bridge_id_for "$pid")"

  if [[ -n "$BLOCKER" ]]; then
    report "blocked" "$pid" "$bridge" "$identity"
    exit "$EXIT_NO_PROCESS"
  fi

  # The prompt rows are where to look first, and the one for a bypass launch
  # is the only row never seen in a real pane. Said on stderr so a caller
  # reading pairs gets it too.
  if [[ "$POSTURE" == "bypass" && "$(ready_row_basis "$READY_ROWS" bypass || true)" == "inferred" ]]; then
    echo "spawn-session: the 'bypass' row of scripts/ready-prompts.tsv is inferred, not seen in a real pane; if '$NAME' is at its prompt, correct that row first" >&2
  fi
  report "not_ready" "$pid" "$bridge" "$identity"
  exit "$EXIT_UNCONFIRMED"
}

main() {
  parse_args "$@"

  [[ -n "$NAME" ]] || { usage >&2; exit "$EXIT_USAGE"; }
  valid_session_name "$NAME" ||
    die "'$NAME' is not a usable session name: use letters, digits, underscore and dash only (a dot or colon is silently rewritten by the multiplexer, leaving a session under a name you did not choose)"

  # Trusting a workspace and removing supervision are two decisions, and one
  # command that takes both lets a single line authorise a directory and turn
  # an unattended session loose in it. Refused as usage, whatever the workspace
  # state, so the same invocation never works on one machine and not another.
  if [[ "$POSTURE" == "bypass" ]] && (( TRUST_FOLDER )); then
    die "--bypass and --trust-folder cannot be combined: trusting a workspace and launching with no supervision are two separate decisions. $(trust_first_steps)"
  fi

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

  # The directory, settled before it is used for anything. Checked as given
  # and again as resolved: the argument can be clean while the directory it
  # names is not, reached by a relative path or through a symbolic link.
  DIR="${DIR:-$PWD}"
  refuse_control_in "the directory" "$DIR"
  [[ -d "$DIR" ]] || die "no such directory: $DIR"
  exact kernel_dir "$DIR" || die "cannot enter directory: $DIR"
  refuse_control_in "the location the directory resolves to" "$EXACT"
  exact logical_dir "$DIR" || die "cannot enter directory: $DIR"
  DIR="$EXACT"
  refuse_control_in "the directory" "$DIR"
  exact physical_dir "$DIR" || die "cannot resolve directory: $DIR"
  DIR_PHYSICAL="$EXACT"
  refuse_control_in "the location the directory resolves to" "$DIR_PHYSICAL"
  # The repository root is what trust is recorded under, so it is read the
  # same way and held to the same rule. Only needed where trust can be
  # looked at.
  if have_trust_tool; then
    exact git_root_of "$DIR" || true
    GIT_ROOT="$EXACT"
    refuse_control_in "the repository that holds the directory" "$GIT_ROOT"
  fi

  local launch_line
  launch_line="$(spawn_launch_command "$NAME" "$POSTURE" "$PRE_LAUNCH")"

  if (( DRY_RUN )); then
    # Everything a dry run adds beyond the plan goes to stderr. The plan on
    # stdout is something callers already parse, and it stays byte for byte
    # what it was, including where its wording is looser than the facts.
    echo "would spawn '$NAME' in $DIR"
    echo "  $launch_line"

    # Whether the real run would get as far as a bypass launch. The warning
    # announces a launch, so it is held back until every refusal the real run
    # would make has been ruled out here too.
    local dry_bypass=0
    if [[ "$POSTURE" == "bypass" ]] && (( ! RESUME )); then
      dry_bypass=1
    fi

    # Report the trust decision without acting on it. A dry run that wrote to
    # the CLI's configuration would not be a dry run.
    if have_trust_tool; then
      local dry_root dry_key
      dry_root="$GIT_ROOT"
      dry_key="$(trust_key "$DIR" "$dry_root")"
      if config_trusts "$CONFIG_FILE" "$dry_key"; then
        echo "  workspace already trusted ($dry_key)"
      elif (( TRUST_FOLDER )) && trust_grantable "$dry_key" "$HOME"; then
        if trust_is_wider "$DIR_PHYSICAL" "$dry_root"; then
          trust_scope_warning "$DIR" "$dry_root" dry-run >&2
        fi
        echo "  would record workspace trust for $dry_key"
      elif (( TRUST_FOLDER )); then
        echo "  workspace trust CANNOT be recorded for the home directory — the CLI"
        echo "  keeps that decision per-session and never writes it down"
      else
        echo "  workspace NOT trusted ($dry_key) — would refuse without --trust-folder"
        # That line predates the refusal of --trust-folder alongside --bypass
        # and reads as advice to add it. Under --bypass the advice that works
        # is the two steps, said on stderr so the line above keeps its bytes.
        if [[ "$POSTURE" == "bypass" ]]; then
          dry_bypass=0
          echo "spawn-session: the real run would refuse: --trust-folder cannot be combined with --bypass. $(trust_first_steps)" >&2
        fi
      fi
    elif [[ "$POSTURE" == "bypass" ]] && (( ! RESUME )); then
      dry_bypass=0
      echo "spawn-session: the real run would refuse: workspace trust cannot be checked without python3, and a --bypass launch needs the workspace known to be trusted" >&2
    fi

    if (( RESUME )); then
      # The plan above says "would spawn" whatever was asked. With --resume
      # the real run creates nothing, so there is no launch to warn about;
      # the correction is made here rather than by rewording stdout.
      echo "spawn-session: with --resume nothing is launched; the real run picks up the existing session '$NAME', or refuses if there is none" >&2
    fi
    if (( dry_bypass )); then
      bypass_warning "$NAME" "$DIR" dry-run >&2
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
    local git_root key
    git_root="$GIT_ROOT"
    key="$(trust_key "$DIR" "$git_root")"
    if ! config_trusts "$CONFIG_FILE" "$key"; then
      if (( TRUST_FOLDER )); then
        trust_grantable "$key" "$HOME" ||
          die "workspace trust cannot be recorded for the home directory: the CLI accepts it for one session only and never writes it down. Launch in a subdirectory, or start the CLI here once by hand."
        # Said before the write, not after: the grant covers more than the
        # directory that was named, and that is the last moment a caller
        # reading this can still stop it.
        if trust_is_wider "$DIR_PHYSICAL" "$git_root"; then
          trust_scope_warning "$DIR" "$git_root" >&2
        fi
        grant_trust "$CONFIG_FILE" "$key" || die "could not record workspace trust"
        TRUST_GRANTED="$key"
      elif [[ "$POSTURE" == "bypass" ]]; then
        # The usual advice here is --trust-folder, which is refused alongside
        # --bypass; sending the caller to a combination that fails would cost
        # them a second refusal to learn what this one could have said.
        die "$DIR is not a trusted workspace yet, so the session would stop at the trust prompt. --trust-folder would record trust for '$key', but it cannot be combined with --bypass. $(trust_first_steps)"
      else
        die "$DIR is not a trusted workspace yet, so the session would stop at the trust prompt. Re-run with --trust-folder to record trust for '$key', or start the CLI there once by hand and accept the prompt."
      fi
    fi
  elif (( TRUST_FOLDER )); then
    die "--trust-folder needs python3, which was not found"
  elif [[ "$POSTURE" == "bypass" ]] && (( ! RESUME )); then
    # Fail closed. Without the check an untrusted workspace is not refused,
    # only unexamined, and an unattended session is the launch that must not
    # ride on "nobody looked". Other postures keep the older behaviour: they
    # stop at the trust prompt and are diagnosed there. With --resume nothing
    # is launched, so there is nothing to refuse: the existing session is
    # picked up as it always was.
    die "workspace trust for $DIR cannot be checked: the check needs python3, which was not found. A --bypass launch is refused unless the workspace is known to be trusted. Install python3, or launch without --bypass."
  fi


  if (( ! RESUME )); then
    # Printed on every bypass launch, immediately before it and after every
    # refusal above, so the line never appears for a launch that did not
    # happen. On stderr, which leaves --porcelain output on stdout untouched.
    if [[ "$POSTURE" == "bypass" ]]; then
      bypass_warning "$NAME" "$DIR" >&2
    fi
    # The warning above says what this is about to do. If the multiplexer
    # then refuses, say that too: left alone, the last word on stderr would be
    # a launch that never happened. The exit status stays the multiplexer's.
    local launch_rc=0
    tm new-session -d -s "$NAME" -c "$DIR" || launch_rc=$?
    if (( launch_rc )); then
      die "the multiplexer could not create session '$NAME'; nothing was launched" "$launch_rc"
    fi
    # The session now exists. If the command that starts the CLI cannot be
    # sent, say so: otherwise the launch warning above is the last word.
    local send_rc=0
    tm send-keys -t "=$NAME:" "$launch_line" Enter || send_rc=$?
    if (( send_rc )); then
      die "session '$NAME' was created, but the command that starts the CLI could not be sent to it; the session is empty" "$send_rc"
    fi
  fi

  if (( ! VERIFY )); then
    report "launched" "" ""
    exit "$EXIT_OK"
  fi

  # From here on the run reports how far the handshake got, on every path.
  HANDSHAKE="not_sent"
  load_tables

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

  # ── readiness, then identity ──────────────────────────────────────────
  #
  # Look before sending. A process existing says nothing about what it is
  # showing: a session held at a startup dialog has a live process too, and
  # anything pasted and submitted then is typed at the dialog. So nothing is
  # sent until the pane shows the input box, and if that never happens the
  # run ends having sent nothing.
  #
  # Then ask the session who it is before sending it anything else. Until
  # that answers, the handshake is the only thing that has been delivered —
  # so a handshake that reached the wrong pane costs a stray line, where a
  # brief would have landed in someone else's conversation.
  local sid="" nonce sent_rc=1
  nonce="$(spawn_nonce)"
  while (( waited < TIMEOUT )); do
    [[ -n "$sid" ]] || sid="$(session_id_for "$pid")"
    look
    if [[ "$GATE" == "ready" ]]; then
      sent_rc=0
      deliver_text "$(handshake_text "$nonce")" || sent_rc=$?
      # Sent, or pasted and not submitted: either way this is over. Only a
      # paste that was held back leaves the pane as it was, to be tried again.
      (( sent_rc == 1 )) || break
    fi
    still_waiting_note "$waited"
    sleep 1
    (( waited += 1 ))
  done

  if (( sent_rc != 0 )); then
    (( sent_rc == 2 )) && HANDSHAKE="not_submitted"
    stop_short "$pid" ""
  fi
  HANDSHAKE="sent"

  local transcript="" ack=""
  while (( waited < TIMEOUT )); do
    [[ -n "$sid" ]] || sid="$(session_id_for "$pid")"
    [[ -n "$transcript" ]] || transcript="$(transcript_for "$sid")"
    if [[ -n "$transcript" ]]; then
      ack="$(ack_line_in "$transcript" "$nonce")"
      [[ -n "$ack" ]] && break
    fi
    if (( ! NOTED )) && (( waited >= INSPECT_AFTER )); then
      look
    fi
    still_waiting_note "$waited"
    sleep 1
    (( waited += 1 ))
  done

  local bridge
  bridge="$(bridge_id_for "$pid")"

  if [[ -z "$ack" ]]; then
    # No answer. Before reporting a bare timeout, look at the pane: if a known
    # startup dialog is holding the session, that is a diagnosis rather than an
    # unknown, and it has a remedy the caller can act on.
    look
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
  # The brief is two more sends, and each is looked at like the handshake's.
  if [[ -n "$BRIEF" ]]; then
    local brief_rc=0
    deliver_text "$BRIEF" || brief_rc=$?
    if (( brief_rc != 0 )); then
      (( brief_rc == 2 )) && BRIEF_HELD="not_submitted"
      stop_short "$pid" "$identity"
    fi
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
