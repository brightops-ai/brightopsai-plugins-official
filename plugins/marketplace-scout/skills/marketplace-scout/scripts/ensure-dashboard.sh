#!/usr/bin/env bash
#
# ensure-dashboard.sh — scaffold the marketplace-scout dashboard under
# CLAUDE_PLUGIN_DATA (or an explicit target). Never overwrites a present copy.
#
# Usage: ensure-dashboard.sh [target]
#   exit 0  dashboard present or freshly scaffolded; prints the path
#   exit 1  dashboard assets or their package-lock.json missing from the plugin,
#           or an existing target cannot be given a pinned install
#   exit 2  CLAUDE_PLUGIN_DATA or CLAUDE_PLUGIN_ROOT unset
#   exit 3  leftover ./dashboard or ./data in cwd; prints an mv instruction
#   exit 4  `npm ci` failed; the target is as it was before the run, so the
#           next run tries again
#
# Dependencies install with `npm ci --ignore-scripts`: exactly the versions
# package-lock.json pins, and no package's install script runs.
#
# A target is complete when it has node_modules. Nothing is ever built in the
# target itself: the scaffold and the install happen in a sibling staging
# directory and are renamed into place only after they succeed, so a failed
# or interrupted run leaves no half-made target for a later run to accept.
#
#   target absent                   stage copy + install, then move into place
#   target present, node_modules    left untouched (user edits are kept)
#   target present, none            install only: node_modules is staged and
#                                   moved in; no other file is touched
#
# SKIP_NPM_INSTALL: if set, skip the npm step (tests set this). A fresh
# scaffold is then copied without node_modules, and an existing target is left
# as it is. The next run without SKIP_NPM_INSTALL installs the dependencies
# into that target (third row above).

set -euo pipefail

if [[ -z "${CLAUDE_PLUGIN_DATA:-}" || -z "${CLAUDE_PLUGIN_ROOT:-}" ]]; then
  echo "ensure-dashboard.sh: CLAUDE_PLUGIN_DATA and CLAUDE_PLUGIN_ROOT must be set" >&2
  exit 2
fi

TARGET="${1:-$CLAUDE_PLUGIN_DATA/dashboard}"

legacy_dashboard=0
legacy_data=0
[[ -e ./dashboard ]] && legacy_dashboard=1
[[ -e ./data ]] && legacy_data=1

if [[ ! -e "$TARGET" ]] && [[ "$legacy_dashboard" -eq 1 || "$legacy_data" -eq 1 ]]; then
  dash_mv="mv ./dashboard \"$CLAUDE_PLUGIN_DATA/dashboard\""
  data_mv="mv ./data \"$CLAUDE_PLUGIN_DATA/data\""
  if [[ "$legacy_dashboard" -eq 1 && "$legacy_data" -eq 1 ]]; then
    echo "legacy ./dashboard and ./data in cwd; move with: $dash_mv && $data_mv"
  elif [[ "$legacy_dashboard" -eq 1 ]]; then
    echo "legacy ./dashboard in cwd; move with: $dash_mv"
  else
    echo "legacy ./data in cwd; move with: $data_mv"
  fi
  exit 3
fi

STAGING=""
WORK=""
cleanup() {
  # Only ever removes a directory this run created with the name below.
  if [[ -n "$STAGING" && -d "$STAGING" && "${STAGING##*/}" == .dashboard-staging.* ]]; then
    rm -rf "$STAGING"
  fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM HUP

# Sibling of the target, so the final rename stays on one filesystem. The
# staging directory is private (mktemp, mode 700); the work happens in a
# subdirectory created with the caller's umask, which is what gets moved.
new_staging() {
  local parent
  parent="$(dirname -- "$TARGET")"
  mkdir -p "$parent"
  STAGING="$(mktemp -d "$parent/.dashboard-staging.XXXXXX")"
  WORK="$STAGING/dashboard"
  mkdir "$WORK"
}

# `npm ci` installs only what package-lock.json pins and fails if it and
# package.json disagree. --ignore-scripts keeps every dependency's install
# script from running with the user's environment; the dashboard toolchain
# needs none. Runs in the staging directory, never in the target.
install_in_staging() {
  if ! (cd "$WORK" && npm ci --ignore-scripts); then
    echo "ensure-dashboard.sh: npm ci failed; $TARGET is unchanged. Fix the cause and run again." >&2
    exit 4
  fi
  # node_modules is the completion signal, even for an empty dependency set.
  mkdir -p "$WORK/node_modules"
}

skip_install=0
if [[ -n "${SKIP_NPM_INSTALL+x}" ]]; then
  skip_install=1
fi

src="${CLAUDE_PLUGIN_ROOT}/skills/marketplace-scout/assets/dashboard"

if [[ -e "$TARGET" ]]; then
  if [[ -d "$TARGET/node_modules" || ! -f "$TARGET/package.json" ]]; then
    echo "dashboard present at $TARGET; not overwriting"
    exit 0
  fi
  if [[ "$skip_install" -eq 1 ]]; then
    echo "dashboard present at $TARGET; not overwriting"
    echo "dependencies are not installed there (SKIP_NPM_INSTALL is set); a run without it installs them"
    exit 0
  fi

  # Present but never installed: a SKIP_NPM_INSTALL scaffold, or a target an
  # older version left behind when its install failed. Install only.
  lock="$TARGET/package-lock.json"
  if [[ ! -f "$lock" ]]; then
    # Scaffolded before the lockfile shipped. The plugin's lockfile pins this
    # target only if its package.json is still the plugin's.
    if [[ -f "$src/package-lock.json" ]] && cmp -s "$TARGET/package.json" "$src/package.json"; then
      lock="$src/package-lock.json"
    else
      echo "ensure-dashboard.sh: $TARGET has no node_modules and no package-lock.json, and its package.json is not the plugin's; refusing to install unpinned dependencies. Move that directory aside to get a fresh scaffold." >&2
      exit 1
    fi
  fi

  new_staging
  cp "$TARGET/package.json" "$WORK/package.json"
  cp "$lock" "$WORK/package-lock.json"
  install_in_staging

  if [[ -e "$TARGET/node_modules" ]]; then
    echo "dashboard present at $TARGET; not overwriting"
    exit 0
  fi
  if [[ ! -f "$TARGET/package-lock.json" ]]; then
    cp "$WORK/package-lock.json" "$TARGET/package-lock.json"
  fi
  mv "$WORK/node_modules" "$TARGET/node_modules"
  mkdir -p "${CLAUDE_PLUGIN_DATA}/data/images"
  echo "dashboard ready at $TARGET (dependencies installed into the existing copy)"
  exit 0
fi

if [[ ! -d "$src" ]]; then
  echo "ensure-dashboard.sh: missing dashboard assets at $src" >&2
  exit 1
fi
# Checked before anything is created: the lockfile is what pins the install.
if [[ ! -f "$src/package-lock.json" ]]; then
  echo "ensure-dashboard.sh: missing $src/package-lock.json; refusing to install unpinned dependencies" >&2
  exit 1
fi

new_staging
for item in "$src"/*; do
  [[ -e "$item" ]] || continue
  name="${item##*/}"
  if [[ "$name" == "node_modules" ]]; then
    continue
  fi
  cp -R "$item" "$WORK/"
done

# The copy loop carries package-lock.json into the staging directory beside
# package.json, so it reaches the target with it.
if [[ "$skip_install" -eq 0 ]]; then
  install_in_staging
fi

if [[ -e "$TARGET" ]]; then
  # Another run finished first. Its copy stands; this one is discarded.
  echo "dashboard present at $TARGET; not overwriting"
  exit 0
fi
mv "$WORK" "$TARGET"
mkdir -p "${CLAUDE_PLUGIN_DATA}/data/images"

if [[ "$skip_install" -eq 1 ]]; then
  echo "dashboard scaffolded at $TARGET; dependencies not installed (SKIP_NPM_INSTALL is set); a run without it installs them"
else
  echo "dashboard ready at $TARGET"
fi
