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
# Every spec file loads it as the first line of setup(), and of setup_file()
# when it has one:
#
#   load '../../../scripts/test-support/sandbox-guard'
#
# scripts/tests/test_sandbox_guard.py fails when a spec file does not.
#
# Loading does four things, in this order, before anything else in the test:
#
#   1. Works out which directories count as temp, and refuses when the answer
#      would prove nothing (see claude_sandbox_roots).
#   2. Refuses an override inherited from the caller that is not a clean
#      absolute path resolving under a temp directory. The caller set it on
#      purpose; it is not quietly ignored.
#   3. Points HOME at a fresh directory under BATS_TEST_TMPDIR, and gives every
#      unset override a default beside it. Nothing is created before the
#      directory it goes in has passed the same check.
#   4. Checks that every guarded variable is set and resolves under a temp
#      directory.
#
# HOME is replaced without asking because every shell has one and it says
# nothing about intent. The overrides exist only when somebody exported them.
#
# The guarded path variables, and the scripts whose defaults they replace:
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
# One more variable is a name, not a path, and is guarded as one:
#
#   CLAUDE_CODE_PROJECT_DIR_NAME   lib/dream/claude_env.py joins it onto the
#                        config directory as written, so a value with a slash
#                        or ".." leaves the sandbox the six above built. Left
#                        unset when unset; refused when it is not a plain name.
#
# The Python suites enforce the same lists from sandbox_guard.py, beside this
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

CLAUDE_SANDBOX_NAME_VAR="CLAUDE_CODE_PROJECT_DIR_NAME"

# Physical paths a guarded variable may resolve under. Filled by
# claude_sandbox_roots; the first entry is the one named in a refusal.
CLAUDE_SANDBOX_ROOTS=()

# The result of the last claude_sandbox_visible call.
CLAUDE_SANDBOX_VISIBLE=""

# Characters that need no rendering. Spelled out one by one, with no ranges: a
# range is matched by the locale's collation order, and this list is what
# decides that a value holds no control character. "-" is last so the bracket
# expression it is used in reads it as itself.
CLAUDE_SANDBOX_PLAIN='abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 /._+=,:;@%~()-'

# claude_sandbox_plain <text>
#
# One command for the usual case, in place of the several hundred the
# character-by-character rendering below takes. A spec that calls
# claude_sandbox_assert itself runs them under bats' command tracing.
claude_sandbox_plain() {
  [[ "$1" != *[!$CLAUDE_SANDBOX_PLAIN]* ]]
}

# claude_sandbox_visible <text>
#
# Sets CLAUDE_SANDBOX_VISIBLE to the text on one line, with every control
# character written out (\n, \t, \r, \xHH, and \u00HH for U+0080 to U+009F)
# and a backslash doubled so the rendering cannot pass for the real thing.
#
# Every value printed here comes from the environment. Printed raw, a value
# holding a newline followed by "WARNING: ..." forges a second warning, and
# one holding an escape sequence repaints the line that mattered. The same
# rendering is how a control character is detected: a value that changes
# under it, apart from its backslashes, has one.
#
# It sets a variable instead of printing because command substitution drops
# trailing newlines, which is the very thing being looked for.
claude_sandbox_visible() {
  local text="$1" code oct ch esc
  if claude_sandbox_plain "$text"; then
    CLAUDE_SANDBOX_VISIBLE="$text"
    return 0
  fi
  text="${text//\\/\\\\}"

  for code in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 \
              25 26 27 28 29 30 31 127; do
    printf -v oct '%03o' "$code"
    printf -v ch '%b' "\\0$oct"
    case "$code" in
      9)  esc='\t' ;;
      10) esc='\n' ;;
      13) esc='\r' ;;
      *)  printf -v esc '\\x%02x' "$code" ;;
    esac
    text="${text//"$ch"/$esc}"
  done

  for code in 128 129 130 131 132 133 134 135 136 137 138 139 140 141 142 143 \
              144 145 146 147 148 149 150 151 152 153 154 155 156 157 158 159; do
    printf -v oct '%03o' "$code"
    printf -v ch '%b' "\\0302\\0$oct"
    printf -v esc '\\u00%02x' "$code"
    text="${text//"$ch"/$esc}"
  done

  CLAUDE_SANDBOX_VISIBLE="$text"
}

# claude_sandbox_has_control <text>
claude_sandbox_has_control() {
  if claude_sandbox_plain "$1"; then
    return 1
  fi
  claude_sandbox_visible "$1"
  [[ "$CLAUDE_SANDBOX_VISIBLE" != "${1//\\/\\\\}" ]]
}

# claude_sandbox_refuse <fact; consequence.> [how to proceed]
#
# The repo's warning shape: the fact read at run time, the consequence as one
# capitalised verb, then the refusal. Always one line.
claude_sandbox_refuse() {
  claude_sandbox_visible "WARNING: $1 Refusing.${2:+ $2}"
  printf '%s\n' "$CLAUDE_SANDBOX_VISIBLE" >&2
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
    BATS_TEST_TMPDIR | BATS_FILE_TMPDIR) echo "its sandbox" ;;
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

# The result of the last successful claude_sandbox_physical call.
CLAUDE_SANDBOX_PHYSICAL=""

# claude_sandbox_physical <path>
#
# Sets CLAUDE_SANDBOX_PHYSICAL to the path with every symbolic link resolved.
# (A variable, not output: every caller would need a second subshell to read
# it, and bats runs this for every variable before every test.) The path need not exist:
# the nearest existing directory is resolved and the rest is appended. Fails
# when the answer cannot be trusted: a link to a file or to nothing, a ".." in
# the part that does not exist yet (which a plain prefix test would let climb
# back out of the temp directory), or a control character anywhere in the
# result.
#
# The command substitution ends in a sentinel, so a directory whose name ends
# in a newline keeps it and is refused, instead of being read as the directory
# beside it.
claude_sandbox_physical() {
  local path="$1" rest=""
  [[ -n "$path" ]] || return 1
  [[ "$path" == /* ]] || path="$PWD/$path"
  while [[ "$path" == */ && "$path" != "/" ]]; do
    path="${path%/}"
  done

  # A link to a file, or to nothing. cd cannot enter it, and readlink does not
  # say the same thing everywhere about a target that ends in a newline, so
  # there is no reading it that can be trusted.
  if [[ -L "$path" && ! -d "$path" ]]; then
    return 1
  fi

  while [[ ! -d "$path" ]]; do
    [[ ! -L "$path" ]] || return 1
    rest="/${path##*/}$rest"
    path="${path%/*}"
    [[ -n "$path" ]] || path="/"
  done
  case "$rest/" in
    */../*) return 1 ;;
  esac

  path="$(cd -P -- "$path" 2>/dev/null && pwd -P && printf x)" || return 1
  path="${path%x}"
  path="${path%$'\n'}"
  [[ "$path" != "/" ]] || path=""
  path="$path$rest"
  path="${path:-/}"
  if claude_sandbox_has_control "$path"; then
    return 1
  fi
  CLAUDE_SANDBOX_PHYSICAL="$path"
}

# claude_sandbox_within <physical-path> <physical-root>
claude_sandbox_within() {
  [[ "$1" == "$2" || "$1" == "${2%/}"/* ]]
}

# claude_sandbox_passwd_home
#
# Echoes the home directory from the user database, not from HOME: HOME is one
# of the variables being checked.
claude_sandbox_passwd_home() {
  (
    unset HOME
    printf '%s\n' ~
  )
}

# claude_sandbox_usable_root <physical-root> <physical-home> <physical-config>
#
# "Under a temp directory" proves nothing when that directory contains the
# home directory, or is, is inside, or contains the real Claude config
# directory. A temp directory elsewhere under the home directory is fine.
claude_sandbox_usable_root() {
  local root="$1" home="$2" config="$3"
  if [[ -n "$home" ]] && claude_sandbox_within "$home" "$root"; then
    return 1
  fi
  if [[ -n "$config" ]]; then
    if claude_sandbox_within "$root" "$config" || claude_sandbox_within "$config" "$root"; then
      return 1
    fi
  fi
}

# claude_sandbox_roots
#
# Fills CLAUDE_SANDBOX_ROOTS. The first root is the temp directory bats itself
# uses (TMPDIR, else /tmp); it must exist, and a refusal follows when it is
# not usable. /tmp is added when usable, and so is the per-user temp directory
# on macOS, which is where `mktemp -d` puts things there whatever TMPDIR says.
claude_sandbox_roots() {
  local tmp="${TMPDIR:-/tmp}" primary home config="" candidate extra known root
  CLAUDE_SANDBOX_ROOTS=()

  if [[ ! -d "$tmp" ]] || ! claude_sandbox_physical "$tmp"; then
    claude_sandbox_refuse \
      "the temp directory $tmp is not an existing directory this guard can resolve; this test would WRITE its sandbox to a path nobody checked." \
      "Set TMPDIR to an existing directory, or unset it."
    return 1
  fi

  primary="$CLAUDE_SANDBOX_PHYSICAL"

  home="$(claude_sandbox_passwd_home)"
  if [[ "$home" == /* ]] && claude_sandbox_physical "$home"; then
    home="$CLAUDE_SANDBOX_PHYSICAL"
    if claude_sandbox_physical "$home/.claude"; then
      config="$CLAUDE_SANDBOX_PHYSICAL"
    fi
  else
    home=""
  fi

  if [[ -n "$home" ]] && claude_sandbox_within "$home" "$primary"; then
    claude_sandbox_refuse \
      "the temp directory $primary contains the home directory $home, so a path under it proves nothing; this test could WRITE into the real Claude config." \
      "Set TMPDIR to a directory that does not contain the home directory."
    return 1
  fi
  if [[ -n "$config" ]] && claude_sandbox_within "$primary" "$config"; then
    claude_sandbox_refuse \
      "the temp directory $primary is inside the real Claude config directory $config; this test would WRITE its sandbox into the real Claude config." \
      "Set TMPDIR to a directory outside $config."
    return 1
  fi
  if [[ -n "$config" ]] && claude_sandbox_within "$config" "$primary"; then
    claude_sandbox_refuse \
      "the temp directory $primary contains the real Claude config directory $config, so a path under it proves nothing; this test could WRITE into the real Claude config." \
      "Set TMPDIR to a directory that does not contain $config."
    return 1
  fi
  CLAUDE_SANDBOX_ROOTS=("$primary")

  for candidate in /tmp "$(getconf DARWIN_USER_TEMP_DIR 2>/dev/null || true)"; do
    [[ "$candidate" == /* && -d "$candidate" ]] || continue
    claude_sandbox_physical "$candidate" || continue
    extra="$CLAUDE_SANDBOX_PHYSICAL"
    claude_sandbox_usable_root "$extra" "$home" "$config" || continue
    known=0
    for root in "${CLAUDE_SANDBOX_ROOTS[@]}"; do
      [[ "$root" != "$extra" ]] || known=1
    done
    [[ "$known" -eq 1 ]] || CLAUDE_SANDBOX_ROOTS+=("$extra")
  done
}

# claude_sandbox_check <NAME>
#
# Returns 0 when the variable holds a clean absolute path that resolves under
# a temp directory. Otherwise prints the refusal and returns 1.
claude_sandbox_check() {
  local name="$1" value physical root state remedy
  value="${!name:-}"
  remedy="Unset $name to get a fresh temp directory, or point it under ${CLAUDE_SANDBOX_ROOTS[0]}."
  case "$name" in
    BATS_*) remedy="Run bats with TMPDIR unset, or set to an existing temp directory." ;;
  esac

  if [[ -z "$value" ]]; then
    state="unset"
    [[ -z "${!name+set}" ]] || state="empty"
    claude_sandbox_refuse \
      "$name is $state; this test would WRITE into $(claude_sandbox_real_target "$name")." \
      "Load scripts/test-support/sandbox-guard first; it sets one under the temp directory."
    return 1
  fi

  # Checked before anything else reads the value: every later step passes it
  # through a command substitution, which would drop a trailing newline and
  # check a different path from the one the script under test receives.
  if claude_sandbox_has_control "$value"; then
    claude_sandbox_refuse \
      "$name holds a control character ($value); this test would WRITE $(claude_sandbox_noun "$name") to a path nobody checked." \
      "$remedy"
    return 1
  fi

  # A relative value depends on the working directory at the moment it is
  # used, and the Python code under test expands a leading "~".
  if [[ "$value" != /* ]]; then
    claude_sandbox_refuse \
      "$name is $value, which is not an absolute path; this test would WRITE $(claude_sandbox_noun "$name") to a path nobody checked." \
      "$remedy"
    return 1
  fi

  if ! claude_sandbox_physical "$value"; then
    claude_sandbox_refuse \
      "$name is $value, which cannot be resolved to a real path; this test would WRITE $(claude_sandbox_noun "$name") to a path nobody checked." \
      "$remedy"
    return 1
  fi
  physical="$CLAUDE_SANDBOX_PHYSICAL"

  for root in "${CLAUDE_SANDBOX_ROOTS[@]}"; do
    if claude_sandbox_within "$physical" "$root"; then
      return 0
    fi
  done

  claude_sandbox_refuse \
    "$name resolves to $physical, outside the temp directory ${CLAUDE_SANDBOX_ROOTS[0]}; this test would WRITE $(claude_sandbox_noun "$name") there." \
    "$remedy"
  return 1
}

# claude_sandbox_check_name
#
# Returns 0 when the project directory name is unset or a plain name.
claude_sandbox_check_name() {
  local name="$CLAUDE_SANDBOX_NAME_VAR" value
  value="${!name:-}"
  [[ -n "$value" ]] || return 0

  if claude_sandbox_has_control "$value" ||
    [[ "$value" == */* || "$value" == *\\* || "$value" == *..* || "$value" == "." ]]; then
    claude_sandbox_refuse \
      "$name is $value, which is a path and not a directory name; this test would WRITE session transcripts and memory outside the sandboxed Claude config directory." \
      "Unset $name, or set it to a plain name."
    return 1
  fi
}

# claude_sandbox_assert
#
# Every guarded variable is set and safe. Runs at load; a spec that changes
# one of them afterwards can call it again.
claude_sandbox_assert() {
  local name
  if [[ "${#CLAUDE_SANDBOX_ROOTS[@]}" -eq 0 ]]; then
    claude_sandbox_roots || return 1
  fi
  for name in "${CLAUDE_SANDBOX_VARS[@]}"; do
    claude_sandbox_check "$name" || return 1
  done
  claude_sandbox_check_name
}

# claude_sandbox_enter
#
# The whole guard. Runs when this file is loaded.
#
# bats runs its DEBUG trap on every command of every function while functrace
# (set -T) is on, which it needs to report where a spec failed. Inside this
# guard that reporting is worth nothing, since a refusal is reported at the
# `load` line either way, and it made the guard several times slower than the
# specs it protects. Functrace is switched off for the functions called from
# here and put back before returning.
claude_sandbox_enter() {
  local traced=0 status=0
  case "$-" in
    *T*)
      traced=1
      set +T
      ;;
  esac
  claude_sandbox_enter_untraced || status=$?
  [[ "$traced" -eq 0 ]] || set -T
  return "$status"
}

claude_sandbox_enter_untraced() {
  local name base_name="BATS_TEST_TMPDIR" sandbox

  claude_sandbox_roots || return 1

  # What the caller exported is honoured only when it is safe.
  claude_sandbox_check_name || return 1
  for name in "${CLAUDE_SANDBOX_VARS[@]}"; do
    [[ "$name" != HOME ]] || continue
    [[ -n "${!name:-}" ]] || continue
    claude_sandbox_check "$name" || return 1
  done

  [[ -n "${BATS_TEST_TMPDIR:-}" ]] || base_name="BATS_FILE_TMPDIR"
  if [[ -z "${!base_name:-}" ]]; then
    claude_sandbox_refuse \
      "neither BATS_TEST_TMPDIR nor BATS_FILE_TMPDIR is set, so there is nowhere to build a sandbox; this test would WRITE into the real Claude config." \
      "Load the guard from setup() under bats 1.4 or newer."
    return 1
  fi
  # Nothing is created until the directory it would go in has passed.
  claude_sandbox_check "$base_name" || return 1
  sandbox="${!base_name}/.claude-sandbox"

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
