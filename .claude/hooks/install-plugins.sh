#!/usr/bin/env bash
#
# SessionStart hook — install the plugins this repo enables.
#
# `enabledPlugins` in .claude/settings.json flips a plugin on, but it does not
# fetch it. Claude Code has no auto-install for plugins that only project
# settings enable (anthropics/claude-code#41669, #23737), so every fresh
# container — Claude Code on the web, cloud sessions, CI — starts with the
# plugin enabled and missing, and none of its skills load.
#
# Installing is idempotent and takes ~2s once the plugin is cached, so this
# runs on every session start. It never fails the session: a broken install
# costs you the skills, not the session.

set -uo pipefail

PLUGINS=(
  "mattpocock-skills@claude-plugins-official"
)

for plugin in "${PLUGINS[@]}"; do
  if ! claude plugin install "$plugin" -y >&2; then
    echo "warning: could not install $plugin — its skills will be unavailable this session" >&2
  fi
done

exit 0
