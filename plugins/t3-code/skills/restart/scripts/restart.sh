#!/bin/sh
# Quit T3 Code, optionally run a command while it is closed, reopen it, then message a thread.
# Detaches itself, so it survives the T3 session that launched it. macOS only.
#
# Usage: restart.sh --notify <threadId> --log <path> [--delay <seconds>] [--dry-run] [-- <command> [args...]]
#   --notify   thread that gets the "T3 Code is back" message after the restart
#   --log      new file that receives the transcript of the run (mode 0600); an existing
#              path or a symlink is refused
#   --delay    seconds to wait before quitting, so the launching turn can finish (default 20)
#   --dry-run  log each step without quitting, running, opening or messaging
#   --         everything after it is the command, run directly (no shell) once T3 Code has
#              exited and before it reopens. Its stdout and stderr go to the log; the log
#              names only the basename of the command, never its arguments.
# A value that begins with -- is refused for --notify, --log and --delay.
#
# The script prints "detached" only after the detached run has written its "start:" line and
# the launcher has acknowledged it by creating <log>.go. The detached run waits up to 30 seconds
# for that file and removes it once seen; with no acknowledgement it writes
# "result: aborted-no-ack" and exits without touching the app. The launcher never creates the
# file if it gave up waiting for "start:".
# The log is created exclusively and opened once, on a descriptor handed to the detached run; the
# path is never reopened for writing. The log's "result:" line is written (and the write checked)
# before the follow-up message is sent; a "notify:" line (accepted or failed) follows it and
# never changes the result. "accepted" means the t3 CLI accepted the message.
#
# Environment:
#   T3_APP_ID                bundle id (default com.t3tools.t3code); letters, digits, . and -
#   T3_RESTART_OSASCRIPT     osascript to use (default /usr/bin/osascript)   } for tests
#   T3_RESTART_OPEN          open to use (default /usr/bin/open)             } only; the
#   T3_RESTART_T3            t3 CLI to use (default: found on PATH, then    } defaults are
#                            ~/.local/bin/t3, ~/.t3/bin/t3)                  } what runs live
#   T3_RESTART_POLL_SECONDS  seconds between state checks (default 1; may be fractional)
#   T3_RESTART_ACK_SECONDS   seconds the detached run waits for the acknowledgement (default 30)
#   T3_RESTART_MAX_POLLS     checks to wait for the app to quit (default 60); the wait for it to
#                            reopen is half that, and for the follow-up message one and a half times
# Exit: 0 detached or finished, 1 the restart failed (see the log), 2 bad arguments or a failed
# preflight (perl missing; the t3 CLI or the command not an executable regular file; log path
# unusable).

APP_ID="${T3_APP_ID:-com.t3tools.t3code}"
OSASCRIPT="${T3_RESTART_OSASCRIPT:-/usr/bin/osascript}"
OPEN="${T3_RESTART_OPEN:-/usr/bin/open}"
POLL="${T3_RESTART_POLL_SECONDS:-1}"
MAX_POLLS="${T3_RESTART_MAX_POLLS:-60}"
ACK_SECONDS="${T3_RESTART_ACK_SECONDS:-30}"
NOTIFY=""; LOG=""; DELAY=20; DRY=0
USAGE="usage: restart.sh --notify <threadId> --log <path> [--delay <seconds>] [--dry-run] [-- <command> [args...]]"

die() { echo "$1" >&2; echo "$USAGE" >&2; exit 2; }
say() { echo "$(date '+%H:%M:%S') $*"; }

while [ $# -gt 0 ]; do
  case "$1" in
    --) shift; break ;;
    --dry-run) DRY=1; shift ;;
    --notify|--log|--delay)
      [ $# -ge 2 ] || die "$1 needs a value"
      case "$2" in --*) die "$1 needs a value, not an option: $2" ;; esac
      case "$1" in --notify) NOTIFY="$2" ;; --log) LOG="$2" ;; --delay) DELAY="$2" ;; esac
      shift 2 ;;
    *) die "unknown argument: $1" ;;
  esac
done
# "$@" is now the command after --, if any.

[ -n "$NOTIFY" ] && [ -n "$LOG" ] || die "--notify and --log are required"
case "$DELAY" in ''|*[!0-9]*) die "--delay must be a whole number of seconds" ;; esac
case "$NOTIFY" in *[!A-Za-z0-9:%._-]*) die "--notify may hold only letters, digits, : % . _ -" ;; esac
case "$APP_ID" in ''|*[!A-Za-z0-9.-]*) die "T3_APP_ID may hold only letters, digits, . and -" ;; esac
case "$POLL" in ''|*[!0-9.]*) die "T3_RESTART_POLL_SECONDS must be a number" ;; esac
case "$MAX_POLLS" in ''|*[!0-9]*) die "T3_RESTART_MAX_POLLS must be a whole number" ;; esac
case "$ACK_SECONDS" in ''|*[!0-9]*) die "T3_RESTART_ACK_SECONDS must be a whole number" ;; esac

# Find an executable file for a command word; builtins and functions do not count.
resolve() {
  case "$1" in
    */*) if [ -f "$1" ] && [ -x "$1" ]; then printf '%s\n' "$1"; return 0; fi; return 1 ;;
  esac
  _old_ifs="$IFS"; IFS=:
  for _dir in $PATH; do
    [ -n "$_dir" ] || _dir=.
    if [ -f "$_dir/$1" ] && [ -x "$_dir/$1" ]; then IFS="$_old_ifs"; printf '%s\n' "$_dir/$1"; return 0; fi
  done
  IFS="$_old_ifs"; return 1
}

T3_CLI="${T3_RESTART_T3:-}"
if [ -z "$T3_CLI" ]; then
  T3_CLI="$(resolve t3)"
  if [ -z "$T3_CLI" ]; then
    for c in "$HOME/.local/bin/t3" "$HOME/.t3/bin/t3"; do
      if [ -f "$c" ] && [ -x "$c" ]; then T3_CLI="$c"; break; fi
    done
  fi
fi

CMD0=""
if [ $# -gt 0 ]; then CMD0="$(resolve "$1")"; fi

if [ -z "$T3_RESTART_CHILD" ]; then
  # Preflight: everything that can be checked before detaching.
  PERL="$(resolve perl)"
  [ -n "$PERL" ] || { echo "preflight: perl not found (needed to detach)" >&2; exit 2; }
  [ -n "$T3_CLI" ] && [ -f "$T3_CLI" ] && [ -x "$T3_CLI" ] || { echo "preflight: t3 CLI is not an executable file (set T3_RESTART_T3 or put t3 on PATH)" >&2; exit 2; }
  if [ $# -gt 0 ] && [ -z "$CMD0" ]; then
    echo "preflight: command is not an executable file: ${1##*/}" >&2; exit 2
  fi
  GO="$LOG.go"
  if [ -L "$LOG" ] || [ -e "$LOG" ]; then echo "log path exists or is a symlink; pass a new path: $LOG" >&2; exit 2; fi
  if [ -L "$GO" ] || [ -e "$GO" ]; then echo "acknowledgement path exists; remove it or pass a new log path: $GO" >&2; exit 2; fi

  # Create the log exclusively and privately, and keep it open on descriptor 3 for the child.
  # (`command exec` keeps a failed redirection from ending the shell.)
  _umask="$(umask)"; umask 077; set -C
  { command exec 3>"$LOG"; } 2>/dev/null
  _opened=$?
  set +C; umask "$_umask"
  [ "$_opened" = 0 ] || { echo "cannot create log: $LOG" >&2; exit 2; }

  # Detach: the child must be a session leader of its own. Die loudly if it cannot be.
  if [ "$DRY" = 1 ]; then set -- --dry-run -- "$@"; else set -- -- "$@"; fi
  # shellcheck disable=SC2016  # the perl program is literal
  T3_RESTART_CHILD=1 "$PERL" -MPOSIX -e '
    my $pid = fork;
    die "fork: $!\n" unless defined $pid;
    exit 0 if $pid;
    my $sid = POSIX::setsid();
    die "setsid: " . ($! || "no session id") . "\n" unless defined $sid && $sid > 0;
    exec @ARGV or die "exec: $!\n";' \
    /bin/sh "$0" --notify "$NOTIFY" --log "$LOG" --delay "$DELAY" "$@" \
    </dev/null >&3 2>&3
  status=$?
  exec 3>&-
  i=0
  while [ "$i" -lt 25 ]; do
    if grep -q ' start: app=' "$LOG" 2>/dev/null; then
      # Acknowledge only now that the run is seen to be alive; it quits nothing without this.
      if ! ( umask 077; set -C; : >"$GO" ) 2>/dev/null; then
        echo "detach failed: could not create the acknowledgement file $GO" >&2; exit 1
      fi
      if [ "$DRY" = 1 ]; then
        echo "detached; dry run, T3 Code would quit in ${DELAY}s; log: $LOG"
      else
        echo "detached; T3 Code quits in ${DELAY}s; log: $LOG"
      fi
      exit 0
    fi
    sleep 0.2; i=$((i+1))
  done
  echo "detach failed (launcher exit $status): no start line in $LOG after 5s; nothing was acknowledged, so the run quits nothing" >&2
  exit 1
fi

probe() {
  _out="$("$OSASCRIPT" -e "application id \"$APP_ID\" is running" 2>/dev/null)" || { echo unknown; return; }
  case "$_out" in true|false) echo "$_out" ;; *) echo unknown ;; esac
}

CMD_NAME="none"
[ -z "$CMD0" ] || CMD_NAME="${CMD0##*/}"
# Write a result line; if the write fails, stop before anything else (no notification).
result() { echo "result: $1" || exit 1; }

say "start: app=$APP_ID notify=$NOTIFY delay=${DELAY}s dry_run=$DRY cli=${T3_CLI:-missing} command=$CMD_NAME"

# Nothing quits until the launcher acknowledges that it saw the line above.
GO="$LOG.go"
i=0
while [ ! -f "$GO" ] && [ "$i" -lt $((ACK_SECONDS * 5)) ]; do sleep 0.2; i=$((i+1)); done
if [ ! -f "$GO" ] || [ -L "$GO" ]; then
  say "no acknowledgement from the launcher within ${ACK_SECONDS}s; nothing was changed"
  result aborted-no-ack
  exit 1
fi
rm -f "$GO"

if [ "$DRY" = 1 ]; then
  say "dry run: would wait ${DELAY}s, would quit, would run [$CMD_NAME], would reopen, would message $NOTIFY"
  say "app state now: $(probe)"
  result dry-run
  exit 0
fi

sleep "$DELAY"
say "quitting"
"$OSASCRIPT" -e "tell application id \"$APP_ID\" to quit" || say "quit request failed; waiting to see whether the app exits"
i=0; STATE="$(probe)"
while [ "$STATE" != false ] && [ "$i" -lt "$MAX_POLLS" ]; do sleep "$POLL"; i=$((i+1)); STATE="$(probe)"; done
if [ "$STATE" != false ]; then
  say "app state is '$STATE' after $i checks; nothing was changed"
  result failed-to-quit
  exit 1
fi
say "stopped after $i checks"

CLOSED_STATUS="none"
if [ $# -gt 0 ]; then
  if [ -z "$CMD0" ]; then
    CLOSED_STATUS=127
    say "command not found: ${1##*/}"
  else
    shift
    say "running while closed: $CMD_NAME"
    "$CMD0" "$@"
    CLOSED_STATUS=$?
  fi
  say "while-closed exit $CLOSED_STATUS"
  sleep "$POLL"; sleep "$POLL"
fi

say "opening"
"$OPEN" -b "$APP_ID"
i=0; STATE="$(probe)"
while [ "$STATE" != true ] && [ "$i" -lt $((MAX_POLLS / 2)) ]; do sleep "$POLL"; i=$((i+1)); STATE="$(probe)"; done
if [ "$STATE" != true ]; then
  say "app did not come up (state '$STATE'); open it by hand"
  result failed-to-open
  exit 1
fi
say "app is running"

# The result line comes first; the follow-up message cannot change it.
if [ "$CLOSED_STATUS" != "none" ] && [ "$CLOSED_STATUS" != "0" ]; then
  result while-closed-failed
  FINAL=1
else
  result ok
  FINAL=0
fi

MSG="T3 Code is back after the scripted restart (automated message from the t3-code restart skill's restart.sh). While-closed command exit: $CLOSED_STATUS. Log: $LOG. Validate the restart, then tell each paused thread it can resume."
i=0; SENT=0
while [ "$i" -lt $((MAX_POLLS * 3 / 2)) ]; do
  if "$T3_CLI" thread send "$NOTIFY" "$MSG" >/dev/null 2>&1; then SENT=1; break; fi
  sleep "$POLL"; i=$((i+1))
done
if [ "$SENT" = 1 ]; then echo "notify: accepted"; else echo "notify: failed"; fi
exit "$FINAL"
