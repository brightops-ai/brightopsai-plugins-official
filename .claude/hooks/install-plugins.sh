#!/usr/bin/env bash
#
# SessionStart hook — activate the tracked git hooks, then make sure the
# plugins this repo enables are installed.
#
# Git hooks: git never clones hooks, so a fresh clone commits with no local
# secret scan until scripts/install-hooks.sh has pointed core.hooksPath at
# .githooks/. That script is idempotent, so it runs on every session start.
#
# Plugins: `enabledPlugins` in .claude/settings.json flips a plugin on, but it
# does not fetch it. Claude Code has no auto-install for plugins that only
# project settings enable (anthropics/claude-code#41669, #23737), so every
# fresh container — Claude Code on the web, cloud sessions, CI — starts with
# the plugin enabled and missing, and none of its skills load.
#
# `claude plugin install` takes no version or commit pin (checked on Claude
# Code 2.1.330), so an install resolves whatever the marketplace serves at
# that moment. This hook therefore installs a plugin only when it is not
# installed yet, and never updates one. Either way it prints the installed
# version to stderr, so a change of version is visible. To move to a newer
# version on purpose: `claude plugin update <plugin>`.
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

# Prints the installed version of plugin $1, read from `claude plugin list
# --json` on stdin. Prints "unknown" when the plugin is listed without a
# version, and nothing when it is not listed. Uses only POSIX tools: a fresh
# container may have neither jq nor python.
installed_version() {
  local record version
  record="$(tr -d '\n' | tr '}' '\n' |
    grep -F -e "\"id\": \"$1\"" -e "\"id\":\"$1\"" | head -n 1)"
  [ -n "$record" ] || return 0
  version="$(printf '%s\n' "$record" |
    sed -n 's/.*"version" *: *"\([^"]*\)".*/\1/p')"
  printf '%s\n' "${version:-unknown}"
}

if ! command -v claude >/dev/null 2>&1; then
  echo "warning: claude is not on PATH — skipping the plugin check; plugin skills may be unavailable this session" >&2
  exit 0
fi

for plugin in "${PLUGINS[@]}"; do
  version="$(claude plugin list --json 2>/dev/null | installed_version "$plugin")"
  if [ -n "$version" ]; then
    echo "install-plugins: $plugin $version is installed — not updating" >&2
    continue
  fi

  echo "WARNING: $plugin is not installed; this INSTALLS the version its marketplace serves right now." >&2
  if claude plugin install "$plugin" -y >&2; then
    version="$(claude plugin list --json 2>/dev/null | installed_version "$plugin")"
    echo "install-plugins: installed $plugin ${version:-unknown}" >&2
  else
    echo "warning: could not install $plugin — its skills will be unavailable this session" >&2
  fi
done

exit 0
