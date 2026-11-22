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
#   exit 4  `npm ci` failed, or a file could not be written into the target;
#           the target is as it was before the run, so the next run tries again
#   exit 5  something in the target appeared or changed while this run was
#           working. Nothing of the user's was overwritten or nested into, and
#           anything this run had exchanged was put back. Run again.
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
#                                   SHIPPED_PACKAGE_JSON and "Exchanging a
#                                   file" below); no other file is touched
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
SET_ASIDE=""
TAG=""
# has_entries <dir>: something is in it, hidden or not.
has_entries() {
  local entry
  for entry in "$1"/* "$1"/.[!.]* "$1"/..?*; do
    if [[ -e "$entry" || -L "$entry" ]]; then
      return 0
    fi
  done
  return 1
}
cleanup() {
  # Only ever removes a directory this run created with the name below.
  if [[ -n "$STAGING" && -d "$STAGING" && "${STAGING##*/}" == .dashboard-staging.* ]]; then
    # A file moved out of the target is never deleted along with the staging
    # directory. If one is still here it could not be put back; it stays, and
    # the next run looks for it (recover_set_aside).
    if [[ -n "$SET_ASIDE" && -d "$SET_ASIDE" ]] && has_entries "$SET_ASIDE"; then
      echo "ensure-dashboard.sh: $SET_ASIDE holds what could not be put back into $TARGET. It was left in place; the next run puts it back." >&2
      return
    fi
    rm -rf "$STAGING"
  fi
}
trap cleanup EXIT

# A signal normally stops the run at once. While files in the target are being
# exchanged it is only noted, and acted on once the exchange is complete or
# undone: stopping between two steps would leave a file out of the target.
PENDING_SIGNAL=""
stop_on_signal() {
  trap 'exit 130' INT
  trap 'exit 143' TERM HUP
}
hold_signals() {
  trap 'PENDING_SIGNAL=130' INT
  trap 'PENDING_SIGNAL=143' TERM HUP
}
stop_on_signal

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
  # Names that cannot already exist inside a destination; see place().
  TAG="${STAGING##*.}"
  INCOMING="$STAGING/.incoming.$TAG"
  # Where files moved out of the target wait; made only when one is moved.
  SET_ASIDE="$STAGING/set-aside.${TARGET##*/}"
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

have_sha256() {
  command -v sha256sum >/dev/null 2>&1 || command -v shasum >/dev/null 2>&1
}

# sha256_of <file>: prints the hex digest. Fails when the file cannot be read
# or neither tool exists (coreutils has sha256sum, macOS has shasum); the
# caller then treats the file as not recognised.
sha256_of() {
  local out
  if command -v sha256sum >/dev/null 2>&1; then
    out="$(sha256sum <"$1" 2>/dev/null)" || return 1
  elif command -v shasum >/dev/null 2>&1; then
    out="$(shasum -a 256 <"$1" 2>/dev/null)" || return 1
  else
    return 1
  fi
  out="${out%% *}"
  [[ ${#out} -eq 64 ]] || return 1
  printf '%s\n' "$out"
}

# file_state <file> <plugin's file> <known digest>...: prints
#   absent            nothing there
#   unreadable        a regular file this user cannot read
#   current           byte-identical to the file this release ships
#   earlier:<sha256>  byte-identical to one an earlier release shipped
#   other             anything else: edited, unknown, not a regular file, or
#                     no sha256 tool
file_state() {
  local file=$1 current=$2 sum known
  shift 2
  if [[ ! -e "$file" && ! -L "$file" ]]; then
    echo absent
    return 0
  fi
  if [[ -L "$file" || ! -f "$file" ]]; then
    echo other
    return 0
  fi
  if [[ ! -r "$file" ]]; then
    echo unreadable
    return 0
  fi
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

# state_of <package.json|package-lock.json> [<file>]: file_state of that file
# in the target, or of <file> judged as that kind.
state_of() {
  if [[ "$1" == package.json ]]; then
    file_state "${2:-$TARGET/$1}" "$src/$1" "${SHIPPED_PACKAGE_JSON[@]}"
  else
    file_state "${2:-$TARGET/$1}" "$src/$1" "${SHIPPED_PACKAGE_LOCK[@]}"
  fi
}

# holds <file> <sha256>: file is a regular file with exactly that content.
holds() {
  local have
  [[ -f "$1" && ! -L "$1" ]] || return 1
  have="$(sha256_of "$1")" || return 1
  [[ "$have" == "$2" ]]
}

# --- Exchanging a file in a target the user may be editing -------------------
#
# The shell has no compare-and-swap, and a check followed by a rename over the
# path would discard whatever was saved between the two. So a file is never
# replaced where it stands:
#
#   1. it is moved out of the target into SET_ASIDE (a rename);
#   2. what was moved is checked there, where its path can no longer be
#      written to. Only a file that is an earlier release's, byte for byte,
#      is ever dropped;
#   3. the new file is put at the now empty path with put_file, which never
#      overwrites and never shows a partial file.
#
# If any step fails, or what was moved turns out to be the user's, everything
# is put back the same way (settle). SET_ASIDE is the record of what is out
# of the target: a run that is killed between two steps leaves it behind, and
# the next run puts it back before it looks at the target (recover_set_aside).

# put_file <src> <dst>: give dst the entry src, only if nothing is at dst.
#   0  dst is now src (src's own name is gone)
#   1  something is at dst; it was not touched
#   2  nothing is at dst and src could not be put there
# A regular file is hard-linked: link(2) fails when dst exists, so there is no
# gap between a check and the write, and the file appears whole. `-n` keeps
# both GNU and BSD ln from following a dst that became a symlink to a
# directory. Where links are not available, and for an entry that is not a
# regular file, it falls back to the rename place() uses, which does have a
# gap between its check and the rename on some systems.
put_file() {
  local src=$1 dst=$2 name=${1##*/}
  if [[ -e "$dst" || -L "$dst" ]]; then
    return 1
  fi
  if [[ -f "$src" && ! -L "$src" ]] && ln -n "$src" "$dst" 2>/dev/null; then
    if [[ ! -L "$dst" && "$dst" -ef "$src" ]]; then
      rm -f "$src"
      return 0
    fi
    # dst became a directory first and took the link in as an entry.
    if [[ ! -L "$dst/$name" && "$dst/$name" -ef "$src" ]]; then
      rm -f "$dst/$name"
    fi
    return 1
  fi
  if [[ -e "$dst" || -L "$dst" ]]; then
    return 1
  fi
  mv -n "$src" "$dst" 2>/dev/null || true
  if [[ -e "$dst/$name" || -L "$dst/$name" ]]; then
    if ! mv "$dst/$name" "$src"; then
      echo "ensure-dashboard.sh: could not take $dst/$name back out; remove it by hand" >&2
    fi
    return 1
  fi
  if [[ -e "$src" || -L "$src" ]]; then
    if [[ -e "$dst" || -L "$dst" ]]; then
      return 1
    fi
    return 2
  fi
  return 0
}

# settle <file> <package.json|package-lock.json> <tag>: find a home for a file
# that was moved out of the target.
#   0  it is back at its path
#   3  its path is taken and it is a release's own file: dropped
#   4  its path is taken and it is the user's: saved beside it, and reported
#   1  it could not be put anywhere; it stays where it is
settle() {
  local file=$1 f=$2 tag=$3 rc=0 n saved
  if [[ ! -e "$file" && ! -L "$file" ]]; then
    return 0
  fi
  put_file "$file" "$TARGET/$f" || rc=$?
  if [[ "$rc" -eq 0 ]]; then
    return 0
  fi
  if [[ "$rc" -eq 1 ]]; then
    case "$(state_of "$f" "$file")" in
      current | earlier:*)
        rm -f "$file"
        return 3
        ;;
    esac
    for n in "" .2 .3 .4 .5; do
      saved="$TARGET/$f.set-aside.$tag$n"
      if put_file "$file" "$saved"; then
        echo "ensure-dashboard.sh: $TARGET/$f was replaced while it was out of the directory. What it held before is saved as $saved." >&2
        return 4
      fi
    done
  fi
  echo "ensure-dashboard.sh: could not put $file back as $TARGET/$f." >&2
  return 1
}

# take_back <package.json|package-lock.json>: take out of the target the file
# this run put there, if it is still that file. Something else found there is
# the user's and goes back.
take_back() {
  local f=$1 out="$SET_ASIDE/ours.$TAG.$1"
  if ! mv "$TARGET/$f" "$out" 2>/dev/null; then
    if [[ -e "$TARGET/$f" || -L "$TARGET/$f" ]]; then
      echo "ensure-dashboard.sh: could not take $TARGET/$f back out." >&2
      return 1
    fi
    return 0
  fi
  if [[ -f "$out" && ! -L "$out" ]] && cmp -s "$out" "$WORK/$f"; then
    rm -f "$out"
    return 0
  fi
  settle "$out" "$f" "$TAG"
}

# recover_set_aside: put back what an earlier run moved out of this target and
# did not return, because it was killed between two steps or could not write.
# Its staging directory is still beside the target. A file whose path is empty
# goes back; one whose path is taken is dropped if it is a release's own and
# saved beside the path if it is the user's. The originals are handled before
# anything that run had put in, so an original wins an empty path.
recover_set_aside() {
  local parent name staging dir tag f file rc
  case "$TARGET" in
    */*)
      parent="${TARGET%/*}"
      if [[ -z "$parent" ]]; then
        parent=/
      fi
      ;;
    *) parent=. ;;
  esac
  name="${TARGET##*/}"
  for staging in "$parent"/.dashboard-staging.*; do
    dir="$staging/set-aside.$name"
    if [[ -L "$staging" || -L "$dir" || ! -d "$dir" ]]; then
      continue
    fi
    tag="${staging##*.}"
    for f in package.json package-lock.json; do
      for file in "$dir/was.$tag.$f" "$dir/ours.$tag.$f"; do
        if [[ -e "$file" || -L "$file" ]]; then
          rc=0
          settle "$file" "$f" "$tag" || rc=$?
          if [[ "$rc" -eq 0 ]]; then
            echo "ensure-dashboard.sh: put $TARGET/$f back; an earlier run stopped while it was out of the directory." >&2
          fi
        fi
      done
    done
    if rmdir "$dir" 2>/dev/null; then
      echo "ensure-dashboard.sh: $staging was left by a run that stopped part way. Nothing in it is needed any more; it can be deleted." >&2
    fi
  done
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
  recover_set_aside
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
  manifest_state="$(state_of package.json)"
  lock_state="$(state_of package-lock.json)"
  for f in package.json package-lock.json; do
    if [[ "$f" == package.json && "$manifest_state" == unreadable ]] ||
      [[ "$f" == package-lock.json && "$lock_state" == unreadable ]]; then
      echo "ensure-dashboard.sh: $TARGET/$f cannot be read; fix its permissions and run again." >&2
      exit 1
    fi
  done

  # This release's pinned pair applies when the target's package.json is a
  # release's own and its lockfile is too, or is missing. A file the user
  # changed is never replaced: the target then installs from what it holds.
  plugin_pair=0
  if [[ -f "$src/package-lock.json" && "$manifest_state" != other && "$lock_state" != other ]]; then
    plugin_pair=1
  fi

  if [[ "$plugin_pair" -eq 0 && "$lock_state" == absent ]]; then
    # Scaffolded before the lockfile shipped, and nothing pins it.
    if [[ "$manifest_state" == other ]] && ! have_sha256; then
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

  # npm may have run for minutes. Before anything in the target is touched,
  # everything the install was planned against has to hold still: both files
  # as they were classified (or, for a target that installs from its own
  # pair, as they were copied), and no node_modules. If not, the target is
  # left exactly as it is.
  require_plain "$TARGET" dir
  if [[ ! -d "$TARGET" ]]; then
    changed_race "$TARGET"
  fi
  require_plain "$TARGET/node_modules" dir
  require_plain "$TARGET/package.json" file
  require_plain "$TARGET/package-lock.json" file
  if [[ -e "$TARGET/node_modules" ]]; then
    lost_race "$TARGET/node_modules"
  fi
  if [[ "$plugin_pair" -eq 1 ]]; then
    if [[ "$(state_of package.json)" != "$manifest_state" ]]; then
      changed_race "$TARGET/package.json"
    fi
    if [[ "$(state_of package-lock.json)" != "$lock_state" ]]; then
      if [[ "$lock_state" == absent ]]; then
        lost_race "$TARGET/package-lock.json"
      fi
      changed_race "$TARGET/package-lock.json"
    fi
  else
    for f in package.json package-lock.json; do
      if ! cmp -s "$TARGET/$f" "$WORK/$f"; then
        changed_race "$TARGET/$f"
      fi
    done
  fi

  # What this run will do to the two files: 0 nothing, 1 exchange an earlier
  # release's file for this release's, 2 create it where there is none.
  do_manifest=0
  do_lock=0
  if [[ "$plugin_pair" -eq 1 ]]; then
    if [[ "$manifest_state" == earlier:* ]]; then
      do_manifest=1
    fi
    if [[ "$lock_state" == earlier:* ]]; then
      do_lock=1
    elif [[ "$lock_state" == absent ]]; then
      do_lock=2
    fi
  fi
  was_manifest="$SET_ASIDE/was.$TAG.package.json"
  was_lock="$SET_ASIDE/was.$TAG.package-lock.json"
  new_manifest="$STAGING/new.$TAG.package.json"
  new_lock="$STAGING/new.$TAG.package-lock.json"
  if [[ "$do_manifest" -ne 0 ]]; then
    cp "$WORK/package.json" "$new_manifest"
  fi
  if [[ "$do_lock" -ne 0 ]]; then
    cp "$WORK/package-lock.json" "$new_lock"
  fi
  if [[ "$do_manifest" -ne 0 || "$do_lock" -ne 0 ]]; then
    mkdir "$SET_ASIDE"
  fi

  # From here the target changes. See "Exchanging a file" above. The order is:
  # both old files out, both checked, both new files in, node_modules in. It
  # is the completion signal and arrives last. Every state on the way is one
  # a later run finishes: it either holds a release's own files with no
  # node_modules, or a file is out and SET_ASIDE says so.
  hold_signals
  problem=""
  code=5
  took_manifest=0
  took_lock=0
  put_manifest=0
  put_lock=0

  if [[ "$do_manifest" -eq 1 ]]; then
    if mv "$TARGET/package.json" "$was_manifest" 2>/dev/null; then
      took_manifest=1
    else
      problem="$TARGET/package.json changed while this run was working; it was not replaced"
    fi
  fi
  if [[ -z "$problem" && "$do_lock" -eq 1 ]]; then
    if mv "$TARGET/package-lock.json" "$was_lock" 2>/dev/null; then
      took_lock=1
    else
      problem="$TARGET/package-lock.json changed while this run was working; it was not replaced"
    fi
  fi
  if [[ -z "$problem" && "$took_manifest" -eq 1 ]] && ! holds "$was_manifest" "${manifest_state#earlier:}"; then
    problem="$TARGET/package.json changed while this run was working; it was not replaced"
  fi
  if [[ -z "$problem" && "$took_lock" -eq 1 ]] && ! holds "$was_lock" "${lock_state#earlier:}"; then
    problem="$TARGET/package-lock.json changed while this run was working; it was not replaced"
  fi

  if [[ -z "$problem" && "$do_manifest" -ne 0 ]]; then
    rc=0
    put_file "$new_manifest" "$TARGET/package.json" || rc=$?
    if [[ "$rc" -eq 0 ]]; then
      put_manifest=1
    elif [[ "$rc" -eq 1 ]]; then
      problem="$TARGET/package.json was replaced while this run was working; it was left as it is now"
    else
      problem="could not write $TARGET/package.json"
      code=4
    fi
  fi
  if [[ -z "$problem" && "$do_lock" -ne 0 ]]; then
    rc=0
    put_file "$new_lock" "$TARGET/package-lock.json" || rc=$?
    if [[ "$rc" -eq 0 ]]; then
      put_lock=1
    elif [[ "$rc" -eq 1 && "$do_lock" -eq 2 ]]; then
      problem="$TARGET/package-lock.json appeared while this run was working; it was not overwritten"
    elif [[ "$rc" -eq 1 ]]; then
      problem="$TARGET/package-lock.json was replaced while this run was working; it was left as it is now"
    else
      problem="could not write $TARGET/package-lock.json"
      code=4
    fi
  fi
  if [[ -z "$problem" ]]; then
    if ! mv "$WORK/node_modules" "$INCOMING" 2>/dev/null; then
      problem="could not move node_modules out of $WORK"
      code=4
    elif ! place "$INCOMING" "$TARGET/node_modules"; then
      problem="$TARGET/node_modules appeared while this run was working; it was not overwritten"
    fi
  fi

  if [[ -n "$problem" ]]; then
    # Undo in reverse: what this run put in comes back out, then what it took
    # out goes back. A path someone else has filled in the meantime is theirs.
    notes=""
    for f in package-lock.json package.json; do
      if [[ "$f" == package.json ]]; then
        put=$put_manifest took=$took_manifest was=$was_manifest
      else
        put=$put_lock took=$took_lock was=$was_lock
      fi
      if [[ "$put" -eq 1 ]]; then
        if ! take_back "$f"; then
          notes="$notes What this run put at $TARGET/$f could not be taken back out; see above."
        elif [[ "$took" -eq 0 ]]; then
          notes="$notes $TARGET/$f, which this run had created, was removed again."
        fi
      fi
      if [[ "$took" -eq 1 ]]; then
        rc=0
        settle "$was" "$f" "$TAG" || rc=$?
        if [[ "$rc" -eq 0 ]]; then
          notes="$notes $TARGET/$f was put back as it was."
        elif [[ "$rc" -eq 3 ]]; then
          notes="$notes $TARGET/$f is what replaced it meanwhile."
        else
          notes="$notes $TARGET/$f was not put back; see above."
        fi
      fi
    done
    stop_on_signal
    if [[ -z "$notes" ]]; then
      notes=" Nothing in $TARGET was changed."
    fi
    echo "ensure-dashboard.sh: $problem.$notes Run again." >&2
    exit "$code"
  fi

  # The files that were taken out were checked: an earlier release's, byte
  # for byte. Nothing of the user's is in them.
  rm -f "$was_manifest" "$was_lock"
  stop_on_signal
  mkdir -p "${CLAUDE_PLUGIN_DATA}/data/images"
  replaced=""
  if [[ "$do_manifest" -eq 1 ]]; then
    replaced="package.json"
  fi
  if [[ "$do_lock" -eq 1 ]]; then
    replaced="${replaced:+$replaced and }package-lock.json"
  fi
  if [[ -n "$replaced" ]]; then
    echo "$replaced in $TARGET came unmodified from an earlier release; replaced with this release's"
  fi
  echo "dashboard ready at $TARGET (dependencies installed into the existing copy)"
  if [[ -n "$PENDING_SIGNAL" ]]; then
    exit "$PENDING_SIGNAL"
  fi
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
