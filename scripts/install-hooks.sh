#!/usr/bin/env bash
# Activates this repo's tracked git hooks.
#
# Git does not clone hooks — .git/hooks is local to a checkout and never
# travels. Pointing core.hooksPath at the tracked .githooks/ directory is what
# makes a fresh clone actually run the gitleaks scan, and it needs no husky
# dependency for a repo that has no package.json yet.
#
# The rule this script keeps:
#
#   It asks git what is in effect: the ordered list of every core.hooksPath
#   value with its scope and the file it comes from, as git evaluates it here
#   (includes and their conditions included). The last entry wins.
#
#   It writes one thing, core.hooksPath=.githooks in the repository config
#   (.git/config), and only when the list is empty, or when --force was given
#   and writing that file can change the winner: the winner is written in
#   .git/config itself, or comes from the global or system config, which
#   .git/config outranks.
#
#   It refuses, before changing anything, when core.hooksPath is already set
#   to something else (an empty value counts) and --force was not given; when
#   --force was given but the winner comes from a worktree's own config, the
#   command line, the environment or a file .git/config includes; when git
#   cannot say where the winner comes from; and when a hook file is missing.
#
#   The write is a swap under git's own config lock: the new file replaces
#   .git/config only if .git/config is still, byte for byte, what this script
#   read. If the hooks are then not active, the same swap puts the old bytes
#   back, and only if the file is still what this script wrote. File modes
#   are changed last, and put back the same way.
#
#   So exit 0 means active, and any other exit means as it was, with one
#   exception this script cannot prevent and always reports: if, after this
#   script wrote .git/config and before it could undo, another process
#   changed that file or took its lock, the file is left alone. The message
#   then says what was left and the command that removes it.
#
# Idempotent. Safe to re-run on every session, and safe to call from a
# package.json "prepare" script once this repo grows one. When the hooks are
# already active it writes nothing.
#
# It reports the hooks active only when both hook files exist and are
# executable, and the hooks directory git itself reports
# (`git rev-parse --git-path hooks`) is this worktree's .githooks.
#
# Usage:  ./scripts/install-hooks.sh [--force]
#
# Exit status: 0 hooks active in this worktree; 1 not active; 2 bad arguments.

set -euo pipefail

usage() {
  echo "usage: install-hooks.sh [--force]" >&2
}

force=0
if [ "$#" -gt 1 ]; then
  usage
  exit 2
fi
case "${1:-}" in
  "") ;;
  --force) force=1 ;;
  *)
    usage
    exit 2
    ;;
esac

# `git config` reads GIT_CONFIG as the one file to look in. No other git
# command does, so with it set this script would read one configuration while
# `git commit` uses another, and could report hooks active that never run.
unset GIT_CONFIG

if [ "$(git rev-parse --is-inside-work-tree 2>/dev/null || true)" != "true" ]; then
  echo "install-hooks: not inside a git work tree — nothing to install." >&2
  exit 1
fi

# To the top of the work tree by a relative path. The absolute path is never
# passed through a command substitution, which would drop a trailing newline
# from a directory name and leave this script somewhere else.
cdup="$(git rev-parse --show-cdup)"
if [ -n "$cdup" ]; then
  cd "$cdup"
fi

if [ ! -d .githooks ]; then
  echo "install-hooks: no .githooks/ directory in $PWD — nothing to install." >&2
  exit 1
fi

wanted=".githooks"
newline=$'\n'

# The hooks the scan depends on. A core.hooksPath that names a directory
# without them is accepted by git and runs nothing.
required_hooks="pre-commit pre-merge-commit"

# The repository config file: the one file this script writes. In a linked
# worktree it is the shared one. The path ends in "config", so the command
# substitution cannot shorten it.
repo_config="$(git rev-parse --git-path config)"

# show <text>: the text in quotes, or in the shell's own escaped form when it
# holds a byte that would not be seen (a newline, a control character).
show() {
  case "$1" in
    *[![:print:]]* | *"'"*) printf '%q' "$1" ;;
    *) printf "'%s'" "$1" ;;
  esac
}

# --- What git says is in effect ------------------------------------------------
#
# Every core.hooksPath value, in the order git applies them, read
# NUL-terminated so that no byte of a value or a path is lost. The last one
# wins. count is 0 when nothing sets the key. The scope is empty when git is
# older than 2.26 and cannot report it.
count=0
scopes=()
origins=()
values=()
winner_scope=""
winner_origin=""
winner_value=""

list_hooks_path() {
  # $1 is --show-scope or empty. Fields first, then "rc=<git's exit status>".
  local rc=0
  if [ -n "$1" ]; then
    git config "$1" --show-origin --null --get-all core.hooksPath 2>/dev/null || rc=$?
  else
    git config --show-origin --null --get-all core.hooksPath 2>/dev/null || rc=$?
  fi
  printf 'rc=%s\0' "$rc"
}

# Fills fields with what list_hooks_path printed, and fields_rc with the exit
# status at the end of it ("unknown" if even that did not arrive).
fields=()
fields_rc=""
collect_fields() {
  local field last="rc=unknown"
  fields=()
  while IFS= read -r -d '' field; do
    fields+=("$field")
    last="$field"
  done < <(list_hooks_path "$1")
  fields_rc="${last#rc=}"
}

read_hooks_path() {
  local per=3 rc i
  collect_fields --show-scope
  if [ "$fields_rc" = "129" ]; then
    # This git does not know --show-scope. Origins only.
    per=2
    collect_fields ""
  fi
  rc="$fields_rc"

  count=0
  scopes=()
  origins=()
  values=()
  winner_scope=""
  winner_origin=""
  winner_value=""
  case "$rc" in
    1) return 0 ;;
    0) ;;
    *)
      echo "install-hooks: WARNING: git could not read its configuration (git config exited $rc); commits here may SKIP the gitleaks hooks. Not active." >&2
      exit 1
      ;;
  esac

  local total=$((${#fields[@]} - 1))
  if [ $((total % per)) -ne 0 ]; then
    echo "install-hooks: WARNING: git listed core.hooksPath in a form this script does not know; commits here may SKIP the gitleaks hooks. Not active." >&2
    exit 1
  fi
  i=0
  while [ "$i" -lt "$total" ]; do
    if [ "$per" = "3" ]; then
      scopes+=("${fields[$i]}")
      origins+=("${fields[$((i + 1))]}")
      values+=("${fields[$((i + 2))]}")
    else
      scopes+=("")
      origins+=("${fields[$i]}")
      values+=("${fields[$((i + 1))]}")
    fi
    i=$((i + per))
  done
  count="${#values[@]}"
  if [ "$count" -gt 0 ]; then
    winner_scope="${scopes[$((count - 1))]}"
    winner_origin="${origins[$((count - 1))]}"
    winner_value="${values[$((count - 1))]}"
  fi
}

# The directory git will look in for a hook, by git's own account, with its
# bytes intact: the "x" keeps a trailing newline in the name from being
# dropped, and exactly the one newline git prints after it is removed.
hooks_dir=""
read_hooks_dir() {
  local out
  out="$(
    git rev-parse --git-path hooks
    printf x
  )"
  out=${out%x}
  hooks_dir=${out%"$newline"}
}

# True when git looks for hooks in this worktree's .githooks directory,
# however core.hooksPath spells it. -ef compares the directories themselves,
# so no path is printed and read back.
hooks_are_ours() {
  # A relative path that starts with a dash names the right directory and
  # still does not work: git hands "-dir/pre-commit" to a shell, which reads
  # it as options.
  case "$hooks_dir" in
    "" | -*) return 1 ;;
  esac
  [ "$count" -gt 0 ] && [ "$hooks_dir" -ef "$wanted" ]
}

# True when the winner is written in the repository config file itself, not
# in a file it includes.
winner_is_direct() {
  [ "$winner_scope" = "local" ] || return 1
  case "$winner_origin" in
    file:*) [ "${winner_origin#file:}" -ef "$repo_config" ] ;;
    *) return 1 ;;
  esac
}

# --- The one write, and its undo -----------------------------------------------
#
# swap_config <expected> <new>: under git's config lock, replace the repository
# config with <new>, but only if it is still byte for byte <expected>.
# Returns 0 done; 1 the lock is held; 2 the config is not <expected>; 3 the
# new file could not be put in place. Nothing is changed unless it returns 0.
config_lock="$repo_config.lock"
holding_lock=0
swap_config() {
  if ! (
    set -o noclobber
    : >"$config_lock"
  ) 2>/dev/null; then
    return 1
  fi
  holding_lock=1
  local result=0
  if ! cmp -s "$repo_config" "$1"; then
    result=2
  elif ! cp -p "$2" "$config_lock" 2>/dev/null; then
    result=3
  elif ! mv -f "$config_lock" "$repo_config" 2>/dev/null; then
    result=3
  fi
  if [ "$result" != "0" ]; then
    rm -f "$config_lock"
  fi
  holding_lock=0
  return "$result"
}

succeeded=0
config_written=0
config_before=""
config_after=""
keep_before=0
prior_direct=0
changed_modes=()

finish() {
  local status=$?
  trap - EXIT
  # Exit 0 is a claim that the hooks are active. Nothing but reaching the end
  # of this script may make it: bash 3.2 leaves a script that dies of an
  # expansion error with the status of the command before it, which can be 0.
  if [ "$succeeded" != "1" ] && [ "$status" = "0" ]; then
    status=1
  fi
  if [ "$holding_lock" = "1" ]; then
    rm -f "$config_lock"
    holding_lock=0
  fi
  if [ "$succeeded" != "1" ]; then
    if [ "$config_written" = "1" ]; then
      local undo=0
      swap_config "$config_after" "$config_before" || undo=$?
      case "$undo" in
        0)
          echo "install-hooks: the core.hooksPath this run wrote was undone: the repository config is byte for byte what it was." >&2
          ;;
        2)
          echo "install-hooks: WARNING: something else changed the repository config after this run wrote core.hooksPath=$wanted to it, so this run LEFT the file alone and undid nothing. See what is there now: git config --show-origin --get-all core.hooksPath" >&2
          ;;
        *)
          if [ "$prior_direct" = "0" ]; then
            echo "install-hooks: WARNING: the core.hooksPath this run wrote could not be undone, because git's config lock ($(show "$config_lock")) is held or the file cannot be replaced. This LEAVES core.hooksPath=$wanted in the repository config. Once the lock is gone, remove it with: git config --file $(show "$repo_config") --unset-all core.hooksPath" >&2
          else
            keep_before=1
            echo "install-hooks: WARNING: the core.hooksPath this run wrote could not be undone, because git's config lock ($(show "$config_lock")) is held or the file cannot be replaced. This LEAVES core.hooksPath=$wanted in the repository config in place of the value(s) that were there. The config as it was is kept beside it. Once the lock is gone, put it back with: cp -p $(show "$config_before") $(show "$repo_config")" >&2
          fi
          ;;
      esac
    fi
    if [ "${#changed_modes[@]}" -gt 0 ]; then
      local hook
      for hook in "${changed_modes[@]}"; do
        chmod u-x "$hook" 2>/dev/null || true
      done
    fi
  fi
  if [ -n "$config_after" ]; then
    rm -f "$config_after"
  fi
  if [ -n "$config_before" ] && [ "$keep_before" != "1" ]; then
    rm -f "$config_before"
  fi
  exit "$status"
}
trap finish EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

# --- Checks: nothing is changed until all of these pass -------------------

read_hooks_path
read_hooks_dir

need_write=0
if ! hooks_are_ours; then
  need_write=1
fi

if [ "$need_write" = "1" ] && [ "$count" -gt 0 ]; then
  shown="$(show "$winner_value")"
  if [ -z "$winner_value" ]; then
    shown="'' (an empty value: git then runs no hooks at all)"
  fi

  if [ "$force" != "1" ]; then
    cat >&2 <<MSG

install-hooks: WARNING: core.hooksPath is already $shown; setting it here
REPLACES that for this clone and every worktree of it, and the hooks there stop
running. Refusing. Nothing was changed.

The gitleaks hooks are NOT active in this worktree. To hand core.hooksPath to
this repo's .githooks on purpose:

  ./scripts/install-hooks.sh --force

MSG
    exit 1
  fi

  # --force writes the repository config, which every worktree shares. It is
  # only worth writing when that write changes the winner. The decision goes
  # by where the winner comes from, never by what its value is.
  #
  # git puts a replaced value where the last value it replaces was (seen with
  # git 2.56.1), so a winner written in the repository config stays the
  # winner after the write, whatever is included before it. Where no value is
  # written there, git adds one to an existing [core] section, which may sit
  # before an include that sets the key; that case is refused, not guessed.
  where=""
  remedy=""
  see="git config --show-origin --show-scope --get-all core.hooksPath"
  case "$winner_scope" in
    worktree)
      where="this worktree's own config (config.worktree), which outranks the repository config"
      remedy="git config --worktree --unset-all core.hooksPath"
      ;;
    command)
      where="the command line or the environment (git -c, GIT_CONFIG_COUNT, GIT_CONFIG_PARAMETERS), which outranks the repository config"
      remedy="unset the variable, or drop the -c option, that sets core.hooksPath"
      ;;
    local)
      if ! winner_is_direct; then
        where="a file the repository config includes (include.path or includeIf), $(show "${winner_origin#file:}"), which this script does not edit"
        remedy="remove core.hooksPath from the included file, or the include from the repository config"
      fi
      ;;
    global | system) ;;
    "")
      where="a level this git cannot name (git config --show-scope needs git 2.26 or newer), so this script cannot tell whether a write to the repository config would take effect"
      remedy="remove the value by hand where --show-origin says it is set"
      see="git config --show-origin --get-all core.hooksPath"
      ;;
    *)
      where="a level this script does not know ($(show "$winner_scope")), so it cannot tell whether a write to the repository config would take effect"
      remedy="remove the value by hand where --show-origin says it is set"
      ;;
  esac
  if [ -n "$where" ]; then
    cat >&2 <<MSG

install-hooks: WARNING: --force replaces core.hooksPath in the repository
config, but the effective value in this worktree is $shown
and it comes from $where;
commits here SKIP the gitleaks hooks. Not active. Refusing. Nothing was changed.

See where it is set:

  $see

Remove it on purpose, then run this script again:

  $remedy

MSG
    exit 1
  fi
fi

missing=""
for hook in $required_hooks; do
  [ -f "$wanted/$hook" ] || missing="$missing $wanted/$hook"
done
if [ -n "$missing" ]; then
  cat >&2 <<MSG

install-hooks: WARNING: missing hook file(s):$missing. Git runs nothing for a
hook that is not there, so commits here SKIP the gitleaks scan it would have
run. Not active. Nothing was changed.

Restore them from the repository, then run this script again:

  git checkout -- $wanted

MSG
  exit 1
fi

# --- The write ---------------------------------------------------------------

if [ "$need_write" = "1" ]; then
  for tool in cp mv rm cmp; do
    if ! command -v "$tool" >/dev/null 2>&1; then
      echo "install-hooks: WARNING: '$tool' is not on PATH and this script needs it to write the repository config safely; commits here SKIP the gitleaks hooks. Not active. Nothing was changed." >&2
      exit 1
    fi
  done
  if [ -L "$repo_config" ] || [ ! -f "$repo_config" ]; then
    cat >&2 <<MSG

install-hooks: WARNING: the repository config ($(show "$repo_config"))
is a symlink or not a regular file, and this script only replaces a regular
file; commits here SKIP the gitleaks hooks. Not active. Nothing was changed.

Set it by hand:

  git config core.hooksPath $wanted

MSG
    exit 1
  fi

  # How many values the file itself holds now: what an undo that cannot run
  # has to tell the reader to put back.
  i=0
  while [ "$i" -lt "$count" ]; do
    case "${origins[$i]}" in
      file:*)
        if [ "${scopes[$i]}" != "worktree" ] && [ "${origins[$i]#file:}" -ef "$repo_config" ]; then
          prior_direct=$((prior_direct + 1))
        fi
        ;;
    esac
    i=$((i + 1))
  done

  # The config as it is, and as it should become, both beside the real one so
  # that the swap is a rename within one directory. git edits the copy; the
  # real file is not touched until the swap.
  config_before="$repo_config.install-hooks.$$.before"
  config_after="$repo_config.install-hooks.$$.after"
  if ! cp -p "$repo_config" "$config_before" 2>/dev/null || ! cp -p "$config_before" "$config_after" 2>/dev/null; then
    cat >&2 <<MSG

install-hooks: WARNING: could not write core.hooksPath: nothing can be created
beside the repository config ($(show "$repo_config")); commits here SKIP the
gitleaks hooks. Not active. Nothing was changed.

MSG
    exit 1
  fi
  # --replace-all: the key may hold several values in the repository config,
  # and a plain set refuses to overwrite more than one.
  if ! git config --file "$config_after" --replace-all core.hooksPath "$wanted"; then
    cat >&2 <<MSG

install-hooks: WARNING: could not write core.hooksPath: git could not prepare
the new repository config (its error is above); commits here SKIP the gitleaks
hooks. Not active. Nothing was changed.

MSG
    exit 1
  fi

  if [ "$count" -gt 0 ]; then
    echo "install-hooks: --force: replacing core.hooksPath $(show "$winner_value") with '$wanted' in the repository config." >&2
  fi

  swapped=0
  swap_config "$config_before" "$config_after" || swapped=$?
  case "$swapped" in
    0) config_written=1 ;;
    1)
      cat >&2 <<MSG

install-hooks: WARNING: could not write core.hooksPath: git's config lock
($(show "$config_lock")) is held, so another git command is writing the
repository config, or one died and left the lock; commits here SKIP the
gitleaks hooks. Not active. Nothing was changed.

If no git command is running, remove the lock file and run this script again.

MSG
      exit 1
      ;;
    2)
      cat >&2 <<MSG

install-hooks: WARNING: could not write core.hooksPath: the repository config
changed while this script was checking it, so what it checked is no longer
what is there; commits here SKIP the gitleaks hooks. Not active.
This run changed nothing.

Run this script again.

MSG
      exit 1
      ;;
    *)
      cat >&2 <<MSG

install-hooks: WARNING: could not write core.hooksPath: the new repository
config could not be put in place; commits here SKIP the gitleaks hooks.
Not active. Nothing was changed.

MSG
      exit 1
      ;;
  esac
fi

# Read back what git will really use. The checks above are meant to make this
# pass every time; if something they did not foresee still wins, say so. The
# EXIT trap then undoes the write and reports what it did.
read_hooks_path
read_hooks_dir
if ! hooks_are_ours; then
  seen="unset"
  if [ "$count" -gt 0 ]; then
    seen="$(show "$winner_value")"
  fi
  cat >&2 <<MSG

install-hooks: WARNING: the repository config says core.hooksPath=$wanted, but
the effective value in this worktree is $seen and git looks
for hooks in $(show "$hooks_dir"); commits here SKIP the gitleaks hooks.
Not active.

Something with higher precedence overrides the repository config. Find it
with:

  git config --show-origin --show-scope --get-all core.hooksPath

MSG
  exit 1
fi

# --- File modes, last ----------------------------------------------------------

# Tracked-file modes survive a clone, but a hook that lost its exec bit fails
# silently as "no hook" rather than as an error, so assert rather than assume.
# Only the owner's bit is added, so taking it away again restores the mode
# exactly.
for hook in "$wanted"/*; do
  if [ -f "$hook" ] && [ ! -x "$hook" ]; then
    changed_modes+=("$hook")
    chmod u+x "$hook" 2>/dev/null || true
  fi
done

not_executable=""
for hook in $required_hooks; do
  [ -x "$wanted/$hook" ] || not_executable="$not_executable $wanted/$hook"
done
if [ -n "$not_executable" ]; then
  cat >&2 <<MSG

install-hooks: WARNING: not executable and could not be made so:$not_executable.
Git treats a hook without the exec bit as no hook, so commits here SKIP the
gitleaks scan. Not active.

  chmod u+x$not_executable

MSG
  exit 1
fi

succeeded=1

echo "install-hooks: core.hooksPath is $(show "$winner_value") — hooks active in this worktree."

if ! command -v gitleaks >/dev/null 2>&1; then
  cat >&2 <<'MSG'

install-hooks: WARNING: gitleaks is not on PATH; the hooks BLOCK every
`git commit` and merge commit until it is installed.

  macOS:
    brew install gitleaks

  Linux x86_64 (the pinned release CI uses; a failed checksum stops the install):
    (tmp="$(mktemp -d)" && cd "$tmp" \
      && curl -fsSLO https://github.com/gitleaks/gitleaks/releases/download/v8.30.1/gitleaks_8.30.1_linux_x64.tar.gz \
      && echo "551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb  gitleaks_8.30.1_linux_x64.tar.gz" | sha256sum -c - \
      && tar -xzf gitleaks_8.30.1_linux_x64.tar.gz gitleaks \
      && mkdir -p ~/.local/bin \
      && install -m 0755 gitleaks ~/.local/bin/gitleaks)

  Then check that the shell finds it:
    command -v gitleaks
  If that prints nothing after the Linux install, ~/.local/bin is not on PATH.
  Add it, check again, and put the same line in your shell profile to keep it:
    export PATH="$HOME/.local/bin:$PATH"

MSG
elif version="$(gitleaks version 2>/dev/null)" && [ -n "$version" ]; then
  echo "install-hooks: gitleaks $version found — the scan is live for \`git commit\` and merge commits."
else
  cat >&2 <<'MSG'

install-hooks: WARNING: gitleaks is on PATH but `gitleaks version` failed, so
this script cannot confirm that the scanner works. The hooks run their own
scan and BLOCK a commit only when that scan cannot complete. Check it with:

  gitleaks version

MSG
fi

# What the hooks do not see. Git runs pre-commit for only some of the commits
# these commands make, and which ones has changed between git versions, so the
# statement is the cautious one. What was observed, with git 2.56.1, is pinned
# in scripts/tests/test_commit_hook_coverage.py. CI is not a second chance at
# those commits: it scans the files in the tree it checks out, not history.
echo "install-hooks: a commit made by rebase, cherry-pick or revert may not have been scanned (git runs pre-commit for only some of them). CI scans the files in the tree at the head of a pull request and on main, not history: it does not see a value that one commit added and a later one removed."
