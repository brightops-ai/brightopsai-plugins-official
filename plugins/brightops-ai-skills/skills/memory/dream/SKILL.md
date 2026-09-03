---
name: dream
description: >
  This skill should be used when the user asks to "run dream", "consolidate my
  memory", "clean up my Claude memory", "improve memory from my sessions",
  "apply the memory fixes", "apply signed-off memory changes", or asks for a
  scheduled memory consolidation pass over recent sessions. Also trigger when a
  scheduled routine fires with a dream full-analysis or apply-fixes request.
argument-hint: "[full-analysis|apply-fixes]"
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - Glob
  - Grep
---

# Dream

Consolidate what recent sessions revealed into the memory that loads next time.

Two modes, meant to run a day apart:

| Mode | Does |
|---|---|
| `full-analysis` (default) | Analyse sessions, repair what is certain, propose the rest |
| `apply-fixes` | Apply only the proposals that have been ticked |

## References

- `references/scheduling.md` — running the two modes as routines, and the invocation requirement
- `references/configuration.md` — settings, defaults, and where run state lives
- `references/rules-and-instructions.md` — when a finding belongs in a path-scoped rule or an instruction file

## Why this skill is model-invocable

Every other user-driven workflow in this plugin sets
`disable-model-invocation: true` and carries a one-line description. This one
must not, and the reason is not stylistic.

That field also prevents a **scheduled task** from firing the skill. Running
unattended on a schedule is this skill's entire purpose, so setting the flag
would leave a routine that fires and does nothing, with no error to notice.

**Do not "correct" this to match the other skills.** The deviation is recorded
in the repository conventions for the same reason.

## Workflow: full-analysis

### 1. Prepare the run

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/lib/dream/cli.py" resolve
```

Stop if `memory_exists` is false and say the location was not found. An empty
result from the wrong directory is indistinguishable from a clean one.

Create a run directory under the per-plugin data directory, named by timestamp.
Never write run state inside the plugin directory.

### 2. Analyse recent sessions

Follow the `session-analysis` procedure in `dream` mode, producing
`analysis.md` in the run directory. Pass `--since` from the previous run's
timestamp when one exists; otherwise the default window.

### 3. Improve memory

Follow the `improve-memory` procedure, giving it the analysis alongside the
audit. It snapshots before writing, applies only what is mechanically certain,
and returns everything else as proposals.

### 4. Carry forward the previous overview

When a previous overview exists, read its pending items so proposals keep their
identity and sighting count across runs. Items already ticked belong to the
apply-fixes run, not this one. Items unticked past the expiry threshold move to
declined and are dropped.

### 5. Write the overview and deliver

Write `memory-improvement-overview.md`, then follow the `send-result` procedure
with a short summary: what was applied, how many items await a decision, and
where the full document is.

### 6. Prune

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/lib/dream/cli.py" prune --keep 10
```

## Workflow: apply-fixes

### 1. Find the pending overview

Locate the most recent `memory-improvement-overview.md` in the run directories.
If there is none, say so plainly and stop — this is not a failure.

### 2. Read what was signed off

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/lib/dream/cli.py" approved "<overview path>"
```

Only ticked items. An unticked item is left alone and stays pending.

### 3. Apply

Snapshot first:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/lib/dream/cli.py" snapshot
```

Then make each approved change, one at a time, exactly as its item describes. Do
not extend an item beyond what it says, and do not apply an item whose meaning
has become unclear — report it instead.

### 4. Record and deliver

Rewrite the overview with applied items moved into the applied section, then
deliver a summary naming each change and the snapshot path.

## Guardrails

- Never apply an item that was not ticked
- Never touch an instruction file automatically; those are proposals in both modes
- A failure in any stage names the stage and leaves memory unchanged
- Undo is `cli.py restore`, which puts the newest snapshot's files back
