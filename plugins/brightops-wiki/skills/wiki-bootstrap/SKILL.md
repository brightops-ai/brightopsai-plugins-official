---
name: wiki-bootstrap
description: This skill should be used when the user asks to "set up the wiki", "bootstrap brightops-wiki", "install the auto-capture wiki", "configure the wiki capture", "where do my session captures go", or runs the brightops-wiki plugin for the first time. Also use when the user reports that nuggets are accumulating in the wiki inbox but no wiki exists at the configured location, or when they ask to migrate from a per-project wiki to the global brightops-wiki layout.
version: 0.1.0
---

# Wiki Bootstrap

The brightops-wiki plugin auto-captures session conclusions to a global wiki via a Stop hook. This skill handles the first-run setup: detect or create the wiki directory, run the underlying Ss1024sS LLM-wiki bootstrap, apply the brightops-wiki patches, and verify the capture → compile loop works end-to-end.

The plugin's hook and slash command are auto-registered when the plugin is enabled — this skill does NOT modify `~/.claude/settings.json`. The skill's job is to scaffold the user's wiki directory so that the hook has somewhere to write nuggets and the slash command has something to compile.

## Triggers

Activate when the user wants to set up the wiki, asks where captures go, or runs the plugin for the first time and there is no wiki directory yet.

## Prerequisites

- Python 3.9+ on PATH
- `git` on PATH
- `~/.claude/settings.json` exists (Claude Code installed)
- The brightops-wiki plugin is enabled in Claude Code (check `/plugin list`)

## Default behavior

The wiki lives at `$BRIGHTOPS_WIKI_ROOT`, defaulting to `$HOME/Documents/wiki` if unset. The hook script and slash command both read from this same env var, so changing it after install requires updating the user's shell profile and restarting Claude Code.

## Workflow

Follow these steps in order. Skip a step only if its preconditions are clearly already met.

### Step 1 — detect existing install

Resolve the wiki location:

```bash
WIKI_ROOT="${BRIGHTOPS_WIKI_ROOT:-$HOME/Documents/wiki}"
```

Check whether a brightops-wiki install is already present:

```bash
test -d "$WIKI_ROOT/docs/wiki" && \
test -f "$WIKI_ROOT/scripts/wiki_check.py" && \
echo "exists" || echo "missing"
```

If `exists`: jump to Step 5 (verify) — do NOT re-bootstrap. Report the current wiki location and run the validation checks.

If `missing`: ask the user to confirm the location before scaffolding. Default is `$HOME/Documents/wiki`. If they want a different location, instruct them to set `BRIGHTOPS_WIKI_ROOT` in their shell profile (e.g., `~/.zshrc`) and restart Claude Code, then re-run this skill.

### Step 2 — clone Ss1024sS LLM-wiki and run its bootstrap

The brightops-wiki plugin builds on Ss1024sS/LLM-wiki for the underlying validation scripts. Clone it to a temp location and run its bootstrap script against the user's chosen wiki root.

```bash
TMPDIR=$(mktemp -d)
git clone --depth=1 https://github.com/Ss1024sS/LLM-wiki.git "$TMPDIR/llm-wiki"
mkdir -p "$WIKI_ROOT"
python3 "$TMPDIR/llm-wiki/scripts/bootstrap_knowledge_system.py" "$WIKI_ROOT" "BrightOps Wiki"
```

This generates ~30 files: `docs/wiki/` with required pages, `scripts/` with validators, `manifests/` with the raw sources CSV, `.claude-plugin/` placeholders, and a CI workflow.

### Step 3 — patch the Ss1024sS bootstrap output

The Ss1024sS bootstrap has three known issues that must be patched. Read `references/ss1024ss-patches.md` for the full diff and rationale. The patches are:

1. **`.gitignore`** — overwrite the buggy literal-`\n` file with proper newlines, plus add `inbox/raw/` and `inbox/.session_state/` ignores.
2. **Chinese template files** — replace 8 generated files (`SCHEMA.md`, `README.md`, `project-overview.md`, `current-status.md`, `sources-and-data.md`, `github-and-raw-strategy.md`, `manifests/README.md`, `AGENTS.md`) with English equivalents.
3. **`scripts/provenance_check.py`** — apply a ~5-line patch to recognize absolute paths (the original only handles `raw/` prefix). Required for cross-tree wikis.
4. **`CLAUDE.md`** — comment out the `version_check.py` invocation in the session protocol so the wiki dir doesn't phone home to GitHub on every session start.

For each of the 8 Chinese files: read the file, detect any non-ASCII content, replace with the English template from `references/ss1024ss-patches.md`. The patches reference is structured so that each file has its English replacement ready to copy.

### Step 4 — initialize the multi-project pages layout

The Ss1024sS bootstrap produces a flat `docs/wiki/` structure. brightops-wiki uses `docs/wiki/pages/<project>/` subdirectories. Create the empty `pages/` directory and initialize the inbox structure:

```bash
mkdir -p "$WIKI_ROOT/docs/wiki/pages"
mkdir -p "$WIKI_ROOT/inbox/raw"
mkdir -p "$WIKI_ROOT/inbox/processed"
mkdir -p "$WIKI_ROOT/inbox/.session_state"
touch "$WIKI_ROOT/inbox/processed/.gitkeep"
```

Then run the brightops-wiki `regenerate_index.py` once to produce a deterministic `index.md` that wiki_check will accept:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/regenerate_index.py" --wiki-root "$WIKI_ROOT"
```

### Step 5 — verify

Run all four validation checks. They must all pass before considering the install complete:

```bash
cd "$WIKI_ROOT"
python3 scripts/wiki_check.py
python3 scripts/raw_manifest_check.py
python3 scripts/provenance_check.py
python3 scripts/stale_report.py
```

Expected output for a fresh install:
- `wiki_check: OK` — 8 required files present
- `raw_manifest_check: OK` — empty manifest is valid
- `provenance_check: OK` — 0 checked, 0 fresh, N session-exempt
- `stale_report: OK` — 0 fresh, N session-exempt

If any check fails, read the error and either fix the underlying issue or report it to the user. Do NOT proceed to Step 6 until checks are green.

### Step 6 — initialize git and commit

```bash
cd "$WIKI_ROOT"
git init -q
git add .
git -c user.name="$(git config user.name || echo BrightOps)" \
    -c user.email="$(git config user.email || echo wiki@brightops.local)" \
    commit -q -m "init: brightops-wiki bootstrap"
```

### Step 7 — confirm the hook is active

The plugin's hook auto-registers when the plugin is enabled, but **Claude Code must be restarted after installing the plugin** for the hook to take effect. Tell the user:

> The wiki is bootstrapped. The Stop hook fires every 12 user messages from any Claude Code session and writes a nugget to `$WIKI_ROOT/inbox/raw/`. To process the inbox automatically, open a dedicated terminal in `$WIKI_ROOT`, run `claude`, then run `/loop 15m /wiki-process-inbox`. Leave that terminal open. Restart any other Claude Code sessions for the hook to start firing.

Do NOT modify `~/.claude/settings.json`. The plugin handles registration.

### Step 8 — detect MemPalace and recommend

brightops-wiki captures synthesis (compiled conclusions). MemPalace captures verbatim breadth (every word of every session). They are complementary — the wiki answers "what did we decide and why", MemPalace answers "what did we actually say". The two can be integrated in v0.2.0+ via a `mempalace:drawer_xxx` source URI scheme in `provenance_check.py`.

Detect whether MemPalace is installed:

```bash
if command -v mempalace >/dev/null 2>&1 || \
   (command -v pipx >/dev/null 2>&1 && pipx list 2>/dev/null | grep -qi mempalace); then
    echo "mempalace: installed"
else
    echo "mempalace: not installed"
fi
```

**If installed**, confirm to the user:

> MemPalace detected. It can be integrated with brightops-wiki in a future release (wiki pages become searchable drawers; cross-reference between synthesis and raw). For now, both systems operate independently.

**If not installed**, recommend but do NOT auto-install:

> MemPalace is not installed. It's a separate local-first memory system (https://github.com/milla-jovovich/mempalace) that complements brightops-wiki by capturing verbatim conversation content across your whole workspace. Installing it is optional — brightops-wiki works fine on its own.
>
> If you want it: `pipx install mempalace`, then `mempalace init ~/local_dev` and `mempalace mine ~/local_dev` for the initial scan. The first mine takes ~5-10 minutes (downloads a local embedding model, indexes source files). Everything stays local — no cloud calls, no API keys.
>
> Do NOT install MemPalace as part of this bootstrap. The wiki is ready to use either way.

Record the detection result but do not treat "not installed" as a failure. Continue to the final report.

### Step 9 — report

Print a summary:

- Wiki location
- How many wiki pages were created (should be 8 required, 0 topic)
- Whether the inbox is empty (should be yes)
- The git commit hash
- MemPalace status (installed / not installed)
- Next steps for the user (run `/loop` in a dedicated terminal)

## Failure modes

**The Ss1024sS clone fails (network issue)**: report the failure and stop. Suggest the user check their connection and retry.

**Python bootstrap script errors**: read the traceback, identify the cause. Common issues are wrong Python version (needs 3.9+) or permission issues. Fix or report.

**One of the check scripts fails after patching**: this is a real bug — the patch was incomplete. Re-read `references/ss1024ss-patches.md`, verify each patch was applied correctly, run checks again. If still failing, leave the wiki in place and report the exact error to the user.

**`BRIGHTOPS_WIKI_ROOT` set to a directory inside another git repo**: the bootstrap will create a nested git repo, which is usually wrong. Warn the user and ask them to choose a path that isn't already inside another repo.

## Related files

- `references/architecture.md` — full design notes including the Karpathy / MemPalace / Ss1024sS lineage and the recursion guard reasoning
- `references/ss1024ss-patches.md` — exact diffs and English replacement files for the bootstrap output

## What this skill does NOT do

- Does NOT modify `~/.claude/settings.json` (the plugin's `hooks/hooks.json` handles hook registration automatically when the plugin is enabled)
- Does NOT install the slash command (`commands/wiki-process-inbox.md` is also auto-discovered by the plugin loader)
- Does NOT install `regenerate_index.py` into the user's wiki dir (it lives in the plugin and is called via `${CLAUDE_PLUGIN_ROOT}/scripts/regenerate_index.py`)
- Does NOT migrate existing per-project wikis from other locations (that's a separate operation — ask the user if they want guidance)
- Does NOT install or configure MemPalace (separate concern)
