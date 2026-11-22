#!/usr/bin/env bats
#
# Behaviour of the spawn-session skill's script and its pure decision lib.
#
# Specs that drive tmux use a private server named with `tmux -L` (see
# helpers/tmux-sandbox.bash) and only ever create zz-spawn-* sessions. The
# specs for what the launcher says before it launches put a recording stand-in
# for the multiplexer on PATH instead, so they need no tmux and reach no
# server. No spec launches the real `claude` binary.

setup() {
  load '../../../scripts/test-support/sandbox-guard'
  PLUGIN_ROOT="$(cd "$(dirname "$BATS_TEST_FILENAME")/.." && pwd)"
  SKILL_DIR="$PLUGIN_ROOT/skills/sessions/spawn-session"
  LIB="$SKILL_DIR/scripts/lib/session-spawn.sh"
  SPAWN="$SKILL_DIR/scripts/spawn-session.sh"
  # shellcheck source=../skills/sessions/spawn-session/scripts/lib/session-spawn.sh
  source "$LIB"
  load 'helpers/tmux-sandbox'
}

# ── the launch line ─────────────────────────────────────────────────────────

@test "spawn_launch_command defaults to acceptEdits and never resumes" {
  run spawn_launch_command "demo" "" ""

  [ "$status" -eq 0 ]
  [[ "$output" == *"--remote-control demo"* ]]
  [[ "$output" == *"--permission-mode acceptEdits"* ]]
  # This tool spawns; it never resumes. --continue in particular resolves to
  # the newest conversation in the working directory rather than a named one,
  # so in a directory hosting two sessions it hijacks the wrong one.
  [[ "$output" != *"--continue"* ]]
  [[ "$output" != *"--resume"* ]]
}

@test "spawn_launch_command emits bypass only for the exact posture token" {
  run spawn_launch_command "demo" "bypass" ""
  [[ "$output" == *"--dangerously-skip-permissions"* ]]
  [[ "$output" != *"--permission-mode"* ]]

  # Fail toward fewer privileges: anything unrecognised is acceptEdits, never
  # bypass. A typo or a corrupted value must not silently grant more.
  local junk
  for junk in "Bypass" "bypass " "--dangerously-skip-permissions" "yes" "x"; do
    run spawn_launch_command "demo" "$junk" ""
    [[ "$output" == *"--permission-mode acceptEdits"* ]] || {
      echo "posture '$junk' did not fall back to acceptEdits: $output"; return 1; }
  done
}

@test "spawn_launch_command clears the nested-session variables" {
  # A claude spawned from inside another claude inherits these and refuses to
  # start, believing it is nested. The pane is a child of whatever launched
  # the script, so they must be cleared in the pane itself.
  run spawn_launch_command "demo" "" ""
  [[ "$output" == *"unset "* ]]
  [[ "$output" == *"CLAUDECODE"* ]]
}

@test "spawn_launch_command places a pre-launch command before claude" {
  # The portability escape hatch: this plugin knows nothing about any
  # particular machine's environment injection, so a caller supplies it.
  run spawn_launch_command "demo" "" 'set -a; . "$HOME/env"; set +a'
  [ "$status" -eq 0 ]
  [[ "$output" == *'set -a; . "$HOME/env"; set +a'* ]]
  # It must run BEFORE claude, or it cannot affect it.
  local pre_at claude_at
  pre_at="${output%%set -a*}"
  claude_at="${output%%claude *}"
  [ "${#pre_at}" -lt "${#claude_at}" ]
}

# ── session names ───────────────────────────────────────────────────────────

@test "valid_session_name accepts the safe charset and rejects the rest" {
  local ok
  for ok in "demo" "DEMO" "a" "worker-1" "worker_1" "AB-cd_09"; do
    run valid_session_name "$ok"
    [ "$status" -eq 0 ] || { echo "rejected valid name '$ok'"; return 1; }
  done

  # A dot or a colon is NOT rejected by the multiplexer — it is silently
  # rewritten to an underscore. The session then exists under a name the
  # caller never chose, and every later exact-match lookup misses it. Reject
  # rather than inherit a silent rename.
  local bad
  for bad in "" "with.dot" "with:colon" "-leading-dash" "has space" "sla/sh" 'semi;colon' '$(id)' "üñî"; do
    run valid_session_name "$bad"
    [ "$status" -ne 0 ] || { echo "accepted invalid name '$bad'"; return 1; }
  done
}

@test "valid_session_name enforces a length ceiling" {
  local long
  long="$(printf 'a%.0s' {1..64})"
  run valid_session_name "$long"
  [ "$status" -eq 0 ]

  run valid_session_name "${long}a"
  [ "$status" -ne 0 ]
}

# ── reading the session's own state ─────────────────────────────────────────

@test "spawn_verdict separates 'not running' from 'running but unreachable'" {
  # These are different facts with different remedies, and collapsing them is
  # what makes a caller destroy a working session to fix connectivity.
  run spawn_verdict "" ""
  [ "$output" = "no_process" ]

  run spawn_verdict "" "session_abc"
  [ "$output" = "no_process" ]

  # A live process whose bridge id is absent, or the JSON literal null, is
  # alive-but-unreachable — the state a liveness check misses, because both
  # the process and its session survive a dead bridge.
  run spawn_verdict "4242" ""
  [ "$output" = "bridge_dead" ]

  run spawn_verdict "4242" "null"
  [ "$output" = "bridge_dead" ]

  run spawn_verdict "4242" "session_abc"
  [ "$output" = "healthy" ]
}

@test "bridge_url renders a remote-control link, and refuses to invent one" {
  run bridge_url "session_abc123"
  [ "$status" -eq 0 ]
  [ "$output" = "https://claude.ai/code/session_abc123" ]

  # No id means no link. Emitting a bare prefix would hand the caller a URL
  # that looks usable and is not.
  run bridge_url ""
  [ "$status" -ne 0 ]
  [ -z "$output" ]

  run bridge_url "null"
  [ "$status" -ne 0 ]
  [ -z "$output" ]
}

# ── the driver: launching ───────────────────────────────────────────────────
#
# These specs drive a real multiplexer, because what they check IS target
# resolution and pane I/O. They run against a private server named per test
# and only ever create zz-spawn-* sessions.

live_setup() {
  tmux_sandbox_start
  STUB_DIR="$BATS_TEST_TMPDIR/bin"
  stub_claude_bin "$STUB_DIR/claude"
  # The launch line's own escape hatch puts the stub ahead of anything real
  # on the pane's PATH, so no spec can reach the installed CLI.
  PRE_LAUNCH="export PATH=$STUB_DIR:\$PATH"
  SESSIONS_DIR="$BATS_TEST_TMPDIR/sessions"
  mkdir -p "$SESSIONS_DIR"

  # A fixture configuration, never the real one. The trust check reads the
  # CLI's own config file by default, and --trust-folder writes it; a suite
  # that inherited that default would read — and could modify — the config
  # belonging to every session on the machine.
  CONFIG_FILE="$BATS_TEST_TMPDIR/claude.json"
  echo '{"projects":{}}' > "$CONFIG_FILE"
  TRUST_FLAG="--trust-folder"
}

# pretrust <dir>
#
# Record trust for a directory in the fixture configuration, and stop passing
# --trust-folder. --bypass is refused alongside --trust-folder, so a spec that
# launches with bypass settles trust first — the same two steps a caller takes.
# The key is derived the way the launcher derives it, so the entry written is
# the entry it looks up.
pretrust() {
  python3 "$SKILL_DIR/scripts/lib/trust-config.py" grant "$CONFIG_FILE" "$(fixture_key "$1")"
  TRUST_FLAG=""
}

# fixture_key <dir>
#
# Echoes the key the launcher records trust under for this directory.
fixture_key() {
  local dir
  dir="$(cd "$1" && pwd)"
  trust_key "$dir" "$(git -C "$dir" rev-parse --show-toplevel 2>/dev/null || true)"
}

spawn() {
  SPAWN_SESSIONS_DIR="$SESSIONS_DIR" SPAWN_CONFIG_FILE="$CONFIG_FILE" \
    "$SPAWN" --socket "$SANDBOX_SOCKET" --pre-launch "$PRE_LAUNCH" ${TRUST_FLAG:+"$TRUST_FLAG"} "$@"
}

teardown() {
  tmux_sandbox_stop
}

# bats test_tags=live
@test "spawns a detached session in the named directory with the named posture" {
  live_setup
  local dir="$BATS_TEST_TMPDIR/work"
  mkdir -p "$dir"
  pretrust "$dir"

  run spawn "zz-spawn-a" --dir "$dir" --bypass --no-verify
  [ "$status" -eq 0 ]

  ts has-session -t "=zz-spawn-a"
  [ "$(ts display-message -p -t "=zz-spawn-a:" '#{pane_current_path}')" = "$dir" ]

  # The evidence that posture reached the pane is the typed line itself. An
  # 80-column pane wraps it, so join before matching.
  local i content=""
  for i in $(seq 1 20); do
    content="$(ts capture-pane -p -J -t "=zz-spawn-a:")"
    content="${content//$'\n'/}"
    [[ "$content" == *"--dangerously-skip-permissions"* ]] && break
    sleep 0.2
  done
  [[ "$content" == *"--dangerously-skip-permissions"* ]]
  [[ "$content" != *"--permission-mode"* ]]
}

# bats test_tags=live
@test "refuses a name that already has a live session, and leaves it alone" {
  live_setup
  ts new-session -d -s "zz-spawn-taken" -c /tmp
  local before
  before="$(ts display-message -p -t "=zz-spawn-taken:" '#{session_created}')"

  run spawn "zz-spawn-taken" --dir /tmp --no-verify
  [ "$status" -eq 2 ]
  [[ "$output" == *"already"* ]]

  # Still the same session: not killed, not relaunched, not pasted into.
  ts has-session -t "=zz-spawn-taken"
  [ "$(ts display-message -p -t "=zz-spawn-taken:" '#{session_created}')" = "$before" ]
}

# bats test_tags=live
@test "refuses a name the multiplexer would silently rename, creating nothing" {
  live_setup

  run spawn "zz.spawn.dots" --dir /tmp --no-verify
  [ "$status" -eq 2 ]

  # Neither the requested name nor the mangled one exists.
  ! ts has-session -t "=zz.spawn.dots" 2>/dev/null
  ! ts has-session -t "=zz_spawn_dots" 2>/dev/null
}

# bats test_tags=live
@test "dry run reports the plan and launches nothing" {
  live_setup
  pretrust /tmp

  run spawn "zz-spawn-dry" --dir /tmp --bypass --dry-run
  [ "$status" -eq 0 ]
  [[ "$output" == *"zz-spawn-dry"* ]]
  [[ "$output" == *"--dangerously-skip-permissions"* ]]

  ! ts has-session -t "=zz-spawn-dry" 2>/dev/null
}

# ── the driver: verifying ───────────────────────────────────────────────────

# bats test_tags=live
@test "a session with a live bridge reports healthy and hands back its link" {
  live_setup_hs
  stub_answering "\$PWD" acceptEdits '"session_test123"'

  run spawn_hs "zz-spawn-ok" --dir /tmp --timeout 25
  [ "$status" -eq 0 ]
  [[ "$output" == *"https://claude.ai/code/session_test123"* ]]
  # The link is bridge-scoped, and saying so is the point of printing it here.
  [[ "$output" == *"this bridge only"* ]]
}

# bats test_tags=live
@test "a live session with no bridge is reported unreachable, not killed" {
  live_setup_hs
  stub_answering "\$PWD" acceptEdits 'null'

  run spawn_hs "zz-spawn-nobridge" --dir /tmp --timeout 25
  [ "$status" -eq 3 ]
  [[ "$output" == *"not reachable"* || "$output" == *"not established"* ]]

  # Still running. A dead bridge is a connectivity fault; the session holds a
  # real conversation and destroying it to repair connectivity loses work.
  ts has-session -t "=zz-spawn-nobridge"
  [ -n "$(ts list-panes -t "=zz-spawn-nobridge" -F '#{pane_pid}')" ]
}

# bats test_tags=live
@test "a session whose CLI never starts is reported as never started" {
  live_setup_hs
  # Exits immediately: the session exists, but nothing is running in it.
  use_fake_cli "FAKE_EXIT=1"

  run spawn_hs "zz-spawn-dead" --dir /tmp --timeout 2
  [ "$status" -eq 4 ]
}

# bats test_tags=live
@test "porcelain output is tab-separated key/value pairs" {
  live_setup_hs
  stub_answering "\$PWD" acceptEdits '"session_p"'

  run spawn_hs "zz-spawn-tsv" --dir /tmp --timeout 25 --porcelain
  [ "$status" -eq 0 ]
  [[ "$output" == *$'name\tzz-spawn-tsv'* ]]
  [[ "$output" == *$'verdict\thealthy'* ]]
  [[ "$output" == *$'identity\tok'* ]]
  [[ "$output" == *$'url\thttps://claude.ai/code/session_p'* ]]
  # Prose belongs to the human report, not this one.
  [[ "$output" != *"this bridge only"* ]]
}

# ── the handshake protocol ──────────────────────────────────────────────────

@test "the handshake asks for exactly the reply the matcher accepts" {
  # The instruction we send and the pattern we search for are two statements
  # of one format. If they drift, verification silently never matches and
  # every spawn reports unconfirmed. Tying them together in a spec is the only
  # thing that keeps them honest.
  local nonce="7f3a9c2b"
  local reply="SPAWN-ACK $nonce cwd=/some/where posture=bypass"

  run ack_matches "$nonce" "$reply"
  [ "$status" -eq 0 ]

  # A reply carrying a different token belongs to a different spawn.
  run ack_matches "$nonce" "SPAWN-ACK deadbeef cwd=/some/where posture=bypass"
  [ "$status" -ne 0 ]

  run ack_matches "$nonce" "I have read the brief and am starting work."
  [ "$status" -ne 0 ]
}

@test "the handshake text does not itself match the pattern it asks for" {
  # The instruction lands in the same transcript the reply is read from. If
  # the instruction contained a literal well-formed acknowledgement, the
  # spawner would match its own request and declare the session confirmed
  # before it had said anything at all.
  local nonce="7f3a9c2b"
  local text
  text="$(handshake_text "$nonce")"

  [[ "$text" == *"$nonce"* ]]   # it must carry the token
  run ack_matches "$nonce" "$text"
  [ "$status" -ne 0 ]           # but must not read as a reply
}

@test "parse_ack reads back the directory and posture the session reported" {
  run parse_ack cwd "SPAWN-ACK abc cwd=/home/x/proj posture=acceptEdits"
  [ "$output" = "/home/x/proj" ]

  run parse_ack posture "SPAWN-ACK abc cwd=/home/x/proj posture=acceptEdits"
  [ "$output" = "acceptEdits" ]

  # A session that cannot determine its own posture says so rather than
  # guessing; that is a weaker answer, not a wrong one.
  run parse_ack posture "SPAWN-ACK abc cwd=/tmp posture=unknown"
  [ "$output" = "unknown" ]
}

@test "ack_verdict aborts on a directory mismatch and tolerates an unknown posture" {
  run ack_verdict "/work" "/work" "bypass" "bypass"
  [ "$output" = "ok" ]

  # The wrong-pane detector. A session answering from somewhere else is not
  # the session we launched, and nothing further may be sent to it.
  run ack_verdict "/work" "/elsewhere" "bypass" "bypass"
  [ "$output" = "mismatch_cwd" ]

  # A definite disagreement about posture is also disqualifying: it means the
  # session is not running under the permissions the caller asked for.
  run ack_verdict "/work" "/work" "bypass" "acceptEdits"
  [ "$output" = "mismatch_posture" ]

  # Unknown is not disagreement. Aborting here would fail every session that
  # cannot introspect its own launch flags, for no safety gain.
  run ack_verdict "/work" "/work" "bypass" "unknown"
  [ "$output" = "posture_unverified" ]
}

# ── the driver: the handshake round trip ────────────────────────────────────

# use_fake_cli <ENV=VALUE>...
#
# Put the fixture CLI (helpers/fake-cli.sh) on the pane's PATH and configure
# it through the launcher's own pre-launch hook — which is also a live test of
# that hook, since it is the mechanism a real caller uses to set up a session's
# environment.
use_fake_cli() {
  mkdir -p "$STUB_DIR"
  cp "$PLUGIN_ROOT/tests/helpers/fake-cli.sh" "$STUB_DIR/claude"
  chmod +x "$STUB_DIR/claude"

  local line="export PATH=$STUB_DIR:\$PATH"
  line+="; export SPAWN_SESSIONS_DIR=$SESSIONS_DIR"
  line+="; export SPAWN_PROJECTS_DIR=$PROJECTS_DIR"
  local kv
  for kv in "$@"; do
    line+="; export $kv"
  done
  PRE_LAUNCH="$line"
}

# stub_answering <reported-cwd> [posture] [bridge-json]
#
# A session that answers the handshake. Passing a literal path makes it answer
# from somewhere it is not, which is the wrong-pane case.
stub_answering() {
  local reported="$1" posture="${2:-bypass}" bridge="${3:-}"
  local args=( "FAKE_POSTURE=$posture" )
  [[ "$reported" != '$PWD' ]] && args+=( "FAKE_REPORT_CWD=$reported" )
  case "$bridge" in
    null)  args+=( "FAKE_BRIDGE_NULL=1" ) ;;
    '"'*) args+=( "FAKE_BRIDGE_ID=${bridge//\"/}" ) ;;
  esac
  use_fake_cli "${args[@]}"
}

# stub_recording [reported-cwd]
#
# Answers the handshake and records every line it receives into $RECORD.
stub_recording() {
  local reported="${1:-\$PWD}"
  local args=( "FAKE_RECORD=$RECORD" "FAKE_SESSION_ID=99999999-8888-7777-6666-555555555555" )
  [[ "$reported" != '$PWD' ]] && args+=( "FAKE_REPORT_CWD=$reported" )
  use_fake_cli "${args[@]}"
}

live_setup_hs() {
  live_setup
  PROJECTS_DIR="$BATS_TEST_TMPDIR/projects"
  mkdir -p "$PROJECTS_DIR"
}

spawn_hs() {
  SPAWN_SESSIONS_DIR="$SESSIONS_DIR" SPAWN_PROJECTS_DIR="$PROJECTS_DIR" \
  SPAWN_CONFIG_FILE="$CONFIG_FILE" \
    "$SPAWN" --socket "$SANDBOX_SOCKET" --pre-launch "$PRE_LAUNCH" ${TRUST_FLAG:+"$TRUST_FLAG"} "$@"
}

# bats test_tags=live
@test "a session that identifies itself correctly is confirmed" {
  live_setup_hs
  local dir="$BATS_TEST_TMPDIR/work"
  mkdir -p "$dir"
  pretrust "$dir"
  stub_answering "\$PWD" bypass

  run spawn_hs "zz-spawn-hs-ok" --dir "$dir" --bypass --timeout 25
  [ "$status" -eq 0 ]
  [[ "$output" == *"confirmed"* ]]
}

# bats test_tags=live
@test "a session answering from the wrong directory aborts the spawn" {
  live_setup_hs
  local dir="$BATS_TEST_TMPDIR/work"
  mkdir -p "$dir"
  pretrust "$dir"
  # Answers from somewhere it is not: the shape of a handshake that reached a
  # different pane than the one intended.
  stub_answering "/somewhere/else" bypass

  run spawn_hs "zz-spawn-hs-bad" --dir "$dir" --bypass --timeout 25
  [ "$status" -ne 0 ]
  [ "$status" -ne 5 ]
  [[ "$output" == *"mismatch"* || "$output" == *"different directory"* ]]
}

# bats test_tags=live
@test "a session that never answers is unconfirmed, not failed, and is left running" {
  live_setup_hs
  # Never answers: reads its pane and says nothing.
  use_fake_cli "FAKE_SILENT=1"

  run spawn_hs "zz-spawn-hs-quiet" --dir /tmp --timeout 6
  [ "$status" -eq 5 ]
  [[ "$output" == *"unconfirmed"* ]]

  # Unconfirmed is not failed: the session keeps running and is not touched.
  ts has-session -t "=zz-spawn-hs-quiet"
}

# ── the brief ───────────────────────────────────────────────────────────────

@test "brief_source refuses two sources and tolerates none" {
  run brief_source "some text" ""
  [ "$output" = "inline" ]

  run brief_source "" "/path/to/file"
  [ "$output" = "file" ]

  # No brief is a legitimate request: spawn the session, confirm it, stop.
  run brief_source "" ""
  [ "$output" = "none" ]

  # Two sources is ambiguous, and guessing which one the caller meant is how
  # the wrong brief gets delivered.
  run brief_source "some text" "/path/to/file"
  [ "$status" -ne 0 ]
}

# bats test_tags=live
@test "a multi-line brief arrives whole, as one paste, after the handshake" {
  live_setup_hs
  RECORD="$BATS_TEST_TMPDIR/received.txt"
  stub_recording

  local brief="FIRST-LINE of the brief
second line with  spaces
third line: a colon, a \$dollar and a 'quote'
LAST-LINE of the brief"

  run spawn_hs "zz-spawn-brief" --dir /tmp --timeout 25 --prompt "$brief"
  [ "$status" -eq 0 ]

  # Every line arrived — the truncation bug loses everything after the first.
  local received
  received="$(cat "$RECORD")"
  [[ "$received" == *"FIRST-LINE of the brief"* ]]
  [[ "$received" == *"second line with  spaces"* ]]
  [[ "$received" == *"third line: a colon, a \$dollar and a 'quote'"* ]]
  [[ "$received" == *"LAST-LINE of the brief"* ]]

  # And it arrived as ONE paste, not as a run of keystrokes. Exactly two
  # pastes reach the session — the handshake and the brief — so a brief that
  # had been typed would leave only one paste-start marker behind, and the
  # terminal would have seen a submission at every newline in between.
  [ "$(grep -c $'\033\[200~' "$RECORD")" -eq 2 ]

  # The brief's interior lines carry no markers at all: they are text inside
  # the block, not separate deliveries.
  local interior
  interior="$(grep -F 'second line with' "$RECORD")"
  [[ "$interior" != *$'\033'* ]]
}

# bats test_tags=live
@test "no brief is delivered to a session that failed to identify itself" {
  live_setup_hs
  RECORD="$BATS_TEST_TMPDIR/received.txt"
  # Answers from somewhere it is not, so identity cannot be confirmed.
  stub_recording "/somewhere/else"
  local dir="$BATS_TEST_TMPDIR/work"
  mkdir -p "$dir"

  run spawn_hs "zz-spawn-nobrief" --dir "$dir" --timeout 25 --prompt "SECRET-BRIEF-TEXT"
  [ "$status" -ne 0 ]

  # The handshake reached it; the brief never did.
  [[ "$(cat "$RECORD")" != *"SECRET-BRIEF-TEXT"* ]]
}

# ── workspace trust ─────────────────────────────────────────────────────────

@test "trust_key uses the repository root when there is one" {
  # This is the CLI's own rule, and it has a consequence worth being loud
  # about: granting trust for a directory inside a repository grants it for
  # the whole repository, not just that directory.
  run trust_key "/repo/sub/dir" "/repo"
  [ "$output" = "/repo" ]

  run trust_key "/loose/dir" ""
  [ "$output" = "/loose/dir" ]
}

source_driver() {
  # shellcheck source=../skills/sessions/spawn-session/scripts/spawn-session.sh
  source "$SPAWN"
  # The driver sets strict mode for its own run. Its nounset and pipefail are
  # taken back off, so they do not apply to the rest of the test body.
  # errexit stays on: it is how bats fails a spec, and with it off every check
  # after this line, a failing one included, leaves the spec passing. A check
  # that is meant to fail goes through `run`, which errexit does not reach.
  set +u +o pipefail
}

@test "granting trust adds the entry and preserves everything else in the file" {
  source_driver
  local cfg="$BATS_TEST_TMPDIR/claude.json"
  cat > "$cfg" <<'JSON'
{
  "numStartups": 42,
  "projects": {
    "/existing/project": { "hasTrustDialogAccepted": true, "allowedTools": ["Read"] }
  },
  "someOtherKey": {"nested": [1, 2, 3]}
}
JSON

  run grant_trust "$cfg" "/new/place"
  [ "$status" -eq 0 ]

  # The new entry is there...
  run config_trusts "$cfg" "/new/place"
  [ "$status" -eq 0 ]

  # ...and nothing else was disturbed. This file belongs to the CLI and holds
  # unrelated state for every project on the machine; a writer that rewrote it
  # wholesale would destroy work it never looked at.
  run config_trusts "$cfg" "/existing/project"
  [ "$status" -eq 0 ]
  grep -q '"numStartups": 42' "$cfg"
  grep -q '"allowedTools"' "$cfg"
  grep -q '"someOtherKey"' "$cfg"
  grep -q '"nested"' "$cfg"
}

@test "granting trust refuses while another writer holds the lock" {
  source_driver
  local cfg="$BATS_TEST_TMPDIR/locked.json"
  echo '{"projects":{}}' > "$cfg"
  # The CLI takes this same lock. Writing through it would mean last-writer-
  # wins against every running session, silently discarding their changes.
  mkdir "$cfg.lock"

  SPAWN_LOCK_RETRIES=2 run grant_trust "$cfg" "/somewhere"
  [ "$status" -ne 0 ]

  run config_trusts "$cfg" "/somewhere"
  [ "$status" -ne 0 ]

  rmdir "$cfg.lock"
}

@test "config_trusts reports untrusted for a missing file or absent entry" {
  source_driver
  run config_trusts "$BATS_TEST_TMPDIR/does-not-exist.json" "/anywhere"
  [ "$status" -ne 0 ]

  echo '{"projects":{"/other":{"hasTrustDialogAccepted":true}}}' > "$BATS_TEST_TMPDIR/c.json"
  run config_trusts "$BATS_TEST_TMPDIR/c.json" "/anywhere"
  [ "$status" -ne 0 ]

  # An entry explicitly set to false is a refusal on record, not an absence.
  echo '{"projects":{"/x":{"hasTrustDialogAccepted":false}}}' > "$BATS_TEST_TMPDIR/d.json"
  run config_trusts "$BATS_TEST_TMPDIR/d.json" "/x"
  [ "$status" -ne 0 ]
}

# ── naming the blocker ──────────────────────────────────────────────────────

blocker_table() {
  cat "$SKILL_DIR/scripts/startup-blockers.tsv"
}

@test "blocker_for names the dialog holding a session and what settles it" {
  local pane="Accessing workspace:
  /some/path
Quick safety check: Is this a project you created or one you trust?
❯ No, exit
  Yes, I trust this folder"

  run blocker_for "$(blocker_table)" "$pane"
  [ "$status" -eq 0 ]
  [[ "$output" == trust* ]]
  # The remedy is the point: a bare "it is stuck" is what this replaces.
  [[ "$output" == *"--trust-folder"* ]]
}

@test "blocker_for ignores comments and blank lines, and stays silent on no match" {
  # The table is checked-in data with a long explanatory header; a parser that
  # treated those comment lines as patterns would match almost any pane.
  run blocker_for "$(blocker_table)" "a perfectly ordinary session, working away"
  [ "$status" -ne 0 ]
  [ -z "$output" ]

  # In particular, prose from the table's own header must never match.
  run blocker_for "$(blocker_table)" "Columns, tab-separated: id pattern what remedy"
  [ "$status" -ne 0 ]
}

@test "blocker_for distinguishes the bypass disclaimer from the trust dialog" {
  # Different dialogs, different remedies. Reporting the wrong one sends the
  # reader to change a setting that was never the problem.
  local pane="  ❯ No, exit
    Yes, I accept"
  run blocker_for "$(blocker_table)" "$pane"
  [[ "$output" == bypass-disclaimer* ]]
  [[ "$output" == *"disclaimer"* ]]
}

@test "blocker_for matches literally, so pattern characters are not wildcards" {
  # Patterns are data, and data can contain regex metacharacters. Treating
  # them as expressions would let one entry match panes it was never meant to.
  run blocker_for "id	a.c	what	remedy" "abc"
  [ "$status" -ne 0 ]

  run blocker_for "id	a.c	what	remedy" "xxa.cxx"
  [ "$status" -eq 0 ]
}

@test "version_verdict reports drift without pretending to know the future" {
  run version_verdict "2.1.259" "2.1.259"
  [ "$output" = "ok" ]

  # Advisory, never blocking: the tool still works, but the dialog wording it
  # was verified against may have moved.
  run version_verdict "2.2.000" "2.1.259"
  [ "$output" = "drift" ]

  run version_verdict "" "2.1.259"
  [ "$output" = "unknown" ]
}

# bats test_tags=live
@test "a session held at a startup dialog is diagnosed, not just timed out" {
  live_setup_hs
  RECORD="$BATS_TEST_TMPDIR/received.txt"
  # Shows the trust dialog and answers nothing, as a real session would.
  use_fake_cli "FAKE_SILENT=1" "FAKE_RECORD=$RECORD" "FAKE_PANE_TEXT='Yes, I trust this folder'"

  run spawn_hs "zz-spawn-blocked" --dir /tmp --timeout 6
  [ "$status" -eq 4 ]
  [[ "$output" == *"blocked"* ]]
  [[ "$output" == *"trust"* ]]
  # The remedy, not just the diagnosis.
  [[ "$output" == *"--trust-folder"* ]]
  # And nothing was typed at it: the session is there, it started recording,
  # and it received no input at all.
  ts has-session -t "=zz-spawn-blocked"
  [ -e "$RECORD" ]
  [ ! -s "$RECORD" ]
}

# bats test_tags=live
@test "a session that never shows its prompt is sent nothing and left running" {
  live_setup_hs
  RECORD="$BATS_TEST_TMPDIR/received.txt"
  # Started, and draws nothing the launcher recognises as a prompt or a dialog.
  use_fake_cli "FAKE_NO_PROMPT=1" "FAKE_RECORD=$RECORD"

  run spawn_hs "zz-spawn-noprompt" --dir /tmp --timeout 6
  [ "$status" -eq 5 ]
  [[ "$output" == *"the input prompt never appeared"* ]]
  [[ "$output" == *"handshake was not sent"* ]]

  ts has-session -t "=zz-spawn-noprompt"
  [ -e "$RECORD" ]
  [ ! -s "$RECORD" ]
}

# bats test_tags=live
@test "a dialog that quotes a status line is sent nothing" {
  live_setup_hs
  RECORD="$BATS_TEST_TMPDIR/received.txt"
  # Not a dialog the table knows, and it carries the wording of a status
  # line. There is no input box on the pane, so nothing is typed at it.
  use_fake_cli "FAKE_RECORD=$RECORD" "FAKE_PANE_TEXT='Color theme dialog: accept edits on'"

  run spawn_hs "zz-spawn-color" --dir /tmp --timeout 6
  [ "$status" -eq 5 ]
  [[ "$output" == *"handshake was not sent"* ]]

  ts has-session -t "=zz-spawn-color"
  [ -e "$RECORD" ]
  [ ! -s "$RECORD" ]
}

# bats test_tags=live
@test "resume picks up an existing session and delivers the brief" {
  live_setup_hs
  RECORD="$BATS_TEST_TMPDIR/received.txt"
  stub_recording

  # First run: the session comes up but the caller sends no brief.
  run spawn_hs "zz-spawn-resume" --dir /tmp --timeout 25
  [ "$status" -eq 0 ]

  # Second run resumes it rather than refusing, and delivers the brief. No
  # state was carried between the two runs: everything is re-derived from what
  # is observable now.
  run spawn_hs "zz-spawn-resume" --dir /tmp --timeout 25 --resume --prompt "RESUMED-BRIEF"
  [ "$status" -eq 0 ]
  [[ "$(cat "$RECORD")" == *"RESUMED-BRIEF"* ]]

  # Exactly one session: resuming must not create a second.
  [ "$(ts list-sessions -F '#{session_name}' | grep -c '^zz-spawn-resume$')" -eq 1 ]
}

# bats test_tags=live
@test "resume refuses when there is no session to resume" {
  live_setup_hs
  use_fake_cli

  run spawn_hs "zz-spawn-absent" --dir /tmp --timeout 5 --resume
  [ "$status" -eq 2 ]
  [[ "$output" == *"no session"* ]]
  ! ts has-session -t "=zz-spawn-absent" 2>/dev/null
}

@test "trust_grantable refuses the home directory, where trust is never persisted" {
  # The CLI treats the home directory as a special case: accepting trust there
  # applies to the running session only and is deliberately not written to
  # configuration. Writing the entry anyway would succeed, change nothing the
  # CLI reads, and leave the next session stopping at the same dialog — a tool
  # reporting success while achieving nothing.
  run trust_grantable "/home/someone" "/home/someone"
  [ "$status" -ne 0 ]

  run trust_grantable "/home/someone/project" "/home/someone"
  [ "$status" -eq 0 ]

  run trust_grantable "/srv/thing" "/home/someone"
  [ "$status" -eq 0 ]
}

# ── saying what is about to happen ──────────────────────────────────────────
#
# A hazard is named by the command, on stderr, at the moment it runs: that is
# when the caller is deciding what to do next. These specs pin the wording
# shape (the run-time fact, then the consequence as one capitalised verb) and
# the stream, because a warning on stdout would corrupt --porcelain output and
# a warning nobody can parse out of the report would be dropped.

# has <text> <needle> / lacks <text> <needle>
#
# Literal substring checks, as functions. A bare `[[ ]]` that comes out false
# fails a spec only where the shell running bats applies errexit to it, which
# bash 3.2 — still the system shell on macOS — does not unless it is the last
# line. A function returning non-zero fails the spec everywhere, so the specs
# below cannot pass on one machine for want of the shell that would fail them.
has() {
  [[ "$1" == *"$2"* ]] || { echo "expected to find: $2"; echo "in: $1"; return 1; }
}

lacks() {
  [[ "$1" != *"$2"* ]] || { echo "expected not to find: $2"; echo "in: $1"; return 1; }
}

# clean <file>
#
# Fails if the file holds any control byte other than the newline ending each
# line, or the two-byte form of a control character from U+0080 to U+009F.
clean() {
  local hits
  hits="$(LC_ALL=C grep -c '[[:cntrl:]]' "$1" || true)"
  [ "$hits" = "0" ] || { echo "control bytes in $1:"; LC_ALL=C od -c "$1"; return 1; }
  hits="$(LC_ALL=C grep -c "$(printf '\302[\200-\237]')" "$1" || true)"
  [ "$hits" = "0" ] || { echo "second-block control characters in $1:"; LC_ALL=C od -c "$1"; return 1; }
}

# count <pattern> <file>
#
# Echoes how many lines of the file match. Never fails, so a count of zero is
# an answer rather than an error.
count() {
  grep -c -- "$1" "$2" || true
}

@test "visible renders every control character as text, on one line" {
  run visible "a"$'\n'"b"$'\t'"c"$'\r'"d"$'\033'"[31me"$'\177'"f"$'\001'"g"
  [ "${#lines[@]}" -eq 1 ]
  [ "$output" = 'a\nb\tc\rd\x1b[31me\x7ff\x01g' ]

  # A backslash is doubled, so a rendered newline and the two characters
  # backslash-n cannot be told to mean the same thing.
  run visible 'a\nb'
  [ "$output" = 'a\\nb' ]

  # The second control block arrives as two bytes in UTF-8; some terminals
  # act on it exactly as they act on an escape.
  run visible "x"$'\302\233'"31my"
  [ "$output" = 'x\u009b31my' ]

  # Ordinary text, including multi-byte characters, passes through untouched.
  run visible "/some/where with spaces/é—ü & * ? [x]"
  [ "$output" = "/some/where with spaces/é—ü & * ? [x]" ]

  visible "a"$'\n'"WARNING: forged"$'\033'"[2K"$'\302\233'"1A" > "$BATS_TEST_TMPDIR/v"
  [ "$(count '' "$BATS_TEST_TMPDIR/v")" = "1" ]
  clean "$BATS_TEST_TMPDIR/v"
}

@test "a warning stays one line whatever its fields contain" {
  local evil="/tmp/x"$'\n'"WARNING: fixture line; this LAUNCHES nothing"$'\033'"[1A"

  bypass_warning "de"$'\033'"mo" "$evil" > "$BATS_TEST_TMPDIR/w"
  [ "$(count '' "$BATS_TEST_TMPDIR/w")" = "1" ]
  [ "$(count '^WARNING' "$BATS_TEST_TMPDIR/w")" = "1" ]
  clean "$BATS_TEST_TMPDIR/w"
  has "$(cat "$BATS_TEST_TMPDIR/w")" 'in /tmp/x\nWARNING: fixture line; this LAUNCHES nothing\x1b[1A; this LAUNCHES a session'

  trust_scope_warning "$evil" "/repo"$'\r'"x" > "$BATS_TEST_TMPDIR/w"
  [ "$(count '' "$BATS_TEST_TMPDIR/w")" = "1" ]
  [ "$(count '^WARNING' "$BATS_TEST_TMPDIR/w")" = "1" ]
  clean "$BATS_TEST_TMPDIR/w"
}

@test "bypass_warning names the session and directory, then the consequence" {
  run bypass_warning "demo" "/some/where"
  [ "$status" -eq 0 ]
  [ "${#lines[@]}" -eq 1 ]
  has "$output" "WARNING: --bypass turns ALL permission prompts off for 'demo' in /some/where; this LAUNCHES "

  # A dry run launches nothing, so it says what the real run does.
  run bypass_warning "demo" "/some/where" dry-run
  [ "${#lines[@]}" -eq 1 ]
  has "$output" "'demo' in /some/where; without --dry-run this LAUNCHES "
}

@test "trust_is_wider is true only for a directory below a repository root" {
  run trust_is_wider "/repo/sub/dir" "/repo"
  [ "$status" -eq 0 ]

  # The root itself is exactly what was named.
  run trust_is_wider "/repo" "/repo"
  [ "$status" -ne 0 ]

  # Outside a repository the key is the directory, so nothing is widened.
  run trust_is_wider "/loose/dir" ""
  [ "$status" -ne 0 ]
}

@test "trust_scope_warning names both the directory and the repository" {
  run trust_scope_warning "/repo/sub/dir" "/repo"
  [ "${#lines[@]}" -eq 1 ]
  has "$output" "WARNING: /repo/sub/dir is inside the repository /repo; this RECORDS trust for the whole repository"

  run trust_scope_warning "/repo/sub/dir" "/repo" dry-run
  has "$output" "/repo; without --dry-run this RECORDS trust for the whole repository"
}

# stub_setup
#
# A fixture configuration and a stand-in multiplexer that records each call
# and, unless told otherwise, reports that no session exists. With --no-verify
# the launcher's only effects are multiplexer calls, so everything up to and
# including the launch is assertable with no tmux installed and no server —
# private or otherwise — ever contacted.
#
# The stand-in appends to the same file the launcher's stderr is appended to.
# That file is the trace: one ordered record of what was said and what was
# done, which is the only way to assert that a warning came before the act it
# warns about rather than merely that both happened.
#
#   MUX_HAS_SESSION=0   has-session succeeds (a session of that name exists)
#   MUX_NEW_SESSION=<n> new-session exits with this status
#   MUX_SEND_KEYS=<n>   send-keys exits with this status
#
# For the specs that go past the launch (see stub_cli_running):
#
#   MUX_PANE_PID=<pid>     list-panes reports this as the pane's process
#   MUX_PANE=<file>        capture-pane prints this file (nothing if unset)
#   MUX_PANE_LATER=<file>  capture-pane prints this one instead, from capture
#   MUX_PANE_LATER_AT=<n>  number <n> of the run onwards (default 2)
#   MUX_PANE_ON_PASTE=<file>      ...or this one, once paste number
#   MUX_PANE_ON_PASTE_AT=<n>      <n> has been made (default 1)
#   MUX_PANE_ON_SUBMIT=<file>     ...or this one, once a paste has been
#                                 submitted with Enter
#   MUX_CAPTURE_RC=<n>     capture-pane prints the pane, then exits with this
#   MUX_ANSWER_TO=<file>   a submitted paste carrying a handshake is answered
#   MUX_ANSWER_CWD=<dir>   by appending the acknowledgement to this transcript,
#   MUX_ANSWER_POSTURE=<p> reporting this directory and posture (acceptEdits)
#   MUX_RECEIVED=<file>    every submitted paste is appended here
stub_setup() {
  CONFIG_FILE="$BATS_TEST_TMPDIR/claude.json"
  echo '{"projects":{}}' > "$CONFIG_FILE"
  TRUST_FLAG=""
  WORK="$BATS_TEST_TMPDIR/work"
  mkdir -p "$WORK"
  OUT="$BATS_TEST_TMPDIR/stdout"
  ERR="$BATS_TEST_TMPDIR/stderr"
  TRACE="$BATS_TEST_TMPDIR/trace"
  WANT="$BATS_TEST_TMPDIR/want"
  MUX_DIR="$BATS_TEST_TMPDIR/mux"
  STUB_PATH="$MUX_DIR:$PATH"
  mkdir -p "$MUX_DIR"
  cat > "$MUX_DIR/tmux" <<'STUB'
#!/usr/bin/env bash
# One call, one line: an argument may contain a newline, and a trace is only
# an order if every entry stays on a line of its own.
args="$*"
nl=$'\n'
printf 'mux: %s\n' "${args//$nl/<NL>}" >> "$TRACE"
case " $args " in
  *" has-session "*) exit "${MUX_HAS_SESSION:-1}" ;;
  *" new-session "*) exit "${MUX_NEW_SESSION:-0}" ;;
  *" send-keys "*)
    # A paste followed by Enter is a submission: the session now has the text.
    if [[ -r "$TRACE.pasted" && "${!#}" == "Enter" ]]; then
      text="$(<"$TRACE.pasted")"
      rm -f "$TRACE.pasted"
      : > "$TRACE.submitted"
      if [[ -n "${MUX_RECEIVED:-}" ]]; then
        printf '%s\n' "$text" >> "$MUX_RECEIVED"
      fi
      if [[ -n "${MUX_ANSWER_TO:-}" && "$text" == *"the token "* ]]; then
        nonce="${text##*the token }"
        nonce="${nonce%%[![:alnum:]]*}"
        printf '{"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"SPAWN-ACK %s cwd=%s posture=%s"}]}}\n' \
          "$nonce" "$MUX_ANSWER_CWD" "${MUX_ANSWER_POSTURE:-acceptEdits}" >> "$MUX_ANSWER_TO"
      fi
    fi
    exit "${MUX_SEND_KEYS:-0}" ;;
  *" list-panes "*)
    if [[ -n "${MUX_PANE_PID:-}" ]]; then
      printf '%s\n' "$MUX_PANE_PID"
    fi ;;
  *" capture-pane "*)
    # This call is already in the trace, so the count is its own number.
    n="$(grep -c '^mux: .* capture-pane ' "$TRACE")"
    pastes="$(grep -c '^mux: .* paste-buffer ' "$TRACE")"
    pane="${MUX_PANE:-}"
    if [[ -n "${MUX_PANE_LATER:-}" ]] && (( n >= ${MUX_PANE_LATER_AT:-2} )); then
      pane="$MUX_PANE_LATER"
    fi
    if [[ -n "${MUX_PANE_ON_PASTE:-}" ]] && (( pastes >= ${MUX_PANE_ON_PASTE_AT:-1} )); then
      pane="$MUX_PANE_ON_PASTE"
    fi
    if [[ -n "${MUX_PANE_ON_SUBMIT:-}" && -e "$TRACE.submitted" ]]; then
      pane="$MUX_PANE_ON_SUBMIT"
    fi
    if [[ -n "$pane" && -r "$pane" ]]; then
      printf '%s\n' "$(<"$pane")"
    fi
    exit "${MUX_CAPTURE_RC:-0}" ;;
  *" load-buffer "*)
    # The launcher deletes the file once it is loaded, so keep what it held.
    if [[ -r "${!#}" ]]; then
      printf '%s' "$(<"${!#}")" > "$TRACE.buffer"
    fi ;;
  *" paste-buffer "*)
    if [[ -r "$TRACE.buffer" ]]; then
      mv "$TRACE.buffer" "$TRACE.pasted"
    fi ;;
  *" delete-buffer "*)
    rm -f "$TRACE.buffer" ;;
esac
exit 0
STUB
  chmod +x "$MUX_DIR/tmux"
}

# stub_readers
#
# Put recording stand-ins for the two programs the launcher reads through —
# `cat` for a brief file, `python3` for the trust configuration — ahead of the
# real ones. Each notes the call in the trace and then runs the real program,
# so behaviour is unchanged and "was never opened" becomes something a spec
# can observe instead of infer.
stub_readers() {
  local tool real
  for tool in cat python3; do
    real="$(command -v "$tool")"
    cat > "$MUX_DIR/$tool" <<STUB
#!/usr/bin/env bash
printf 'read: $tool %s\n' "\$*" >> "\$TRACE"
exec "$real" "\$@"
STUB
    chmod +x "$MUX_DIR/$tool"
  done
}

# spawn_stub <args...>
#
# Runs the launcher against the stand-in. Afterwards:
#
#   $OUT    stdout, exactly as written — compared with cmp, never through a
#           variable, because a command substitution drops trailing newlines
#   $ERR    stderr alone
#   $TRACE  stderr and the stand-ins' calls, in the order they happened
spawn_stub() {
  local rc=0
  : > "$TRACE"
  rm -f "$TRACE.buffer" "$TRACE.pasted" "$TRACE.submitted"
  PATH="$STUB_PATH" TRACE="$TRACE" \
  SPAWN_CONFIG_FILE="$CONFIG_FILE" \
  SPAWN_SESSIONS_DIR="$BATS_TEST_TMPDIR/sessions" \
  SPAWN_PROJECTS_DIR="$BATS_TEST_TMPDIR/projects" \
    "$SPAWN" --socket "zzspawn-stub" "$@" > "$OUT" 2>> "$TRACE" || rc=$?
  grep -v -e '^mux: ' -e '^read: ' "$TRACE" > "$ERR" || true
  return "$rc"
}

# want <printf-format> [args...]
#
# Records the stdout a run is expected to produce, for cmp against $OUT.
want() {
  # shellcheck disable=SC2059 # the format is the recorded text
  printf "$@" > "$WANT"
}

# at <pattern>
#
# Echoes the line number of the first trace entry matching the pattern.
at() {
  grep -n -- "$1" "$TRACE" | head -1 | cut -d: -f1
}

# The launch line for a session called NAME, less the name. Written out rather
# than produced by spawn_launch_command: an expectation computed by the code
# under test agrees with it by construction.
LAUNCH_PREFIX='unset CLAUDECODE CLAUDE_CODE_CHILD_SESSION CLAUDE_CODE_SESSION_ID CLAUDE_CODE_ENTRYPOINT CLAUDE_CODE_EXECPATH CLAUDE_EFFORT; claude'

@test "a bypass launch warns once on stderr, before the session is created" {
  stub_setup
  pretrust "$WORK"

  run spawn_stub "zz-spawn-warn" --dir "$WORK" --bypass --no-verify
  [ "$status" -eq 0 ]

  [ "$(count '' "$ERR")" = "1" ]
  has "$(cat "$ERR")" "WARNING: --bypass turns ALL permission prompts off for 'zz-spawn-warn' in $WORK; this LAUNCHES "

  # Said first, done second. A warning printed after the session exists is a
  # report, and reaches a caller too late to change anything.
  local warned created typed
  warned="$(at '^WARNING: --bypass ')"
  created="$(at '^mux: .*new-session -d -s zz-spawn-warn')"
  typed="$(at '^mux: .*send-keys .*--dangerously-skip-permissions')"
  [ -n "$warned" ]
  [ -n "$created" ]
  [ -n "$typed" ]
  [ "$warned" -lt "$created" ]
  [ "$created" -lt "$typed" ]

  # On stderr only: the report on stdout is what it always was.
  want "session 'zz-spawn-warn' in %s (bypass)\n  launched (not verified)\n" "$WORK"
  cmp "$WANT" "$OUT"
}

@test "a launch without --bypass prints no warning" {
  stub_setup
  pretrust "$WORK"

  run spawn_stub "zz-spawn-plain" --dir "$WORK" --no-verify
  [ "$status" -eq 0 ]
  [ ! -s "$ERR" ]
  [ "$(count '^mux: .*send-keys .*--permission-mode acceptEdits' "$TRACE")" = "1" ]
}

@test "a dry run with --bypass prints the warning and launches nothing" {
  stub_setup
  pretrust "$WORK"

  run spawn_stub "zz-spawn-drywarn" --dir "$WORK" --bypass --dry-run
  [ "$status" -eq 0 ]

  [ "$(count '' "$ERR")" = "1" ]
  has "$(cat "$ERR")" "WARNING: --bypass turns ALL permission prompts off for 'zz-spawn-drywarn' in $WORK; without --dry-run this LAUNCHES "

  # Nothing was asked of the multiplexer at all.
  [ "$(count '^mux: ' "$TRACE")" = "0" ]
}

@test "stdout is byte for byte what it was before the warnings existed" {
  stub_setup
  local key
  key="$(fixture_key "$WORK")"

  # An untrusted preview. The line about --trust-folder is the old one, kept
  # to the byte; what actually works under --bypass is said on stderr, and the
  # launch warning is held back because the real run would refuse.
  run spawn_stub "zz-spawn-tsv" --dir "$WORK" --bypass --dry-run --porcelain
  [ "$status" -eq 0 ]
  want "would spawn 'zz-spawn-tsv' in %s\n  %s --dangerously-skip-permissions --remote-control zz-spawn-tsv\n  workspace NOT trusted (%s) — would refuse without --trust-folder\n" \
    "$WORK" "$LAUNCH_PREFIX" "$key"
  cmp "$WANT" "$OUT"
  [ "$(count '' "$ERR")" = "1" ]
  has "$(cat "$ERR")" "the real run would refuse: --trust-folder cannot be combined with --bypass. First record trust"
  lacks "$(cat "$ERR")" "this LAUNCHES"

  # A trusted preview.
  pretrust "$WORK"
  run spawn_stub "zz-spawn-tsv" --dir "$WORK" --bypass --dry-run --porcelain
  [ "$status" -eq 0 ]
  want "would spawn 'zz-spawn-tsv' in %s\n  %s --dangerously-skip-permissions --remote-control zz-spawn-tsv\n  workspace already trusted (%s)\n" \
    "$WORK" "$LAUNCH_PREFIX" "$key"
  cmp "$WANT" "$OUT"
  [ "$(count '^WARNING' "$ERR")" = "1" ]

  # An ordinary launch, as a caller parses it: key, tab, value.
  run spawn_stub "zz-spawn-tsv" --dir "$WORK" --bypass --no-verify --porcelain
  [ "$status" -eq 0 ]
  want 'name\tzz-spawn-tsv\ndirectory\t%s\nposture\tbypass\nverdict\tlaunched\npid\t\nbrief\tnone\n' "$WORK"
  cmp "$WANT" "$OUT"
  [ "$(count '^WARNING' "$ERR")" = "1" ]

  # And the same launch without --bypass, which says nothing on stderr.
  run spawn_stub "zz-spawn-tsv" --dir "$WORK" --no-verify --porcelain
  [ "$status" -eq 0 ]
  want 'name\tzz-spawn-tsv\ndirectory\t%s\nposture\tacceptEdits\nverdict\tlaunched\npid\t\nbrief\tnone\n' "$WORK"
  cmp "$WANT" "$OUT"
  [ ! -s "$ERR" ]
}

@test "--bypass with --trust-folder is refused as usage, naming the two steps" {
  stub_setup
  stub_readers
  cp "$CONFIG_FILE" "$BATS_TEST_TMPDIR/config.before"
  local brief="$BATS_TEST_TMPDIR/brief.txt"
  echo "BRIEF-TEXT" > "$brief"

  # The stand-ins do record when the launcher gets as far as reading: this
  # run, without the refused combination, opens the brief and the config.
  run spawn_stub "zz-spawn-both" --dir "$WORK" --bypass --dry-run --prompt-file "$brief"
  [ "$status" -eq 0 ]
  [ "$(count '^read: cat ' "$TRACE")" = "1" ]
  [ "$(count '^read: python3 ' "$TRACE")" = "1" ]

  local args
  for args in "--bypass --trust-folder" "--trust-folder --bypass" "-b --trust-folder --dry-run" \
              "--resume --bypass --trust-folder" "--trust-folder -b --resume --no-verify"; do
    # shellcheck disable=SC2086 # word splitting is the point: one flag per word
    run spawn_stub "zz-spawn-both" --dir "$WORK" --prompt-file "$brief" $args
    [ "$status" -eq 2 ] || { echo "'$args' exited $status"; return 1; }
    [ ! -s "$OUT" ]

    [ "$(count '' "$ERR")" = "1" ]
    local err
    err="$(cat "$ERR")"
    has "$err" "--bypass and --trust-folder cannot be combined"
    # The alternative, in order: trust without bypass, then bypass alone.
    has "$err" "First record trust: run once with --trust-folder and without --bypass"
    has "$err" "Then run again with --bypass and without --trust-folder."
    # A refusal launches nothing, so it must not announce a launch.
    lacks "$err" "this LAUNCHES"

    # Refused before anything was looked at: the brief was not read, the
    # trust configuration was not opened, the multiplexer was not asked
    # whether the session exists.
    [ "$(count '^read: ' "$TRACE")" = "0" ] || { cat "$TRACE"; return 1; }
    [ "$(count '^mux: ' "$TRACE")" = "0" ] || { cat "$TRACE"; return 1; }
  done

  cmp "$BATS_TEST_TMPDIR/config.before" "$CONFIG_FILE"
  [ ! -e "$CONFIG_FILE.lock" ]
}

@test "--help wins over the refused combination and exits 0" {
  stub_setup

  # Asking how to use the command is never an attempt to use it. --help is
  # acted on where it is read, so it answers whatever else is on the line.
  run spawn_stub "zz-spawn-help" --bypass --trust-folder --help
  [ "$status" -eq 0 ]
  has "$(cat "$OUT")" "usage: spawn-session.sh <name> [options]"
  # Every exit code a caller can receive is in the summary.
  local code
  for code in "0 reachable" "2 usage or refusal" "3 alive but unreachable" "4 never started" "5 running but unconfirmed"; do
    has "$(cat "$OUT")" "$code"
  done
  [ ! -s "$ERR" ]
  [ "$(count '^mux: ' "$TRACE")" = "0" ]
}

@test "an untrusted workspace under --bypass is refused with the two steps" {
  stub_setup

  run spawn_stub "zz-spawn-untrusted" --dir "$WORK" --bypass --no-verify
  [ "$status" -eq 2 ]
  [ ! -s "$OUT" ]

  [ "$(count '' "$ERR")" = "1" ]
  local err
  err="$(cat "$ERR")"
  has "$err" "not a trusted workspace"
  # Not the usual "re-run with --trust-folder": that combination is refused,
  # so the advice has to be the one that works.
  has "$err" "First record trust: run once with --trust-folder and without --bypass"
  has "$err" "Then run again with --bypass and without --trust-folder."
  lacks "$err" "this LAUNCHES"
  [ "$(count '^mux: .*new-session' "$TRACE")" = "0" ]
}

# without_python
#
# Narrow PATH to the stand-in multiplexer and the few programs the launcher
# needs before it launches, leaving python3 out. What is under test is the
# launcher's behaviour when the trust check cannot run, and the only honest
# way to produce that is for the interpreter not to be found.
without_python() {
  local bin="$BATS_TEST_TMPDIR/nopython" tool
  mkdir -p "$bin"
  for tool in bash dirname readlink; do
    ln -s "$(command -v "$tool")" "$bin/$tool"
  done
  STUB_PATH="$MUX_DIR:$bin"
}

@test "a bypass launch is refused when workspace trust cannot be checked" {
  stub_setup
  without_python

  # Fail closed: unchecked is not trusted, and this is the launch that must
  # not go ahead on the strength of nobody having looked.
  run spawn_stub "zz-spawn-nopy" --dir "$WORK" --bypass --no-verify
  [ "$status" -eq 2 ] || { cat "$TRACE"; return 1; }
  [ ! -s "$OUT" ]
  [ "$(count '' "$ERR")" = "1" ]
  has "$(cat "$ERR")" "workspace trust for $WORK cannot be checked: the check needs python3, which was not found."
  has "$(cat "$ERR")" "launch without --bypass"
  lacks "$(cat "$ERR")" "this LAUNCHES"
  [ "$(count '^mux: .*new-session' "$TRACE")" = "0" ]

  # The preview says the same, and announces no launch.
  run spawn_stub "zz-spawn-nopy" --dir "$WORK" --bypass --dry-run
  [ "$status" -eq 0 ]
  want "would spawn 'zz-spawn-nopy' in %s\n  %s --dangerously-skip-permissions --remote-control zz-spawn-nopy\n" "$WORK" "$LAUNCH_PREFIX"
  cmp "$WANT" "$OUT"
  [ "$(count '' "$ERR")" = "1" ]
  has "$(cat "$ERR")" "the real run would refuse: workspace trust cannot be checked without python3"
  lacks "$(cat "$ERR")" "this LAUNCHES"

  # Any other posture launches as it always has: it stops at the trust
  # prompt if there is one, and is diagnosed there.
  run spawn_stub "zz-spawn-nopy" --dir "$WORK" --no-verify
  [ "$status" -eq 0 ] || { cat "$TRACE"; return 1; }
  [ ! -s "$ERR" ]
  [ "$(count '^mux: .*new-session -d -s zz-spawn-nopy' "$TRACE")" = "1" ]
}

@test "resuming an existing bypass session needs no trust check" {
  stub_setup
  without_python

  # Nothing is launched on this path, so there is no launch to refuse: with
  # the interpreter missing it must behave exactly as it did before the
  # fail-closed check was added for new launches.
  MUX_HAS_SESSION=0 run spawn_stub "zz-spawn-nopy" --dir "$WORK" --resume --bypass --no-verify --porcelain
  [ "$status" -eq 0 ] || { cat "$TRACE"; return 1; }
  [ -s "$OUT" ]
  [ ! -s "$ERR" ]
  [ "$(count '^mux: .*new-session' "$TRACE")" = "0" ]

  # The preview does not claim the real run would refuse.
  run spawn_stub "zz-spawn-nopy" --dir "$WORK" --resume --bypass --dry-run
  [ "$status" -eq 0 ]
  lacks "$(cat "$ERR")" "would refuse"
  has "$(cat "$ERR")" "with --resume nothing is launched"
}

@test "a session whose launch command cannot be sent is reported as empty" {
  stub_setup
  pretrust "$WORK"

  MUX_SEND_KEYS=19 run spawn_stub "zz-spawn-nosend" --dir "$WORK" --bypass --no-verify
  # The multiplexer's own status, with the last word on stderr saying what
  # actually happened rather than leaving the launch warning standing.
  [ "$status" -eq 19 ]
  [ ! -s "$OUT" ]
  local warned explained
  warned="$(at '^WARNING: --bypass ')"
  explained="$(at "session 'zz-spawn-nosend' was created, but the command that starts the CLI could not be sent")"
  [ -n "$warned" ]
  [ -n "$explained" ]
  [ "$warned" -lt "$explained" ]
}

@test "a launch the multiplexer refuses says nothing was launched" {
  stub_setup
  pretrust "$WORK"

  MUX_NEW_SESSION=1 run spawn_stub "zz-spawn-fail" --dir "$WORK" --bypass --no-verify
  # The multiplexer's own status, as before.
  [ "$status" -eq 1 ]
  [ ! -s "$OUT" ]

  # The warning is true when it is printed; when the launch then fails, the
  # last line on stderr takes it back rather than leaving it standing.
  local warned tried retracted
  warned="$(at '^WARNING: --bypass ')"
  tried="$(at '^mux: .*new-session')"
  retracted="$(at "could not create session 'zz-spawn-fail'; nothing was launched")"
  [ -n "$warned" ]
  [ -n "$tried" ]
  [ -n "$retracted" ]
  [ "$warned" -lt "$tried" ]
  [ "$tried" -lt "$retracted" ]
  [ "$(count '^mux: .*send-keys' "$TRACE")" = "0" ]
}

@test "--resume with --bypass announces no launch, in a preview or for real" {
  stub_setup
  pretrust "$WORK"

  # The preview keeps its old stdout, which says "would spawn" whatever was
  # asked; stderr says what the real run does.
  run spawn_stub "zz-spawn-res" --dir "$WORK" --resume --bypass --dry-run
  [ "$status" -eq 0 ]
  want "would spawn 'zz-spawn-res' in %s\n  %s --dangerously-skip-permissions --remote-control zz-spawn-res\n  workspace already trusted (%s)\n" \
    "$WORK" "$LAUNCH_PREFIX" "$(fixture_key "$WORK")"
  cmp "$WANT" "$OUT"
  [ "$(count '' "$ERR")" = "1" ]
  has "$(cat "$ERR")" "with --resume nothing is launched"
  lacks "$(cat "$ERR")" "WARNING"

  # For real, against a session that exists: nothing is created, so nothing
  # is warned about.
  MUX_HAS_SESSION=0 run spawn_stub "zz-spawn-res" --dir "$WORK" --resume --bypass --no-verify
  [ "$status" -eq 0 ]
  [ ! -s "$ERR" ]
  [ "$(count '^mux: .*new-session' "$TRACE")" = "0" ]
  [ "$(count '^mux: .*send-keys' "$TRACE")" = "0" ]
}

@test "control bytes in a directory or session name never reach stderr raw" {
  stub_setup
  # A directory whose name carries a line that looks like a warning of its
  # own, and one carrying an escape sequence that erases the line it is on.
  local forged="$BATS_TEST_TMPDIR/evil"$'\n'"WARNING: fixture line; this LAUNCHES nothing"
  local erasing="$BATS_TEST_TMPDIR/esc"$'\033'"[2K"$'\r'"x"
  mkdir -p "$forged" "$erasing"

  # A directory with a control character in its path is refused outright (it
  # used to launch, and be quoted in the warning). The refusal quotes it, so
  # what this spec is about holds for the line that is printed now.
  local dir
  for dir in "$forged" "$erasing"; do
    # Refused, untrusted: the directory is quoted in the refusal.
    run spawn_stub "zz-spawn-ctl" --dir "$dir" --bypass --no-verify
    [ "$status" -eq 2 ]
    [ "$(count '' "$ERR")" = "1" ]
    [ "$(count '^WARNING' "$ERR")" = "0" ]
    clean "$ERR"

    # Refused with trust on record too: nothing is launched, so no launch is
    # announced, and the one line on stderr is still the refusal.
    pretrust "$dir"
    run spawn_stub "zz-spawn-ctl" --dir "$dir" --bypass --no-verify
    [ "$status" -eq 2 ]
    [ "$(count '' "$ERR")" = "1" ]
    [ "$(count '^WARNING' "$ERR")" = "0" ]
    clean "$ERR"
    [ "$(count '^mux: ' "$TRACE")" = "0" ]

    run spawn_stub "zz-spawn-ctl" --dir "$dir" --bypass --dry-run
    [ "$status" -eq 2 ]
    [ "$(count '' "$ERR")" = "1" ]
    [ "$(count '^WARNING' "$ERR")" = "0" ]
    clean "$ERR"
  done

  # The rendering is visible, not a deletion: the reader can see what was there.
  run spawn_stub "zz-spawn-ctl" --dir "$forged" --bypass --dry-run
  has "$(cat "$ERR")" "evil\\nWARNING: fixture line; this LAUNCHES nothing'. Refused"
  lacks "$(cat "$ERR")" "this LAUNCHES a session"
  run spawn_stub "zz-spawn-ctl" --dir "$erasing" --bypass --dry-run
  has "$(cat "$ERR")" "esc\\x1b[2K\\rx'. Refused"

  # A session name is refused before it is used, and the refusal quotes it.
  local name
  for name in "zz"$'\033'"[31mred" "zz"$'\n'"WARNING: fixture line"; do
    run spawn_stub "$name" --dir "$WORK" --bypass --no-verify
    [ "$status" -eq 2 ]
    [ "$(count '' "$ERR")" = "1" ]
    [ "$(count '^WARNING' "$ERR")" = "0" ]
    has "$(cat "$ERR")" "is not a usable session name"
    clean "$ERR"
  done
}

@test "a directory named with control bytes inside a repository gets one refusal line and no trust" {
  # This spec used to pin the scope warning staying on one line for such a
  # directory. The directory is refused now, before the warning is reached, so
  # what is pinned is the line that replaced it: one line, nothing raw, and
  # no trust recorded for the repository around it. The warning's own
  # rendering is covered by "a warning stays one line whatever its fields
  # contain".
  stub_setup
  local repo="$BATS_TEST_TMPDIR/repo"
  git init -q "$repo"
  local sub="$repo/sub"$'\n'"WARNING: fixture line"$'\033'"[1A"
  mkdir -p "$sub"
  cp "$CONFIG_FILE" "$BATS_TEST_TMPDIR/config.before"

  run spawn_stub "zz-spawn-scopectl" --dir "$sub" --trust-folder --dry-run
  [ "$status" -eq 2 ]
  [ "$(count '' "$ERR")" = "1" ]
  [ "$(count '^WARNING' "$ERR")" = "0" ]
  clean "$ERR"

  run spawn_stub "zz-spawn-scopectl" --dir "$sub" --trust-folder --no-verify
  [ "$status" -eq 2 ]
  [ "$(count '' "$ERR")" = "1" ]
  [ "$(count '^WARNING' "$ERR")" = "0" ]
  clean "$ERR"
  [ "$(count '^mux: ' "$TRACE")" = "0" ]
  cmp "$BATS_TEST_TMPDIR/config.before" "$CONFIG_FILE"
}

@test "--trust-folder inside a repository warns that the whole repository is trusted" {
  stub_setup
  local repo="$BATS_TEST_TMPDIR/repo"
  git init -q "$repo"
  mkdir -p "$repo/sub/dir"
  local root
  root="$(cd "$repo" && pwd -P)"

  # The dry run says it and writes nothing.
  cp "$CONFIG_FILE" "$BATS_TEST_TMPDIR/config.before"
  run spawn_stub "zz-spawn-scope" --dir "$repo/sub/dir" --trust-folder --dry-run
  [ "$status" -eq 0 ]
  [ "$(count '' "$ERR")" = "1" ]
  has "$(cat "$ERR")" "WARNING: $repo/sub/dir is inside the repository $root; without --dry-run this RECORDS trust for the whole repository"
  lacks "$(cat "$OUT")" "WARNING"
  cmp "$BATS_TEST_TMPDIR/config.before" "$CONFIG_FILE"

  # The real run says it before it writes, then records exactly the key it
  # named.
  stub_readers
  run spawn_stub "zz-spawn-scope" --dir "$repo/sub/dir" --trust-folder --no-verify
  [ "$status" -eq 0 ]
  [ "$(count '' "$ERR")" = "1" ]
  has "$(cat "$ERR")" "WARNING: $repo/sub/dir is inside the repository $root; this RECORDS trust for the whole repository"
  lacks "$(cat "$OUT")" "WARNING"
  local warned granted
  warned="$(at '^WARNING: ')"
  granted="$(at '^read: python3 .* grant ')"
  [ -n "$warned" ]
  [ -n "$granted" ]
  [ "$warned" -lt "$granted" ]
  python3 "$SKILL_DIR/scripts/lib/trust-config.py" check "$CONFIG_FILE" "$root"
}

@test "--trust-folder at a repository root prints no scope warning" {
  stub_setup
  local repo="$BATS_TEST_TMPDIR/repo"
  git init -q "$repo"

  run spawn_stub "zz-spawn-root" --dir "$repo" --trust-folder --dry-run
  [ "$status" -eq 0 ]
  [ ! -s "$ERR" ]

  # Reached through a symbolic link the named path and the reported root
  # differ as text while being one directory; that is not a wider grant.
  ln -s "$repo" "$BATS_TEST_TMPDIR/link"
  run spawn_stub "zz-spawn-root" --dir "$BATS_TEST_TMPDIR/link" --trust-folder --dry-run
  [ "$status" -eq 0 ]
  [ ! -s "$ERR" ]
}

@test "the trust dialog's remedy is one that works for a session that exists" {
  # Re-running under the same name is refused as already running, so advice
  # to "re-run with --trust-folder" sends the reader into a second refusal.
  run blocker_for "$(blocker_table)" "  Yes, I trust this folder"
  [ "$status" -eq 0 ]
  has "$output" "accept the prompt"
  has "$output" "--resume"
  # And it must not suggest the combination that is refused.
  has "$output" "never together with --bypass"
}

# ── looking before sending ──────────────────────────────────────────────────
#
# The handshake is input. It is pasted and submitted, so it must not be sent
# until the pane shows the input box, and never to a pane showing a startup
# dialog. These specs go past the launch with no multiplexer installed: the
# stand-in reports a pane with a CLI process in it and shows whatever the spec
# puts in $PANE.

FIXTURES="$BATS_TEST_DIRNAME/fixtures/spawn-session"

@test "has_control finds a control character anywhere, including at the end" {
  local bad
  for bad in "repo"$'\n' $'\n'"repo" "re"$'\n'"po" "re"$'\t'"po" "re"$'\r'"po" \
             "re"$'\033'"[2Kpo" "re"$'\001'"po" "re"$'\177'"po" "re"$'\302\233'"po"; do
    run has_control "$bad"
    [ "$status" -eq 0 ] || { echo "missed: $(visible "$bad")"; return 1; }
  done

  # Ordinary names, including multi-byte ones and a literal backslash-n, are
  # not control characters. The dash and the e-acute both carry a byte in the
  # range the second control block uses, as a continuation byte.
  local ok
  for ok in "" "/some/where" "/with spaces/and-dash_1" "/é—ü/日本" 'back\nslash' "a'b\"c"; do
    run has_control "$ok"
    [ "$status" -ne 0 ] || { echo "flagged: $ok"; return 1; }
  done
}

# utf8_locale
#
# Echoes the name of a UTF-8 locale this machine has.
utf8_locale() {
  local name
  for name in en_US.UTF-8 C.UTF-8 C.utf8 en_US.utf8; do
    if locale -a 2>/dev/null | grep -qx "$name"; then
      echo "$name"
      return 0
    fi
  done
  echo "no UTF-8 locale found" >&2
  return 1
}

@test "bytes that are not UTF-8 are refused and rendered, whatever the locale" {
  # A lone byte from 0x80 to 0x9f is the second control block as an 8-bit
  # terminal reads it: 0x9b opens a control sequence. It is not the UTF-8
  # encoding of anything, so no rule about characters catches it, and the
  # answer must not turn on the locale the caller happens to have.
  local probe='
source "$1"
for code in 128 129 130 131 132 133 134 135 136 137 138 139 140 141 142 143 \
            144 145 146 147 148 149 150 151 152 153 154 155 156 157 158 159 \
            192 193 245 255; do
  printf -v oct "%03o" "$code"
  printf -v byte "%b" "\\0$oct"
  printf -v hex "%02x" "$code"
  for text in "a${byte}b" "${byte}" "tail${byte}"; do
    has_control "$text" || { echo "not refused: 0x$hex"; exit 1; }
    shown="$(visible "$text")"
    want="${text//"$byte"/\\x$hex}"
    [ "$shown" = "$want" ] || { echo "0x$hex rendered as: $shown"; exit 1; }
  done
done

# Forms a decoder must not accept: a sequence cut short, an overlong one that
# would decode to U+009B, a surrogate, and something past U+10FFFF.
for text in "$2" "$3" "$4" "$5"; do
  has_control "$text" || { echo "not refused: $(visible "$text")"; exit 1; }
  case "$(visible "$text")" in *\\x*) ;; *) echo "not rendered"; exit 1 ;; esac
done

# Well-formed names keep working and are printed as they are. Each of these
# has bytes in the 0x80 to 0x9f range inside a valid sequence.
for text in "é" "ł" "日本" "😀" "a—b" "/tmp/é/ł/日本/😀"; do
  if has_control "$text"; then echo "flagged: $text"; exit 1; fi
  [ "$(visible "$text")" = "$text" ] || { echo "changed: $text"; exit 1; }
done
'
  local utf8 cut overlong surrogate beyond
  utf8="$(utf8_locale)"
  cut="tr"$'\346\227'
  overlong="a"$'\340\202\233'"b"
  surrogate=$'\355\240\200'
  beyond=$'\364\220\200\200'

  run env LC_ALL=C bash -c "$probe" _ "$LIB" "$cut" "$overlong" "$surrogate" "$beyond"
  [ "$status" -eq 0 ] || { echo "LC_ALL=C: $output"; return 1; }

  run env LC_ALL="$utf8" bash -c "$probe" _ "$LIB" "$cut" "$overlong" "$surrogate" "$beyond"
  [ "$status" -eq 0 ] || { echo "LC_ALL=$utf8: $output"; return 1; }

  run env -u LC_ALL -u LC_CTYPE -u LANG bash -c "$probe" _ "$LIB" "$cut" "$overlong" "$surrogate" "$beyond"
  [ "$status" -eq 0 ] || { echo "no locale set: $output"; return 1; }
}

@test "exact keeps the trailing newlines a command substitution would drop" {
  source_driver

  exact printf 'repo\n'
  [ "$EXACT" = "repo" ]

  # The directory named `repo` plus a newline: the line printed for it ends in
  # two. A bare substitution returns `repo`, which is its sibling.
  exact printf 'repo\n\n'
  [ "$EXACT" = "repo"$'\n' ]
  [ "$(printf 'repo\n\n')" = "repo" ]

  exact printf ''
  [ -z "$EXACT" ]

  # A command that fails leaves nothing behind to be mistaken for a path.
  EXACT="stale"
  if exact false; then
    echo "exact reported success for a command that failed"
    return 1
  fi
  [ -z "$EXACT" ]
}

ready_table() {
  cat "$SKILL_DIR/scripts/ready-prompts.tsv"
}

# verdict <pane-text>
#
# Echoes the first word of what pane_verdict makes of the pane, with the real
# tables.
verdict() {
  local out
  out="$(pane_verdict "$(blocker_table)" "$(ready_table)" "$1")"
  printf '%s\n' "${out%%$'\t'*}"
}

BOX="────────────────
❯ 
────────────────"
STATUS="  ⏵⏵ accept edits on (shift+tab to cycle)"
TRUST_DIALOG="Accessing workspace:
  /some/path
Quick safety check: Is this a project you created or one you trust?
❯ 1. Yes, I trust this folder
  2. No, exit"

@test "a status line matches its row whole or cut short, and nothing else does" {
  local row="⏵⏵ accept edits on"

  # Whole, with whatever the CLI puts after it.
  run status_matches "$row" "⏵⏵ accept edits on (shift+tab to cycle) · ← for agents"
  [ "$status" -eq 0 ]
  run status_matches "$row" "⏵⏵ accept edits on"
  [ "$status" -eq 0 ]

  # Cut short by a narrow pane, as the real CLI draws it at 20, 16 and 12
  # columns, and with the ellipsis a cut can leave.
  local cut
  for cut in "⏵⏵ accept edits" "⏵⏵ accept  ·" "⏵⏵" "⏵⏵ accept edi…"; do
    run status_matches "$row" "$cut"
    [ "$status" -eq 0 ] || { echo "did not match the cut line: $cut"; return 1; }
  done

  # Not this row: another mode, the wording without its symbol, the wording
  # further along a line, less than the symbol, and nothing.
  local other
  for other in "⏸ plan mode on" "accept edits on" "❯ 1. accept edits on" \
               "Color theme dialog: accept edits on" "⏵" "⏵⏵ accept all" ""; do
    run status_matches "$row" "$other"
    [ "$status" -ne 0 ] || { echo "matched: $other"; return 1; }
  done

  # Each posture this tool launches has a row, and the table says how each
  # row is known.
  run status_row_for "$(ready_table)" "⏵⏵ accept edits on (shift+tab to cycle)"
  [ "$output" = "accept-edits" ]
  run status_row_for "$(ready_table)" "⏵⏵ bypass permissions on (shift+tab to cycle)"
  [ "$output" = "bypass" ]
  run status_row_for "$(ready_table)" "⏸ manual mode on · ? for shortcuts · ← for agents"
  [ "$output" = "manual" ]
  run ready_row_basis "$(ready_table)" accept-edits
  [ "$output" = "seen" ]
  run ready_row_basis "$(ready_table)" bypass
  [ "$output" = "inferred" ]

  # Prose from the table's own header is not a row.
  run status_row_for "$(ready_table)" "Columns, tab-separated:"
  [ "$status" -ne 0 ]
  [ -z "$output" ]

  # Literal, like the dialog table: a question mark is a question mark.
  run status_row_for "id	a?c	seen" "abc"
  [ "$status" -ne 0 ]
  run status_row_for "id	a?c	seen" "a?c and more"
  [ "$output" = "id" ]
}

@test "pane_verdict permits input only when the input box is at the foot of the pane" {
  # The box with its status line under it, and nothing after.
  run pane_verdict "$(blocker_table)" "$(ready_table)" "$BOX
$STATUS"
  [ "$output" = "ready	accept-edits" ]

  # Whatever is typed in the box, on one line or several, it is still the box.
  [ "$(verdict "────────────────
❯ [Pasted text #1 +10 lines]
────────────────
$STATUS")" = "ready" ]
  [ "$(verdict "────────────────
❯ first line of a draft
  second line of it
────────────────
$STATUS")" = "ready" ]

  # A dialog, and no box.
  run pane_verdict "$(blocker_table)" "$(ready_table)" "$TRUST_DIALOG"
  [[ "$output" == "blocked	trust	"* ]]

  # Nothing recognised is not readiness: an empty pane, and a dialog the
  # table has no row for.
  [ "$(verdict "")" = "waiting" ]
  [ "$(verdict "A dialog nobody has listed yet
❯ 1. Yes, proceed
  2. No, exit")" = "waiting" ]

  # The wording of a status line is not the box. A dialog can offer it as an
  # option, a shell can echo it, and a busy screen can show it with no box.
  [ "$(verdict "Select a color theme
❯ 1. accept edits on
  2. Continue")" = "waiting" ]
  [ "$(verdict "\$ printf '%s' 'accept edits on'; claude --permission-mode acceptEdits")" = "waiting" ]
  [ "$(verdict "Color theme dialog: accept edits on")" = "waiting" ]
  [ "$(verdict "Running the previous turn…
$STATUS")" = "waiting" ]

  # The pane shows the typed launch command before the CLI draws anything.
  local posture line
  for posture in "" "bypass"; do
    line="$(spawn_launch_command "zz-spawn-demo" "$posture" 'export PATH=/some/bin:$PATH')"
    [ "$(verdict "\$ $line")" = "waiting" ]
  done

  # A box is not enough without a status line under it, and two rules with
  # something other than the prompt glyph between them are not a box.
  [ "$(verdict "$BOX")" = "waiting" ]
  [ "$(verdict "────────────────
Some heading
────────────────
$STATUS")" = "waiting" ]
  [ "$(verdict "$BOX
  some line that is not a status line")" = "waiting" ]

  # The box has to be the last thing on the pane. A box that was never
  # cleared, with something else drawn after it, is not where input goes.
  [ "$(verdict "$BOX
$STATUS
A dialog nobody has listed yet
with several lines of explanation
and more of it
and more
and more still
  1. Yes, proceed")" = "waiting" ]

  # With no ready table there is nothing to find, so nothing is ever ready.
  run pane_verdict "$(blocker_table)" "" "$BOX
$STATUS"
  [ "$output" = "waiting" ]
}

@test "dialog wording counts by where it is, not by being on the pane" {
  # Earlier output that quotes a dialog is above the box, or is prose on a
  # line of its own under it. The box is what is showing: ready.
  [ "$(verdict "Earlier output: the menu option is Yes, I trust this folder
$BOX
$STATUS")" = "ready" ]
  [ "$(verdict "$BOX
$STATUS
Earlier output: the menu option is Yes, I trust this folder")" = "ready" ]

  # A dialog drawn under a box that was never cleared is the dialog's screen.
  # Its options are options: focused, numbered, or bare.
  local out
  out="$(pane_verdict "$(blocker_table)" "$(ready_table)" "$BOX
$STATUS
Dialog
❯ Yes, I trust this folder")"
  [[ "$out" == "blocked	trust	"* ]]
  out="$(pane_verdict "$(blocker_table)" "$(ready_table)" "$BOX
$STATUS
  2. Yes, I trust this folder")"
  [[ "$out" == "blocked	trust	"* ]]
  [ "$(verdict "$BOX
$STATUS
  Yes, I accept")" = "blocked" ]

  # A focused option of a dialog nobody has listed is still not a status
  # line: not ready, and not a diagnosis either.
  [ "$(verdict "$BOX
$STATUS
❯ 1. Yes, proceed")" = "waiting" ]

  # Above a box, dialog wording is earlier output whichever way the verdict
  # goes: a box with a status line nobody has listed is unknown, not blocked.
  [ "$(verdict "Earlier output: Yes, I trust this folder
$BOX
  some line that is not a status line")" = "waiting" ]

  # Every row of the dialog table blocks when it is what the pane shows, and
  # when it is drawn as an option under a stale box.
  local line id pattern rest
  while IFS= read -r line; do
    [[ -z "$line" || "$line" == '#'* ]] && continue
    IFS=$'\t' read -r id pattern rest <<< "$line"
    out="$(pane_verdict "$(blocker_table)" "$(ready_table)" "Dialog
❯ $pattern")"
    [[ "$out" == "blocked	$id	"* ]] || { echo "$id alone: $out"; return 1; }
    out="$(pane_verdict "$(blocker_table)" "$(ready_table)" "$BOX
$STATUS
Dialog
❯ $pattern")"
    [[ "$out" == "blocked	$id	"* ]] || { echo "$id under a box: $out"; return 1; }
  done < "$SKILL_DIR/scripts/startup-blockers.tsv"
}

@test "the real CLI's input box reads as ready at every pane width" {
  # What tmux captured from the real CLI, from 100 columns down to 12. Below
  # 25 the status line is cut short, and at 12 only its symbol is left.
  local width out
  for width in 100 40 25 20 16 12; do
    [ -r "$FIXTURES/pane-accept-edits-$width.txt" ]
    out="$(pane_verdict "$(blocker_table)" "$(ready_table)" "$(cat "$FIXTURES/pane-accept-edits-$width.txt")")"
    [ "$out" = "ready	accept-edits" ] || { echo "at $width columns: $out"; return 1; }
  done
}

# stub_cli_running [bridge-json]
#
# Make the stand-in report a session with a CLI process in it: a pane process,
# a child of it whose arguments carry the remote-control flag, and that
# child's state file and transcript where the launcher looks for them. The
# process table is stood in for as well, so no process is started.
#
#   $PANE        what the pane shows; a spec writes it (pane_* below)
#   $TRANSCRIPT  the session's transcript
#   $RECEIVED    every paste the session was sent and had submitted
stub_cli_running() {
  local bridge="${1:-\"session_stub\"}"
  local sid="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

  printf '%s\n' '#!/usr/bin/env bash' 'echo 4343' > "$MUX_DIR/pgrep"
  printf '%s\n' '#!/usr/bin/env bash' \
    'echo "claude --permission-mode acceptEdits --remote-control zz-spawn"' > "$MUX_DIR/ps"
  chmod +x "$MUX_DIR/pgrep" "$MUX_DIR/ps"

  mkdir -p "$BATS_TEST_TMPDIR/sessions" "$BATS_TEST_TMPDIR/projects/encoded-dir"
  printf '{"pid":4343,"sessionId":"%s","bridgeSessionId":%s}\n' "$sid" "$bridge" \
    > "$BATS_TEST_TMPDIR/sessions/4343.json"
  TRANSCRIPT="$BATS_TEST_TMPDIR/projects/encoded-dir/$sid.jsonl"
  : > "$TRANSCRIPT"

  PANE="$BATS_TEST_TMPDIR/pane"
  RECEIVED="$BATS_TEST_TMPDIR/received"
  : > "$RECEIVED"
  export MUX_PANE_PID=4242 MUX_PANE="$PANE" MUX_RECEIVED="$RECEIVED"
  # A version is always given, so no spec asks the installed CLI for its own.
  # This is the one the dialog patterns are pinned to; a spec that wants a
  # different answer sets SPAWN_CLI_VERSION on its own run.
  SPAWN_CLI_VERSION="$(cli_version_in_driver PINNED_CLI_VERSION)"
  export SPAWN_CLI_VERSION
}

# cli_version_in_driver <variable>
#
# Echoes a CLI version the launcher records for itself.
cli_version_in_driver() {
  sed -n "s/^$1=\"\(.*\)\"\$/\1/p" "$SPAWN"
}

pane_dialog() {
  printf '%s\n' "Accessing workspace:" "" "  /some/path" "" \
    "Quick safety check: Is this a project you created or one you trust?" "" \
    "❯ 1. Yes, I trust this folder" "  2. No, exit" > "${1:-$PANE}"
}

pane_prompt() {
  printf '%s\n' "$BOX" "$STATUS" > "${1:-$PANE}"
}

pane_starting() {
  printf '%s\n' "\$ $LAUNCH_PREFIX --permission-mode acceptEdits --remote-control zz-spawn" > "${1:-$PANE}"
}

# sent <verb>
#
# Echoes how many times the launcher asked the multiplexer to do this.
sent() {
  count "^mux: .* $1 " "$TRACE"
}

# submitted
#
# Echoes how many times the launcher pressed Enter on its own: a send-keys
# carrying nothing else. The launch command is typed with its Enter in one
# call and is not counted.
submitted() {
  count '^mux: .* send-keys -t =[^ ]*: Enter$' "$TRACE"
}

# looked_before_every <pattern>
#
# Fails unless each multiplexer call matching the pattern comes straight
# after a look at the pane, with no other call between the two.
looked_before_every() {
  awk -v pat="$1" '
    /^mux: / {
      if ($0 ~ pat) { seen = 1; if (prev !~ / capture-pane /) { print "no look before: " $0; bad = 1 } }
      prev = $0
    }
    END { if (!seen) { print "nothing matched " pat; bad = 1 } exit bad }' "$TRACE"
}

@test "a pane showing a startup dialog receives no input before it is diagnosed" {
  stub_setup
  pretrust "$WORK"
  stub_cli_running
  pane_dialog

  SPAWN_INSPECT_AFTER=1 run spawn_stub "zz-spawn-held" --dir "$WORK" --timeout 2
  [ "$status" -eq 4 ] || { cat "$TRACE"; return 1; }

  # It looked, and having looked it sent nothing: no buffer loaded, nothing
  # pasted, nothing submitted.
  [ "$(sent capture-pane)" -ge 1 ]
  [ "$(sent load-buffer)" = "0" ] || { echo "input was sent to a pane showing a dialog:"; cat "$TRACE"; return 1; }
  [ "$(sent paste-buffer)" = "0" ]
  [ ! -s "$RECEIVED" ]
  has "$(cat "$OUT")" "blocked  trust"
  has "$(cat "$OUT")" "nothing was sent to it"
  lacks "$(cat "$OUT")" "differs from"
  # At the inspection mark it says what it sees, and goes on waiting.
  [ "$(count '' "$ERR")" = "1" ]
  has "$(cat "$ERR")" "'zz-spawn-held' is held at a startup dialog (trust); still waiting"
  # The one send-keys is the launch command, typed into the new shell before
  # there was a CLI to show anything.
  [ "$(sent send-keys)" = "1" ] || { cat "$TRACE"; return 1; }
  [ "$(count '^mux: .* send-keys .*--remote-control zz-spawn-held Enter$' "$TRACE")" = "1" ]
  [ "$(at ' send-keys ')" -lt "$(at ' capture-pane ')" ]

  # Picking up a session that is already at the dialog types nothing at all,
  # and the brief stays undelivered.
  MUX_HAS_SESSION=0 run spawn_stub "zz-spawn-held" --dir "$WORK" --timeout 2 --resume --prompt "BRIEF-TEXT"
  [ "$status" -eq 4 ] || { cat "$TRACE"; return 1; }
  [ "$(sent load-buffer)" = "0" ] || { cat "$TRACE"; return 1; }
  [ "$(sent paste-buffer)" = "0" ]
  [ "$(sent send-keys)" = "0" ]
  [ ! -s "$RECEIVED" ]
  lacks "$(cat "$OUT")" "brief    delivered"

  # A caller reading pairs can tell that nothing was sent.
  MUX_HAS_SESSION=0 run spawn_stub "zz-spawn-held" --dir "$WORK" --timeout 1 --resume --porcelain
  [ "$status" -eq 4 ]
  has "$(cat "$OUT")" $'verdict\tblocked'
  has "$(cat "$OUT")" $'handshake\tnot_sent'
}

@test "a pane that never shows the prompt gets no handshake and is reported, not pasted into" {
  stub_setup
  pretrust "$WORK"
  stub_cli_running
  # A shell that has echoed the launch command and drawn nothing since.
  pane_starting

  SPAWN_CLI_VERSION="$(cli_version_in_driver READY_CLI_VERSION)" SPAWN_INSPECT_AFTER=1 \
    run spawn_stub "zz-spawn-slow" --dir "$WORK" --timeout 2
  # Running, and nothing known about it: not failed.
  [ "$status" -eq 5 ] || { cat "$TRACE"; return 1; }
  [ "$(sent load-buffer)" = "0" ] || { echo "input was sent to a pane that never showed the prompt:"; cat "$TRACE"; return 1; }
  [ "$(sent paste-buffer)" = "0" ]
  [ "$(sent send-keys)" = "1" ]
  [ ! -s "$RECEIVED" ]
  [ "$(sent capture-pane)" -ge 2 ]
  has "$(cat "$OUT")" "the input prompt never appeared"
  has "$(cat "$OUT")" "handshake was not sent"
  has "$(cat "$OUT")" "nothing was sent to it"
  has "$(cat "$OUT")" "--resume"
  has "$(cat "$OUT")" "ready-prompts.tsv"
  lacks "$(cat "$OUT")" "differs from"
  [ "$(count '' "$ERR")" = "1" ]
  has "$(cat "$ERR")" "'zz-spawn-slow' has not shown its input prompt after 1s, and no known dialog; nothing has been sent to it; still waiting"

  # The same for a pane that shows nothing at all, as pairs. On a CLI other
  # than the one the prompt patterns come from, the report says the wording
  # may have moved.
  rm -f "$PANE"
  SPAWN_CLI_VERSION="9.9.9" MUX_HAS_SESSION=0 run spawn_stub "zz-spawn-slow" --dir "$WORK" --timeout 1 --resume --porcelain
  [ "$status" -eq 5 ]
  has "$(cat "$OUT")" $'verdict\tnot_ready'
  has "$(cat "$OUT")" $'handshake\tnot_sent'
  has "$(cat "$OUT")" $'brief\tnone'
  [ "$(sent load-buffer)" = "0" ]
  [ "$(sent send-keys)" = "0" ]
  [ ! -s "$ERR" ]

  SPAWN_CLI_VERSION="9.9.9" MUX_HAS_SESSION=0 run spawn_stub "zz-spawn-slow" --dir "$WORK" --timeout 1 --resume
  [ "$status" -eq 5 ]
  has "$(cat "$OUT")" "CLI 9.9.9 differs from $(cli_version_in_driver READY_CLI_VERSION), which these"
  has "$(cat "$OUT")" "prompt patterns were taken from"
}

@test "a bypass launch that never shows readiness points at the inferred row" {
  stub_setup
  pretrust "$WORK"
  stub_cli_running
  pane_starting

  # The row for a bypass launch is the one row nobody has seen in a real
  # pane, so it is the first thing to check, and the caller is told so
  # whether it reads prose or pairs.
  MUX_HAS_SESSION=0 run spawn_stub "zz-spawn-byp" --dir "$WORK" --timeout 1 --resume --bypass --porcelain
  [ "$status" -eq 5 ] || { cat "$TRACE"; return 1; }
  [ "$(count '' "$ERR")" = "1" ]
  has "$(cat "$ERR")" "the 'bypass' row of scripts/ready-prompts.tsv is inferred, not seen in a real pane; if 'zz-spawn-byp' is at its prompt, correct that row first"

  # No other posture is told that: its rows were seen.
  MUX_HAS_SESSION=0 run spawn_stub "zz-spawn-byp" --dir "$WORK" --timeout 1 --resume --porcelain
  [ "$status" -eq 5 ]
  [ ! -s "$ERR" ]

  # A bypass session that does show its status line is delivered to.
  printf '%s\n' "$BOX" "  ⏵⏵ bypass permissions on (shift+tab to cycle)" > "$PANE"
  MUX_ANSWER_TO="$TRANSCRIPT" MUX_ANSWER_CWD="$WORK" MUX_ANSWER_POSTURE=bypass MUX_HAS_SESSION=0 \
    run spawn_stub "zz-spawn-byp" --dir "$WORK" --timeout 10 --resume --bypass --prompt "BRIEF-TEXT"
  [ "$status" -eq 0 ] || { cat "$TRACE"; cat "$OUT"; return 1; }
  has "$(cat "$RECEIVED")" "BRIEF-TEXT"
  [ ! -s "$ERR" ]
}

@test "a pane showing the prompt is sent the handshake, then the brief, and is confirmed" {
  stub_setup
  pretrust "$WORK"
  stub_cli_running
  pane_prompt

  MUX_ANSWER_TO="$TRANSCRIPT" MUX_ANSWER_CWD="$WORK" \
    run spawn_stub "zz-spawn-ready" --dir "$WORK" --timeout 10 --prompt "BRIEF-TEXT"
  [ "$status" -eq 0 ] || { cat "$TRACE"; cat "$OUT"; return 1; }
  has "$(cat "$OUT")" "identity confirmed"
  has "$(cat "$OUT")" "brief    delivered"
  has "$(cat "$OUT")" "https://claude.ai/code/session_stub"
  lacks "$(cat "$OUT")" "not_sent"
  [ ! -s "$ERR" ]

  # Looked first, then loaded, pasted and submitted, in that order.
  local looked loaded pasted
  looked="$(at ' capture-pane ')"
  loaded="$(at ' load-buffer ')"
  pasted="$(at ' paste-buffer ')"
  [ -n "$looked" ] || { echo "the handshake was sent without the pane being looked at:"; cat "$TRACE"; return 1; }
  [ "$looked" -lt "$loaded" ]
  [ "$loaded" -lt "$pasted" ]
  # Two deliveries, the handshake and then the brief, each one paste and one
  # submission; the third send-keys is the launch command.
  [ "$(sent load-buffer)" = "2" ]
  [ "$(sent paste-buffer)" = "2" ]
  [ "$(sent send-keys)" = "3" ]
  [ "$(submitted)" = "2" ]
  has "$(cat "$RECEIVED")" "the word SPAWN-ACK"
  has "$(cat "$RECEIVED")" "BRIEF-TEXT"

  # Each of the four things sent has its own look straight before it.
  looked_before_every ' paste-buffer ' || { cat "$TRACE"; return 1; }
  looked_before_every ' send-keys -t =[^ ]*: Enter$' || { cat "$TRACE"; return 1; }

  # As pairs, a run that verified says the handshake went.
  : > "$TRANSCRIPT"
  MUX_ANSWER_TO="$TRANSCRIPT" MUX_ANSWER_CWD="$WORK" MUX_HAS_SESSION=0 \
    run spawn_stub "zz-spawn-ready" --dir "$WORK" --timeout 10 --resume --porcelain --prompt "BRIEF-TEXT"
  [ "$status" -eq 0 ] || { cat "$TRACE"; cat "$OUT"; return 1; }
  has "$(cat "$OUT")" $'verdict\thealthy'
  has "$(cat "$OUT")" $'identity\tok'
  has "$(cat "$OUT")" $'brief\tdelivered'
  has "$(cat "$OUT")" $'handshake\tsent'

  # The exit codes after the handshake are what they were. No bridge: 3.
  stub_cli_running 'null'
  pane_prompt
  MUX_ANSWER_TO="$TRANSCRIPT" MUX_ANSWER_CWD="$WORK" MUX_HAS_SESSION=0 \
    run spawn_stub "zz-spawn-ready" --dir "$WORK" --timeout 10 --resume
  [ "$status" -eq 3 ] || { cat "$TRACE"; cat "$OUT"; return 1; }

  # Answering from another directory: refused, and the brief is not sent.
  stub_cli_running
  pane_prompt
  MUX_ANSWER_TO="$TRANSCRIPT" MUX_ANSWER_CWD="/somewhere/else" MUX_HAS_SESSION=0 \
    run spawn_stub "zz-spawn-ready" --dir "$WORK" --timeout 10 --resume --prompt "BRIEF-TEXT"
  [ "$status" -eq 2 ] || { cat "$TRACE"; cat "$OUT"; return 1; }
  has "$(cat "$ERR")" "different directory"
  lacks "$(cat "$RECEIVED")" "BRIEF-TEXT"

  # A prompt, a handshake sent, and no answer: unconfirmed, as before, and
  # the report does not claim that nothing was sent.
  stub_cli_running
  pane_prompt
  MUX_HAS_SESSION=0 run spawn_stub "zz-spawn-ready" --dir "$WORK" --timeout 2 --resume --porcelain
  [ "$status" -eq 5 ] || { cat "$TRACE"; cat "$OUT"; return 1; }
  [ "$(sent load-buffer)" = "1" ]
  has "$(cat "$OUT")" $'verdict\tunconfirmed'
  has "$(cat "$OUT")" $'handshake\tsent'
  lacks "$(cat "$OUT")" "not_sent"

  # A dialog that comes up once the handshake has been submitted and goes
  # unanswered is still diagnosed, and that report does not claim that
  # nothing was sent either.
  stub_cli_running
  pane_prompt
  local later="$BATS_TEST_TMPDIR/pane.later"
  pane_dialog "$later"
  MUX_PANE_ON_SUBMIT="$later" MUX_HAS_SESSION=0 \
    run spawn_stub "zz-spawn-ready" --dir "$WORK" --timeout 2 --resume
  [ "$status" -eq 4 ] || { cat "$TRACE"; cat "$OUT"; return 1; }
  [ "$(sent load-buffer)" = "1" ]
  [ "$(submitted)" = "1" ]
  has "$(cat "$OUT")" "blocked  trust"
  lacks "$(cat "$OUT")" "nothing was sent"
}

@test "a dialog that clears is followed by the handshake, never preceded by it" {
  stub_setup
  pretrust "$WORK"
  stub_cli_running
  pane_dialog
  local later="$BATS_TEST_TMPDIR/pane.later"
  pane_prompt "$later"

  # The dialog shows for the first two looks; a person accepts it; the third
  # look finds the prompt.
  MUX_PANE_LATER="$later" MUX_PANE_LATER_AT=3 MUX_ANSWER_TO="$TRANSCRIPT" MUX_ANSWER_CWD="$WORK" \
    run spawn_stub "zz-spawn-clears" --dir "$WORK" --timeout 10
  [ "$status" -eq 0 ] || { cat "$TRACE"; cat "$OUT"; return 1; }
  has "$(cat "$OUT")" "identity confirmed"

  # Nothing was loaded until the pane had been seen without the dialog.
  local loaded looks_before
  loaded="$(at ' load-buffer ')"
  looks_before="$(head -n "$loaded" "$TRACE" | grep -c ' capture-pane ' || true)"
  [ "$looks_before" = "3" ] || { cat "$TRACE"; return 1; }
  [ "$(sent load-buffer)" = "1" ]
}

@test "status-line wording outside the input box is not readiness" {
  stub_setup
  pretrust "$WORK"
  stub_cli_running

  # A dialog nobody has listed, one of whose options reads like a status
  # line. Nothing is sent to it.
  printf '%s\n' "Select a color theme" "❯ 1. accept edits on" "  2. Continue" > "$PANE"
  MUX_HAS_SESSION=0 run spawn_stub "zz-spawn-quote" --dir "$WORK" --timeout 2 --resume --porcelain
  [ "$status" -eq 5 ] || { cat "$TRACE"; return 1; }
  [ "$(sent load-buffer)" = "0" ] || { echo "input was sent to a dialog that quotes a status line:"; cat "$TRACE"; return 1; }
  [ "$(sent paste-buffer)" = "0" ]
  [ "$(sent send-keys)" = "0" ]
  [ ! -s "$RECEIVED" ]
  has "$(cat "$OUT")" $'verdict\tnot_ready'
  has "$(cat "$OUT")" $'handshake\tnot_sent'

  # The same wording, echoed by the shell from the caller's own pre-launch
  # command, before the CLI has drawn anything.
  printf '%s\n' "\$ printf '%s' 'accept edits on'; claude --permission-mode acceptEdits" > "$PANE"
  run spawn_stub "zz-spawn-quote" --dir "$WORK" --timeout 2 --porcelain \
    --pre-launch "printf '%s' 'accept edits on'"
  [ "$status" -eq 5 ] || { cat "$TRACE"; return 1; }
  [ "$(sent load-buffer)" = "0" ] || { echo "input was sent on the strength of an echoed command:"; cat "$TRACE"; return 1; }
  [ "$(sent paste-buffer)" = "0" ]
  # The one send-keys is the launch command.
  [ "$(sent send-keys)" = "1" ]
  [ "$(submitted)" = "0" ]
  has "$(cat "$OUT")" $'handshake\tnot_sent'
}

@test "a dialog that replaces the input box holds back whatever comes next" {
  stub_setup
  pretrust "$WORK"
  stub_cli_running
  local dialog="$BATS_TEST_TMPDIR/pane.dialog"
  pane_dialog "$dialog"

  # Between the look that found the box and the look before the paste: the
  # paste is held back, and what was staged for it is dropped.
  pane_prompt
  MUX_PANE_LATER="$dialog" MUX_PANE_LATER_AT=2 MUX_HAS_SESSION=0 \
    run spawn_stub "zz-spawn-gone" --dir "$WORK" --timeout 2 --resume --porcelain
  [ "$status" -eq 4 ] || { cat "$TRACE"; cat "$OUT"; return 1; }
  [ "$(sent paste-buffer)" = "0" ] || { echo "pasted at a dialog:"; cat "$TRACE"; return 1; }
  [ "$(sent send-keys)" = "0" ]
  [ "$(sent delete-buffer)" -ge 1 ]
  has "$(cat "$OUT")" $'verdict\tblocked'
  has "$(cat "$OUT")" $'handshake\tnot_sent'

  # After the paste, before its Enter: the paste went to the box, the Enter
  # is held back, and the report says exactly that.
  pane_prompt
  MUX_PANE_ON_PASTE="$dialog" MUX_HAS_SESSION=0 \
    run spawn_stub "zz-spawn-gone" --dir "$WORK" --timeout 3 --resume --porcelain
  [ "$status" -eq 4 ] || { cat "$TRACE"; cat "$OUT"; return 1; }
  [ "$(sent paste-buffer)" = "1" ]
  [ "$(sent send-keys)" = "0" ] || { echo "Enter was sent to a dialog:"; cat "$TRACE"; return 1; }
  [ ! -s "$RECEIVED" ]
  has "$(cat "$OUT")" $'verdict\tblocked'
  has "$(cat "$OUT")" $'handshake\tnot_submitted'
  has "$(cat "$OUT")" $'brief\tnone'

  MUX_PANE_ON_PASTE="$dialog" MUX_HAS_SESSION=0 \
    run spawn_stub "zz-spawn-gone" --dir "$WORK" --timeout 3 --resume
  [ "$status" -eq 4 ]
  has "$(cat "$OUT")" "the handshake was pasted, and Enter was not sent"
  has "$(cat "$OUT")" "blocked  trust"
  lacks "$(cat "$OUT")" "nothing was sent"

  # The same when what replaced the box is nothing the launcher knows: not
  # a diagnosis, and still no Enter.
  local unknown="$BATS_TEST_TMPDIR/pane.unknown"
  printf '%s\n' "Something else entirely" "❯ 1. Continue" > "$unknown"
  MUX_PANE_ON_PASTE="$unknown" MUX_HAS_SESSION=0 \
    run spawn_stub "zz-spawn-gone" --dir "$WORK" --timeout 3 --resume --porcelain
  [ "$status" -eq 5 ] || { cat "$TRACE"; cat "$OUT"; return 1; }
  [ "$(sent paste-buffer)" = "1" ]
  [ "$(sent send-keys)" = "0" ]
  has "$(cat "$OUT")" $'verdict\tnot_ready'
  has "$(cat "$OUT")" $'handshake\tnot_submitted'

  # After a valid acknowledgement, before the brief: identity is confirmed
  # and reported, and the brief is not pasted.
  : > "$TRANSCRIPT"
  MUX_PANE_ON_SUBMIT="$dialog" MUX_ANSWER_TO="$TRANSCRIPT" MUX_ANSWER_CWD="$WORK" MUX_HAS_SESSION=0 \
    run spawn_stub "zz-spawn-gone" --dir "$WORK" --timeout 5 --resume --porcelain --prompt "BRIEF-TEXT"
  [ "$status" -eq 4 ] || { cat "$TRACE"; cat "$OUT"; return 1; }
  [ "$(sent paste-buffer)" = "1" ] || { echo "the brief was pasted at a dialog:"; cat "$TRACE"; return 1; }
  [ "$(submitted)" = "1" ]
  lacks "$(cat "$RECEIVED")" "BRIEF-TEXT"
  has "$(cat "$OUT")" $'verdict\tblocked'
  has "$(cat "$OUT")" $'identity\tok'
  has "$(cat "$OUT")" $'handshake\tsent'
  has "$(cat "$OUT")" $'brief\tnone'
  lacks "$(cat "$OUT")" $'brief\tdelivered'

  : > "$TRANSCRIPT"
  MUX_PANE_ON_SUBMIT="$dialog" MUX_ANSWER_TO="$TRANSCRIPT" MUX_ANSWER_CWD="$WORK" MUX_HAS_SESSION=0 \
    run spawn_stub "zz-spawn-gone" --dir "$WORK" --timeout 5 --resume --prompt "BRIEF-TEXT"
  [ "$status" -eq 4 ]
  has "$(cat "$OUT")" "a startup dialog came up after the session identified itself"
  has "$(cat "$OUT")" "identity was confirmed. The brief was not sent"
  lacks "$(cat "$OUT")" "brief    delivered"

  # After the brief's paste, before its Enter.
  : > "$TRANSCRIPT"
  : > "$RECEIVED"
  MUX_PANE_ON_PASTE="$dialog" MUX_PANE_ON_PASTE_AT=2 MUX_ANSWER_TO="$TRANSCRIPT" MUX_ANSWER_CWD="$WORK" MUX_HAS_SESSION=0 \
    run spawn_stub "zz-spawn-gone" --dir "$WORK" --timeout 5 --resume --porcelain --prompt "BRIEF-TEXT"
  [ "$status" -eq 4 ] || { cat "$TRACE"; cat "$OUT"; return 1; }
  [ "$(sent paste-buffer)" = "2" ]
  [ "$(submitted)" = "1" ] || { echo "the brief's Enter was sent to a dialog:"; cat "$TRACE"; return 1; }
  lacks "$(cat "$RECEIVED")" "BRIEF-TEXT"
  has "$(cat "$OUT")" $'handshake\tsent'
  has "$(cat "$OUT")" $'brief\tnot_submitted'
}

@test "a narrow pane with the input box showing is still delivered to" {
  stub_setup
  pretrust "$WORK"
  stub_cli_running

  # The real CLI's screen as tmux captured it, where the status line is cut
  # short: "accept edits" at 20 columns, "accept  ·" at 16, the symbol alone
  # at 12.
  local width
  for width in 20 16 12; do
    cp "$FIXTURES/pane-accept-edits-$width.txt" "$PANE"
    : > "$TRANSCRIPT"
    : > "$RECEIVED"
    MUX_ANSWER_TO="$TRANSCRIPT" MUX_ANSWER_CWD="$WORK" MUX_HAS_SESSION=0 \
      run spawn_stub "zz-spawn-narrow" --dir "$WORK" --timeout 10 --resume --porcelain --prompt "BRIEF-TEXT"
    [ "$status" -eq 0 ] || { echo "at $width columns:"; cat "$TRACE"; cat "$OUT"; return 1; }
    has "$(cat "$OUT")" $'verdict\thealthy'
    has "$(cat "$OUT")" $'brief\tdelivered'
    has "$(cat "$RECEIVED")" "BRIEF-TEXT"
  done
}

@test "dialog wording in earlier output does not stop a visible input box being used" {
  stub_setup
  pretrust "$WORK"
  stub_cli_running

  # A working session whose screen still shows a line that quotes a dialog,
  # under the status line and then above the box.
  local shape
  for shape in under above; do
    if [[ "$shape" == "under" ]]; then
      printf '%s\n' "$BOX" "$STATUS" "Earlier output: the menu option is Yes, I trust this folder" > "$PANE"
    else
      printf '%s\n' "Earlier output: the menu option is Yes, I trust this folder" "$BOX" "$STATUS" > "$PANE"
    fi
    : > "$TRANSCRIPT"
    : > "$RECEIVED"
    MUX_ANSWER_TO="$TRANSCRIPT" MUX_ANSWER_CWD="$WORK" MUX_HAS_SESSION=0 \
      run spawn_stub "zz-spawn-quoted" --dir "$WORK" --timeout 10 --resume --porcelain --prompt "BRIEF-TEXT"
    [ "$status" -eq 0 ] || { echo "quotation $shape the box:"; cat "$TRACE"; cat "$OUT"; return 1; }
    has "$(cat "$OUT")" $'verdict\thealthy'
    has "$(cat "$RECEIVED")" "BRIEF-TEXT"
  done

  # The other way round: a dialog drawn under a box that was never cleared
  # is a dialog, and gets nothing.
  printf '%s\n' "$BOX" "$STATUS" "Dialog" "❯ Yes, I trust this folder" > "$PANE"
  : > "$RECEIVED"
  MUX_HAS_SESSION=0 run spawn_stub "zz-spawn-quoted" --dir "$WORK" --timeout 2 --resume --porcelain --prompt "BRIEF-TEXT"
  [ "$status" -eq 4 ] || { cat "$TRACE"; cat "$OUT"; return 1; }
  [ "$(sent load-buffer)" = "0" ]
  [ "$(sent send-keys)" = "0" ]
  [ ! -s "$RECEIVED" ]
  has "$(cat "$OUT")" $'verdict\tblocked'
  has "$(cat "$OUT")" $'handshake\tnot_sent'
}

@test "a look that fails is not readiness, whatever it printed" {
  stub_setup
  pretrust "$WORK"
  stub_cli_running
  pane_prompt

  # The multiplexer prints a frame showing the prompt and then fails. What
  # the pane shows is not known, so nothing is sent.
  MUX_CAPTURE_RC=1 MUX_HAS_SESSION=0 \
    run spawn_stub "zz-spawn-nolook" --dir "$WORK" --timeout 2 --resume --porcelain
  [ "$status" -eq 5 ] || { cat "$TRACE"; cat "$OUT"; return 1; }
  [ "$(sent capture-pane)" -ge 2 ]
  [ "$(sent load-buffer)" = "0" ] || { echo "input was sent after a failed look:"; cat "$TRACE"; return 1; }
  [ "$(sent paste-buffer)" = "0" ]
  [ "$(sent send-keys)" = "0" ]
  [ ! -s "$RECEIVED" ]
  has "$(cat "$OUT")" $'verdict\tnot_ready'
  has "$(cat "$OUT")" $'handshake\tnot_sent'
}

@test "every run that verifies says how far the handshake got" {
  stub_setup
  pretrust "$WORK"

  # No CLI process ever appears: the run ends before the handshake, and the
  # pairs say so, as they do for every other ending before it.
  run spawn_stub "zz-spawn-none" --dir "$WORK" --timeout 1 --porcelain
  [ "$status" -eq 4 ] || { cat "$TRACE"; cat "$OUT"; return 1; }
  has "$(cat "$OUT")" $'verdict\tno_process'
  has "$(cat "$OUT")" $'brief\tnone'
  has "$(cat "$OUT")" $'handshake\tnot_sent'
  [ "$(sent load-buffer)" = "0" ]

  # A launch that is not verified attempts no handshake and has no pair for
  # one. Its output is pinned byte for byte in an earlier spec.
  run spawn_stub "zz-spawn-none" --dir "$WORK" --no-verify --porcelain
  [ "$status" -eq 0 ]
  lacks "$(cat "$OUT")" "handshake"
}

# ── the directory ───────────────────────────────────────────────────────────
#
# A path is carried through command substitutions, which drop every trailing
# newline. A directory whose name ends in one therefore resolves to its
# sibling, and a path holding any other control character corrupts the lines
# it is printed on. Both are refused as usage before the path is used.

# refused_dir <args...>
#
# Runs the launcher and asserts a control-character refusal: exit 2, nothing
# on stdout, one clean line on stderr, the trust configuration neither read
# nor written, and nothing asked of the multiplexer.
#
# Every check returns for itself. One caller runs this in a subshell on the
# left of `||`, where errexit is off and an unguarded failing line would be
# passed over.
refused_dir() {
  local rc=0
  spawn_stub "$@" || rc=$?
  [ "$rc" -eq 2 ] || { echo "exit $rc for: $(visible "$*")"; cat "$TRACE"; return 1; }
  [ ! -s "$OUT" ] || { echo "stdout: $(cat "$OUT")"; return 1; }
  [ "$(count '' "$ERR")" = "1" ] || { cat "$ERR"; return 1; }
  clean "$ERR" || return 1
  utf8_only "$ERR" || return 1
  has "$(cat "$ERR")" "has a control character, or a byte that is not valid UTF-8, in its path" || return 1
  [ "$(count '^read: python3 ' "$TRACE")" = "0" ] || { cat "$TRACE"; return 1; }
  [ "$(count '^mux: ' "$TRACE")" = "0" ] || { cat "$TRACE"; return 1; }
  cmp "$BATS_TEST_TMPDIR/config.before" "$CONFIG_FILE" || return 1
  [ ! -e "$CONFIG_FILE.lock" ] || return 1
}

# utf8_only <file>
#
# Fails if the file holds a byte that is not part of well-formed UTF-8. A
# lone byte from 0x80 to 0x9f is one, and `clean` does not look for it.
utf8_only() {
  python3 -c 'import sys; open(sys.argv[1], "rb").read().decode("utf-8")' "$1" 2>/dev/null ||
    { echo "bytes that are not UTF-8 in $1:"; LC_ALL=C od -c "$1"; return 1; }
}

@test "a directory whose name ends in a newline is refused, not resolved to its sibling" {
  stub_setup
  stub_readers
  local ws="$BATS_TEST_TMPDIR/ws"
  local sibling="$ws/repo"
  local named="$ws/repo"$'\n'
  mkdir -p "$sibling" "$named"
  git init -q "$sibling"
  git init -q "$named"
  cp "$CONFIG_FILE" "$BATS_TEST_TMPDIR/config.before"

  # The stand-ins do record a trust lookup and a launch when there is one:
  # the sibling, named honestly, is trusted and launched in.
  run spawn_stub "zz-spawn-nl" --dir "$sibling" --trust-folder --no-verify
  [ "$status" -eq 0 ]
  [ "$(count '^read: python3 .* grant ' "$TRACE")" = "1" ]
  [ "$(count '^mux: .*new-session' "$TRACE")" = "1" ]
  cp "$BATS_TEST_TMPDIR/config.before" "$CONFIG_FILE"

  # Named with the newline: refused, and the sibling is not trusted in its
  # place or handed to the multiplexer as the working directory.
  refused_dir "zz-spawn-nl" --dir "$named" --trust-folder --no-verify
  has "$(cat "$ERR")" "repo\\n'"
  refused_dir "zz-spawn-nl" --dir "$named" --trust-folder --dry-run
  refused_dir "zz-spawn-nl" --dir "$named" --no-verify
  refused_dir "zz-spawn-nl" --dir "$named" --bypass --no-verify

  # The argument can be clean while the directory is not. Launched from
  # inside it, with no --dir at all:
  local rc=0
  ( cd "$named" && refused_dir "zz-spawn-nl" --trust-folder --no-verify ) || rc=$?
  [ "$rc" -eq 0 ]
  ( cd "$named" && refused_dir "zz-spawn-nl" --dir . --trust-folder --no-verify ) || rc=$?
  [ "$rc" -eq 0 ]

  # Reached through a symbolic link with an ordinary name:
  ln -s "$named" "$ws/link"
  refused_dir "zz-spawn-nl" --dir "$ws/link" --trust-folder --no-verify
  has "$(cat "$ERR")" "the location the directory resolves to"
  has "$(cat "$ERR")" "repo\\n'"
}

@test "a name that leads through a link and back out is held to where it really leads" {
  stub_setup
  stub_readers
  cp "$CONFIG_FILE" "$BATS_TEST_TMPDIR/config.before"

  # From `work`, `link` points into a directory whose name ends in a newline.
  # The shell reads `link/..` as `work`; the kernel reads it as the parent of
  # what the link points to, which is the directory with the newline. Trust
  # for `work`, and a session started there, is not what the name leads to.
  local work="$BATS_TEST_TMPDIR/ws/work"
  mkdir -p "$work/repo"$'\n'"/leaf"
  ln -s "$work/repo"$'\n'"/leaf" "$work/link"

  local rc=0
  ( cd "$work" && refused_dir "zz-spawn-dots" --dir link/.. --trust-folder --no-verify ) || rc=$?
  [ "$rc" -eq 0 ]
  ( cd "$work" && refused_dir "zz-spawn-dots" --dir link/.. --trust-folder --dry-run ) || rc=$?
  [ "$rc" -eq 0 ]
  ( cd "$work" && refused_dir "zz-spawn-dots" --dir link/.. --no-verify ) || rc=$?
  [ "$rc" -eq 0 ]
  ( cd "$work" && spawn_stub "zz-spawn-dots" --dir link/.. --trust-folder --no-verify ) || true
  has "$(cat "$ERR")" "the location the directory resolves to"
  has "$(cat "$ERR")" "repo\\n'"

  # Where the two readings differ and neither holds a control character, the
  # launcher uses the shell's, as it always has: the directory holding the
  # link, not the parent of what the link points to.
  local plain="$BATS_TEST_TMPDIR/ws/plain"
  mkdir -p "$plain/from" "$plain/target/leaf"
  ln -s "$plain/target/leaf" "$plain/from/link"
  rc=0
  ( cd "$plain/from" && spawn_stub "zz-spawn-dots" --dir link/.. --trust-folder --no-verify ) || rc=$?
  [ "$rc" -eq 0 ] || { cat "$TRACE"; return 1; }
  [ "$(count "^mux: .*new-session -d -s zz-spawn-dots -c $plain/from\$" "$TRACE")" = "1" ] || { cat "$TRACE"; return 1; }
}

@test "a directory with any control character in its path is refused as usage" {
  stub_setup
  stub_readers
  cp "$CONFIG_FILE" "$BATS_TEST_TMPDIR/config.before"

  local ws="$BATS_TEST_TMPDIR/ws" dir
  # A newline in the middle, a tab, a carriage return, an escape, a delete,
  # and a control character from the second block. And one in a parent: the
  # last component is ordinary.
  for dir in "$ws/mid"$'\n'"dle" "$ws/ta"$'\t'"b" "$ws/c"$'\r'"r" "$ws/es"$'\033'"[2Kc" \
             "$ws/de"$'\177'"l" "$ws/c"$'\302\233'"1" "$ws/par"$'\n'"ent/child"; do
    mkdir -p "$dir"
    refused_dir "zz-spawn-ctl" --dir "$dir" --trust-folder --no-verify
    refused_dir "zz-spawn-ctl" --dir "$dir" --trust-folder --dry-run
  done

  # One that does not exist is refused the same way, on the name alone.
  refused_dir "zz-spawn-ctl" --dir "$ws/absent"$'\n' --no-verify

  # Ordinary names still launch: spaces, multi-byte characters, a backslash.
  for dir in "$ws/with space" "$ws/é—ü" "$ws/back\\nslash"; do
    mkdir -p "$dir"
    run spawn_stub "zz-spawn-ok" --dir "$dir" --trust-folder --no-verify
    [ "$status" -eq 0 ] || { echo "refused: $dir"; cat "$TRACE"; return 1; }
    [ "$(count '^mux: .*new-session -d -s zz-spawn-ok' "$TRACE")" = "1" ]
  done
}

@test "a path that is not valid UTF-8 is refused, and names that are keep working" {
  stub_setup
  stub_readers
  cp "$CONFIG_FILE" "$BATS_TEST_TMPDIR/config.before"
  local ws="$BATS_TEST_TMPDIR/ws" utf8
  mkdir -p "$ws"
  utf8="$(utf8_locale)"

  # A lone 0x9b is what an 8-bit terminal reads as the start of a control
  # sequence, and it is not the encoding of any character. Refused on the
  # name alone, before trust is looked at, whatever the caller's locale; and
  # the refusal prints it as text.
  local byte dir
  for byte in $'\200' $'\233' $'\237' $'\377'; do
    dir="$ws/a${byte}b"
    LC_ALL=C refused_dir "zz-spawn-raw" --dir "$dir" --trust-folder --no-verify
    LC_ALL="$utf8" refused_dir "zz-spawn-raw" --dir "$dir" --trust-folder --no-verify
    LC_ALL="$utf8" refused_dir "zz-spawn-raw" --dir "$dir" --trust-folder --dry-run
    LC_ALL="$utf8" refused_dir "zz-spawn-raw" --dir "$dir" --no-verify
    LC_ALL="$utf8" refused_dir "zz-spawn-raw" --dir "$dir" --bypass --no-verify
  done
  LC_ALL="$utf8" refused_dir "zz-spawn-raw" --dir "$ws/a"$'\233'"b" --no-verify
  has "$(cat "$ERR")" "a\\x9bb'"

  # Where the filesystem will hold such a name, the routes that reach it
  # without it being the argument are refused too. macOS will not create one,
  # so this half runs on Linux.
  local raw="$ws/raw"$'\233'"dir" rc=0
  if mkdir "$raw" 2>/dev/null; then
    git init -q "$raw"
    mkdir "$raw/sub"
    refused_dir "zz-spawn-raw" --dir "$raw" --trust-folder --no-verify
    refused_dir "zz-spawn-raw" --dir "$raw/sub" --trust-folder --no-verify
    ( cd "$raw" && refused_dir "zz-spawn-raw" --trust-folder --no-verify ) || rc=$?
    [ "$rc" -eq 0 ]
    ( cd "$raw" && refused_dir "zz-spawn-raw" --dir . --trust-folder --dry-run ) || rc=$?
    [ "$rc" -eq 0 ]
    ln -s "$raw" "$ws/rawlink"
    refused_dir "zz-spawn-raw" --dir "$ws/rawlink" --trust-folder --no-verify
  fi

  # Valid names whose encoding uses those same byte values keep working, in
  # each locale: an accent, a stroke, CJK, an emoji.
  local name locale
  for name in "é" "ł" "日本" "😀"; do
    mkdir -p "$ws/$name"
    for locale in C "$utf8"; do
      rc=0
      LC_ALL="$locale" spawn_stub "zz-spawn-utf8" --dir "$ws/$name" --trust-folder --no-verify || rc=$?
      [ "$rc" -eq 0 ] || { echo "refused '$name' under LC_ALL=$locale:"; cat "$TRACE"; return 1; }
      [ "$(count '^mux: .*new-session -d -s zz-spawn-utf8' "$TRACE")" = "1" ]
      cp "$BATS_TEST_TMPDIR/config.before" "$CONFIG_FILE"
    done
  done

  # A session name is printed in its refusal, and is rendered the same way.
  rc=0
  spawn_stub "zz"$'\233'"31mred" --dir "$WORK" --no-verify || rc=$?
  [ "$rc" -eq 2 ]
  [ "$(count '' "$ERR")" = "1" ]
  utf8_only "$ERR"
  has "$(cat "$ERR")" "'zz\\x9b31mred' is not a usable session name"
}
