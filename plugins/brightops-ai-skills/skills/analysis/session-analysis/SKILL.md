---
name: session-analysis
description: Analyse recent session transcripts for a chosen purpose, such as memory consolidation.
disable-model-invocation: true
argument-hint: "[dream|time] [--window-days N] [--all-projects]"
context: fork
allowed-tools:
  - Bash
  - Read
  - Write
  - Glob
  - Grep
---

# Session analysis

Mine the raw record of what happened in recent sessions, rather than what the
memory system already chose to save.

Takes an analysis mode. `dream` looks for what should have been remembered and
was not. The mode is an argument because the same extraction serves other
questions of the same data — `time` is a worked example in the references.

Runs forked, so the digest never enters the calling session's context.

## References

- `references/transcript-signals.md` — record shapes, what each signal means, and what it does not mean
- `references/analysis-modes.md` — what `dream` mode produces, and how to add a mode

## The division of labour

The bundled script finds **structure**. It never decides meaning.

Measured against real transcripts, matching correction-like phrasing caught
about six percent of human turns, and most of what it caught were not
corrections — "you can stop it now", "we don't need the inbox anymore". Phrasing
is not the signal. Structure is: a run that was interrupted, a command that
failed the same way repeatedly, a permission that was refused.

Deciding an episode *was* a correction, and that three differently-worded
episodes were the *same* correction, is your job.

## Workflow

### 1. Extract

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/lib/dream/cli.py" extract \
  --window-days 7 --out "<run-dir>/digest.json"
```

Defaults to the current project and the last seven days. Pass `--since` with the
previous run's timestamp when one exists, so the window self-heals after a
missed run.

Check `retention_gap` in the output. A non-empty value means transcripts inside
the requested window were already deleted by retention — say so in the analysis
rather than reporting on less data as though it were all of it.

Check `truncated`. When true, the digest hit its token budget and the oldest
episodes were dropped.

### 2. Read the digest

Each episode carries its kind, what ran before it, and what it touched:

| Kind | What it evidences |
|---|---|
| `interrupted` | The user stopped the run. Strong evidence the approach was wrong. |
| `permission-denied` | A tool call was refused. Evidence of an unstated boundary. |
| `tool-failure` | A command failed; `occurrences` counts identical failures. |
| `quick-turn-after-edit` | A terse human turn right after an edit. Often a correction, often not. |

None of these is a correction by itself. Read the surrounding fields.

### 3. Cluster by target, never by phrasing

Group episodes by **what was being corrected** — the file, the tool, the
convention, the recurring decision. Two episodes belong together when they
concern the same thing, even when they share no words.

A cluster of three or more across different sessions is the signal worth
carrying: it is something the user has now said repeatedly and memory did not
capture.

### 4. Write the analysis

Write `analysis.md` into the run directory. For each cluster state what happened,
how many times, in which sessions, and what a memory or rule would need to say to
stop it recurring. Order by how often it recurred.

Separate confident findings from speculative ones. A cluster of one is an
observation, not a pattern; say which you are looking at.

Return the analysis file path to the caller.

## Guardrails

- Secrets are redacted during extraction; never quote raw transcript text that bypassed the digest
- Never claim a pattern the digest does not support
- Never propose a memory the user did not say something to justify
- Report the window actually analysed, not the window requested
