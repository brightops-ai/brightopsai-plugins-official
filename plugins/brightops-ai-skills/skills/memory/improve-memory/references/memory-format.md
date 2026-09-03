# Auto memory on disk

## Location

`<config dir>/projects/<project>/memory/`, where the config directory honours
`CLAUDE_CONFIG_DIR` and defaults to `~/.claude`.

Two things make hardcoding this wrong:

- The `autoMemoryDirectory` setting relocates it, and is read from any settings
  scope — user, project, local or policy.
- `<project>` derives from the **git repository root**, not the working
  directory, so every worktree and subdirectory of one repository shares a
  single memory directory. `CLAUDE_CODE_PROJECT_DIR_NAME` overrides the name.

Always resolve with `cli.py resolve` rather than assuming.

## Layout

```
memory/
├── MEMORY.md      index, one line per memory, loaded every session
├── user_role.md   one memory
└── ...
```

`MEMORY.md` is the only file loaded at session start. Topic files are read on
demand, and **only if the index points at them**. A topic file with no index
entry is unreachable: it exists, costs nothing, and is never recalled.

## Load limits

**The first 200 lines or 25KB of `MEMORY.md`, whichever comes first.**

Everything past that is dropped at load. No error is raised, in the session or
anywhere else. An index that has grown past the limit is quietly delivering less
memory every session, and the only symptom is Claude not knowing something it
was told.

This is the single most valuable check in the audit.

## Frontmatter

Two shapes exist in the wild, and both must be read.

Documented, flat:

```yaml
---
type: user
modified: 2026-09-01T10:00:00Z
---
```

Written by Claude Code in practice, nested — this is what the overwhelming
majority of real memory files look like:

```yaml
---
name: user-role
description: what this memory holds
metadata:
  node_type: memory
  type: user
  modified: 2026-08-10T09:37:14.187Z
---
```

A parser handling only the flat form reports every real file as missing its
type. That produced 77 false findings against 80 real files on the machine this
was developed against, which is why the parser reads one level of nesting and
a top-level key wins over a nested one.

`type` is one of `user`, `feedback`, `project`, `reference`.

`modified` is stamped by Claude Code whenever it writes a file that already has
frontmatter. It is free staleness data: no inference needed.
