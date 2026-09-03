# When a finding does not belong in memory

Not everything worth remembering belongs in auto memory. Three homes exist, and
picking the wrong one either wastes context or loses the change entirely.

## The three homes

**Auto memory** — a fact that matters across the project. Loaded every session
through the index, so it costs context every time.

**A path-scoped rule** (`.claude/rules/*.md`) — guidance that only applies to a
class of files. With a `paths:` field it loads only when Claude touches a
matching file, and costs nothing otherwise.

```yaml
---
paths:
  - "src/api/**/*.ts"
---
```

**An instruction file** (`CLAUDE.md`) — a standing instruction a person wants
enforced everywhere.

## Choosing

Ask **when does this need to be true?**

- Always, and it is a fact about the work → memory
- Only when touching a particular kind of file → a path-scoped rule
- Always, and it is an instruction the user wants followed → propose a CLAUDE.md
  change, never write it

A correction that fires repeatedly on one file type is the clearest case for a
rule. Putting it in memory spends context in every session to say something that
matters in a few.

## Instruction files are proposed, never written

Both modes propose; neither writes. The blast radius is every future session in
the project, and the change was inferred from transcripts rather than asked for.

## Generated instruction files

Some `CLAUDE.md` files are generated from source fragments and say so, usually
in a header along the lines of "this file is generated, do not edit".

Editing one produces a change that disappears at the next regeneration —
silently, with no error, some days later. Worse, the change is filed in a
place its own maintenance process does not know about.

When a proposal targets a file carrying a generated-file marker:

1. Say the file is generated and quote the marker.
2. Name the source it is generated from, if the file says.
3. Propose the change **against that source**, not against the file.
4. If the source cannot be identified, say so and propose nothing — a proposal
   the reader cannot act on correctly is worse than none.

## Overlap with existing tooling

Claude Code's own checkup already proposes trims for an oversized checked-in
`CLAUDE.md`. Do not duplicate that. This suite's contribution is different:
proposals grounded in what actually happened in recent sessions, rather than in
what the file looks like.
