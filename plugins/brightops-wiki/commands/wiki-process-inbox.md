---
description: Process the wiki capture inbox — compile nuggets into pages, regenerate index, run checks, commit
---

Process the wiki capture inbox at `$BRIGHTOPS_WIKI_ROOT/inbox/raw/` (default `$HOME/Documents/wiki/inbox/raw/`).

Read `$BRIGHTOPS_WIKI_ROOT` from the environment. If unset, use `$HOME/Documents/wiki`. All paths in this command resolve relative to that root.

## Step 1 — cheap empty check (CRITICAL, do this FIRST)

Run a single Bash command to check if the inbox has any pending nuggets:

```bash
WIKI_ROOT="${BRIGHTOPS_WIKI_ROOT:-$HOME/Documents/wiki}"
ls "$WIKI_ROOT"/inbox/raw/*.md 2>/dev/null | wc -l | tr -d ' '
```

If output is `0`, immediately report `inbox empty — nothing to do` and STOP. Do not read any other files. This is the idle-tick short-circuit — it must be fast and cheap.

If output is > 0, continue.

## Step 2 — inventory

List the nuggets and read each one's full content:

```bash
ls "$WIKI_ROOT"/inbox/raw/
```

Use the Read tool on each nugget. Each has YAML frontmatter with `origin_project`, `origin_session`, `origin_cwd`, `captured_at`, `exchange_count` and a body with topic title + Decisions / Findings / Files touched / Open questions sections.

A nugget may also contain only the literal string `NONE — no durable conclusions in this session.` — these are trivial-session nuggets and get archived without compilation.

## Step 3 — route and compile each nugget

For each nugget:

### 3a. Skip trivial nuggets
If the body contains only `NONE — no durable conclusions in this session.`, skip directly to step 3e (archive). Do NOT create a wiki page.

### 3b. Determine target project subdirectory
- Primary rule: `target_project = origin_project` from the frontmatter
- **Meta-nugget exception**: if `origin_project` is `local-dev`, `tmp`, `home`, `downloads`, or another "not a real project" value, read the nugget body to determine the actual subject. If the content is about wiki/mempalace/tooling infrastructure, target `wiki-tooling`. If it's about a specific project named in the body, target that project. When unsure, target `meta`.
- Subdirectory path: `$WIKI_ROOT/docs/wiki/pages/<target_project>/`
- If the subdir doesn't exist, create it with `mkdir -p` and log the creation to `log.md` as `[REGISTRY] new project: <target_project>`.

### 3c. Locate or create the target page
- List existing files in `pages/<target_project>/`
- **Exact filename match (no semantic similarity)**: derive a slug from the nugget's `# <title>` line by lowercasing, replacing non-alphanumeric with `-`, collapsing repeated dashes, trimming leading/trailing dashes, and capping at 60 characters. Append `.md`. If a file with that exact name exists, append to it. Otherwise create a new file.

### 3d. Compile or append

**For a NEW page**, write it with full YAML frontmatter:

```yaml
---
title: <topic title from nugget>
source: session
origin_project: <target_project>
origin_sessions: [<origin_session from nugget>]
captured_at: <captured_at from nugget>
compiled_at: <current UTC ISO-8601>
created: <current date YYYY-MM-DD>
updated: <current date YYYY-MM-DD>
tags: [auto-compiled]
status: current
---
```

Then the body: copy the nugget's content verbatim, or restructure lightly.

**For an EXISTING page**, append a new section at the bottom:

```markdown

## Session: <captured_at> (origin: <origin_session>)

### Decisions
- (from nugget)

### Findings
- (from nugget)
```

Update the page's frontmatter `updated:` field to today and append the origin_session to `origin_sessions:`.

### 3e. Archive the nugget

Move the processed nugget to `inbox/processed/YYYY-MM-DD/`:

```bash
DATE=$(date +%Y-%m-%d)
mkdir -p "$WIKI_ROOT/inbox/processed/$DATE"
mv "$WIKI_ROOT/inbox/raw/<nugget-filename>" "$WIKI_ROOT/inbox/processed/$DATE/"
```

## Step 4 — append to log.md

Append ONE log entry to `$WIKI_ROOT/docs/wiki/log.md` matching the format `^## \[YYYY-MM-DD\] .+ \| .+$` (enforced by `wiki_check.py`):

```markdown

## [2026-04-07] auto-ingest | processed <N> nugget(s)

- Promoted to: pages/<project>/<topic>.md
- Origin sessions: <list>
- Archived: inbox/processed/<date>/
- Skipped trivial: <N>
```

## Step 5 — regenerate index and run checks

```bash
cd "$WIKI_ROOT"
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/regenerate_index.py"
python3 scripts/wiki_check.py
python3 scripts/provenance_check.py
```

If any check fails: report the failure, do NOT commit, leave the work in the tree for manual review, and STOP.

If all checks pass, continue.

## Step 6 — scoped git commit

**NEVER use `git add -A` or `git add .`** — that would sweep up any mid-edit work. Use a scoped add with explicit paths:

```bash
cd "$WIKI_ROOT"
git add docs/wiki/pages/ docs/wiki/index.md docs/wiki/log.md inbox/processed/
git status --short    # verify only expected files are staged
git commit -m "wiki: auto-ingest <N> nugget(s) from inbox

Pages: <list>
Origin sessions: <list>"
```

## Step 7 — final report

Report a short summary: nuggets processed, pages created/appended/skipped, routing decisions for any meta-nuggets, the commit hash.

## Error handling

If any step fails unexpectedly, leave all work in place (do NOT roll back), report what happened, and stop. The next loop tick will pick up where you left off.

If a specific nugget is malformed and can't be parsed, move it to `inbox/processed/<date>/malformed/`, log the issue in `log.md`, and continue with other nuggets.
