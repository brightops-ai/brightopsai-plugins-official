#!/usr/bin/env bash
#
# ensure-dashboard.sh — scaffold the marketplace-scout dashboard under
# CLAUDE_PLUGIN_DATA (or an explicit target). Never overwrites a present copy.
#
# Usage: ensure-dashboard.sh [target]
#   exit 0  dashboard present or freshly scaffolded; prints the path
#   exit 2  CLAUDE_PLUGIN_DATA or CLAUDE_PLUGIN_ROOT unset
#   exit 3  leftover ./dashboard or ./data in cwd; prints an mv instruction
#
# SKIP_NPM_INSTALL: if set, skip `npm install` (tests set this).

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

if [[ -e "$TARGET" ]]; then
  echo "dashboard present at $TARGET; not overwriting"
  exit 0
fi

src="${CLAUDE_PLUGIN_ROOT}/skills/marketplace-scout/assets/dashboard"
if [[ ! -d "$src" ]]; then
  echo "ensure-dashboard.sh: missing dashboard assets at $src" >&2
  exit 1
fi

mkdir -p "$TARGET"
for item in "$src"/*; do
  [[ -e "$item" ]] || continue
  name="${item##*/}"
  if [[ "$name" == "node_modules" ]]; then
    continue
  fi
  cp -R "$item" "$TARGET/"
done
mkdir -p "${CLAUDE_PLUGIN_DATA}/data/images"

if [[ -z "${SKIP_NPM_INSTALL+x}" ]]; then
  (cd "$TARGET" && npm install)
fi

echo "dashboard ready at $TARGET"
