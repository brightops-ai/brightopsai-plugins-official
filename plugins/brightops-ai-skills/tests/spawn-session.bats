#!/usr/bin/env bats
#
# Behaviour of the spawn-session skill's script and its pure decision lib.
#
# Specs that drive tmux use a private server named with `tmux -L` (see
# helpers/tmux-sandbox.bash) and only ever create zz-spawn-* sessions. No spec
# launches the real `claude` binary.

setup() {
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
}

spawn() {
  SPAWN_SESSIONS_DIR="$SESSIONS_DIR" SPAWN_CONFIG_FILE="$CONFIG_FILE" \
    "$SPAWN" --socket "$SANDBOX_SOCKET" --pre-launch "$PRE_LAUNCH" --trust-folder "$@"
}

teardown() {
  tmux_sandbox_stop
}

# bats test_tags=live
@test "spawns a detached session in the named directory with the named posture" {
  live_setup
  local dir="$BATS_TEST_TMPDIR/work"
  mkdir -p "$dir"

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
    "$SPAWN" --socket "$SANDBOX_SOCKET" --pre-launch "$PRE_LAUNCH" --trust-folder "$@"
}

# bats test_tags=live
@test "a session that identifies itself correctly is confirmed" {
  live_setup_hs
  local dir="$BATS_TEST_TMPDIR/work"
  mkdir -p "$dir"
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
  # The driver sets strict mode for its own run; leaving it on would apply it
  # to the rest of the test body, where a deliberately failing check is the
  # thing being asserted.
  set +e +u +o pipefail
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
  # Shows the trust dialog and answers nothing, as a real session would.
  use_fake_cli "FAKE_SILENT=1" "FAKE_PANE_TEXT=Yes, I trust this folder"

  run spawn_hs "zz-spawn-blocked" --dir /tmp --timeout 6
  [ "$status" -eq 4 ]
  [[ "$output" == *"blocked"* ]]
  [[ "$output" == *"trust"* ]]
  # The remedy, not just the diagnosis.
  [[ "$output" == *"--trust-folder"* ]]
  # And nothing was typed at it.
  ts has-session -t "=zz-spawn-blocked"
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
