# shellcheck shell=bash
#
# Private tmux server for every spec that touches a live tmux binary.
#
# Specs here drive real tmux, because the behaviour under test IS tmux target
# resolution and pane I/O. Driving the user's default server from a test is
# how a test suite kills the sessions running it, so nothing in this suite is
# allowed to reach it.
#
# The isolation mechanism is `tmux -L <socket-name>`, which names a server
# explicitly on every invocation. The alternative — exporting TMUX_TMPDIR and
# relying on inheritance — is a trap: $TMUX is set inside any tmux session and
# takes precedence over TMUX_TMPDIR, so a spec that looks sandboxed runs
# against the real server. An explicit -L on every call cannot be overridden
# by an inherited variable.
#
# Every session created here is named zz-spawn-*; teardown refuses to touch
# anything else, and kills only the private server it created.

# tmux_sandbox_start
#
# Names a per-test server and anchors it with a keepalive session. tmux exits
# a server as soon as its last session ends (exit-empty), so without the
# keepalive the server can vanish between two commands of the same spec.
tmux_sandbox_start() {
  SANDBOX_SOCKET="zzspawn-$$-${BATS_TEST_NUMBER:-0}"
  export SANDBOX_SOCKET
  tmux -L "$SANDBOX_SOCKET" new-session -d -s zz-spawn-keepalive -c /tmp
  tmux_sandbox_assert
}

# tmux_sandbox_assert
#
# Refuse to proceed unless the socket answering is the private one. Belt and
# braces over tmux_sandbox_start: guards against a reordered setup or a
# future edit that drops the socket name.
tmux_sandbox_assert() {
  local sock
  sock="$(tmux -L "${SANDBOX_SOCKET:?}" display-message -p '#{socket_path}' 2>/dev/null || true)"
  if [[ -z "$sock" || "$sock" != *"$SANDBOX_SOCKET" ]]; then
    echo "refusing: tmux socket '$sock' is not the sandbox '$SANDBOX_SOCKET'" >&2
    return 1
  fi
}

# ts <args...>
#
# Run tmux against the sandbox server. Specs call this, never bare `tmux`.
ts() {
  tmux -L "${SANDBOX_SOCKET:?}" "$@"
}

# tmux_sandbox_stop
#
# The only destructive call in the harness, so it re-verifies everything
# itself. bats runs teardown even when setup failed, which means this can be
# reached with no sandbox in place — every guard failing means "do nothing",
# never "fall back to the default server".
tmux_sandbox_stop() {
  [[ -n "${SANDBOX_SOCKET:-}" ]] || return 0
  [[ "$SANDBOX_SOCKET" == zzspawn-* ]] || return 0
  tmux_sandbox_assert 2>/dev/null || return 0

  # Read the socket path from the server before ending it: afterwards there
  # is nothing left to ask, and reconstructing the path by hand would guess
  # at a directory layout that differs between platforms.
  local sock
  sock="$(tmux -L "$SANDBOX_SOCKET" display-message -p '#{socket_path}' 2>/dev/null || true)"

  tmux -L "$SANDBOX_SOCKET" kill-server 2>/dev/null || true

  # Ending the server does not unlink its socket, so without this every run
  # leaves one behind and the directory fills with dead entries. Guarded on
  # the sandbox prefix so this can only ever remove a socket this harness
  # created.
  if [[ -S "$sock" && "$(basename "$sock")" == zzspawn-* ]]; then
    rm -f "$sock"
  fi
}

# stub_claude_bin <path> [body]
#
# Write an inert executable standing in for `claude`. No spec may ever launch
# the real binary: it would mint a session upstream, spend tokens, and on a
# developer machine could collide with the user's own sessions.
stub_claude_bin() {
  local path="$1" body="${2:-}"
  mkdir -p "$(dirname "$path")"
  {
    echo '#!/usr/bin/env bash'
    if [[ -n "$body" ]]; then
      echo "$body"
    else
      echo 'sleep 300'
    fi
  } > "$path"
  chmod +x "$path"
}
