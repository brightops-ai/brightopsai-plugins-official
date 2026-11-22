#!/usr/bin/env bats
#
# ensure-dashboard.sh: first-run scaffold under CLAUDE_PLUGIN_DATA.
# Never point CLAUDE_PLUGIN_DATA or CLAUDE_PLUGIN_ROOT at a real ~/.claude.

setup() {
  load '../../../scripts/test-support/sandbox-guard'
  PLUGIN_ROOT="$(cd "$(dirname "$BATS_TEST_FILENAME")/.." && pwd)"
  SCRIPT="$PLUGIN_ROOT/skills/marketplace-scout/scripts/ensure-dashboard.sh"

  export CLAUDE_PLUGIN_ROOT="$BATS_TEST_TMPDIR/plugin-root"
  export CLAUDE_PLUGIN_DATA="$BATS_TEST_TMPDIR/plugin-data"
  export SKIP_NPM_INSTALL=1

  local assets="$CLAUDE_PLUGIN_ROOT/skills/marketplace-scout/assets/dashboard"
  mkdir -p "$assets/src" "$assets/node_modules/pkg" "$CLAUDE_PLUGIN_DATA"
  printf '%s\n' '{"name":"fake-dashboard","version":"1.0.0"}' >"$assets/package.json"
  printf '%s\n' '{"name":"fake-dashboard","version":"1.0.0","lockfileVersion":3,"packages":{}}' \
    >"$assets/package-lock.json"
  printf '%s\n' 'original' >"$assets/src/marker.txt"
  printf '%s\n' 'do-not-copy' >"$assets/node_modules/pkg/index.js"

  WORKDIR="$BATS_TEST_TMPDIR/cwd"
  mkdir -p "$WORKDIR"
  cd "$WORKDIR" || return 1
}

# Put a recording `npm` first on PATH. It never touches the network: it logs
# its arguments, its cwd, and whether the lockfile is beside it, then behaves
# like an install. With NPM_STUB_EXIT set to a non-zero status it leaves a
# partial node_modules behind and fails with that status, as a real `npm ci`
# does when it dies half way. NPM_STUB_SLEEP makes it slow enough to interrupt.
stub_npm() {
  local bin="$BATS_TEST_TMPDIR/bin"
  export NPM_LOG="$BATS_TEST_TMPDIR/npm.log"
  mkdir -p "$bin"
  cat >"$bin/npm" <<'STUB'
#!/usr/bin/env bash
{
  printf 'args=%s\n' "$*"
  printf 'cwd=%s\n' "$PWD"
  if [[ -f package-lock.json ]]; then echo 'lockfile=present'; else echo 'lockfile=absent'; fi
} >>"$NPM_LOG"
if [[ -n "${NPM_STUB_SLEEP:-}" ]]; then sleep "$NPM_STUB_SLEEP"; fi
mkdir -p node_modules
if [[ "${NPM_STUB_EXIT:-0}" -ne 0 ]]; then
  echo 'partial' >node_modules/half-installed
  exit "$NPM_STUB_EXIT"
fi
echo 'installed' >node_modules/complete
STUB
  chmod +x "$bin/npm"
  PATH="$bin:$PATH"
}

npm_calls() {
  if [[ -f "$NPM_LOG" ]]; then grep -c '^args=' "$NPM_LOG"; else echo 0; fi
}

# No staging directory may outlive a run, whatever its outcome.
assert_no_staging_left() {
  run find "$CLAUDE_PLUGIN_DATA" -maxdepth 1 -name '.dashboard-staging.*'
  [ -z "$output" ]
}

@test "fresh scaffold copies assets under CLAUDE_PLUGIN_DATA and skips node_modules" {
  run "$SCRIPT"
  [ "$status" -eq 0 ]

  local dest="$CLAUDE_PLUGIN_DATA/dashboard"
  [ -f "$dest/package.json" ]
  [ -f "$dest/package-lock.json" ]
  [ -f "$dest/src/marker.txt" ]
  [ ! -e "$dest/node_modules" ]
  [ -d "$CLAUDE_PLUGIN_DATA/data/images" ]
  [[ "$output" == *"$dest"* ]]
}

@test "installs with npm ci --ignore-scripts in staging, lockfile beside package.json" {
  stub_npm
  unset SKIP_NPM_INSTALL

  run "$SCRIPT"
  [ "$status" -eq 0 ]

  [ "$(npm_calls)" -eq 1 ]
  grep -qx 'args=ci --ignore-scripts' "$NPM_LOG"
  grep -qx 'lockfile=present' "$NPM_LOG"
  # npm runs in a staging directory beside the target, never in the target.
  grep -q "^cwd=.*/\.dashboard-staging\.[^/]*/dashboard\$" "$NPM_LOG"
  ! grep -qx "cwd=$CLAUDE_PLUGIN_DATA/dashboard" "$NPM_LOG"

  [ -f "$CLAUDE_PLUGIN_DATA/dashboard/node_modules/complete" ]
  [ -f "$CLAUDE_PLUGIN_DATA/dashboard/package-lock.json" ]
  [[ "$output" == *"dashboard ready at $CLAUDE_PLUGIN_DATA/dashboard"* ]]
  assert_no_staging_left
}

@test "failed install leaves no target, and the next run installs" {
  stub_npm
  unset SKIP_NPM_INSTALL

  run env NPM_STUB_EXIT=42 "$SCRIPT"
  [ "$status" -eq 4 ]
  [[ "$output" == *"npm ci failed"* ]]
  [ ! -e "$CLAUDE_PLUGIN_DATA/dashboard" ]
  assert_no_staging_left

  run "$SCRIPT"
  [ "$status" -eq 0 ]
  [ "$(npm_calls)" -eq 2 ]
  [ -f "$CLAUDE_PLUGIN_DATA/dashboard/node_modules/complete" ]
  [ ! -e "$CLAUDE_PLUGIN_DATA/dashboard/node_modules/half-installed" ]
  assert_no_staging_left
}

@test "interrupted install leaves no target and no staging directory" {
  stub_npm
  unset SKIP_NPM_INSTALL
  export NPM_STUB_SLEEP=2

  "$SCRIPT" >/dev/null 2>&1 3>&- &
  local pid=$! tries=0 rc=0
  until [[ -f "$NPM_LOG" ]] || [[ "$tries" -ge 50 ]]; do
    sleep 0.1
    tries=$((tries + 1))
  done
  [ -f "$NPM_LOG" ]

  kill -TERM "$pid"
  wait "$pid" || rc=$?
  [ "$rc" -eq 143 ]
  [ ! -e "$CLAUDE_PLUGIN_DATA/dashboard" ]
  assert_no_staging_left
}

@test "complete target is not reinstalled and keeps user edits" {
  stub_npm
  unset SKIP_NPM_INSTALL

  run "$SCRIPT"
  [ "$status" -eq 0 ]
  printf '%s\n' 'user-edit' >"$CLAUDE_PLUGIN_DATA/dashboard/src/marker.txt"

  run "$SCRIPT"
  [ "$status" -eq 0 ]
  [[ "$output" == *"not overwriting"* ]]
  [ "$(npm_calls)" -eq 1 ]
  [ "$(cat "$CLAUDE_PLUGIN_DATA/dashboard/src/marker.txt")" = "user-edit" ]
}

@test "run after a skipped install installs into the existing target only" {
  stub_npm

  run "$SCRIPT"
  [ "$status" -eq 0 ]
  [[ "$output" == *"dependencies not installed"* ]]
  [ ! -e "$CLAUDE_PLUGIN_DATA/dashboard/node_modules" ]
  printf '%s\n' 'user-edit' >"$CLAUDE_PLUGIN_DATA/dashboard/src/marker.txt"

  # Still skipped: reported, nothing installed.
  run "$SCRIPT"
  [ "$status" -eq 0 ]
  [[ "$output" == *"not overwriting"* ]]
  [[ "$output" == *"dependencies are not installed"* ]]
  [ "$(npm_calls)" -eq 0 ]

  unset SKIP_NPM_INSTALL
  run "$SCRIPT"
  [ "$status" -eq 0 ]
  [ "$(npm_calls)" -eq 1 ]
  grep -qx 'lockfile=present' "$NPM_LOG"
  [ -f "$CLAUDE_PLUGIN_DATA/dashboard/node_modules/complete" ]
  [ "$(cat "$CLAUDE_PLUGIN_DATA/dashboard/src/marker.txt")" = "user-edit" ]
  assert_no_staging_left
}

@test "failed install into an existing target changes nothing, then retries" {
  stub_npm
  run "$SCRIPT"
  [ "$status" -eq 0 ]
  printf '%s\n' 'user-edit' >"$CLAUDE_PLUGIN_DATA/dashboard/src/marker.txt"
  unset SKIP_NPM_INSTALL

  run env NPM_STUB_EXIT=42 "$SCRIPT"
  [ "$status" -eq 4 ]
  [ ! -e "$CLAUDE_PLUGIN_DATA/dashboard/node_modules" ]
  [ "$(cat "$CLAUDE_PLUGIN_DATA/dashboard/src/marker.txt")" = "user-edit" ]
  assert_no_staging_left

  run "$SCRIPT"
  [ "$status" -eq 0 ]
  [ "$(npm_calls)" -eq 2 ]
  [ -f "$CLAUDE_PLUGIN_DATA/dashboard/node_modules/complete" ]
  [ ! -e "$CLAUDE_PLUGIN_DATA/dashboard/node_modules/half-installed" ]
}

@test "pre-lockfile target with the plugin's package.json gets the plugin lockfile" {
  stub_npm
  unset SKIP_NPM_INSTALL
  local dest="$CLAUDE_PLUGIN_DATA/dashboard"
  mkdir -p "$dest/src"
  cp "$CLAUDE_PLUGIN_ROOT/skills/marketplace-scout/assets/dashboard/package.json" "$dest/package.json"
  printf '%s\n' 'user-edit' >"$dest/src/marker.txt"

  run "$SCRIPT"
  [ "$status" -eq 0 ]
  grep -qx 'lockfile=present' "$NPM_LOG"
  [ -f "$dest/package-lock.json" ]
  [ -f "$dest/node_modules/complete" ]
  [ "$(cat "$dest/src/marker.txt")" = "user-edit" ]
}

@test "pre-lockfile target with an edited package.json is refused, not installed unpinned" {
  stub_npm
  unset SKIP_NPM_INSTALL
  local dest="$CLAUDE_PLUGIN_DATA/dashboard"
  mkdir -p "$dest"
  printf '%s\n' '{"name":"edited","version":"9.9.9"}' >"$dest/package.json"

  run "$SCRIPT"
  [ "$status" -eq 1 ]
  [[ "$output" == *"refusing to install unpinned dependencies"* ]]
  [ "$(npm_calls)" -eq 0 ]
  [ ! -e "$dest/node_modules" ]
  [ ! -e "$dest/package-lock.json" ]
  assert_no_staging_left
}

# Put an `mv` first on PATH that creates RACE_DST just before the script moves
# something onto it: the destination appears between the script's existence
# check and its move, which is the window a real concurrent run would hit.
stub_racing_mv() {
  local bin="$BATS_TEST_TMPDIR/racebin" real
  real="$(command -v mv)"
  mkdir -p "$bin"
  cat >"$bin/mv" <<STUB
#!/usr/bin/env bash
last="\${@: -1}"
if [[ "\$last" == "\$RACE_DST" && ! -e "\$RACE_DST" ]]; then
  mkdir -p "\$RACE_DST"
  echo 'someone-else' >"\$RACE_DST/theirs.txt"
fi
exec "$real" "\$@"
STUB
  chmod +x "$bin/mv"
  PATH="$bin:$PATH"
}

@test "target that appears during the move is not nested into, and is reported" {
  stub_npm
  stub_racing_mv
  unset SKIP_NPM_INSTALL
  export RACE_DST="$CLAUDE_PLUGIN_DATA/dashboard"

  run "$SCRIPT"
  [ "$status" -eq 5 ]
  [[ "$output" == *"appeared while this run was working"* ]]
  # The other party's directory holds exactly what it held: nothing of ours.
  [ "$(find "$RACE_DST" -mindepth 1 | wc -l | tr -d '[:space:]')" -eq 1 ]
  [ "$(cat "$RACE_DST/theirs.txt")" = "someone-else" ]
  assert_no_staging_left
}

@test "node_modules that appears during the move is not nested into, and is reported" {
  stub_npm
  run "$SCRIPT"
  [ "$status" -eq 0 ]
  stub_racing_mv
  unset SKIP_NPM_INSTALL
  export RACE_DST="$CLAUDE_PLUGIN_DATA/dashboard/node_modules"

  run "$SCRIPT"
  [ "$status" -eq 5 ]
  [[ "$output" == *"appeared while this run was working"* ]]
  [ "$(find "$RACE_DST" -mindepth 1 | wc -l | tr -d '[:space:]')" -eq 1 ]
  [ ! -e "$RACE_DST/complete" ]
  assert_no_staging_left
}

@test "dangling package-lock.json symlink is refused, not written through" {
  stub_npm
  run "$SCRIPT"
  [ "$status" -eq 0 ]
  unset SKIP_NPM_INSTALL
  local dest="$CLAUDE_PLUGIN_DATA/dashboard" outside="$BATS_TEST_TMPDIR/outside/lock.json"
  mkdir -p "$BATS_TEST_TMPDIR/outside"
  rm "$dest/package-lock.json"
  ln -s "$outside" "$dest/package-lock.json"

  run "$SCRIPT"
  [ "$status" -eq 1 ]
  [[ "$output" == *"package-lock.json is a symlink"* ]]
  [ ! -e "$outside" ]
  [ "$(npm_calls)" -eq 0 ]
  [ ! -e "$dest/node_modules" ]
  assert_no_staging_left
}

@test "a regular file named node_modules does not count as installed" {
  stub_npm
  run "$SCRIPT"
  [ "$status" -eq 0 ]
  unset SKIP_NPM_INSTALL
  printf '%s\n' 'not a directory' >"$CLAUDE_PLUGIN_DATA/dashboard/node_modules"

  run "$SCRIPT"
  [ "$status" -eq 1 ]
  [[ "$output" == *"node_modules is not a directory"* ]]
  [ "$(npm_calls)" -eq 0 ]
}

@test "symlinked node_modules and symlinked target are refused" {
  stub_npm
  run "$SCRIPT"
  [ "$status" -eq 0 ]
  unset SKIP_NPM_INSTALL
  mkdir -p "$BATS_TEST_TMPDIR/elsewhere"
  ln -s "$BATS_TEST_TMPDIR/elsewhere" "$CLAUDE_PLUGIN_DATA/dashboard/node_modules"

  run "$SCRIPT"
  [ "$status" -eq 1 ]
  [[ "$output" == *"node_modules is a symlink"* ]]

  run "$SCRIPT" "$CLAUDE_PLUGIN_DATA/linked"
  [ "$status" -eq 0 ]
  rm -rf "$CLAUDE_PLUGIN_DATA/linked"
  ln -s "$BATS_TEST_TMPDIR/elsewhere" "$CLAUDE_PLUGIN_DATA/linked"
  run "$SCRIPT" "$CLAUDE_PLUGIN_DATA/linked"
  [ "$status" -eq 1 ]
  [[ "$output" == *"linked is a symlink"* ]]
  [ "$(npm_calls)" -eq 1 ]
  [ -z "$(ls -A "$BATS_TEST_TMPDIR/elsewhere")" ]
}

@test "trailing slash or /. does not get a symlinked target past the refusal" {
  stub_npm
  unset SKIP_NPM_INSTALL
  # What the link points at looks like an uninstalled dashboard, so a script
  # that followed the link would install into it.
  local referent="$BATS_TEST_TMPDIR/referent" form
  mkdir -p "$referent"
  cp "$CLAUDE_PLUGIN_ROOT/skills/marketplace-scout/assets/dashboard/package.json" "$referent/package.json"
  ln -s "$referent" "$CLAUDE_PLUGIN_DATA/linked"

  # `[ ]` and grep, not `[[ ]]`: under bash 3.2 bats cannot fail a test on a
  # `[[ ]]` that is not its last command.
  for form in "linked" "linked/" "linked//" "linked/." "linked/./"; do
    run "$SCRIPT" "$CLAUDE_PLUGIN_DATA/$form"
    [ "$status" -eq 1 ]
    printf '%s\n' "$output" | grep -q "linked is a symlink"
    [ "$(npm_calls)" -eq 0 ]
    [ "$(ls -A "$referent")" = "package.json" ]
  done
  assert_no_staging_left
}

@test "trailing slash on a plain target is the same target" {
  stub_npm
  unset SKIP_NPM_INSTALL
  run "$SCRIPT" "$CLAUDE_PLUGIN_DATA/custom/"
  [ "$status" -eq 0 ]
  printf '%s\n' "$output" | grep -qx "dashboard ready at $CLAUDE_PLUGIN_DATA/custom"
  [ -f "$CLAUDE_PLUGIN_DATA/custom/node_modules/complete" ]

  run "$SCRIPT" "$CLAUDE_PLUGIN_DATA/custom/."
  [ "$status" -eq 0 ]
  printf '%s\n' "$output" | grep -qx "dashboard present at $CLAUDE_PLUGIN_DATA/custom; not overwriting"
  [ "$(npm_calls)" -eq 1 ]
}

@test "SKIP_NPM_INSTALL scaffolds without calling npm" {
  stub_npm

  run "$SCRIPT"
  [ "$status" -eq 0 ]
  [ -f "$CLAUDE_PLUGIN_DATA/dashboard/package-lock.json" ]
  [ ! -e "$CLAUDE_PLUGIN_DATA/dashboard/node_modules" ]
  [ ! -e "$NPM_LOG" ]
  assert_no_staging_left
}

@test "missing package-lock.json exits 1 and scaffolds nothing" {
  stub_npm
  unset SKIP_NPM_INSTALL
  rm "$CLAUDE_PLUGIN_ROOT/skills/marketplace-scout/assets/dashboard/package-lock.json"

  run "$SCRIPT"
  [ "$status" -eq 1 ]
  [[ "$output" == *"package-lock.json"* ]]
  [ ! -e "$CLAUDE_PLUGIN_DATA/dashboard" ]
  [ ! -e "$NPM_LOG" ]
}

@test "second run does not overwrite a modified file" {
  run "$SCRIPT"
  [ "$status" -eq 0 ]

  printf '%s\n' 'user-edit' >"$CLAUDE_PLUGIN_DATA/dashboard/src/marker.txt"

  run "$SCRIPT"
  [ "$status" -eq 0 ]
  [[ "$output" == *"dashboard present at $CLAUDE_PLUGIN_DATA/dashboard; not overwriting"* ]]
  [ "$(cat "$CLAUDE_PLUGIN_DATA/dashboard/src/marker.txt")" = "user-edit" ]
}

@test "legacy ./dashboard in cwd triggers exit 3 and the mv instruction" {
  mkdir -p ./dashboard
  printf '%s\n' 'legacy' >./dashboard/keep-me.txt

  run "$SCRIPT"
  [ "$status" -eq 3 ]
  [[ "$output" == *"mv ./dashboard "* ]]
  [[ "$output" == *"$CLAUDE_PLUGIN_DATA/dashboard"* ]]
  [ -f ./dashboard/keep-me.txt ]
  [ ! -e "$CLAUDE_PLUGIN_DATA/dashboard" ]
}

@test "missing env exits 2" {
  run env -u CLAUDE_PLUGIN_DATA "$SCRIPT"
  [ "$status" -eq 2 ]

  run env -u CLAUDE_PLUGIN_ROOT "$SCRIPT"
  [ "$status" -eq 2 ]
}
