#!/usr/bin/env bash
# Activates this repo's tracked git hooks.
#
# Git does not clone hooks — .git/hooks is local to a checkout and never
# travels. Pointing core.hooksPath at the tracked .githooks/ directory is what
# makes a fresh clone actually run the gitleaks scan, and it needs no husky
# dependency for a repo that has no package.json yet.
#
# Idempotent. Safe to re-run on every session, and safe to call from a
# package.json "prepare" script once this repo grows one. When the hooks are
# already active it writes nothing.
#
# It never silently displaces someone else's hooks: if core.hooksPath already
# names another directory it changes nothing, says so and exits 1. --force
# replaces that value on purpose.
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

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

if [ ! -d .githooks ]; then
  echo "install-hooks: no .githooks/ directory in $repo_root — nothing to install." >&2
  exit 1
fi

# Tracked-file modes survive a clone, but a hook that lost its exec bit fails
# silently as "no hook" rather than as an error, so assert rather than assume.
chmod +x .githooks/* 2>/dev/null || true

wanted=".githooks"

# The value git actually uses in this worktree, from whichever config file
# wins (worktree, repository, global or system). Empty when unset.
effective_hooks_path() {
  git config --type=path --get core.hooksPath || true
}

# True when a core.hooksPath value names this worktree's .githooks directory,
# however it is spelled.
is_ours() {
  [ "$1" = "$wanted" ] && return 0
  [ -d "$1" ] && [ "$(cd "$1" && pwd -P)" = "$(cd "$wanted" && pwd -P)" ]
}

current="$(effective_hooks_path)"

if [ -n "$current" ] && ! is_ours "$current"; then
  if [ "$force" != "1" ]; then
    cat >&2 <<MSG

install-hooks: WARNING: core.hooksPath is already '$current'; setting it here
REPLACES that for this clone and every worktree of it, and the hooks there stop
running. Refusing. Nothing was changed.

The gitleaks hooks are NOT active in this worktree. To hand core.hooksPath to
this repo's .githooks on purpose:

  ./scripts/install-hooks.sh --force

MSG
    exit 1
  fi
  echo "install-hooks: --force: replacing core.hooksPath '$current' with '$wanted' in the repository config." >&2
fi

if [ -z "$current" ] || ! is_ours "$current"; then
  git config core.hooksPath "$wanted"
fi

# Read back what git will really use. A worktree-level value outranks the
# repository config just written, so the write alone proves nothing.
effective="$(effective_hooks_path)"

if [ -z "$effective" ] || ! is_ours "$effective"; then
  cat >&2 <<MSG

install-hooks: WARNING: the repository config now says core.hooksPath=$wanted,
but the effective value in this worktree is '${effective:-<unset>}'; commits
here SKIP the gitleaks hooks. Not active.

A setting with higher precedence (worktree-level config, or one given on the
command line or in the environment) overrides the repository config. Find it
with:

  git config --show-origin --get core.hooksPath

MSG
  exit 1
fi

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

# Not covered by any hook: `git rebase`, `git cherry-pick` and `git revert`
# create commits without running pre-commit. CI scans the tree on pull requests
# and main (.github/workflows/ci.yml) and is the backstop for those.
echo "install-hooks: rebase, cherry-pick and revert run no commit hook; CI's tree scan is the backstop."
