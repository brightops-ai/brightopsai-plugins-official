---
name: improve-memory
description: Audit and consolidate this project's auto memory, proposing what needs a decision.
disable-model-invocation: true
argument-hint: "[--report-only] [--memory-dir <path>]"
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - Glob
  - Grep
---

# Improve memory

Find the defects in a project's auto memory, repair the ones that are
mechanically certain, and propose the rest for a person to decide on.

Run `--report-only` to change nothing at all.

## References

- `references/memory-format.md` — the on-disk layout, frontmatter shape and load limits
- `references/change-classification.md` — what may be applied without asking, and why the line sits there

## Why this exists

An auto memory directory degrades silently. An index that outgrows its load
limit stops delivering the memories past the limit, with no error anywhere. A
topic file that loses its index entry is never read again. Nothing reports any
of this; the session simply stops knowing things it used to know.

## Workflow

### 1. Locate the memory directory

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/lib/dream/cli.py" resolve
```

Read `memory_source` in the output. It says whether the location came from an
`autoMemoryDirectory` setting or the default layout.

If `memory_exists` is false, stop and say so. **Do not report a clean result.**
Nothing was checked, which is not the same as nothing being wrong.

### 2. Audit

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/lib/dream/cli.py" audit
```

Each finding names a check, the file it concerns and why it matters. Read the
findings; do not re-derive them.

### 3. Judge what the script cannot

The audit is deliberately mechanical. Read the memory files and the CLAUDE.md
files that load for this project, then look for what needs an opinion:

- **Duplicates** — two memories asserting the same thing in different words.
  Propose a merge naming both files.
- **Contradictions** — two memories that cannot both be true. Propose a winner
  and say what decided it: recency, specificity, or an explicit correction.
- **Already-covered facts** — a memory restating something CLAUDE.md says.
  Auto memory is documented to skip these, so propose removal.
- **Wrong home** — a memory that only applies to one kind of file. Propose it
  as a path-scoped rule instead; see the `dream` skill's rules guidance.

State the evidence for every proposal. A proposal a reader cannot check is a
proposal they cannot approve.

### 4. Apply the safe repairs

Skip when `--report-only`.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/lib/dream/cli.py" fix
```

This snapshots the directory first and reports the snapshot path. It applies
only the mechanically certain repairs and returns anything else as a proposal.

Never hand-edit memory files to make a change the classification reference puts
in the sign-off tier, even when the right answer looks obvious. The failure mode
is silent: a wrongly merged memory misinforms every later session without ever
producing an error.

### 5. Write the overview

Write `memory-improvement-overview.md` into the run directory with two
sections: what was applied, and what is waiting. Each waiting item is an
unticked checkbox carrying enough context to decide on without rereading
anything.

When a previous overview exists, carry its untouched items forward with their
sighting count so items nobody ticks eventually expire as declined.

### 6. Report

State the memory directory, where the location came from, what was applied,
what is waiting, and the snapshot path. A run that changed nothing still says
so.

## Guardrails

- Report-only mode writes nothing, including no snapshot
- Never write outside the resolved memory directory and the run directory
- Never write user content inside the plugin directory
- If the audit and your reading disagree, say so rather than silently picking one
