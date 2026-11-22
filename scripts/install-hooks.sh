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
#   It writes one thing, core.hooksPath=.githooks in the repository config
#   (.git/config), and only when no config level sets core.hooksPath at all, or
#   when --force was given and every value in effect is written in that file.
#   It may also give the hook files the owner's exec bit.
#
#   It refuses, before changing anything, when core.hooksPath is already set
#   to something else and --force was not given; when --force was given but
#   the value in effect comes from somewhere a write to .git/config cannot
#   outrank or this script does not edit (a worktree's own config, the command
#   line, the environment, a file .git/config includes); when git cannot say
#   where the value comes from; and when a hook file is missing.
#
#   It leaves nothing behind when it does not succeed. A run that ends without
#   the hooks active puts back every file mode it changed and every config
#   value it replaced, so exit 0 means "active" and any other exit means "as
#   it was". An empty core.hooksPath counts as set: git then runs no hooks.
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

# To the top of the work tree by a relative path. The absolute path is never
# passed through a command substitution, which would drop a trailing newline
# from a directory name and leave this script somewhere else.
if ! cdup="$(git rev-parse --show-cdup 2>/dev/null)"; then
  echo "install-hooks: not inside a git work tree — nothing to install." >&2
  exit 1
fi
if [ -n "$cdup" ]; then
  cd "$cdup"
fi

if [ ! -d .githooks ]; then
  echo "install-hooks: no .githooks/ directory in $PWD — nothing to install." >&2
  exit 1
fi

wanted=".githooks"

# The hooks the scan depends on. A core.hooksPath that names a directory
# without them is accepted by git and runs nothing.
required_hooks="pre-commit pre-merge-commit"

# The repository config file: the one file this script writes. In a linked
# worktree it is the shared one.
repo_config="$(git rev-parse --git-path config)"

# Sets is_set (1 when any config level sets core.hooksPath, an empty value
# included) and current (the value git uses, from whichever level wins).
is_set=0
current=""
read_hooks_path() {
  local rc=0
  current="$(git config --type=path --get core.hooksPath)" || rc=$?
  case "$rc" in
    0) is_set=1 ;;
    1)
      is_set=0
      current=""
      ;;
    *)
      echo "install-hooks: WARNING: git could not read its configuration (git config exited $rc); commits here may SKIP the gitleaks hooks. Not active. Nothing was changed." >&2
      exit 1
      ;;
  esac
}

# Where the winning value comes from: worktree, local, global, system or
# command (the command line or the environment). Empty when git is older than
# 2.26 and cannot say.
effective_hooks_scope() {
  local line
  line="$(git config --show-scope --get core.hooksPath 2>/dev/null)" || return 0
  # "<scope><TAB><value>": keep what precedes the first whitespace, using
  # builtins only.
  printf '%s\n' "${line%%[[:space:]]*}"
}

# The directory git will look in for a hook, by git's own account. This does
# not go through `git config`, so it is the check on everything above.
git_hooks_dir() {
  git rev-parse --git-path hooks
}

# True when a path names this worktree's .githooks directory, however it is
# spelled.
is_ours() {
  [ "$1" = "$wanted" ] && return 0
  [ -n "$1" ] && [ -d "$1" ] && [ "$(cd "$1" && pwd -P)" = "$(cd "$wanted" && pwd -P)" ]
}

# True when core.hooksPath is set, names .githooks, and git agrees.
hooks_are_ours() {
  [ "$is_set" = "1" ] && is_ours "$current" && is_ours "$(git_hooks_dir)"
}

# Every core.hooksPath value at the repository level, one per line, with a
# closing "x" so a trailing empty value survives the command substitution.
# $1 is --no-includes (what is written in the file itself) or --includes
# (that, plus what the files it includes add).
repository_values() {
  git config --file "$repo_config" "$1" --get-all core.hooksPath || true
  echo x
}

# --- Undo --------------------------------------------------------------------
#
# Everything this script changes is recorded here first, and put back by the
# EXIT trap unless the run ended with the hooks active.

succeeded=0
changed_modes=()
config_written=0
prior_values=()

undo() {
  local status=$?
  trap - EXIT
  if [ "$succeeded" = "1" ]; then
    exit "$status"
  fi
  if [ "$config_written" = "1" ]; then
    local restored=1
    git config --file "$repo_config" --unset-all core.hooksPath 2>/dev/null || restored=0
    if [ "${#prior_values[@]}" -gt 0 ]; then
      local value
      for value in "${prior_values[@]}"; do
        git config --file "$repo_config" --add core.hooksPath "$value" || restored=0
      done
    fi
    if [ "$restored" = "1" ]; then
      echo "install-hooks: the core.hooksPath this run wrote to the repository config was undone." >&2
    else
      echo "install-hooks: WARNING: could not undo the core.hooksPath this run wrote to the repository config; this LEAVES core.hooksPath=$wanted there. Check it with: git config --show-origin --get-all core.hooksPath" >&2
    fi
  fi
  if [ "${#changed_modes[@]}" -gt 0 ]; then
    local hook
    for hook in "${changed_modes[@]}"; do
      chmod u-x "$hook" 2>/dev/null || true
    done
  fi
  exit "$status"
}
trap undo EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# --- Checks: nothing is changed until all of these pass -------------------

read_hooks_path

if [ "$is_set" = "1" ] && ! is_ours "$current"; then
  shown="'$current'"
  if [ -z "$current" ]; then
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
  # only worth writing when that write is what git will then use. The decision
  # goes by where the winning value comes from, never by what the value is: an
  # empty value from a worktree's own config outranks the repository config
  # exactly as a non-empty one does.
  scope="$(effective_hooks_scope)"
  where=""
  remedy=""
  see="git config --show-origin --show-scope --get-all core.hooksPath"
  case "$scope" in
    worktree)
      where="this worktree's own config (config.worktree), which outranks the repository config"
      remedy="git config --worktree --unset-all core.hooksPath"
      ;;
    command)
      where="the command line or the environment (git -c, GIT_CONFIG_COUNT, GIT_CONFIG_PARAMETERS), which outranks the repository config"
      remedy="unset the variable, or drop the -c option, that sets core.hooksPath"
      ;;
    local)
      if [ "$(repository_values --no-includes)" != "$(repository_values --includes)" ]; then
        where="a file the repository config includes (include.path or includeIf), which this script does not edit"
        remedy="remove core.hooksPath from the included file, or the include from the repository config"
      fi
      ;;
    global | system) ;;
    *)
      where="a level this git cannot name (git config --show-scope needs git 2.26 or newer), so this script cannot tell whether a write to the repository config would take effect"
      remedy="remove the value by hand where --show-origin says it is set"
      see="git config --show-origin --get-all core.hooksPath"
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

# --- Changes: each is recorded before it is made, and undone on failure ------

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
gitleaks scan. Not active. Nothing was changed.

  chmod u+x$not_executable

MSG
  exit 1
fi

if ! hooks_are_ours; then
  if [ "$is_set" = "1" ]; then
    echo "install-hooks: --force: replacing core.hooksPath '$current' with '$wanted' in the repository config." >&2
  fi

  # What is written in the file now, to put back if this run fails.
  while IFS= read -r -d '' value; do
    prior_values+=("$value")
  done < <(git config --file "$repo_config" --no-includes --null --get-all core.hooksPath || true)

  # --replace-all: the key may hold several values in the repository config,
  # and a plain set refuses to overwrite more than one.
  config_written=1
  if ! git config --file "$repo_config" --replace-all core.hooksPath "$wanted"; then
    config_written=0
    cat >&2 <<MSG

install-hooks: WARNING: git could not write core.hooksPath to the repository
config (its error is above); commits here SKIP the gitleaks hooks. Not active.
Nothing was changed.

MSG
    exit 1
  fi
fi

# Read back what git will really use. The checks above are meant to make this
# pass every time; if something they did not foresee still wins, say so, and
# let the trap undo the write.
read_hooks_path
if ! hooks_are_ours; then
  cat >&2 <<MSG

install-hooks: WARNING: the repository config says core.hooksPath=$wanted, but
the effective value in this worktree is '${current:-<unset>}' and git looks
for hooks in '$(git_hooks_dir)'; commits here SKIP the gitleaks hooks.
Not active.

Something with higher precedence overrides the repository config. Find it
with:

  git config --show-origin --show-scope --get-all core.hooksPath

MSG
  exit 1
fi

succeeded=1
effective="$current"

echo "install-hooks: core.hooksPath is '$effective' — hooks active in this worktree."

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

install-hooks: WARNING: gitleaks is on PATH but `gitleaks version` failed; the
hooks BLOCK every `git commit` and merge commit until it works. Reinstall it.

MSG
fi

# What the hooks do not see. Git runs pre-commit for only some of the commits
# these commands make, and which ones has changed between git versions, so the
# statement is the cautious one. What was observed, with git 2.56.1, is pinned
# in scripts/tests/test_commit_hook_coverage.py.
echo "install-hooks: a commit made by rebase, cherry-pick or revert may not have been scanned (git runs pre-commit for only some of them); CI's tree scan is the scan that covers them."
