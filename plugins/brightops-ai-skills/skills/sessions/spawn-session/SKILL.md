---
name: spawn-session
description: Start a named Claude Code session in tmux, verify it, and hand it a starter brief.
disable-model-invocation: true
argument-hint: "<name> [--dir <dir>] [--prompt <text>|--prompt-file <path>] [--bypass] [--trust-folder] [--resume] [--dry-run]"
---

# Spawn a session

Create a named Claude Code session under tmux with remote control enabled, in a
chosen directory and permission posture; confirm the session is really the one
that was launched; then deliver a starter brief to it.

Use when a piece of work wants its own session — a long-running task, a second
pair of hands on a different part of a repository, a worker that reports back.

## Run it

```bash
"${CLAUDE_PLUGIN_ROOT}/skills/sessions/spawn-session/scripts/spawn-session.sh" \
  <name> --dir <directory> --prompt "<brief>"
```

Common options:

| Option | Effect |
|---|---|
| `--dir <dir>` | Where to launch. Defaults to the current directory. |
| `--prompt <text>` / `--prompt-file <path>` | The brief. `-` reads standard input. |
| `--bypass` | Launch with permissions bypassed. Default is `acceptEdits`. |
| `--trust-folder` | Pre-authorise the workspace if it is not trusted yet. |
| `--resume` | Pick up a session that already exists instead of creating one. |
| `--pre-launch <cmd>` | Shell command run in the pane before the CLI starts. |
| `--dry-run` | Report the plan; launch nothing, write nothing. |
| `--porcelain` | Tab-separated key/value output instead of prose. |
| `--socket <name>` | Address a named tmux server rather than the default. |

Read the exit code, not the prose:

| Code | Meaning | What to do |
|---|---|---|
| 0 | Confirmed, and briefed if a brief was given | Nothing |
| 2 | Usage error, or a refusal | Fix the invocation |
| 3 | Running, but not reachable from the web client | Usable locally; note it |
| 4 | Never became usable — never started, or held at a dialog | Apply the reported remedy, then `--resume` |
| 5 | Running and unconfirmed — no answer in time | Leave it alone; look at it |

## How it works, and why it is worth knowing

Delivery happens in two phases, and the order is the safety property.

First a **handshake**: the session is asked to reply with a fixed-format line
carrying a token unique to this spawn, plus the working directory and posture
it observes *for itself*. That reply is read from the session's own transcript,
not from the terminal. If the reported directory disagrees with the one that
was launched, the run aborts and the brief is never sent.

Only then is the **brief** delivered, as a single paste rather than as typed
input. Typed text submits at the first newline, which turns a multi-line brief
into one short message followed by stray fragments.

Two habits follow from this, and both matter more than they look:

- **A busy indicator is not confirmation.** A session that was already working
  looks identical to one that just accepted your input. Only the token coming
  back proves the message was received by *that* session.
- **Nothing is ever typed at a dialog.** A session held at a startup prompt is
  diagnosed and reported with the configuration entry that resolves it. See
  `references/blockers.md`.

## Writing a brief worth sending

The brief is the whole point of the spawn, and a weak one produces a session
that does confident, unwanted work. Cover, in this order:

1. **Who it is and what it owns** — the task, and the boundary around it.
2. **Where the authority stops** — what it must not do without asking. Name
   the irreversible things explicitly: pushing, merging, deleting, deploying,
   restarting anything shared.
3. **What "done" means** — the check that settles it, not a feeling.
4. **What to do when blocked** — who to tell, and to stop rather than improvise.

Write it as instructions to a capable colleague who has no context and cannot
ask a follow-up question before starting. Prefer a file over an inline string
once it runs past a few lines: `--prompt-file` keeps quoting out of the way.

A brief that says only what to build, and nothing about what not to touch, is
the most common way a spawned session causes damage.

## When it does not come up

At 30 seconds the launcher reports what it can see rather than waiting in
silence, and at the ceiling it distinguishes two different situations:

- **Blocked (exit 4).** A known startup dialog is holding the session. The
  report names it and the configuration entry that settles it. Resolve that,
  then re-run with `--resume` to deliver the brief into the same session.
- **Unconfirmed (exit 5).** No answer, nothing recognisable in the way. The
  session is left running and untouched — it may simply be slow. Look at it
  before doing anything: `tmux attach -t "=<name>"`.

Never respond to either by killing and re-spawning. A session that came up
holds a real conversation, and destroying it to tidy up an unknown throws that
away.

## References

- `references/protocol.md` — the handshake format, how the reply is located,
  and the full exit-code contract
- `references/blockers.md` — the startup dialogs, why none is ever answered
  automatically, and how to extend the table

## Requirements

`tmux`, and the Claude Code CLI on the path. `--trust-folder` additionally
needs `python3`; nothing else does.
