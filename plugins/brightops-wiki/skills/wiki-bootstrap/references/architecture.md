# brightops-wiki Architecture

Detailed design notes. SKILL.md has the workflow; this file has the *why*.

## Lineage

brightops-wiki is a hybrid of three prior systems:

1. **Karpathy's LLM Wiki gist** (https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) — the philosophical foundation. Compile-first, writeback mandatory, raw → wiki → code three-layer model. Index.md as content catalog. Log.md as append-only activity log. "Wiki before RAG" at moderate scale. Karpathy's gist assumes deliberate human-driven curation.

2. **Ss1024sS/LLM-wiki** (https://github.com/Ss1024sS/LLM-wiki) — productized Karpathy pattern. Single-file Python bootstrap script generates 11 validators (`wiki_check.py`, `provenance_check.py`, `ingest_raw.py`, etc.) that enforce frontmatter, hash provenance, broken-link detection, and stale-source detection. brightops-wiki ships the validators by running this bootstrap unmodified, then applying targeted patches.

3. **MemPalace** (https://github.com/milla-jovovich/mempalace) — local AI memory system whose Stop hook (`hooks/mempal_save_hook.sh`) is the canonical pattern brightops-wiki copies. The hook does ZERO LLM work itself. It uses simple counters to decide when to fire. When it fires, it returns `{"decision":"block","reason":"..."}` and the **already-active Claude session** does the writeback as its next response. This is the design that makes auto-capture viable at near-zero per-session cost.

## The departure from Karpathy

Karpathy assumes deliberate curation. brightops-wiki adds **automatic capture** because the target user (someone with 25+ active projects) will not sustain manual writeback discipline across context switches.

The trade is explicit: **synthesis precision down, capture recall up**. The compile loop (an LLM) routes nuggets and writes pages with less judgment than a human editor would, but it captures ~95% of insights versus the ~10% a human reliably writes back. The weekly review pass catches drift.

## Three-layer model

```
Any Claude Code session in any project
        │
        │ Stop hook fires every CAPTURE_INTERVAL user messages
        ↓
$WIKI_ROOT/inbox/raw/<session_id>-<nanos>-<rand>.md   ← nuggets
        │
        │ /loop 15m /wiki-process-inbox in dedicated terminal
        ↓
$WIKI_ROOT/docs/wiki/pages/<project>/<topic>.md       ← compiled synthesis
```

The hook is the capture layer. The slash command is the compile layer. The wiki itself is the synthesis layer. None of the three layers can be replaced without breaking the others.

## Recursion guards

The hook has three recursion guards. All three are necessary:

1. **`stop_hook_active=true`** — set by Claude Code on the second Stop after a block. Without this, every block-and-write would trigger another block infinitely. Claude Code's protocol guarantees that after the AI writes the nugget and tries to stop again, this flag is set.

2. **`CLAUDE_PROJECT_DIR == WIKI_ROOT`** — the dedicated `/loop` session runs from inside the wiki itself. If the hook fires for that session and tells the AI to capture itself, the AI captures the capture, and so on. The pwd guard exits silently before any logging happens.

3. **`_just_captured` flag** — set by the manual `/wiki-capture` slash command (planned for v2). The flag tells the hook to reset its counter without firing, preventing the user-initiated capture from immediately triggering an automatic capture on the same exchange.

## Why no bash heuristic filter in the hook

An earlier design had the hook grep the transcript for signal phrases (`"decided"`, `"the root cause"`, etc.) before firing. Two reasons it was rejected:

- **False positives**: any code review or doc reading session contains these phrases without producing durable conclusions. The bash regex approach would fire on most sessions.
- **Better classifier already exists**: the active Claude session has the conversation context. When the hook fires unconditionally and tells Claude "write a nugget if there's anything durable, otherwise write 'NONE'", Claude does the right thing using full context. The compile loop later discards `NONE` nuggets.

This matches MemPalace's stance: "AI does the classification — it knows what's worth saving because it has context."

## Why ${CLAUDE_PLUGIN_ROOT} for paths

Plugin install paths vary by user, OS, and install method. Hardcoding paths like `/Users/danielbright/...` breaks portability. `${CLAUDE_PLUGIN_ROOT}` is set by the Claude Code harness at runtime to the directory containing the plugin's `.claude-plugin/plugin.json`. The hook script and slash command both use it for any references to bundled scripts.

## Why $BRIGHTOPS_WIKI_ROOT for the wiki location

Plugin code lives in `${CLAUDE_PLUGIN_ROOT}` (managed by Claude Code). User data lives somewhere else (managed by the user). The wiki is user data. `$BRIGHTOPS_WIKI_ROOT` is the user-controlled override; the default `$HOME/Documents/wiki` matches the most common reasonable location on macOS.

The hook script and slash command both read this env var. If the user changes it, both must agree — which is automatic because they read from the same source.

## Token cost

Without mitigations, running `/loop 15m /wiki-process-inbox` in a dedicated session with growing context costs $5-8/day idle, $150-450/month worst case on Sonnet.

With the empty-inbox bash short-circuit (mandatory in the slash command), idle ticks cost ~500 tokens instead of ~40K. With backoff after consecutive empty ticks, the steady state is ~$30-60/month.

The bash short-circuit is the single biggest cost lever. It must run before any file reads.

## Why NOT cron or launchd

The user could schedule `claude -p "/wiki-process-inbox"` via cron or launchd. The brightops-wiki design uses `/loop` in a dedicated terminal instead because:

- Visibility — the user sees what the loop is doing in real time
- No background daemon to manage
- Survives `/clear` if the loop does (plugin assumption — verify per session)
- Same-session token efficiency via auto-clear (when supported)

The trade is that the loop dies on reboot or terminal close. Acceptable for a user who doesn't want to manage cron.

## Why a single global wiki, not per-project wikis

Per-project wikis fragment knowledge across 25+ projects. Cross-project insights ("this auth pattern from project A applies to project B") are invisible unless both wikis are searched. A global wiki with `pages/<project>/` subdirectories preserves project boundaries while keeping all synthesis searchable from one place.

The frontmatter `origin_project` field makes routing automatic at compile time. The directory structure makes browsing intuitive. The auto-regenerated `index.md` makes navigation possible without semantic search.

## Why git scoped add, never `git add -A`

The `/wiki-process-inbox` slash command commits its work after every successful compile. If the user is hand-editing pages between loop ticks (e.g., during a weekly review), `git add -A` would sweep up those mid-edit changes and commit them in an unrelated automated commit. The scoped add (`git add docs/wiki/pages/ docs/wiki/index.md docs/wiki/log.md inbox/processed/`) limits the auto-commit to paths the loop owns.

## Known risks

**iCloud + .git**: if `$BRIGHTOPS_WIKI_ROOT` is inside `~/Documents/`, iCloud may "optimize" `.git/pack` files away and silently corrupt the repo. Mitigations: keep canonical wiki at `~/.local/share/wiki/` and rsync to iCloud, or rename `.git` with `.nosync` extension, or use `git --git-dir` separation. The skill should warn if it detects iCloud-synced location.

**Subagent stops fire SubagentStop, not Stop**: brightops-wiki's hook only fires on Stop. Do NOT register the same hook on SubagentStop — subagent intermediate thinking would pollute the inbox.

**Concurrent sessions writing to the inbox**: each session has its own counter file (`<session_id>_last_capture`), but multiple sessions write nuggets to the same `inbox/raw/`. The filename includes nanos + 4 random hex chars to prevent collisions.

## Future work

- **MemPalace integration (v3)**: add `mempalace mine $WIKI_ROOT/` as the last step of `/wiki-process-inbox`, register a `mempalace:drawer_xxx` URI scheme in `provenance_check.py`, mirror `mempal_precompact_hook.sh` to capture before context compaction.
- **`/wiki-capture` manual override**: a slash command that forces a capture immediately, bypassing the counter. Uses the `_just_captured` flag to prevent re-fire.
- **iCloud safety check**: detect at bootstrap time and warn or block.
- **Weekly review skill**: a sibling skill that lists pages created in the last 7 days, runs lint, flags duplicates, lets the user prune.
