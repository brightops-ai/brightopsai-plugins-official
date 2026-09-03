# BrightOps AI Plugins — Claude Code Plugin Marketplace

## Project Structure

`.claude-plugin/marketplace.json` — plugin registry (update when adding/removing plugins)
`plugins/<name>/.claude-plugin/plugin.json` — plugin metadata (name, version, description, author)
`plugins/<name>/skills/<skill>/SKILL.md` — skill definition with YAML frontmatter
`plugins/<name>/skills/<skill>/references/` — supporting docs loaded on demand
`plugins/<name>/skills/<category>/<skill>/SKILL.md` — categorised variant; every such path must be
listed in the plugin manifest's `skills` array, since default discovery only finds skills at the top
level of `skills/`

## Current Plugins

- 1password (v1.2.0) — 2 skills: 1password, ssh-keys
- agent-teams (v1.2.0) — 1 skill: agent-teams
- adversarial-review (v1.3.0) — 1 skill: adversarial-review
- marketplace-scout (v1.1.0) — 1 skill: marketplace-scout
- brightops-ai-skills (v1.1.0) — 2 skills: improve-prompt, calibrate-style

## Adding a New Skill

BrightOps AI workflow skills go into the existing `brightops-ai-skills` plugin, not a new plugin
each. One author-branded plugin holding many skills is the pattern used by comparable skill
collections, and it means a user installs once. Add the skill under a category subdirectory and list
its path in the plugin manifest's `skills` array.

A separate plugin is warranted only for a tool integration carrying heavy external dependencies —
a CLI, browser automation, an MCP server — not for a skill that is mostly a procedure.

## Adding a New Plugin

1. Create `plugins/<name>/.claude-plugin/plugin.json` with name, version, description, author
2. Create `plugins/<name>/skills/<skill>/SKILL.md` with frontmatter (name, description required)
3. Add optional `references/`, `scripts/`, `assets/` subdirs under the skill
4. Register in `.claude-plugin/marketplace.json` — add entry to the plugins array

## Conventions

- SKILL.md frontmatter `description` depends on how the skill is invoked:
  - Model-invocable (no `disable-model-invocation`): third person carrying trigger phrases — "This
    skill should be used when the user asks to..." The trigger list exists to drive model matching.
  - User-invoked (`disable-model-invocation: true`): a single short line. The model cannot invoke
    the skill, so the description is only a picker label and a trigger list is dead weight.
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
- Never store user data inside a plugin directory; it is orphaned by the next version bump. Use
  `${CLAUDE_PLUGIN_DATA}`, which survives updates (but is removed when the plugin is uninstalled
  from all scopes)
- marketplace.json version must match plugin.json version
- Remote: `brightops-ai/brightopsai-plugins-official` on GitHub (public)
