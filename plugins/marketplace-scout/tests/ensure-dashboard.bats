#!/usr/bin/env bats
#
# ensure-dashboard.sh: first-run scaffold under CLAUDE_PLUGIN_DATA.
# Never point CLAUDE_PLUGIN_DATA or CLAUDE_PLUGIN_ROOT at a real ~/.claude.

setup() {
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
# its arguments, its cwd, and whether the lockfile is beside it.
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
STUB
  chmod +x "$bin/npm"
  PATH="$bin:$PATH"
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

@test "installs with npm ci --ignore-scripts in the target, lockfile beside package.json" {
  stub_npm
  unset SKIP_NPM_INSTALL

  run "$SCRIPT"
  [ "$status" -eq 0 ]

  [ "$(grep -c '^args=' "$NPM_LOG")" -eq 1 ]
  grep -qx 'args=ci --ignore-scripts' "$NPM_LOG"
  grep -qx "cwd=$CLAUDE_PLUGIN_DATA/dashboard" "$NPM_LOG"
  grep -qx 'lockfile=present' "$NPM_LOG"
}

@test "SKIP_NPM_INSTALL scaffolds without calling npm" {
  stub_npm

  run "$SCRIPT"
  [ "$status" -eq 0 ]
  [ -f "$CLAUDE_PLUGIN_DATA/dashboard/package-lock.json" ]
  [ ! -e "$NPM_LOG" ]
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
