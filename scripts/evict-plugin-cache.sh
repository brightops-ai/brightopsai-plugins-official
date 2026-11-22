#!/usr/bin/env bash
# Removes one old version of one plugin from this marketplace's plugin cache.
#
# The cache is version-keyed, so after a plugin.json bump the previous
# version's directory is dead weight that can still shadow a debugging session.
# This replaces a hand-filled `rm -rf` whose two path segments, filled from an
# empty variable, would have landed on the whole cache directory.
#
# Usage:  scripts/evict-plugin-cache.sh [--dry-run] <plugin> <old-version>
#
#   --dry-run   print the resolved target and its file count; delete nothing
#               (a non-empty DRY_RUN other than 0 does the same)
#
# Honours CLAUDE_CONFIG_DIR (default: ~/.claude), so tests can sandbox it.
# Runs on macOS (bash 3.2) and Linux.
#
# Exit status: 0 evicted, dry run, or nothing there; 1 refused; 2 bad arguments.

set -euo pipefail

MARKETPLACE="brightopsai-plugins-official"

usage() {
  echo "usage: evict-plugin-cache.sh [--dry-run] <plugin> <old-version>" >&2
  echo "       e.g. evict-plugin-cache.sh --dry-run brightops-ai-skills 1.4.0" >&2
}

# Symlink-free absolute path of an existing path.
resolve() {
  if command -v realpath >/dev/null 2>&1; then
    realpath -- "$1"
  else
    python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$1"
  fi
}

# Any DRY_RUN value other than empty or 0 means dry run, so DRY_RUN=true
# cannot fall through to a real delete.
case "${DRY_RUN:-0}" in
  0 | "") dry_run=0 ;;
  *) dry_run=1 ;;
esac
if [ "${1:-}" = "--dry-run" ]; then
  dry_run=1
  shift
fi

if [ "$#" -ne 2 ]; then
  usage
  exit 2
fi

plugin="${1:?evict-plugin-cache: <plugin> is empty}"
version="${2:?evict-plugin-cache: <old-version> is empty}"

# Strict shapes: neither can carry a slash, a dot-dot segment or a glob.
plugin_re='^[a-z0-9]+(-[a-z0-9]+)*$'
version_re='^[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z]+([.-][0-9A-Za-z]+)*)?(\+[0-9A-Za-z]+([.-][0-9A-Za-z]+)*)?$'

if [[ ! "$plugin" =~ $plugin_re ]]; then
  echo "evict-plugin-cache: '$plugin' is not a plugin slug (lowercase letters, digits, single hyphens). Refusing." >&2
  usage
  exit 2
fi
if [[ ! "$version" =~ $version_re ]]; then
  echo "evict-plugin-cache: '$version' is not a semantic version (MAJOR.MINOR.PATCH). Refusing." >&2
  usage
  exit 2
fi

config_dir="${CLAUDE_CONFIG_DIR:-${HOME:?evict-plugin-cache: HOME is not set}/.claude}"
cache_root="$config_dir/plugins/cache/$MARKETPLACE"
target="$cache_root/$plugin/$version"

if [ -L "$target" ] || { [ -e "$target" ] && [ ! -d "$target" ]; }; then
  echo "WARNING: '$target' is a symlink or not a directory; this DELETES whatever it points at. Refusing." >&2
  exit 1
fi
if [ ! -d "$target" ]; then
  echo "evict-plugin-cache: nothing to evict: $target does not exist."
  exit 0
fi

# Containment: with every symlink resolved, the target must be exactly
# <cache root>/<plugin>/<version>. A symlinked plugin directory that leads out
# of the cache root, or to another plugin inside it, fails this.
root_real="$(resolve "$cache_root")"
target_real="$(resolve "$target")"
if [ -z "$root_real" ] || [ "$target_real" != "$root_real/$plugin/$version" ]; then
  echo "WARNING: '$target' resolves to '$target_real', not '$root_real/$plugin/$version'; this DELETES files outside the plugin cache. Refusing." >&2
  exit 1
fi

count="$(find "$target_real" -type f | wc -l | tr -d ' ')"

if [ "$dry_run" = "1" ]; then
  echo "dry run: would delete $target_real ($count files)"
  exit 0
fi

echo "WARNING: evicting cached $plugin $version; this DELETES $target_real ($count files). Claude Code re-creates it only if that version is installed again." >&2
rm -rf -- "$target_real"
echo "evicted $target_real"
