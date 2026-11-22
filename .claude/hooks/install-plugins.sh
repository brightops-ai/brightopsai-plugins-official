#!/usr/bin/env bash
#
# SessionStart hook — activate the tracked git hooks, then make sure the
# plugins this repo enables are installed. .claude/settings.json registers it
# with the `startup` matcher, so it runs for a new session and not on resume,
# /clear or compaction. Every step is idempotent in case it runs again.
#
# Git hooks: git never clones hooks, so a fresh clone commits with no local
# secret scan until scripts/install-hooks.sh has pointed core.hooksPath at
# .githooks/.
#
# Plugins: a plugin that only project settings enable does not load until it
# is installed on the machine, and Claude Code does not download it for that
# entry alone; it does so only when user settings, .claude/settings.local.json,
# --settings or managed settings enable it. An Anthropic-hosted cloud session
# does not add the marketplaces listed under extraKnownMarketplaces either. So
# a fresh container starts with the plugin enabled and missing
# (https://code.claude.com/docs/en/plugins/loading).
#
# What this hook does about it:
#   - Installs a plugin only when `claude plugin list --json` exits 0, parses
#     as JSON and has no row for the plugin that applies to this project. If
#     the listing fails, cannot be parsed or python3 is missing, the answer is
#     unknown and the hook warns and skips the install.
#   - Never updates an installed plugin, and prints the installed version to
#     stderr so a change of version is visible.
#
# What it cannot do: pin. `claude plugin install` takes no version or commit
# (checked on Claude Code 2.1.330), and a commit `ref` is refused for a
# reserved marketplace name such as claude-plugins-official. Marketplace
# auto-update is a separate path; .claude/settings.json turns it off for this
# marketplace (`autoUpdate: false`) in sessions that read that file.
#
# A plugin installed here is on disk, not loaded: it is available from the
# next session, or in this one after /reload-plugins.
#
# Everything this hook prints goes to stderr: SessionStart stdout is added to
# the model's context. It never fails the session: a broken step costs you the
# pre-commit gate or the skills, not the session.

set -uo pipefail

PLUGINS=(
  "mattpocock-skills@claude-plugins-official"
)

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." 2>/dev/null && pwd)"

if [ -z "$repo_root" ] || ! (cd "$repo_root" && bash scripts/install-hooks.sh) >&2; then
  echo "WARNING: scripts/install-hooks.sh failed; commits in this clone SKIP the gitleaks pre-commit scan. Run ./scripts/install-hooks.sh by hand." >&2
fi

# Decides whether plugin $1 is installed for this project. Sets plugin_state
# to installed, missing or unknown, and plugin_detail to the versions found or
# to the reason the answer is unknown. A row counts when its scope is user or
# managed, or project or local with a projectPath that is this repository.
plugin_state="unknown"
plugin_detail=""
plugin_status() {
  local listing
  plugin_state="unknown"
  if ! listing="$(claude plugin list --json)"; then
    plugin_detail="claude plugin list --json failed"
    return
  fi
  if ! command -v python3 >/dev/null 2>&1; then
    plugin_detail="python3 is not on PATH, so the plugin listing cannot be read"
    return
  fi
  if ! plugin_detail="$(printf '%s' "$listing" | python3 -I -c '
import json
import os
import sys

plugin, root = sys.argv[1], os.path.realpath(sys.argv[2])
rows = json.load(sys.stdin)
if not isinstance(rows, list):
    sys.exit(1)
found = []
for row in rows:
    if not isinstance(row, dict):
        sys.exit(1)
    if row.get("id") != plugin:
        continue
    scope = row.get("scope")
    if scope in ("project", "local"):
        path = row.get("projectPath")
        if not isinstance(path, str):
            sys.exit(1)
        if os.path.realpath(path) != root:
            continue
    elif scope not in ("user", "managed"):
        sys.exit(1)
    version = row.get("version")
    if not isinstance(version, str) or not version:
        version = "unknown version"
    found.append("%s (%s scope)" % (version, scope))
print(", ".join(found))
' "$1" "$repo_root")"; then
    plugin_detail="the plugin listing is not the JSON this hook expects"
    return
  fi
  if [ -n "$plugin_detail" ]; then
    plugin_state="installed"
  else
    plugin_state="missing"
  fi
}

if ! command -v claude >/dev/null 2>&1; then
  echo "warning: claude is not on PATH — skipping the plugin check; plugin skills may be unavailable this session" >&2
  exit 0
fi

for plugin in "${PLUGINS[@]}"; do
  plugin_status "$plugin"
  case "$plugin_state" in
    installed)
      echo "install-plugins: $plugin is installed: $plugin_detail — not updating" >&2
      ;;
    missing)
      echo "WARNING: $plugin is not installed; this INSTALLS the version its marketplace serves right now." >&2
      if claude plugin install "$plugin" -y >&2; then
        plugin_status "$plugin"
        if [ "$plugin_state" != "installed" ]; then
          plugin_detail="version not confirmed"
        fi
        echo "install-plugins: installed $plugin: $plugin_detail. It loads in the next session, or in this one after /reload-plugins." >&2
      else
        echo "warning: could not install $plugin — its skills will be unavailable this session" >&2
      fi
      ;;
    *)
      echo "WARNING: cannot tell whether $plugin is installed ($plugin_detail); this SKIPS the install. Check with: claude plugin list" >&2
      ;;
  esac
done

exit 0
