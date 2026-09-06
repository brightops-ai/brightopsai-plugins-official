# agent-teams

> **Deprecated.** This plugin will be removed from the marketplace in a later
> release. Installed copies keep working from cache but stop receiving updates.
> It stores nothing under `${CLAUDE_PLUGIN_DATA}`, so nothing needs migrating.
> A replacement skill will be published separately by BrightOps AI. See
> [ADR 0001](../../docs/adr/0001-plugin-consolidation-scope.md).

## Overview

Orchestrate multi-agent Claude Code teams for parallel research, review,
debugging, and feature development. The skill covers when a team is worth the
token cost, how to partition file ownership, and how to write spawn prompts
teammates can act on without the lead's conversation history.

Templates shipped with the skill: parallel code review, competing debug
hypotheses, cross-layer feature development, and large-scale refactoring.

## Install

Add this marketplace if it is not already configured, then install the plugin
inside Claude Code:

```
/plugin marketplace add brightops-ai/brightopsai-plugins-official
/plugin install agent-teams@brightopsai-plugins-official
```

## Skills

| Invoke | What it does |
|--------|----------------|
| `/agent-teams:agent-teams` | Design the team, write spawn prompts, partition files, and coordinate teammates. |

The skill is model-invocable.

## Prerequisites

- **Claude Code v2.1.178+.** From that version, teammates spawn directly via the
  Agent tool with a `name`. There is no separate team-creation step, and
  `TeamCreate` / `TeamDelete` no longer exist.
- `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` in the `env` section of
  `settings.json` (or the shell environment). Without it, no team is set up at
  session start and Claude does not spawn or propose teammates.
- Split-pane display is optional. The default is in-process (agent panel). Split
  panes need tmux, or iTerm2 with the `it2` CLI.

## Data

This plugin does not write under `${CLAUDE_PLUGIN_DATA}`. Team config and task
lists are Claude Code's own session-derived state, not this plugin's data
directory. Uninstalling the plugin does not remove that Claude Code state.

## Update

`/plugin update` reads the version from this plugin's `plugin.json`. A file-only
edit with no version bump is not picked up — the plugin cache is version-keyed.
See [CHANGELOG.md](CHANGELOG.md).

## Uninstall

Uninstalling this plugin from every scope removes `${CLAUDE_PLUGIN_DATA}`. This
plugin does not store anything there. Claude Code's team and task directories
are separate and are not deleted by uninstalling the plugin.
