#!/usr/bin/env bash
# Activates this repo's tracked git hooks.
#
# Git does not clone hooks — .git/hooks is local to a checkout and never
# travels. Pointing core.hooksPath at the tracked .githooks/ directory is what
# makes a fresh clone actually run the gitleaks pre-commit scan, and it needs no
# husky dependency for a repo that has no package.json yet.
#
# Idempotent. Safe to re-run, and safe to call from a package.json "prepare"
# script once this repo grows one.
#
# Usage:  ./scripts/install-hooks.sh

set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

if [ ! -d .githooks ]; then
  echo "install-hooks: no .githooks/ directory in $repo_root — nothing to install." >&2
  exit 1
fi

# Tracked-file modes survive a clone, but a hook that lost its exec bit fails
# silently as "no hook" rather than as an error, so assert rather than assume.
chmod +x .githooks/* 2>/dev/null || true

git config core.hooksPath .githooks

echo "install-hooks: core.hooksPath -> .githooks"

if command -v gitleaks >/dev/null 2>&1; then
  echo "install-hooks: gitleaks $(gitleaks version 2>/dev/null) found — pre-commit scan is live."
else
  cat >&2 <<'MSG'

install-hooks: WARNING — gitleaks is not on PATH.

The hook is installed but will skip its scan (and say so) until you install it:

  Linux:  curl -sSfL https://raw.githubusercontent.com/gitleaks/gitleaks/master/scripts/install.sh | sh -s -- -b ~/.local/bin
  macOS:  brew install gitleaks

There is no CI scan behind this hook, so until gitleaks is installed this repo
has no secret scanning at all.

MSG
fi
