# Configuration and run state

## Where state lives

`${CLAUDE_PLUGIN_DATA}` — the per-plugin data directory, which survives plugin
updates.

```
<plugin data>/
├── config.json          settings, including the delivery destination
├── runs/<timestamp>/    digest.json, analysis.md, the overview
└── results/             delivered summaries when the destination is a file
```

Never write user state inside the plugin directory: installed plugins live in a
version-keyed cache and anything there is orphaned by the next version bump.

**Snapshots are the deliberate exception.** They live beside the memory
directory, not here, because per-plugin data is removed when the plugin is
uninstalled from its last scope. See the change-classification reference.

## Settings

```json
{
  "destination": "file",
  "window_days": 7,
  "token_budget": 40000,
  "stale_days": 180,
  "expire_after_runs": 3,
  "keep_snapshots": 10
}
```

| Setting | Default | Meaning |
|---|---|---|
| `destination` | `file` | Where summaries go |
| `window_days` | 7 | Fallback window when there is no previous run |
| `token_budget` | 40000 | Ceiling on digest size; the oldest episodes drop first |
| `stale_days` | 180 | Age past which a memory is flagged for confirmation |
| `expire_after_runs` | 3 | Runs an unticked proposal survives before being declined |
| `keep_snapshots` | 10 | Snapshots retained per memory directory |

## Scope

The current project by default. Project identity comes from the git repository
root, so worktrees of one repository share one memory directory and one scope.

Analysing every project at once is a different and harder problem —
consolidating across projects means deciding what is general rather than local —
and is deliberately not the default.

## Exporting

Per-plugin data is deleted when the plugin is uninstalled from its last scope,
unless the uninstall is told to keep it. Copy the `runs/` directory somewhere
durable before uninstalling if the history matters to you.

Memory itself is never at risk from an uninstall: it lives in the memory
directory, and snapshots live beside it.
