# BrightOps AI Plugins — Claude Code Plugin Marketplace

## Project Structure

`.claude-plugin/marketplace.json` — plugin registry (update when adding/removing plugins)
`plugins/<name>/.claude-plugin/plugin.json` — plugin metadata (name, version, description, author)
`plugins/<name>/skills/<skill>/SKILL.md` — skill definition with YAML frontmatter
`plugins/<name>/skills/<skill>/references/` — supporting docs loaded on demand

## Current Plugins

- 1password (v1.1.0) — 2 skills: 1password, ssh-keys
- agent-teams (v1.1.0) — 1 skill: agent-teams

## Adding a New Plugin

1. Create `plugins/<name>/.claude-plugin/plugin.json` with name, version, description, author
2. Create `plugins/<name>/skills/<skill>/SKILL.md` with frontmatter (name, description required)
3. Add optional `references/`, `scripts/`, `assets/` subdirs under the skill
4. Register in `.claude-plugin/marketplace.json` — add entry to the plugins array

## Conventions

- SKILL.md frontmatter `description` uses third person: "This skill should be used when..."
- SKILL.md body uses imperative form, not second person
- Keep SKILL.md under ~2,000 words; move detailed content to references/
- No duplication between SKILL.md body and reference files
- Version bump in both plugin.json AND marketplace.json when updating a plugin
- After version bump, clear stale cache: `rm -rf ~/.claude/plugins/cache/brightopsai-plugins-official/<name>/<old-version>`

## Testing Locally

Reload after changes: `/reload-plugins` in Claude Code
If changes don't appear, check cache at `~/.claude/plugins/cache/brightopsai-plugins-official/`

## Gotchas

- Plugin cache is version-keyed — edits to files without a version bump won't be picked up
- marketplace.json version must match plugin.json version
- Remote: `brightops-ai/brightopsai-plugins-official` on GitHub (public)
