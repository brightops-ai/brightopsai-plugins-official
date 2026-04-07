# Ss1024sS LLM-Wiki Bootstrap Patches

The bootstrap skill runs Ss1024sS LLM-wiki v1.2.2's `bootstrap_knowledge_system.py` unmodified, then applies the four patches documented here. Each patch fixes a known issue in the generated output.

These patches were verified empirically against Ss1024sS LLM-wiki v1.2.2 on 2026-04-07. If Ss1024sS ships a new version and one of these patches no longer applies, update this file and bump the brightops-wiki plugin version.

## Patch 1 — `.gitignore` (shipping bug)

### Problem

The bootstrap script writes `.gitignore` with literal `\n` strings instead of newlines. Result: one single line reading `.obsidian/\nraw/\nraw_local/\nraw_vault/\n` which git interprets as one bogus pattern. None of the intended paths are actually ignored.

### Fix

Overwrite the file with this exact content (inbox directories added for brightops-wiki):

```gitignore
.obsidian/
raw/
raw_local/
raw_vault/

# brightops-wiki: nuggets-in-flight and per-session counters are transient.
# inbox/processed/ IS tracked (the auto-commit scopes to it).
inbox/raw/
inbox/.session_state/

# Python
__pycache__/
*.pyc
.venv/

# OS
.DS_Store
```

## Patch 2 — Chinese template files

### Problem

Ss1024sS LLM-wiki ships 8 template files in Chinese, but the README is in English. Users who don't read Chinese will have wiki pages they can't understand. The bootstrap skill replaces each with an English template.

### Affected files

All paths are relative to `$WIKI_ROOT`:

1. `docs/wiki/SCHEMA.md`
2. `docs/wiki/README.md`
3. `docs/wiki/project-overview.md`
4. `docs/wiki/current-status.md`
5. `docs/wiki/sources-and-data.md`
6. `docs/wiki/github-and-raw-strategy.md`
7. `manifests/README.md`
8. `AGENTS.md`

### Detection

For each file, read it and check if it contains any CJK characters (Unicode range U+4E00 to U+9FFF). If yes, replace with the corresponding English template below. If no, skip.

```python
cjk_count = sum(1 for c in text if 0x4E00 <= ord(c) <= 0x9FFF)
if cjk_count > 0:
    # needs replacement
```

### Replacement: `docs/wiki/SCHEMA.md`

```markdown
# Wiki Schema

## Frontmatter (every wiki page must have this)

Every `.md` file (except `index.md`, `log.md`, `README.md`, and `SCHEMA.md`)
starts with YAML frontmatter declaring its source and status:

```yaml
---
title: Page Title
source: where this came from (raw file path, URL, or "session" for chat-derived)
source_hash: a1b2c3d4e5f67890
compiled_at: 2026-04-07T12:00:00+00:00
compiled_from: [src_a1b2c3d4e5, src_f6g7h8i9j0]
created: 2026-04-07
updated: 2026-04-07
tags: [tag1, tag2]
status: current
---
```

### Required fields
- `title` — page title
- `source` — origin of the information; makes every fact traceable
- `created` — creation date (YYYY-MM-DD)

### Optional fields
- `updated` — last update date; defaults to `created` if omitted
- `tags` — flat tag list
- `status` — `current` (default) / `draft` (unverified) / `stale` (suspected outdated)
- `source_hash` — first 16 hex chars of SHA-256 of the source file at compile time.
  Required for file-backed pages; omit for `source: session` pages.
- `compiled_at` — UTC ISO-8601 timestamp of the most recent compile.
- `compiled_from` — optional list of additional source IDs.

### Why this design
- An AI reading any single page knows the provenance without consulting a manifest
- Structured fields are script-validated; prose is not
- Zero extra token cost — frontmatter is part of the page itself

## Rules

1. New raw file arrives → register in `manifests/raw_sources.csv` first
2. New conclusion → write back to a wiki page with valid frontmatter
3. New rule → add the corresponding check
4. No evidence → don't promote it from draft to current
```

### Replacement: `docs/wiki/README.md`

```markdown
# Wiki

This wiki solves three problems:

1. New AI sessions forget everything from prior sessions
2. Research is scattered — no clear "where do I look first"
3. Conclusions only live in chat history and evaporate

## Defaults

- `compile-first` — don't just answer, write the conclusion into a wiki page
- `writeback` is mandatory — every durable fact goes back into the wiki
- Wiki before RAG — for scoped research, direct page reads beat vector search
- Ideas / Intent outrank Code

## Self-check

```bash
python3 scripts/wiki_check.py
python3 scripts/raw_manifest_check.py
python3 scripts/provenance_check.py
```
```

### Replacement: `docs/wiki/project-overview.md`

```markdown
---
title: Project Overview
source: session
created: 2026-04-07
tags: [overview]
status: draft
---

# Project Overview

> One-line definition, main goal, delivery boundary. Replace this stub with real content after the first real ingest.

## Purpose

Describe what this wiki covers.

## Main goals

- _Add specific goals as they're decided._

## Out of scope

- _Define boundaries to keep the wiki focused._
```

### Replacement: `docs/wiki/current-status.md`

```markdown
---
title: Current Status
source: session
created: 2026-04-07
tags: [status]
status: current
---

# Current Status

> What's done, what's in progress, what's blocked, recent risks.
> Updated at the end of every session per the writeback rule.

## Done

- Wiki bootstrapped

## In progress

- _Add active work here._

## Blocked

- _None._

## Recent risks

- _None tracked yet._
```

### Replacement: `docs/wiki/sources-and-data.md`

```markdown
---
title: Sources and Data
source: session
created: 2026-04-07
tags: [data, raw]
status: current
---

# Sources and Data

Raw research material lives in a local directory outside this repo.
Only the manifest and compiled wiki pages are committed.

## Workflow when new files arrive

```bash
python3 scripts/ingest_raw.py             # scan, hash, dedupe, update manifest
python3 scripts/stale_report.py           # which wiki pages are now suspect
python3 scripts/delta_compile.py --write-drafts   # manual recompile stubs
```

None of these scripts call an LLM. Synthesis happens after, by hand or by
the active Claude session reading the draft stubs.

## What counts as raw

Anything that isn't code or wiki: PDFs, spreadsheets, screenshots, customer
attachments, chat exports, debug captures, CAD files, archives, audio, video.
```

### Replacement: `docs/wiki/github-and-raw-strategy.md`

```markdown
---
title: GitHub and Raw Strategy
source: session
created: 2026-04-07
tags: [strategy, git]
status: current
---

# GitHub and Raw Strategy

## The split

- **This repo** (eventually private): code + wiki + manifests + verified examples
- **Local raw vault**: PDFs, spreadsheets, images, customer originals
- **Memory repo** (optional, separate): compiled long-term memory exports — never raw bytes

## Why

Stuffing every raw file into git produces a heavy repo with useless diffs.
The things that actually deserve version control are conclusions, rules,
answer tables, and clean indexes. Not piles of binary originals.

## How it's enforced

- `.gitignore` excludes `raw/`, `raw_local/`, `raw_vault/`
- `untracked_raw_check.py` flags any binary that slipped past
- `provenance_check.py` confirms wiki pages still match the raw they were compiled from
```

### Replacement: `manifests/README.md`

```markdown
# Manifests

This directory holds the index of raw research files, not the raw files themselves.

- `raw_sources.csv` — human-editable manifest, one row per raw file
- `raw_index.json` — machine-readable lock written by `ingest_raw.py`
- `intake_report.md` — diff summary written by `ingest_raw.py`
- `stale_report.md` — written by `stale_report.py`
- `delta_compile_report.md` — written by `delta_compile.py`

Raw files themselves stay outside the repo and are gitignored.
```

### Replacement: `AGENTS.md`

```markdown
# Agent Rules

This repo defaults to `wiki-first`, not `chat-first`.

## 1. Default startup for every new session

Unless the task is pure chat, always do this first:

<!-- 0. `python3 scripts/version_check.py` — disabled: no per-session network calls -->
1. Read `docs/wiki/index.md`
2. Read `docs/wiki/current-status.md`
3. Read `docs/wiki/log.md`

Don't guess from session memory alone.

## 2. Default stance

- `compile-first`
- `writeback` is mandatory
- Wiki before heavy RAG for scoped research
- `Idea / Intent` outranks `Code`

## 3. Knowledge layers

- raw: source material (outside git)
- wiki: compiled current consensus (in git)
- code: execution layer (in git)

Changing code without writing back to the wiki = incomplete work.

## 4. Consistency rules

- If `current-status.md` conflicts with another wiki page → trust the more specific page, then fix `current-status.md`
- If `log.md` is missing prior session entries → don't guess, only append your own
- If two wiki pages contradict → flag to the user, resolve before continuing
```

## Patch 3 — `scripts/provenance_check.py` absolute-path support

### Problem

The bootstrap's generated `provenance_check.py` only recognizes source paths that start with `raw/` (relative to the project root). brightops-wiki requires **absolute paths** so the wiki can reference files outside its own tree (e.g., research files in a separate project). Without this patch, provenance resolution silently fails for any absolute path and the check reports every cross-tree page as "unresolved source."

### Location in the script

Find this block (roughly lines 90-99 in the generated file):

```python
        # Try to resolve source path
        source_path = None
        if source_line.startswith("raw/"):
            candidate = ROOT / source_line
            if candidate.exists():
                source_path = candidate
        for sid, spath in manifest_paths.items():
            if sid in source_line or source_line in str(spath):
                source_path = spath
                break
```

### Replacement

Replace with this block (adds the absolute-path branch, makes the manifest lookup a fallback only):

```python
        # Try to resolve source path
        source_path = None
        if source_line.startswith("/"):
            # Absolute path — used when the wiki lives outside the source tree
            # (e.g., global wiki at ~/Documents/wiki referencing ~/local_dev/*)
            candidate = Path(source_line)
            if candidate.exists():
                source_path = candidate
        elif source_line.startswith("raw/"):
            candidate = ROOT / source_line
            if candidate.exists():
                source_path = candidate
        if source_path is None:
            for sid, spath in manifest_paths.items():
                if sid in source_line or source_line in str(spath):
                    source_path = spath
                    break
```

The key changes:
1. New leading `if source_line.startswith("/"):` branch for absolute paths
2. `raw/` branch becomes `elif`
3. Manifest lookup only runs if neither prefix branch found the file (wrapped in `if source_path is None:`)

### Verification

After the patch, this should work without setting `PROJECT_RAW_ROOT`:

```bash
cd "$WIKI_ROOT"
python3 scripts/provenance_check.py
# Expected: "provenance_check: OK (N checked, N fresh, M session-exempt, 0 without hash)"
```

## Patch 4 — Disable `version_check.py` phone-home

### Problem

The generated `CLAUDE.md` starts with a session protocol that runs `python3 scripts/version_check.py` on every session start. That script calls the GitHub API to check for updates to Ss1024sS LLM-wiki. For a wiki billed as local-only, making a network call on every session is an unwelcome surprise.

### Fix

Edit `CLAUDE.md` at the wiki root. Find this block:

```markdown
### Session Start
0. Run `python3 scripts/version_check.py` — check for LLM-wiki updates (silent if up to date)
1. Read `docs/wiki/index.md` — get the full page list
```

Replace with:

```markdown
### Session Start
<!-- 0. `python3 scripts/version_check.py` — disabled: no network calls per session -->
1. Read `docs/wiki/index.md` — get the full page list
```

The file `scripts/version_check.py` is left alone — it's still present but nothing invokes it on startup. Users can run it manually if they want to check for Ss1024sS updates.

## Patch application order

The bootstrap skill should apply these in this order:

1. Patch 1 (`.gitignore`) — safest first step, unblocks git from accidentally tracking raw files
2. Patch 4 (`CLAUDE.md`) — before anything triggers the broken session protocol
3. Patch 2 (Chinese files) — large mechanical replacement, easiest to verify
4. Patch 3 (`provenance_check.py`) — last, because it depends on the others being correct

After all four patches, run `python3 scripts/wiki_check.py` to verify nothing is broken. All 8 required files should exist (Patch 2 rewrites them), `.gitignore` should have real newlines, `CLAUDE.md` should have the disabled version check, and `provenance_check.py` should handle absolute paths.
