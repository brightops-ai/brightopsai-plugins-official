# brightops-ai-skills

## Overview

BrightOps AI workflow skills for Claude Code — one plugin holding many skills,
rather than a plugin per skill. Skills live in category subdirectories and are
listed in the plugin manifest's `skills` array.

All skills are user-invoked except `dream`, which stays model-invocable so a
scheduled routine can fire it.

## Install

Add this marketplace if it is not already configured, then install the plugin
inside Claude Code:

```
/plugin marketplace add brightops-ai/brightopsai-plugins-official
/plugin install brightops-ai-skills@brightopsai-plugins-official
```

## Skills

| Invoke | What it does |
|--------|----------------|
| `/brightops-ai-skills:improve-prompt` | Turn rough dictated or hastily typed input into a task brief another session can act on. Output is text to copy; the skill never runs the prompt it writes. User-invoked. |
| `/brightops-ai-skills:calibrate-style` | Optional setup for `improve-prompt`. Collects samples, derives speaking and typing style, and seeds the vocabulary. User-invoked. |
| `/brightops-ai-skills:dream` | Consolidate recent sessions into the memory that loads next time. Two modes a day apart: `full-analysis` then `apply-fixes`. Model-invocable so a schedule can fire it. |
| `/brightops-ai-skills:improve-memory` | Audit auto memory for silent defects, repair what is certain, propose the rest. User-invoked. |
| `/brightops-ai-skills:session-analysis` | Distil session transcripts into candidate episodes for a chosen purpose. Runs forked. User-invoked. |
| `/brightops-ai-skills:send-result` | Deliver a run summary to a configured destination (a file by default, or a command). Never infers a destination. User-invoked. |
| `/brightops-ai-skills:spawn-session` | Start a named Claude Code session in tmux, confirm it by a handshake token, then paste a starter brief. User-invoked. |

## Prerequisites

- `python3` (standard library only) for `dream`, `improve-memory`,
  `session-analysis`, and `send-result`
- `tmux` and the Claude Code CLI on `PATH` for `spawn-session`. `--trust-folder`
  on that skill also needs `python3`
- **Dream scheduling: Claude Code v2.1.196+.** From that version,
  `disable-model-invocation` also prevents a scheduled task from firing the
  skill. `dream` omits the flag on purpose; setting it would leave a routine
  that fires, does nothing, and reports no error. Other skills in this plugin
  keep the flag and are person-driven only.

## Data

Persistent plugin state lives under `${CLAUDE_PLUGIN_DATA}`:

- `vocabulary.md` — `improve-prompt` / `calibrate-style` local vocabulary
  (conventions of expression only; never task content). Export with
  `--export` before uninstalling if it should survive.
- `config.json` — `dream` / `send-result` settings, including the delivery
  destination
- `runs/<timestamp>/` — `dream` run state (`digest.json`, `analysis.md`, the
  overview)
- `results/` — delivered summaries when the destination is a file

Memory itself and `improve-memory` snapshots live beside the project's memory
directory, not here, so they survive uninstall. `spawn-session` does not write
plugin data; it uses tmux. `session-analysis` writes into a run directory the
caller names (for `dream`, that is under `runs/`).

## Update

`/plugin update` reads the version from this plugin's `plugin.json`. A file-only
edit with no version bump is not picked up — the plugin cache is version-keyed.
See [CHANGELOG.md](CHANGELOG.md).

## Uninstall

Uninstalling this plugin from every scope removes `${CLAUDE_PLUGIN_DATA}` —
vocabulary, run history, delivery config, and file-destination summaries.
Memory files and snapshots are not in that directory and are not deleted.
Copy `vocabulary.md` and `runs/` somewhere durable first if they matter.
