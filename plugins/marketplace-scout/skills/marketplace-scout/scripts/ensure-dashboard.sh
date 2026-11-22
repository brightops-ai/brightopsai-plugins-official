#!/usr/bin/env bash
#
# ensure-dashboard.sh — scaffold the marketplace-scout dashboard under
# CLAUDE_PLUGIN_DATA (or an explicit target). Never overwrites a present copy.
#
# Usage: ensure-dashboard.sh [target]
#   exit 0  dashboard present or freshly scaffolded; prints the path
#   exit 1  dashboard assets or their package-lock.json missing from the plugin,
#           an existing target cannot be given a pinned install, or the target
#           (or its package.json, package-lock.json or node_modules) is a
#           symlink or not the kind of entry it should be
#   exit 2  CLAUDE_PLUGIN_DATA or CLAUDE_PLUGIN_ROOT unset
#   exit 3  leftover ./dashboard or ./data in cwd; prints an mv instruction
#   exit 4  `npm ci` failed; the target is as it was before the run, so the
#           next run tries again
#   exit 5  the destination appeared, or a file this run was about to replace
#           changed, while this run was working; nothing was overwritten or
#           nested inside it. Run again.
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
#                                   moved in. package.json and package-lock.json
#                                   are brought to this release's when they are
#                                   an earlier release's, unmodified (see
#                                   SHIPPED_PACKAGE_JSON); no other file is
#                                   touched
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
# Name the entry itself, not what it leads to: a path ending in "/" or "/."
# is resolved through a symlink, so "link/" would pass every check below
# while "link" is refused.
while [[ "$TARGET" == */ || "$TARGET" == */. ]] && [[ "$TARGET" != / ]]; do
  TARGET="${TARGET%/.}"
  TARGET="${TARGET%/}"
done
if [[ -z "$TARGET" ]]; then
  TARGET=/
fi

# This script writes through no symlink and treats nothing but a real
# directory as a dashboard. A dangling link is neither "present" nor "absent".
refuse_entry() {
  echo "ensure-dashboard.sh: $1 is $2; refusing to use it. Move it aside and run again." >&2
  exit 1
}
# require_plain <path> <file|dir>: nothing there, or exactly that kind of entry.
require_plain() {
  if [[ -L "$1" ]]; then
    refuse_entry "$1" "a symlink"
  fi
  if [[ -e "$1" ]]; then
    if [[ "$2" == dir && ! -d "$1" ]]; then
      refuse_entry "$1" "not a directory"
    fi
    if [[ "$2" == file && ! -f "$1" ]]; then
      refuse_entry "$1" "not a regular file"
    fi
  fi
}
require_plain "$TARGET" dir

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
INCOMING=""
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
  # A name that cannot already exist inside the destination; see place().
  INCOMING="$STAGING/.incoming.${STAGING##*.}"
}

# place <src> <dst>: rename src to dst only if dst does not exist. `mv` moves
# its source *into* a directory that is already there, so a destination that
# appears after the check would end up holding the scaffold as a subdirectory.
# src therefore has a name no destination can already contain, and the result
# is checked: anything nested is taken back out. Returns 1 when dst exists.
place() {
  local src=$1 dst=$2 name=${1##*/}
  if [[ -e "$dst" || -L "$dst" ]]; then
    return 1
  fi
  # Known transient: no portable mv renames onto a path without ever treating
  # it as a directory (GNU has -T, BSD has -h, POSIX has neither). If a
  # symlink to a directory appears at dst right here, mv follows it for the
  # moment it takes the check below to move the source back out.
  mv -n "$src" "$dst" 2>/dev/null || true
  if [[ -e "$dst/$name" || -L "$dst/$name" ]]; then
    if ! mv "$dst/$name" "$src"; then
      echo "ensure-dashboard.sh: could not take $dst/$name back out; remove it by hand" >&2
    fi
    return 1
  fi
  [[ ! -e "$src" && -d "$dst" && ! -L "$dst" ]]
}

lost_race() {
  echo "ensure-dashboard.sh: $1 appeared while this run was working; nothing was overwritten. Run again." >&2
  exit 5
}

changed_race() {
  echo "ensure-dashboard.sh: $1 changed while this run was working; it was not replaced. Run again." >&2
  exit 5
}

# sha256 of every package.json and package-lock.json a release of this plugin
# has shipped in assets/dashboard, oldest first. A target that was never
# installed and still holds one of these, byte for byte, holds no edit of the
# user's, so it is moved to this release's pinned pair instead of being
# refused or installed from a superseded lockfile.
#
# When either file changes, APPEND the new digest and keep the old ones:
# dropping one strands every scaffold made by that release.
# tests/test_dashboard_lockfile.py fails until the current files are listed.
# Before listing a release, check that a dashboard scaffolded by each earlier
# one still builds with the new package.json: its source files are kept.
SHIPPED_PACKAGE_JSON=(
  a05ee697d8e0fca325b04fa52394107f9cb7c41b6b6fa048f623d82a5a63692a # first dashboard, no zod
  af4034f20c141a3ee71815d845bbbeedd3680dd9df8b9599513bccae1fda0f13 # dashboard v2 through 1.3.0
  92ddf9f8456912b1291c0024657fc461dd8cffa699f6c62c0bbe17880c15875f # 1.3.1
)
SHIPPED_PACKAGE_LOCK=(
  a61d5d64d39e7cf607a268013a012382626a83f5d8f210de63df704e23b11a82 # 1.3.0
  0f932b65f853789be515ace4bfc3eb085ba97d78454b2116a68c6858e87b1bad # 1.3.1
)

# sha256_of <file>: prints the hex digest. Fails when neither tool exists
# (coreutils has sha256sum, macOS has shasum), and the caller then treats the
# file as not recognised.
sha256_of() {
  local out
  if command -v sha256sum >/dev/null 2>&1; then
    out="$(sha256sum <"$1")" || return 1
  elif command -v shasum >/dev/null 2>&1; then
    out="$(shasum -a 256 <"$1")" || return 1
  else
    return 1
  fi
  out="${out%% *}"
  [[ ${#out} -eq 64 ]] || return 1
  printf '%s\n' "$out"
}

# file_state <file> <plugin's file> <known digest>...: prints
#   current           byte-identical to the file this release ships
#   earlier:<sha256>  byte-identical to one an earlier release shipped
#   other             anything else: edited, unknown, or no sha256 tool
file_state() {
  local file=$1 current=$2 sum known
  shift 2
  if [[ -f "$current" ]] && cmp -s "$file" "$current"; then
    echo current
    return 0
  fi
  if sum="$(sha256_of "$file")"; then
    for known in "$@"; do
      if [[ "$sum" == "$known" ]]; then
        echo "earlier:$sum"
        return 0
      fi
    done
  fi
  echo other
}

# swap_in <src> <dst> <sha256>: put src in place of the regular file dst, only
# while dst still has the content that was checked. The rename replaces dst
# whole, so it is not written through if it became a link. As in place(), a
# dst that became a directory would take src in as an entry: src has a name
# nothing there can already have, and it is taken back out. Returns 1 when
# dst was not replaced.
swap_in() {
  local src=$1 dst=$2 want=$3 name=${1##*/} have
  if [[ -L "$dst" || ! -f "$dst" ]]; then
    return 1
  fi
  have="$(sha256_of "$dst")" || return 1
  if [[ "$have" != "$want" ]]; then
    return 1
  fi
  mv -f "$src" "$dst" 2>/dev/null || true
  if [[ -e "$dst/$name" || -L "$dst/$name" ]]; then
    if ! mv "$dst/$name" "$src"; then
      echo "ensure-dashboard.sh: could not take $dst/$name back out; remove it by hand" >&2
    fi
    return 1
  fi
  [[ ! -e "$src" && -f "$dst" && ! -L "$dst" ]]
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
  require_plain "$TARGET/node_modules" dir
  require_plain "$TARGET/package.json" file
  require_plain "$TARGET/package-lock.json" file
  if [[ -d "$TARGET/node_modules" || ! -f "$TARGET/package.json" ]]; then
    echo "dashboard present at $TARGET; not overwriting"
    exit 0
  fi
  if [[ "$skip_install" -eq 1 ]]; then
    echo "dashboard present at $TARGET; not overwriting"
    echo "dependencies are not installed there (SKIP_NPM_INSTALL is set); a run without it installs them"
    exit 0
  fi

  # Present but never installed: a SKIP_NPM_INSTALL scaffold, a target whose
  # node_modules was removed, or one an older version left behind when its
  # install failed. Install only.
  manifest_state="$(file_state "$TARGET/package.json" "$src/package.json" "${SHIPPED_PACKAGE_JSON[@]}")"
  if [[ -f "$TARGET/package-lock.json" ]]; then
    lock_state="$(file_state "$TARGET/package-lock.json" "$src/package-lock.json" "${SHIPPED_PACKAGE_LOCK[@]}")"
  else
    lock_state=absent
  fi

  # This release's pinned pair applies when the target's package.json is a
  # release's own and its lockfile is too, or is missing. A file the user
  # changed is never replaced: the target then installs from what it holds.
  plugin_pair=0
  if [[ -f "$src/package-lock.json" && "$manifest_state" != other && "$lock_state" != other ]]; then
    plugin_pair=1
  fi

  if [[ "$plugin_pair" -eq 0 && "$lock_state" == absent ]]; then
    # Scaffolded before the lockfile shipped, and nothing pins it.
    if [[ "$manifest_state" == other ]] && ! sha256_of "$TARGET/package.json" >/dev/null; then
      echo "ensure-dashboard.sh: $TARGET has no node_modules and no package-lock.json, and its package.json is not this release's. With no sha256sum or shasum it cannot be checked against earlier releases; refusing to install unpinned dependencies. Move that directory aside to get a fresh scaffold." >&2
    else
      echo "ensure-dashboard.sh: $TARGET has no node_modules and no package-lock.json, and its package.json is not the plugin's; refusing to install unpinned dependencies. Move that directory aside to get a fresh scaffold." >&2
    fi
    exit 1
  fi

  new_staging
  if [[ "$plugin_pair" -eq 1 ]]; then
    cp "$src/package.json" "$WORK/package.json"
    cp "$src/package-lock.json" "$WORK/package-lock.json"
  else
    cp "$TARGET/package.json" "$WORK/package.json"
    cp "$TARGET/package-lock.json" "$WORK/package-lock.json"
  fi
  install_in_staging

  # Nothing in the target has been touched yet. From here it changes in this
  # order, so that node_modules, the completion signal, arrives last and an
  # interrupted run is finished by the next one.
  replaced=""
  if [[ "$plugin_pair" -eq 1 ]]; then
    if [[ "$manifest_state" == earlier:* ]]; then
      require_plain "$TARGET/package.json" file
      mv "$WORK/package.json" "$INCOMING.package.json"
      if ! swap_in "$INCOMING.package.json" "$TARGET/package.json" "${manifest_state#earlier:}"; then
        changed_race "$TARGET/package.json"
      fi
      replaced="package.json"
    fi

    require_plain "$TARGET/package-lock.json" file
    if [[ "$lock_state" == earlier:* ]]; then
      mv "$WORK/package-lock.json" "$INCOMING.package-lock.json"
      if ! swap_in "$INCOMING.package-lock.json" "$TARGET/package-lock.json" "${lock_state#earlier:}"; then
        changed_race "$TARGET/package-lock.json"
      fi
      replaced="${replaced:+$replaced and }package-lock.json"
    elif [[ "$lock_state" == absent ]]; then
      # Write the lockfile only where nothing exists. noclobber opens the path
      # exclusively, so a file or a link that appeared since the check is not
      # written through.
      if ! (set -o noclobber && cat "$WORK/package-lock.json" >"$TARGET/package-lock.json") 2>/dev/null; then
        lost_race "$TARGET/package-lock.json"
      fi
    fi
  fi

  mv "$WORK/node_modules" "$INCOMING"
  if ! place "$INCOMING" "$TARGET/node_modules"; then
    lost_race "$TARGET/node_modules"
  fi
  mkdir -p "${CLAUDE_PLUGIN_DATA}/data/images"
  if [[ -n "$replaced" ]]; then
    echo "$replaced in $TARGET came unmodified from an earlier release; replaced with this release's"
  fi
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

mv "$WORK" "$INCOMING"
if ! place "$INCOMING" "$TARGET"; then
  # Something created the target first. It stands; this copy is discarded.
  lost_race "$TARGET"
fi
mkdir -p "${CLAUDE_PLUGIN_DATA}/data/images"

if [[ "$skip_install" -eq 1 ]]; then
  echo "dashboard scaffolded at $TARGET; dependencies not installed (SKIP_NPM_INSTALL is set); a run without it installs them"
else
  echo "dashboard ready at $TARGET"
fi
