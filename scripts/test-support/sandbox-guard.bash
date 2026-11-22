# shellcheck shell=bash
#
# Sandbox guard for every bats spec in this repository.
#
# The scripts under test fall back to the real Claude Code directories when
# their override variables are unset, so a spec that forgets one override
# reads and writes the config of every session on the machine, with no error.
# Loading this file is what makes "tests never touch the real Claude config or
# plugin data" hold without any spec having to remember it.
#
# Every spec file loads it as the first line of setup():
#
#   load '../../../scripts/test-support/sandbox-guard'
#
# scripts/tests/test_sandbox_guard.py fails when a spec file does not.
#
# Loading does three things, in this order, before anything else in the test:
#
#   1. Refuses an override inherited from the caller that resolves outside the
#      temp directory. The caller set it on purpose; it is not quietly ignored.
#   2. Points HOME at a fresh directory under BATS_TEST_TMPDIR, and gives every
#      unset override a default beside it.
#   3. Checks that every guarded variable is set and resolves under the temp
#      directory.
#
# HOME is replaced without asking because every shell has one and it says
# nothing about intent. The overrides exist only when somebody exported them.
#
# The guarded variables, and the scripts whose defaults they replace:
#
#   HOME                 spawn-session.sh ($HOME/.claude/sessions,
#                        $HOME/.claude/projects, $HOME/.claude.json);
#                        scripts/evict-plugin-cache.sh ($HOME/.claude);
#                        lib/dream/claude_env.py ($HOME/.claude)
#   CLAUDE_CONFIG_DIR    scripts/evict-plugin-cache.sh; lib/dream/claude_env.py
#   CLAUDE_PLUGIN_DATA   marketplace-scout ensure-dashboard.sh;
#                        lib/dream/delivery.py
#   SPAWN_SESSIONS_DIR   spawn-session.sh
#   SPAWN_PROJECTS_DIR   spawn-session.sh
#   SPAWN_CONFIG_FILE    spawn-session.sh
#
# The Python suites enforce the same list from sandbox_guard.py, beside this
# file. A variable added to one belongs in the other.
#
# Not caught: a spec that points one of these at a real path after loading.
# claude_sandbox_assert re-runs the check for a spec that wants it.
#
# Written for bash 3.2, which is what `env bash` finds on macOS.

CLAUDE_SANDBOX_VARS=(
  HOME
  CLAUDE_CONFIG_DIR
  CLAUDE_PLUGIN_DATA
  SPAWN_SESSIONS_DIR
  SPAWN_PROJECTS_DIR
  SPAWN_CONFIG_FILE
)

# Physical paths a guarded variable may resolve under. Filled by
# claude_sandbox_roots; the first entry is the one named in a refusal.
CLAUDE_SANDBOX_ROOTS=()

# claude_sandbox_refuse <fact; consequence.> [how to proceed]
#
# The repo's warning shape: the fact read at run time, the consequence as one
# capitalised verb, then the refusal.
claude_sandbox_refuse() {
  printf 'WARNING: %s Refusing.%s\n' "$1" "${2:+ $2}" >&2
}

# claude_sandbox_noun <NAME>
#
# What a test would write through this variable.
claude_sandbox_noun() {
  case "$1" in
    HOME) echo "Claude config and plugin data" ;;
    CLAUDE_CONFIG_DIR) echo "Claude config" ;;
    CLAUDE_PLUGIN_DATA) echo "plugin data" ;;
    SPAWN_SESSIONS_DIR) echo "session state" ;;
    SPAWN_PROJECTS_DIR) echo "session transcripts" ;;
    SPAWN_CONFIG_FILE) echo "the Claude config file" ;;
    *) echo "files" ;;
  esac
}

# claude_sandbox_real_target <NAME>
#
# Where the scripts under test fall back to when this variable is unset.
claude_sandbox_real_target() {
  case "$1" in
    HOME) echo "the real home directory" ;;
    CLAUDE_CONFIG_DIR) echo "the real Claude config directory" ;;
    CLAUDE_PLUGIN_DATA) echo "the real plugin data directory" ;;
    SPAWN_SESSIONS_DIR) echo "the real Claude sessions directory" ;;
    SPAWN_PROJECTS_DIR) echo "the real Claude transcripts directory" ;;
    SPAWN_CONFIG_FILE) echo "the real Claude config file" ;;
    *) echo "a real directory" ;;
  esac
}

# claude_sandbox_physical <path>
#
# Echoes the path with every symbolic link resolved. The path need not exist:
# the nearest existing directory is resolved and the rest is appended. Fails
# when the answer cannot be trusted: a dangling link on the way, or a ".." in
# the part that does not exist yet, which a plain prefix test would let climb
# back out of the temp directory.
claude_sandbox_physical() {
  local path="$1" rest="" target hops=0
  [[ -n "$path" ]] || return 1
  [[ "$path" == /* ]] || path="$PWD/$path"
  while [[ "$path" == */ && "$path" != "/" ]]; do
    path="${path%/}"
  done

  # cd cannot enter a link to a file, so follow those by hand.
  while [[ -L "$path" && ! -d "$path" ]]; do
    hops=$((hops + 1))
    ((hops <= 32)) || return 1
    target="$(readlink "$path")" || return 1
    [[ "$target" == /* ]] || target="${path%/*}/$target"
    path="$target"
  done

  while [[ ! -d "$path" ]]; do
    [[ ! -L "$path" ]] || return 1
    rest="/${path##*/}$rest"
    path="${path%/*}"
    [[ -n "$path" ]] || path="/"
  done
  case "$rest/" in
    */../*) return 1 ;;
  esac

  path="$(cd -P -- "$path" 2>/dev/null && pwd -P)" || return 1
  [[ "$path" != "/" ]] || path=""
  path="$path$rest"
  printf '%s\n' "${path:-/}"
}

# claude_sandbox_within <physical-path> <physical-root>
claude_sandbox_within() {
  [[ "$1" == "$2" || "$1" == "${2%/}"/* ]]
}

# claude_sandbox_roots
#
# Fills CLAUDE_SANDBOX_ROOTS with the temp directory bats itself uses
# (TMPDIR, else /tmp) and /tmp.
#
# "Under the temp directory" proves nothing when the temp directory contains
# the home directory, so that is refused rather than believed. The home
# directory is read from the user database, not from HOME, because HOME is
# one of the variables being checked.
claude_sandbox_roots() {
  local primary fallback home=""
  CLAUDE_SANDBOX_ROOTS=()

  if ! primary="$(claude_sandbox_physical "${TMPDIR:-/tmp}")"; then
    claude_sandbox_refuse \
      "the temp directory ${TMPDIR:-/tmp} cannot be resolved; this test could WRITE into the real Claude config." \
      "Set TMPDIR to an existing directory outside the home directory."
    return 1
  fi

  home="$(unset HOME; printf '%s' ~)"
  if [[ "$home" == /* ]]; then
    home="$(claude_sandbox_physical "$home")" || home=""
  else
    home=""
  fi

  if [[ -n "$home" ]] && claude_sandbox_within "$home" "$primary"; then
    claude_sandbox_refuse \
      "the temp directory $primary contains the home directory $home, so a path under it proves nothing; this test could WRITE into the real Claude config." \
      "Set TMPDIR to a directory outside the home directory."
    return 1
  fi
  CLAUDE_SANDBOX_ROOTS=("$primary")

  if fallback="$(claude_sandbox_physical /tmp)" && [[ "$fallback" != "$primary" ]]; then
    if [[ -z "$home" ]] || ! claude_sandbox_within "$home" "$fallback"; then
      CLAUDE_SANDBOX_ROOTS+=("$fallback")
    fi
  fi
}

# claude_sandbox_check <NAME>
#
# Returns 0 when the variable is set and resolves under the temp directory.
# Otherwise prints the refusal and returns 1.
claude_sandbox_check() {
  local name="$1" value physical root state
  value="${!name:-}"

  if [[ -z "$value" ]]; then
    state="unset"
    [[ -z "${!name+set}" ]] || state="empty"
    claude_sandbox_refuse \
      "$name is $state; this test would WRITE into $(claude_sandbox_real_target "$name")." \
      "Load scripts/test-support/sandbox-guard first; it sets one under the temp directory."
    return 1
  fi

  if ! physical="$(claude_sandbox_physical "$value")"; then
    claude_sandbox_refuse \
      "$name is $value, which cannot be resolved to a real path; this test would WRITE $(claude_sandbox_noun "$name") to a path nobody checked." \
      "Unset $name to get a fresh temp directory, or point it under ${CLAUDE_SANDBOX_ROOTS[0]}."
    return 1
  fi

  for root in "${CLAUDE_SANDBOX_ROOTS[@]}"; do
    if claude_sandbox_within "$physical" "$root"; then
      return 0
    fi
  done

  claude_sandbox_refuse \
    "$name resolves to $physical, outside the temp directory ${CLAUDE_SANDBOX_ROOTS[0]}; this test would WRITE $(claude_sandbox_noun "$name") there." \
    "Unset $name to get a fresh temp directory, or point it under ${CLAUDE_SANDBOX_ROOTS[0]}."
  return 1
}

# claude_sandbox_assert
#
# Every guarded variable is set and resolves under the temp directory. Runs
# at load; a spec that changes one of them afterwards can call it again.
claude_sandbox_assert() {
  local name
  if [[ "${#CLAUDE_SANDBOX_ROOTS[@]}" -eq 0 ]]; then
    claude_sandbox_roots || return 1
  fi
  for name in "${CLAUDE_SANDBOX_VARS[@]}"; do
    claude_sandbox_check "$name" || return 1
  done
}

# claude_sandbox_enter
#
# The whole guard. Runs when this file is loaded.
claude_sandbox_enter() {
  local name base sandbox

  claude_sandbox_roots || return 1

  # What the caller exported is honoured only under the temp directory.
  for name in "${CLAUDE_SANDBOX_VARS[@]}"; do
    [[ "$name" != HOME ]] || continue
    [[ -n "${!name:-}" ]] || continue
    claude_sandbox_check "$name" || return 1
  done

  base="${BATS_TEST_TMPDIR:-${BATS_FILE_TMPDIR:-}}"
  if [[ -z "$base" ]]; then
    claude_sandbox_refuse \
      "neither BATS_TEST_TMPDIR nor BATS_FILE_TMPDIR is set, so there is nowhere to build a sandbox; this test would WRITE into the real Claude config." \
      "Load the guard from setup() under bats 1.4 or newer."
    return 1
  fi
  sandbox="$base/.claude-sandbox"

  if ! mkdir -p "$sandbox/home"; then
    claude_sandbox_refuse \
      "the sandbox directory $sandbox/home cannot be created; this test would WRITE into the real Claude config."
    return 1
  fi
  # A live spec starts the user's login shell in a pane with this HOME. zsh
  # with no startup file there opens its first-run questionnaire instead of a
  # prompt on systems that ship it, and the launch line would be typed into
  # that.
  : > "$sandbox/home/.zshrc"

  export HOME="$sandbox/home"
  export CLAUDE_CONFIG_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
  export CLAUDE_PLUGIN_DATA="${CLAUDE_PLUGIN_DATA:-$sandbox/plugin-data}"
  export SPAWN_SESSIONS_DIR="${SPAWN_SESSIONS_DIR:-$CLAUDE_CONFIG_DIR/sessions}"
  export SPAWN_PROJECTS_DIR="${SPAWN_PROJECTS_DIR:-$CLAUDE_CONFIG_DIR/projects}"
  export SPAWN_CONFIG_FILE="${SPAWN_CONFIG_FILE:-$HOME/.claude.json}"

  claude_sandbox_assert
}

claude_sandbox_enter || return 1
