# Migration scope for existing marketplace plugins

A plugin name is the install identity (`<plugin>@brightopsai-plugins-official`).
Moving a skill into another plugin orphans every existing install of the old
name (cache still runs; `/plugin update` never lands), resets
`${CLAUDE_PLUGIN_DATA}` for that skill (the directory is keyed by plugin name),
and changes the invoke. This record decides, per existing plugin, what happens
to it.

- **Status:** Accepted — maintainer decision, 2026-09-06
  ([issue #12](https://github.com/brightops-ai/brightopsai-plugins-official/issues/12))
- **Does not land:** no plugin, manifest, README table, or version change in
  this record. Implementation is separate work.

## Context

`CLAUDE.md` and `CONTRIBUTING.md` split the catalog: BrightOps AI workflow
skills (procedure, no heavy external dependency) go in `brightops-ai-skills`;
a separate plugin is only for a tool integration with a CLI, browser
automation, or an MCP server.

That rule was written for *new* skills. The five plugins already in the
marketplace were published as their own install identities, so each needed
its own call rather than a blanket move.

## Decision

| Plugin | Classification | Decision | Why |
|--------|----------------|----------|-----|
| `1password` | Tool integration | Keep standalone | Depends on the `op` CLI. Exact case reserved for a separate plugin. |
| `marketplace-scout` | Tool integration | Keep standalone | Playwright plugin plus a Facebook login. Also writes listings and dashboard state under `${CLAUDE_PLUGIN_DATA}` — a rename would reset that data. |
| `adversarial-review` | Tool integration | Keep standalone | Playwright plugin plus a grok.com login. Same separate-plugin case. |
| `agent-teams` | Workflow skill | **Deprecate, then remove. Do not consolidate.** | A replacement skill, published separately by BrightOps AI, supersedes it. Moving it into `brightops-ai-skills` first would rename the invoke twice. |
| `brightops-ai-skills` | Workflow-skill home | Stay unchanged | Nothing moves in. |

Nothing consolidates. The consolidation ticket (#13) is closed as not planned.

## Consequences

- Installs of `1password`, `marketplace-scout`, and `adversarial-review` keep
  their identity, invoke names, and data directories.
- `agent-teams` users keep working from cache after removal but stop receiving
  updates. They should move to the replacement skill when it is published.
- `agent-teams` stores nothing under `${CLAUDE_PLUGIN_DATA}` (its SKILL.md only
  describes Claude Code's own team state), so removal drops no user data.

## Removal path for agent-teams

1. **Deprecate.** Mark the plugin deprecated in `plugins/agent-teams/README.md`,
   the `plugin.json` description, and its changelog, naming the replacement
   once it has a public name. Bump the patch version so `/plugin update` users
   see the notice. Keep the marketplace entry for at least one release.
2. **Remove.** Delete `plugins/agent-teams/` and its marketplace entry, drop
   the README table row and Plugin Details entry, record the removal in the
   root `CHANGELOG.md`, and run `scripts/check-marketplace.py`. If the
   replacement is already published, point at it in that changelog entry.

## Alternatives considered

**Consolidate `agent-teams` into `brightops-ai-skills`.** The original
proposal. Rejected: with a replacement coming, the move would cost users an
invoke rename and a data-directory change for a skill that is about to be
superseded anyway.

**Consolidate everything.** Rejected: it would orphan the three tool
integrations' installs, reset `marketplace-scout`'s real data, and pull `op`
plus Playwright/login dependencies into the workflow plugin — the opposite of
the tool-integration exception.
