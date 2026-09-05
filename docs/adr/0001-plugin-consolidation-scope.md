# Plugin consolidation scope for existing marketplace plugins

A plugin name is the install identity (`<plugin>@brightopsai-plugins-official`).
Moving a skill into another plugin orphans every existing install of the old
name (cache still runs; `/plugin update` never lands), resets
`${CLAUDE_PLUGIN_DATA}` for that skill (the directory is keyed by plugin name),
and changes the invoke. This record recommends which of the five existing
plugins stay standalone and which, if any, move into `brightops-ai-skills`.

- **Status:** Proposed — awaiting maintainer decision ([issue #12](https://github.com/brightops-ai/brightopsai-plugins-official/issues/12))
- **Does not land:** no plugin, manifest, README table, or version change in this proposal

## Context

`CLAUDE.md` and `CONTRIBUTING.md` already split the catalog: BrightOps AI
workflow skills (procedure, no heavy external dependency) go in
`brightops-ai-skills`; a separate plugin is only for a tool integration with a
CLI, browser automation, or an MCP server.

That rule was written for *new* skills. The five plugins already in the
marketplace were published as their own install identities. Consolidation is a
breaking change for anyone who already installed the old name, so each plugin
needs its own call, not a blanket move.

## Decision

| Plugin | Classification | Decision | Why |
|--------|----------------|----------|-----|
| `1password` | Tool integration | Keep standalone | Depends on the `op` CLI. Exact case reserved for a separate plugin. |
| `marketplace-scout` | Tool integration | Keep standalone | Playwright plugin plus a Facebook login. Also writes listings and dashboard state under `${CLAUDE_PLUGIN_DATA}` — a rename would reset that data. |
| `adversarial-review` | Tool integration | Keep standalone | Playwright plugin plus a grok.com login. Same separate-plugin case. |
| `agent-teams` | Workflow skill | Consolidate into `brightops-ai-skills`, with the upgrade path below | Procedure skill. Only extra requirement is a Claude Code version floor (v2.1.178+), not an external tool. |
| `brightops-ai-skills` | Workflow-skill home | Stay; receive `agent-teams` | Already the consolidation target. No identity change. |

## Consequences

- Installs of `1password`, `marketplace-scout`, and `adversarial-review` keep
  their current identity, invoke names, and data directories.
- After the move, the invoke becomes `/brightops-ai-skills:agent-teams` instead
  of `/agent-teams:agent-teams`. Anyone still on the standalone plugin keeps
  working from cache until they uninstall or the marketplace entry is removed,
  but they stop receiving updates once the old plugin is gone.
- `agent-teams` stores nothing under `${CLAUDE_PLUGIN_DATA}`, so the data-dir
  reset that a rename would cause does not apply (see upgrade path step 5).
- Accepting this proposal does not perform the move. Implementation is a later
  change, after the maintainer accepts, amends, or rejects this record.

## Upgrade path for agent-teams

Do this only after this ADR is accepted. Order:

1. Add the skill at `plugins/brightops-ai-skills/skills/teams/agent-teams` and
   list `./skills/teams/agent-teams` in that plugin's `plugin.json` `skills`
   array (nested skills are not auto-discovered).
2. Bump `brightops-ai-skills` minor (new skill, not a breaking change to that
   plugin) and changelog the addition, including the new invoke
   `/brightops-ai-skills:agent-teams`.
3. Mark the standalone `agent-teams` plugin deprecated in its README,
   `plugin.json` description, and changelog. Point at the new invoke. Keep the
   marketplace entry for at least one release so `/plugin update` users see the
   notice.
4. In a later release, remove the standalone plugin from the marketplace and
   record that removal in the root `CHANGELOG.md`.
5. No data migration. `plugins/agent-teams/skills/agent-teams/SKILL.md` never
   reads or writes `${CLAUDE_PLUGIN_DATA}` — it only describes Claude Code's
   own team/session state (spawn prompts, tasks, the implicit team). The plugin
   README states the same. Uninstalling the old plugin therefore drops an empty
   data dir, not user files.

People on the old plugin: install `brightops-ai-skills` (if not already),
invoke `/brightops-ai-skills:agent-teams`, then uninstall
`agent-teams@brightopsai-plugins-official`.

## Alternatives considered

**Keep everything standalone.** Avoids orphaning any install and avoids the
invoke rename. Rejected for `agent-teams`: it is a workflow skill, and leaving
it separate means two installs for the procedure catalog, against the rule
already in `CLAUDE.md`. The three tool integrations stay standalone under the
recommended path, so this alternative is what we already choose for those.

**Consolidate everything.** One install, one invoke prefix. Rejected: it would
orphan `1password`, `marketplace-scout`, and `adversarial-review` installs,
reset `marketplace-scout`'s real `${CLAUDE_PLUGIN_DATA}` (CSVs, images,
dashboard), and pull the `op` CLI plus Playwright/login dependencies into the
workflow plugin — the opposite of the tool-integration exception.
