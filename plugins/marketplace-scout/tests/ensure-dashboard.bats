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
# It keeps a copy of the package.json and package-lock.json it ran beside
# ($NPM_LOG.manifest, $NPM_LOG.lock). NPM_STUB_APPEND names a file it adds a
# line to, standing in for a user who edits that file while npm is running.
# NPM_STUB_DO is a command it runs at that same moment, for anything else
# that can happen to the target during the install.
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
if [[ -f package.json ]]; then cp package.json "$NPM_LOG.manifest"; fi
if [[ -f package-lock.json ]]; then cp package-lock.json "$NPM_LOG.lock"; fi
if [[ -n "${NPM_STUB_APPEND:-}" ]]; then echo 'edited during the install' >>"$NPM_STUB_APPEND"; fi
if [[ -n "${NPM_STUB_DO:-}" ]]; then eval "$NPM_STUB_DO"; fi
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

# --- Targets an earlier release scaffolded and never installed ---------------
#
# tests/fixtures holds, byte for byte, the package.json files earlier releases
# shipped and the 1.3.0 lockfile. They are pinned copies on purpose: copying
# package.json from the revision under test cannot notice that the plugin's
# own file has since changed, which is how 1.3.1 first broke this recovery.
#   shipped-manifest-first.json   first dashboard (no zod)
#   shipped-manifest-1.3.0.json   dashboard v2 through 1.3.0 (zod ^3.24.3)
#   shipped-lockfile-1.3.0.json   the lockfile 1.3.0 introduced (zod 3.25.76)

# earlier_target <manifest fixture> [<lockfile fixture>]: a dashboard as an
# earlier release left it, with a file of the user's and no node_modules.
earlier_target() {
  FIXTURES="$PLUGIN_ROOT/tests/fixtures"
  ASSETS="$CLAUDE_PLUGIN_ROOT/skills/marketplace-scout/assets/dashboard"
  DEST="$CLAUDE_PLUGIN_DATA/dashboard"
  mkdir -p "$DEST/src"
  cp "$FIXTURES/$1" "$DEST/package.json"
  if [ -n "${2:-}" ]; then
    cp "$FIXTURES/$2" "$DEST/package-lock.json"
  fi
  printf '%s\n' 'user-edit' >"$DEST/src/marker.txt"
}

# The target holds the plugin's current pair, npm ran against that pair, and
# the user's file is as it was.
assert_on_plugin_pair() {
  cmp -s "$DEST/package.json" "$ASSETS/package.json"
  cmp -s "$DEST/package-lock.json" "$ASSETS/package-lock.json"
  cmp -s "$NPM_LOG.manifest" "$ASSETS/package.json"
  cmp -s "$NPM_LOG.lock" "$ASSETS/package-lock.json"
  [ -f "$DEST/node_modules/complete" ]
  [ "$(cat "$DEST/src/marker.txt")" = "user-edit" ]
  assert_no_staging_left
}

@test "pre-lockfile target with the package.json 1.3.0 and earlier shipped moves to the plugin's pinned pair" {
  stub_npm
  unset SKIP_NPM_INSTALL
  earlier_target shipped-manifest-1.3.0.json

  run "$SCRIPT"
  [ "$status" -eq 0 ]
  printf '%s\n' "$output" | grep -qx "package.json in $DEST came unmodified from an earlier release; replaced with this release's"
  printf '%s\n' "$output" | grep -qx "dashboard ready at $DEST (dependencies installed into the existing copy)"
  [ "$(npm_calls)" -eq 1 ]
  grep -qx 'args=ci --ignore-scripts' "$NPM_LOG"
  assert_on_plugin_pair
}

@test "pre-lockfile target with the first dashboard's package.json moves to the plugin's pinned pair" {
  stub_npm
  unset SKIP_NPM_INSTALL
  earlier_target shipped-manifest-first.json

  run "$SCRIPT"
  [ "$status" -eq 0 ]
  printf '%s\n' "$output" | grep -q "^package.json in $DEST came unmodified from an earlier release"
  [ "$(npm_calls)" -eq 1 ]
  assert_on_plugin_pair
}

@test "pre-lockfile target with an edited copy of an earlier release's package.json is still refused" {
  stub_npm
  unset SKIP_NPM_INSTALL
  earlier_target shipped-manifest-1.3.0.json
  local edited="$BATS_TEST_TMPDIR/edited.json"
  sed 's/"zod": "^3.24.3"/"zod": "^3.25.0"/' "$FIXTURES/shipped-manifest-1.3.0.json" >"$edited"
  run cmp -s "$edited" "$FIXTURES/shipped-manifest-1.3.0.json"
  [ "$status" -ne 0 ]
  cp "$edited" "$DEST/package.json"

  run "$SCRIPT"
  [ "$status" -eq 1 ]
  printf '%s\n' "$output" | grep -q "package.json is not the plugin's; refusing to install unpinned dependencies"
  [ "$(npm_calls)" -eq 0 ]
  cmp -s "$DEST/package.json" "$edited"
  [ ! -e "$DEST/package-lock.json" ]
  [ ! -e "$DEST/node_modules" ]
  assert_no_staging_left
}

@test "one added byte is enough for an earlier release's package.json to be refused" {
  stub_npm
  unset SKIP_NPM_INSTALL
  earlier_target shipped-manifest-1.3.0.json
  printf '\n' >>"$DEST/package.json"

  run "$SCRIPT"
  [ "$status" -eq 1 ]
  printf '%s\n' "$output" | grep -q "refusing to install unpinned dependencies"
  [ "$(npm_calls)" -eq 0 ]
  [ ! -e "$DEST/node_modules" ]
}

@test "never-installed 1.3.0 scaffold moves to the plugin's pinned pair, not its superseded lockfile" {
  stub_npm
  unset SKIP_NPM_INSTALL
  earlier_target shipped-manifest-1.3.0.json shipped-lockfile-1.3.0.json

  run "$SCRIPT"
  [ "$status" -eq 0 ]
  printf '%s\n' "$output" | grep -qx "package.json and package-lock.json in $DEST came unmodified from an earlier release; replaced with this release's"
  [ "$(npm_calls)" -eq 1 ]
  assert_on_plugin_pair
}

@test "a move that stopped half way (current package.json, 1.3.0 lockfile) is finished" {
  stub_npm
  unset SKIP_NPM_INSTALL
  earlier_target shipped-manifest-1.3.0.json shipped-lockfile-1.3.0.json
  cp "$ASSETS/package.json" "$DEST/package.json"

  run "$SCRIPT"
  [ "$status" -eq 0 ]
  printf '%s\n' "$output" | grep -qx "package-lock.json in $DEST came unmodified from an earlier release; replaced with this release's"
  assert_on_plugin_pair
}

@test "a user's own lockfile beside an earlier release's package.json is installed as it is" {
  stub_npm
  unset SKIP_NPM_INSTALL
  earlier_target shipped-manifest-1.3.0.json
  local mine="$BATS_TEST_TMPDIR/mine.json"
  printf '%s\n' '{"name":"mine","lockfileVersion":3,"packages":{}}' >"$mine"
  cp "$mine" "$DEST/package-lock.json"

  run "$SCRIPT"
  [ "$status" -eq 0 ]
  [ "$(npm_calls)" -eq 1 ]
  run grep -c "came unmodified" <<<"$output"
  [ "$output" = "0" ]
  cmp -s "$DEST/package.json" "$FIXTURES/shipped-manifest-1.3.0.json"
  cmp -s "$DEST/package-lock.json" "$mine"
  cmp -s "$NPM_LOG.manifest" "$FIXTURES/shipped-manifest-1.3.0.json"
  cmp -s "$NPM_LOG.lock" "$mine"
  [ -f "$DEST/node_modules/complete" ]
}

@test "an edited package.json beside the 1.3.0 lockfile is installed as it is" {
  stub_npm
  unset SKIP_NPM_INSTALL
  earlier_target shipped-manifest-1.3.0.json shipped-lockfile-1.3.0.json
  local edited="$BATS_TEST_TMPDIR/edited.json"
  sed 's/"private": true/"private": true, "description": "mine"/' "$FIXTURES/shipped-manifest-1.3.0.json" >"$edited"
  run cmp -s "$edited" "$FIXTURES/shipped-manifest-1.3.0.json"
  [ "$status" -ne 0 ]
  cp "$edited" "$DEST/package.json"

  run "$SCRIPT"
  [ "$status" -eq 0 ]
  [ "$(npm_calls)" -eq 1 ]
  cmp -s "$DEST/package.json" "$edited"
  cmp -s "$DEST/package-lock.json" "$FIXTURES/shipped-lockfile-1.3.0.json"
  cmp -s "$NPM_LOG.manifest" "$edited"
  cmp -s "$NPM_LOG.lock" "$FIXTURES/shipped-lockfile-1.3.0.json"
  [ -f "$DEST/node_modules/complete" ]
}

@test "failed install leaves an earlier release's package.json and lockfile as they were, then retries" {
  stub_npm
  unset SKIP_NPM_INSTALL
  earlier_target shipped-manifest-1.3.0.json shipped-lockfile-1.3.0.json

  run env NPM_STUB_EXIT=42 "$SCRIPT"
  [ "$status" -eq 4 ]
  cmp -s "$DEST/package.json" "$FIXTURES/shipped-manifest-1.3.0.json"
  cmp -s "$DEST/package-lock.json" "$FIXTURES/shipped-lockfile-1.3.0.json"
  [ ! -e "$DEST/node_modules" ]
  [ "$(cat "$DEST/src/marker.txt")" = "user-edit" ]
  assert_no_staging_left

  run "$SCRIPT"
  [ "$status" -eq 0 ]
  [ "$(npm_calls)" -eq 2 ]
  [ ! -e "$DEST/node_modules/half-installed" ]
  assert_on_plugin_pair
}

@test "package.json edited while npm runs is not replaced" {
  stub_npm
  unset SKIP_NPM_INSTALL
  earlier_target shipped-manifest-1.3.0.json
  local expected="$BATS_TEST_TMPDIR/expected.json"
  cp "$FIXTURES/shipped-manifest-1.3.0.json" "$expected"
  echo 'edited during the install' >>"$expected"

  run env NPM_STUB_APPEND="$DEST/package.json" "$SCRIPT"
  [ "$status" -eq 5 ]
  printf '%s\n' "$output" | grep -q "$DEST/package.json changed while this run was working; it was not replaced"
  cmp -s "$DEST/package.json" "$expected"
  [ ! -e "$DEST/package-lock.json" ]
  [ ! -e "$DEST/node_modules" ]
  assert_no_staging_left
}

@test "package-lock.json edited while npm runs is not replaced" {
  stub_npm
  unset SKIP_NPM_INSTALL
  earlier_target shipped-manifest-1.3.0.json shipped-lockfile-1.3.0.json
  local expected="$BATS_TEST_TMPDIR/expected.json"
  cp "$FIXTURES/shipped-lockfile-1.3.0.json" "$expected"
  echo 'edited during the install' >>"$expected"

  run env NPM_STUB_APPEND="$DEST/package-lock.json" "$SCRIPT"
  [ "$status" -eq 5 ]
  printf '%s\n' "$output" | grep -q "$DEST/package-lock.json changed while this run was working; it was not replaced"
  cmp -s "$DEST/package-lock.json" "$expected"
  # Nothing was touched: package.json is still the one that lockfile pins.
  cmp -s "$DEST/package.json" "$FIXTURES/shipped-manifest-1.3.0.json"
  # node_modules is the completion signal and never arrived, so the target
  # still counts as not installed.
  [ ! -e "$DEST/node_modules" ]
  assert_no_staging_left

  # The lockfile is now the user's, so the target installs from its own pair,
  # as it would have before this release.
  run "$SCRIPT"
  [ "$status" -eq 0 ]
  cmp -s "$NPM_LOG.manifest" "$FIXTURES/shipped-manifest-1.3.0.json"
  cmp -s "$NPM_LOG.lock" "$expected"
  cmp -s "$DEST/package.json" "$FIXTURES/shipped-manifest-1.3.0.json"
  cmp -s "$DEST/package-lock.json" "$expected"
  [ -f "$DEST/node_modules/complete" ]
}

# hook <tool> <path> <command> [after]: put a <tool> first on PATH that runs
# <command> once, just before its first call that has <path> as an argument
# ("after": just after that call), and otherwise is the real tool. <command>
# runs inside the stub, so $PPID there is the script under test. This is how
# a spec makes something happen to the target at one exact step.
hook() {
  local tool=$1 bin="$BATS_TEST_TMPDIR/hookbin" real
  real="$(command -v "$tool")"
  mkdir -p "$bin"
  printf '%s\n' "$2" >"$bin/$tool.at"
  printf '%s\n' "$3" >"$bin/$tool.do"
  rm -f "$bin/$tool.done" "$bin/$tool.after"
  if [ "${4:-}" = after ]; then
    : >"$bin/$tool.after"
  fi
  cat >"$bin/$tool" <<STUB
#!/usr/bin/env bash
hook_dir="$bin"
hook_tool="$tool"
read -r hook_at <"\$hook_dir/\$hook_tool.at"
if [[ ! -e "\$hook_dir/\$hook_tool.done" ]]; then
  for hook_arg in "\$@"; do
    if [[ "\$hook_arg" == "\$hook_at" ]]; then
      : >"\$hook_dir/\$hook_tool.done"
      if [[ -e "\$hook_dir/\$hook_tool.after" ]]; then
        "$real" "\$@"
        hook_rc=\$?
        source "\$hook_dir/\$hook_tool.do"
        exit "\$hook_rc"
      fi
      source "\$hook_dir/\$hook_tool.do"
      break
    fi
  done
fi
exec "$real" "\$@"
STUB
  chmod +x "$bin/$tool"
  case ":$PATH:" in
    *":$bin:"*) ;;
    *) PATH="$bin:$PATH" ;;
  esac
}

hook_fired() {
  [ -e "$BATS_TEST_TMPDIR/hookbin/$1.done" ]
}

# Nothing this run set aside or saved is left in the target.
assert_nothing_set_aside() {
  run find "$DEST" -name '*.set-aside.*'
  [ -z "$output" ]
}

# The target is the never-installed 1.3.0 scaffold it started as.
assert_still_1_3_0() {
  cmp -s "$DEST/package.json" "$FIXTURES/shipped-manifest-1.3.0.json"
  cmp -s "$DEST/package-lock.json" "$FIXTURES/shipped-lockfile-1.3.0.json"
  [ "$(cat "$DEST/src/marker.txt")" = "user-edit" ]
}

@test "package.json that becomes a directory during the move is not nested into" {
  stub_npm
  unset SKIP_NPM_INSTALL
  earlier_target shipped-manifest-1.3.0.json
  export RACE_DST="$DEST/package.json"
  # The new file is linked into the path the old one was moved out of. The
  # directory appears in between.
  hook ln "$RACE_DST" "mkdir -p '$RACE_DST'; echo 'someone-else' >'$RACE_DST/theirs.txt'"

  run "$SCRIPT"
  [ "$status" -eq 5 ]
  hook_fired ln
  printf '%s\n' "$output" | grep -q "$DEST/package.json was replaced while this run was working; it was left as it is now"
  [ "$(find "$RACE_DST" -mindepth 1 | wc -l | tr -d '[:space:]')" -eq 1 ]
  [ "$(cat "$RACE_DST/theirs.txt")" = "someone-else" ]
  [ ! -e "$DEST/package-lock.json" ]
  [ ! -e "$DEST/node_modules" ]
  assert_nothing_set_aside
  assert_no_staging_left
}

@test "package.json that is a symlink is refused, not replaced through" {
  stub_npm
  unset SKIP_NPM_INSTALL
  earlier_target shipped-manifest-1.3.0.json
  local outside="$BATS_TEST_TMPDIR/outside.json"
  cp "$FIXTURES/shipped-manifest-1.3.0.json" "$outside"
  rm "$DEST/package.json"
  ln -s "$outside" "$DEST/package.json"

  run "$SCRIPT"
  [ "$status" -eq 1 ]
  printf '%s\n' "$output" | grep -q "package.json is a symlink"
  [ "$(npm_calls)" -eq 0 ]
  cmp -s "$outside" "$FIXTURES/shipped-manifest-1.3.0.json"
  [ -L "$DEST/package.json" ]
}

# --- Something changes, fails or stops while the two files are exchanged -----
#
# The script validates the target after npm has finished, then moves an old
# file out, checks what it moved, and links the new one in. `hook` makes
# something happen at one of those steps.

@test "package.json edited after the last check, as it is taken out, keeps the edit" {
  stub_npm
  unset SKIP_NPM_INSTALL
  earlier_target shipped-manifest-1.3.0.json shipped-lockfile-1.3.0.json
  local edited="$BATS_TEST_TMPDIR/edited.json"
  cp "$FIXTURES/shipped-manifest-1.3.0.json" "$edited"
  printf '\n' >>"$edited"
  hook mv "$DEST/package.json" "printf '\n' >>'$DEST/package.json'"

  run "$SCRIPT"
  hook_fired mv
  [ "$status" -eq 5 ]
  printf '%s\n' "$output" | grep -q "$DEST/package.json changed while this run was working; it was not replaced"
  cmp -s "$DEST/package.json" "$edited"
  cmp -s "$DEST/package-lock.json" "$FIXTURES/shipped-lockfile-1.3.0.json"
  [ ! -e "$DEST/node_modules" ]
  assert_nothing_set_aside
  assert_no_staging_left

  # The edit makes the file the user's: the target installs from its own pair.
  run "$SCRIPT"
  [ "$status" -eq 0 ]
  cmp -s "$DEST/package.json" "$edited"
  cmp -s "$DEST/package-lock.json" "$FIXTURES/shipped-lockfile-1.3.0.json"
  cmp -s "$NPM_LOG.manifest" "$edited"
  [ -f "$DEST/node_modules/complete" ]
}

@test "package-lock.json edited after the last check, as it is taken out, keeps the edit and package.json goes back" {
  stub_npm
  unset SKIP_NPM_INSTALL
  earlier_target shipped-manifest-1.3.0.json shipped-lockfile-1.3.0.json
  local edited="$BATS_TEST_TMPDIR/edited.json"
  cp "$FIXTURES/shipped-lockfile-1.3.0.json" "$edited"
  printf '\n' >>"$edited"
  hook mv "$DEST/package-lock.json" "printf '\n' >>'$DEST/package-lock.json'"

  run "$SCRIPT"
  hook_fired mv
  [ "$status" -eq 5 ]
  printf '%s\n' "$output" | grep -q "$DEST/package-lock.json changed while this run was working; it was not replaced"
  printf '%s\n' "$output" | grep -q "$DEST/package.json was put back as it was"
  cmp -s "$DEST/package-lock.json" "$edited"
  # package.json was already out of the directory; it is back, unchanged.
  cmp -s "$DEST/package.json" "$FIXTURES/shipped-manifest-1.3.0.json"
  [ ! -e "$DEST/node_modules" ]
  assert_nothing_set_aside
  assert_no_staging_left

  run "$SCRIPT"
  [ "$status" -eq 0 ]
  cmp -s "$NPM_LOG.manifest" "$FIXTURES/shipped-manifest-1.3.0.json"
  cmp -s "$NPM_LOG.lock" "$edited"
  [ -f "$DEST/node_modules/complete" ]
}

@test "an edit and then a new file at the same path, both while the file is out: neither is lost" {
  stub_npm
  unset SKIP_NPM_INSTALL
  earlier_target shipped-manifest-1.3.0.json shipped-lockfile-1.3.0.json
  local edited="$BATS_TEST_TMPDIR/edited.json"
  cp "$FIXTURES/shipped-manifest-1.3.0.json" "$edited"
  printf '\n' >>"$edited"
  hook mv "$DEST/package.json" "printf '\n' >>'$DEST/package.json'"
  # The edited file is linked back to its path; a new file lands there first.
  hook ln "$DEST/package.json" "printf '%s\n' '{\"name\":\"theirs\"}' >'$DEST/package.json'"

  run "$SCRIPT"
  hook_fired mv
  hook_fired ln
  [ "$status" -eq 5 ]
  [ "$(cat "$DEST/package.json")" = '{"name":"theirs"}' ]
  local saved
  saved="$(find "$DEST" -name 'package.json.set-aside.*')"
  [ -n "$saved" ]
  cmp -s "$saved" "$edited"
  printf '%s\n' "$output" | grep -q "What it held before is saved as $saved"
  cmp -s "$DEST/package-lock.json" "$FIXTURES/shipped-lockfile-1.3.0.json"
  [ ! -e "$DEST/node_modules" ]
  assert_no_staging_left
}

@test "node_modules appearing while npm runs leaves both files as they were" {
  stub_npm
  unset SKIP_NPM_INSTALL
  earlier_target shipped-manifest-1.3.0.json shipped-lockfile-1.3.0.json

  run env NPM_STUB_DO="mkdir -p '$DEST/node_modules/zod' && echo 3.25.76 >'$DEST/node_modules/zod/theirs'" "$SCRIPT"
  [ "$status" -eq 5 ]
  printf '%s\n' "$output" | grep -q "$DEST/node_modules appeared while this run was working; nothing was overwritten"
  assert_still_1_3_0
  [ "$(cat "$DEST/node_modules/zod/theirs")" = "3.25.76" ]
  [ ! -e "$DEST/node_modules/complete" ]
  assert_nothing_set_aside
  assert_no_staging_left

  # What appeared is an install; it and the pair that matches it are kept.
  run "$SCRIPT"
  [ "$status" -eq 0 ]
  printf '%s\n' "$output" | grep -qx "dashboard present at $DEST; not overwriting"
  assert_still_1_3_0
  [ "$(npm_calls)" -eq 1 ]
}

@test "node_modules appearing after both files were exchanged puts both back" {
  stub_npm
  unset SKIP_NPM_INSTALL
  earlier_target shipped-manifest-1.3.0.json shipped-lockfile-1.3.0.json
  hook mv "$DEST/node_modules" "mkdir -p '$DEST/node_modules' && echo theirs >'$DEST/node_modules/theirs.txt'"

  run "$SCRIPT"
  hook_fired mv
  [ "$status" -eq 5 ]
  printf '%s\n' "$output" | grep -q "$DEST/node_modules appeared while this run was working; it was not overwritten"
  printf '%s\n' "$output" | grep -q "$DEST/package.json was put back as it was"
  printf '%s\n' "$output" | grep -q "$DEST/package-lock.json was put back as it was"
  assert_still_1_3_0
  [ "$(find "$DEST/node_modules" -mindepth 1 | wc -l | tr -d '[:space:]')" -eq 1 ]
  [ "$(cat "$DEST/node_modules/theirs.txt")" = "theirs" ]
  assert_nothing_set_aside
  assert_no_staging_left
}

@test "a current package.json that changes while npm runs stops the run" {
  stub_npm
  unset SKIP_NPM_INSTALL
  earlier_target shipped-manifest-1.3.0.json shipped-lockfile-1.3.0.json
  cp "$ASSETS/package.json" "$DEST/package.json"
  local edited="$BATS_TEST_TMPDIR/edited.json"
  cp "$FIXTURES/shipped-manifest-1.3.0.json" "$edited"
  printf '\n' >>"$edited"

  run env NPM_STUB_DO="cp '$edited' '$DEST/package.json'" "$SCRIPT"
  [ "$status" -eq 5 ]
  printf '%s\n' "$output" | grep -q "$DEST/package.json changed while this run was working; it was not replaced"
  cmp -s "$DEST/package.json" "$edited"
  cmp -s "$DEST/package-lock.json" "$FIXTURES/shipped-lockfile-1.3.0.json"
  [ ! -e "$DEST/node_modules" ]
  assert_nothing_set_aside
  assert_no_staging_left
}

@test "a current package-lock.json that changes while npm runs stops the run" {
  stub_npm
  unset SKIP_NPM_INSTALL
  earlier_target shipped-manifest-1.3.0.json
  cp "$ASSETS/package-lock.json" "$DEST/package-lock.json"
  local edited="$BATS_TEST_TMPDIR/edited.json"
  cp "$FIXTURES/shipped-lockfile-1.3.0.json" "$edited"
  printf '\n' >>"$edited"

  run env NPM_STUB_DO="cp '$edited' '$DEST/package-lock.json'" "$SCRIPT"
  [ "$status" -eq 5 ]
  printf '%s\n' "$output" | grep -q "$DEST/package-lock.json changed while this run was working; it was not replaced"
  cmp -s "$DEST/package-lock.json" "$edited"
  cmp -s "$DEST/package.json" "$FIXTURES/shipped-manifest-1.3.0.json"
  [ ! -e "$DEST/node_modules" ]
  assert_nothing_set_aside
  assert_no_staging_left
}

@test "a target installing from its own pair is not completed when a file changes while npm runs" {
  stub_npm
  unset SKIP_NPM_INSTALL
  earlier_target shipped-manifest-1.3.0.json
  printf '%s\n' '{"name":"mine","version":"1.0.0"}' >"$DEST/package.json"
  printf '%s\n' '{"name":"mine","lockfileVersion":3,"packages":{}}' >"$DEST/package-lock.json"

  run env NPM_STUB_APPEND="$DEST/package.json" "$SCRIPT"
  [ "$status" -eq 5 ]
  printf '%s\n' "$output" | grep -q "$DEST/package.json changed while this run was working"
  [ ! -e "$DEST/node_modules" ]
  assert_no_staging_left
}

@test "a file that becomes a symlink while npm runs is refused and nothing is touched" {
  stub_npm
  unset SKIP_NPM_INSTALL
  earlier_target shipped-manifest-1.3.0.json shipped-lockfile-1.3.0.json
  local outside="$BATS_TEST_TMPDIR/outside.json"
  cp "$FIXTURES/shipped-lockfile-1.3.0.json" "$outside"

  run env NPM_STUB_DO="rm '$DEST/package-lock.json' && ln -s '$outside' '$DEST/package-lock.json'" "$SCRIPT"
  [ "$status" -eq 1 ]
  printf '%s\n' "$output" | grep -q "package-lock.json is a symlink"
  cmp -s "$DEST/package.json" "$FIXTURES/shipped-manifest-1.3.0.json"
  [ -L "$DEST/package-lock.json" ]
  cmp -s "$outside" "$FIXTURES/shipped-lockfile-1.3.0.json"
  [ ! -e "$DEST/node_modules" ]
  assert_no_staging_left
}

# A `cat` that writes 32 bytes of a lockfile and then fails, as a full disk
# would. The lockfile used to be written through `cat` straight to its final
# name; it is now linked in whole, so this never runs for it.
stub_partial_cat() {
  local bin="$BATS_TEST_TMPDIR/catbin" real
  real="$(command -v cat)"
  mkdir -p "$bin"
  cat >"$bin/cat" <<STUB
#!/usr/bin/env bash
if [[ "\$#" -eq 1 && "\$1" == */package-lock.json ]]; then
  head -c 32 "\$1"
  exit 1
fi
exec "$real" "\$@"
STUB
  chmod +x "$bin/cat"
  PATH="$bin:$PATH"
}

@test "a lockfile writer that fails part way cannot leave a partial package-lock.json" {
  stub_npm
  unset SKIP_NPM_INSTALL
  earlier_target shipped-manifest-1.3.0.json
  stub_partial_cat

  run "$SCRIPT"
  [ "$status" -eq 0 ]
  assert_on_plugin_pair
}

# Make both ways of putting a file at <path> fail, as a directory that became
# read-only would: `ln` and `mv` refuse that one destination.
stub_unwritable() {
  local bin="$BATS_TEST_TMPDIR/rofsbin" tool real
  mkdir -p "$bin"
  for tool in ln mv; do
    real="$(command -v "$tool")"
    cat >"$bin/$tool" <<STUB
#!/usr/bin/env bash
if [[ "\${@: -1}" == "\$UNWRITABLE" ]]; then
  echo "$tool: \$UNWRITABLE: Read-only file system" >&2
  exit 1
fi
exec "$real" "\$@"
STUB
    chmod +x "$bin/$tool"
  done
  PATH="$bin:$PATH"
}

@test "package-lock.json that cannot be written puts package.json back and says so" {
  stub_npm
  unset SKIP_NPM_INSTALL
  earlier_target shipped-manifest-1.3.0.json
  stub_unwritable

  run env UNWRITABLE="$DEST/package-lock.json" "$SCRIPT"
  [ "$status" -eq 4 ]
  printf '%s\n' "$output" | grep -q "could not write $DEST/package-lock.json"
  printf '%s\n' "$output" | grep -q "$DEST/package.json was put back as it was"
  run grep -c "appeared" <<<"$output"
  [ "$output" = "0" ]
  cmp -s "$DEST/package.json" "$FIXTURES/shipped-manifest-1.3.0.json"
  [ ! -e "$DEST/package-lock.json" ]
  [ ! -e "$DEST/node_modules" ]
  [ "$(cat "$DEST/src/marker.txt")" = "user-edit" ]
  assert_nothing_set_aside
  assert_no_staging_left

  run "$SCRIPT"
  [ "$status" -eq 0 ]
  assert_on_plugin_pair
}

@test "a file that can be neither written nor put back stays set aside, and the next run puts it back" {
  stub_npm
  unset SKIP_NPM_INSTALL
  earlier_target shipped-manifest-1.3.0.json shipped-lockfile-1.3.0.json
  stub_unwritable

  run env UNWRITABLE="$DEST/package.json" "$SCRIPT"
  [ "$status" -eq 4 ]
  printf '%s\n' "$output" | grep -q "could not write $DEST/package.json"
  printf '%s\n' "$output" | grep -q "$DEST/package.json was not put back; see above"
  printf '%s\n' "$output" | grep -q "It was left in place; the next run puts it back"
  # Nothing claims it was put back, and the lockfile, taken out second, is.
  run grep -c "package.json was put back" <<<"$output"
  [ "$output" = "0" ]
  [ ! -e "$DEST/package.json" ]
  cmp -s "$DEST/package-lock.json" "$FIXTURES/shipped-lockfile-1.3.0.json"
  [ ! -e "$DEST/node_modules" ]
  local kept
  kept="$(find "$CLAUDE_PLUGIN_DATA" -path '*/set-aside.dashboard/was.*.package.json')"
  cmp -s "$kept" "$FIXTURES/shipped-manifest-1.3.0.json"

  run "$SCRIPT"
  [ "$status" -eq 0 ]
  printf '%s\n' "$output" | grep -q "put $DEST/package.json back; an earlier run stopped while it was out of the directory"
  assert_recovered_on_plugin_pair
}

@test "a lockfile this run created is removed again when node_modules cannot be placed" {
  stub_npm
  unset SKIP_NPM_INSTALL
  earlier_target shipped-manifest-1.3.0.json
  cp "$ASSETS/package.json" "$DEST/package.json"
  hook mv "$DEST/node_modules" "mkdir -p '$DEST/node_modules' && echo theirs >'$DEST/node_modules/theirs.txt'"

  run "$SCRIPT"
  hook_fired mv
  [ "$status" -eq 5 ]
  printf '%s\n' "$output" | grep -q "$DEST/package-lock.json, which this run had created, was removed again"
  [ ! -e "$DEST/package-lock.json" ]
  cmp -s "$DEST/package.json" "$ASSETS/package.json"
  [ "$(find "$DEST/node_modules" -mindepth 1 | wc -l | tr -d '[:space:]')" -eq 1 ]
  assert_nothing_set_aside
  assert_no_staging_left
}

@test "SIGTERM while the files are exchanged is held until the target is complete" {
  stub_npm
  unset SKIP_NPM_INSTALL
  earlier_target shipped-manifest-1.3.0.json
  hook ln "$DEST/package-lock.json" 'kill -TERM "$PPID"'

  run "$SCRIPT"
  hook_fired ln
  [ "$status" -eq 143 ]
  printf '%s\n' "$output" | grep -qx "dashboard ready at $DEST (dependencies installed into the existing copy)"
  assert_on_plugin_pair
  assert_nothing_set_aside

  run "$SCRIPT"
  [ "$status" -eq 0 ]
  printf '%s\n' "$output" | grep -qx "dashboard present at $DEST; not overwriting"
}

@test "without hard links the files are still exchanged, by rename" {
  stub_npm
  unset SKIP_NPM_INSTALL
  earlier_target shipped-manifest-1.3.0.json shipped-lockfile-1.3.0.json
  local bin="$BATS_TEST_TMPDIR/nolnbin"
  mkdir -p "$bin"
  printf '%s\n' '#!/usr/bin/env bash' 'echo "ln: Operation not supported" >&2' 'exit 1' >"$bin/ln"
  chmod +x "$bin/ln"
  PATH="$bin:$PATH"

  run "$SCRIPT"
  [ "$status" -eq 0 ]
  assert_on_plugin_pair
  assert_nothing_set_aside
}

@test "an unreadable package.json is reported as unreadable" {
  [ "$(id -u)" -ne 0 ] || skip "root reads any file"
  stub_npm
  unset SKIP_NPM_INSTALL
  earlier_target shipped-manifest-1.3.0.json
  chmod 000 "$DEST/package.json"

  run "$SCRIPT"
  chmod 644 "$DEST/package.json"
  [ "$status" -eq 1 ]
  printf '%s\n' "$output" | grep -q "$DEST/package.json cannot be read; fix its permissions and run again"
  run grep -c "sha256sum" <<<"$output"
  [ "$output" = "0" ]
  [ "$(npm_calls)" -eq 0 ]
  cmp -s "$DEST/package.json" "$FIXTURES/shipped-manifest-1.3.0.json"
  [ ! -e "$DEST/node_modules" ]
}

@test "an unreadable package-lock.json is reported as unreadable" {
  [ "$(id -u)" -ne 0 ] || skip "root reads any file"
  stub_npm
  unset SKIP_NPM_INSTALL
  earlier_target shipped-manifest-1.3.0.json shipped-lockfile-1.3.0.json
  chmod 000 "$DEST/package-lock.json"

  run "$SCRIPT"
  chmod 644 "$DEST/package-lock.json"
  [ "$status" -eq 1 ]
  printf '%s\n' "$output" | grep -q "$DEST/package-lock.json cannot be read; fix its permissions and run again"
  [ "$(npm_calls)" -eq 0 ]
  assert_still_1_3_0
}

# --- A run killed outright (SIGKILL) between two steps of the exchange -------
#
# Nothing can run in the killed script, so its staging directory stays beside
# the target, holding what was out of the directory at that moment. Each spec
# kills at one step (the hooked tool dies with the script, so that step does
# not happen), shows the state that leaves, and runs again.

# The killed run's staging directory is still there and holds nothing that
# was taken out of the target.
assert_killed_staging_is_spent() {
  local left
  left="$(find "$CLAUDE_PLUGIN_DATA" -maxdepth 1 -name '.dashboard-staging.*')"
  [ -n "$left" ]
  [ "$(printf '%s\n' "$left" | wc -l | tr -d '[:space:]')" -eq 1 ]
  [ ! -e "$left/set-aside.dashboard" ]
}

assert_recovered_on_plugin_pair() {
  cmp -s "$DEST/package.json" "$ASSETS/package.json"
  cmp -s "$DEST/package-lock.json" "$ASSETS/package-lock.json"
  cmp -s "$NPM_LOG.manifest" "$ASSETS/package.json"
  cmp -s "$NPM_LOG.lock" "$ASSETS/package-lock.json"
  [ -f "$DEST/node_modules/complete" ]
  [ "$(cat "$DEST/src/marker.txt")" = "user-edit" ]
  assert_nothing_set_aside
  assert_killed_staging_is_spent
}

@test "killed with package.json out of the directory: the next run puts it back and finishes" {
  stub_npm
  unset SKIP_NPM_INSTALL
  earlier_target shipped-manifest-1.3.0.json shipped-lockfile-1.3.0.json
  hook mv "$DEST/package-lock.json" 'kill -KILL "$PPID"; exit 1'

  run "$SCRIPT"
  hook_fired mv
  [ "$status" -eq 137 ]
  [ ! -e "$DEST/package.json" ]
  cmp -s "$DEST/package-lock.json" "$FIXTURES/shipped-lockfile-1.3.0.json"
  [ ! -e "$DEST/node_modules" ]

  run "$SCRIPT"
  [ "$status" -eq 0 ]
  printf '%s\n' "$output" | grep -q "put $DEST/package.json back; an earlier run stopped while it was out of the directory"
  printf '%s\n' "$output" | grep -q "was left by a run that stopped part way"
  assert_recovered_on_plugin_pair
}

@test "killed with both files out of the directory: the next run puts them back and finishes" {
  stub_npm
  unset SKIP_NPM_INSTALL
  earlier_target shipped-manifest-1.3.0.json shipped-lockfile-1.3.0.json
  hook ln "$DEST/package.json" 'kill -KILL "$PPID"; exit 1'

  run "$SCRIPT"
  hook_fired ln
  [ "$status" -eq 137 ]
  [ ! -e "$DEST/package.json" ]
  [ ! -e "$DEST/package-lock.json" ]

  # Even a run that installs nothing puts the files back.
  run env SKIP_NPM_INSTALL=1 "$SCRIPT"
  [ "$status" -eq 0 ]
  assert_still_1_3_0
  [ "$(npm_calls)" -eq 1 ]

  run "$SCRIPT"
  [ "$status" -eq 0 ]
  assert_recovered_on_plugin_pair
}

@test "killed with the new package.json in and the lockfile out: the next run finishes" {
  stub_npm
  unset SKIP_NPM_INSTALL
  earlier_target shipped-manifest-1.3.0.json shipped-lockfile-1.3.0.json
  hook ln "$DEST/package-lock.json" 'kill -KILL "$PPID"; exit 1'

  run "$SCRIPT"
  hook_fired ln
  [ "$status" -eq 137 ]
  cmp -s "$DEST/package.json" "$ASSETS/package.json"
  [ ! -e "$DEST/package-lock.json" ]
  [ ! -e "$DEST/node_modules" ]

  run "$SCRIPT"
  [ "$status" -eq 0 ]
  assert_recovered_on_plugin_pair
}

@test "killed on a pre-lockfile target with the new package.json in and no lockfile yet: the next run finishes" {
  stub_npm
  unset SKIP_NPM_INSTALL
  earlier_target shipped-manifest-1.3.0.json
  hook ln "$DEST/package-lock.json" 'kill -KILL "$PPID"; exit 1'

  run "$SCRIPT"
  hook_fired ln
  [ "$status" -eq 137 ]
  cmp -s "$DEST/package.json" "$ASSETS/package.json"
  [ ! -e "$DEST/package-lock.json" ]

  run "$SCRIPT"
  [ "$status" -eq 0 ]
  assert_recovered_on_plugin_pair
}

@test "killed with both new files in and no node_modules: the next run finishes" {
  stub_npm
  unset SKIP_NPM_INSTALL
  earlier_target shipped-manifest-1.3.0.json shipped-lockfile-1.3.0.json
  hook mv "$DEST/node_modules" 'kill -KILL "$PPID"; exit 1'

  run "$SCRIPT"
  hook_fired mv
  [ "$status" -eq 137 ]
  cmp -s "$DEST/package.json" "$ASSETS/package.json"
  cmp -s "$DEST/package-lock.json" "$ASSETS/package-lock.json"
  [ ! -e "$DEST/node_modules" ]

  run "$SCRIPT"
  [ "$status" -eq 0 ]
  assert_recovered_on_plugin_pair
}

@test "killed just after node_modules arrived: the target is complete and the leftovers are dropped" {
  stub_npm
  unset SKIP_NPM_INSTALL
  earlier_target shipped-manifest-1.3.0.json shipped-lockfile-1.3.0.json
  hook mv "$DEST/node_modules" 'kill -KILL "$PPID"; exit 1' after

  run "$SCRIPT"
  hook_fired mv
  [ "$status" -eq 137 ]
  [ -f "$DEST/node_modules/complete" ]

  run "$SCRIPT"
  [ "$status" -eq 0 ]
  printf '%s\n' "$output" | grep -qx "dashboard present at $DEST; not overwriting"
  [ "$(npm_calls)" -eq 1 ]
  assert_recovered_on_plugin_pair
}

# only_tools <name>...: a directory holding links to just those commands, to
# use as the whole PATH of one run.
only_tools() {
  local bin="$BATS_TEST_TMPDIR/only" tool
  mkdir -p "$bin"
  for tool in "$@"; do
    ln -s "$(command -v "$tool")" "$bin/$tool"
  done
  printf '%s\n' "$bin"
}

@test "with no sha256 tool an earlier release's package.json is refused, not guessed at" {
  unset SKIP_NPM_INSTALL
  earlier_target shipped-manifest-1.3.0.json
  local bin
  bin="$(only_tools bash cmp)"

  run env PATH="$bin" "$SCRIPT"
  [ "$status" -eq 1 ]
  printf '%s\n' "$output" | grep -q "With no sha256sum or shasum it cannot be checked against earlier releases; refusing to install unpinned dependencies"
  cmp -s "$DEST/package.json" "$FIXTURES/shipped-manifest-1.3.0.json"
  [ ! -e "$DEST/package-lock.json" ]
  [ ! -e "$DEST/node_modules" ]
}

@test "sha256sum alone recognises an earlier release's package.json" {
  command -v sha256sum >/dev/null || skip "no sha256sum on this machine"
  stub_npm
  unset SKIP_NPM_INSTALL
  earlier_target shipped-manifest-1.3.0.json shipped-lockfile-1.3.0.json
  local bin
  bin="$(only_tools bash cmp dirname mkdir mktemp cp mv ln cat rm rmdir npm sha256sum)"

  run env PATH="$bin" "$SCRIPT"
  [ "$status" -eq 0 ]
  assert_on_plugin_pair
}

@test "shasum alone recognises an earlier release's package.json" {
  command -v shasum >/dev/null || skip "no shasum on this machine"
  stub_npm
  unset SKIP_NPM_INSTALL
  earlier_target shipped-manifest-1.3.0.json shipped-lockfile-1.3.0.json
  local bin
  bin="$(only_tools bash cmp dirname mkdir mktemp cp mv ln cat rm rmdir npm shasum)"

  run env PATH="$bin" "$SCRIPT"
  [ "$status" -eq 0 ]
  assert_on_plugin_pair
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
