# brightops-wiki

Global auto-capture wiki for Claude Code. Captures durable conclusions from any session via a Stop hook, accumulates them in an inbox, and compiles them into project-organized synthesis pages on a `/loop` schedule.

Hybrid of three ideas: [Karpathy's compile-first wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f), [MemPalace's hook-driven capture](https://github.com/milla-jovovich/mempalace), and [Ss1024sS/LLM-wiki's productized bootstrap](https://github.com/Ss1024sS/LLM-wiki).

## What it does

1. A Stop hook fires every 12 user messages (configurable) from any Claude Code session on your machine
2. The hook does NO LLM work — it uses counters and tells the active Claude session to write a "nugget" to `$WIKI_ROOT/inbox/raw/`
3. The active Claude session writes a markdown nugget with frontmatter (`origin_project`, `origin_session`, `captured_at`), then you `/exit` normally
4. A separate dedicated Claude session runs `/loop 15m /wiki-process-inbox` inside the wiki directory
5. Every 15 minutes, that loop compiles pending nuggets into `$WIKI_ROOT/docs/wiki/pages/<project>/<topic>.md`, regenerates the index, runs checks, and commits

**Nuggets from 25+ projects flow into one global wiki, organized by project, provenance-tracked, auditable in git.**

## Installation

Prerequisites:

- Python 3.9+
- `git`
- Claude Code
- A wiki location (default: `$HOME/Documents/wiki`, overridable via `$BRIGHTOPS_WIKI_ROOT`)

Add the marketplace and install the plugin:

```bash
# In Claude Code:
/plugin marketplace add /path/to/brightopsai-plugins-official
/plugin install brightops-wiki@brightopsai-plugins-official
```

Restart Claude Code. The Stop hook will not fire until after a full restart (per Claude Code's hook lifecycle).

Then bootstrap the wiki directory:

```
# In Claude Code, in any session:
Set up the brightops-wiki
```

This triggers the `wiki-bootstrap` skill. It clones Ss1024sS LLM-wiki to a temp dir, runs its bootstrap against your chosen wiki root, applies the four brightops-wiki patches, and verifies everything is working.

Finally, open a dedicated terminal in the wiki root and kick off the processing loop:

```bash
cd "$HOME/Documents/wiki"  # or wherever BRIGHTOPS_WIKI_ROOT points
claude
/loop 15m /wiki-process-inbox
```

Leave that terminal open. Work in other projects normally. Your captures will be compiled automatically.

## Components

| Type | Name | Purpose |
|---|---|---|
| Hook | `hooks/scripts/wiki_capture_hook.sh` | Stop hook, fires every N messages, writes nuggets to inbox |
| Slash command | `commands/wiki-process-inbox.md` | Compiles inbox nuggets into wiki pages |
| Script | `scripts/regenerate_index.py` | Rebuilds `index.md` from `pages/**` (called by slash command) |
| Skill | `skills/wiki-bootstrap/` | Guides first-run setup (clone Ss1024sS, apply patches, verify) |

## Configuration

Environment variables (typically set in your shell rc):

| Variable | Default | Purpose |
|---|---|---|
| `BRIGHTOPS_WIKI_ROOT` | `$HOME/Documents/wiki` | Where the wiki lives on disk |
| `BRIGHTOPS_WIKI_INTERVAL` | `12` | Fire the capture hook every N user messages |

Both variables are read at session start. Changes require restarting Claude Code.

## How captures work (the zero-LLM-cost hook pattern)

The Stop hook does zero LLM work. When it decides to fire:

1. Writes a unique nugget filename to `$WIKI_ROOT/inbox/raw/` (does not write content — that's the AI's job)
2. Returns `{"decision":"block","reason":"write a nugget at <path> with format X"}` to Claude Code
3. Claude Code shows the reason as a system message to the active AI session
4. The active session (which already has the conversation context) writes the nugget as its next response
5. The session `/exit`s normally — the next Stop fires with `stop_hook_active=true` and the hook lets it through

**No extra LLM call per capture.** The cost is the token budget the active session was already going to use.

## Recursion guards

The hook has three guards to prevent feedback loops:

1. `stop_hook_active=true` → second Stop after a block, let it through
2. `CLAUDE_PROJECT_DIR == BRIGHTOPS_WIKI_ROOT` → the dedicated `/loop` session runs inside the wiki and must not capture itself
3. `_just_captured` flag → set by the manual `/wiki-capture` slash command (planned for v0.2) to prevent immediate re-fire

## Project routing

Nuggets carry an `origin_project` field derived from the capturing session's `CLAUDE_PROJECT_DIR` basename (lowercased, non-alphanumeric → `-`). The `/wiki-process-inbox` slash command uses this to route nuggets to `pages/<origin_project>/`.

**Meta-nuggets** — nuggets captured from workspace-root sessions where `origin_project` is `local-dev`, `tmp`, `home`, or similar — are routed by content analysis to the most appropriate existing subdir, or to `wiki-tooling` / `meta` when uncertain.

The `pages/<project>/` directory itself is the project registry. No registry file. New project = new subdir on first nugget, auto-logged to `log.md`.

## Scoped git commits

The compile loop commits only paths it owns: `git add docs/wiki/pages/ docs/wiki/index.md docs/wiki/log.md inbox/processed/`. Never `git add -A`. Any in-flight manual edits in the wiki directory are safe from being swept into automated commits.

## Known risks

- **iCloud-synced wiki locations** (e.g., `~/Documents/wiki/` if `~/Documents/` is iCloud-synced): iCloud may silently corrupt `.git/pack` files. Workarounds: keep canonical wiki at `~/.local/share/wiki/` with rsync-to-iCloud, or rename `.git` with `.nosync` extension, or use `git --git-dir` separation. The bootstrap skill does not currently detect or warn about this — manual awareness required.
- **Plugin cache is version-keyed.** After iterating on brightops-wiki, bump the version in both `plugin.json` and `marketplace.json`, then `rm -rf ~/.claude/plugins/cache/brightopsai-plugins-official/brightops-wiki/<old-version>` to force reload.
- **Hook lifecycle**: hooks load at session start. Changes to the hook script require a full Claude Code restart, not `/reload-plugins`.

## See also

- `skills/wiki-bootstrap/references/architecture.md` — detailed design notes, lineage, and rationale
- `skills/wiki-bootstrap/references/ss1024ss-patches.md` — the four patches the skill applies to Ss1024sS LLM-wiki v1.2.2

## Version

0.1.0 — initial release.
