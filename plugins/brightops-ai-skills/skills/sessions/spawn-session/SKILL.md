---
name: spawn-session
description: Start a named Claude Code session in tmux, verify it, and hand it a starter brief.
disable-model-invocation: true
argument-hint: "<name> [--dir <dir>] [--prompt <text>|--prompt-file <path>] [--bypass | --trust-folder] [--resume] [--dry-run]"
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
| `--dir <dir>` | Where to launch. Defaults to the current directory. Refused when its path holds a control character or is not valid UTF-8. |
| `--prompt <text>` / `--prompt-file <path>` | The brief. `-` reads standard input. |
| `--bypass` | Launch with permissions bypassed. Default is `acceptEdits`. Warns on stderr. Refused with `--trust-folder`. |
| `--trust-folder` | Pre-authorise the workspace if it is not trusted yet. Inside a repository that is the whole repository, and a warning says so. |
| `--resume` | Pick up a session that already exists instead of creating one. |
| `--pre-launch <cmd>` | Shell command run in the pane before the CLI starts. |
| `--dry-run` | Report the plan and the warnings; launch nothing, write nothing. |
| `--porcelain` | Tab-separated key/value output on stdout instead of prose. Warnings stay on stderr. |
| `--socket <name>` | Address a named tmux server rather than the default. |

Read the exit code, not the prose:

| Code | Meaning | What to do |
|---|---|---|
| 0 | Confirmed, and briefed if a brief was given | Nothing |
| 2 | Usage error, or a refusal, including `--bypass` with `--trust-folder` and a directory whose path holds a control character or is not valid UTF-8 | Fix the invocation |
| 3 | Running, but not reachable from the web client | Usable locally; note it |
| 4 | Never became usable — never started, or held at a dialog | Apply the reported remedy, then `--resume` |
| 5 | Running, and not ready or unconfirmed — the input box is not showing, or no answer in time | Leave it alone; look at it |

## Bypass and trust

A line on stderr starting `WARNING:` states what the command is about to do
and to what. Read it before acting on the result, and repeat it to the user
rather than summarising it away. `--bypass` prints one on every launch: the
session runs with all permission prompts off, and nobody approves its
commands. Preview with `--dry-run`, which prints the same warning and launches
nothing. A dry run does not ask tmux whether the name is in use, and its
warning says so: the real run refuses a name that is already running. Use
`--bypass` only when the user asked for an unattended session.

`--bypass` and `--trust-folder` are refused together (exit 2). Trusting a
workspace and removing supervision are separate decisions, taken in separate
invocations:

1. Record trust: run once with `--trust-folder` and without `--bypass`, or have
   the user start the CLI in the directory by hand and accept the prompt.
2. Run again with `--bypass` and without `--trust-folder`.

Step 1 with `--trust-folder` launches an `acceptEdits` session that keeps its
name, so give the `--bypass` launch a different one.

`--bypass` is also refused when workspace trust cannot be checked, which
happens when `python3` is missing. Launch without `--bypass`, or have
`python3` installed.

The exact warning lines, when each is printed, and what the refusal does and
does not guarantee: `references/protocol.md`.

## How it works, and why it is worth knowing

Nothing is sent until the launcher has **looked at the pane** and found the
CLI's input box at the foot of it: a rule, the prompt line, a rule, and a
status line under them. Status-line wording anywhere else on the pane does not
count, and neither does a running process. If the box never appears, the run
ends having sent nothing.

The launcher looks again before each thing it sends: the handshake's paste,
its Enter, the brief's paste, its Enter. When the box is gone, that send and
everything after it is held back, and the report says what went and what did
not.

Delivery then happens in two phases, and the order is the safety property.

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
- **A dialog is never answered, and a send is held back when the input box
  is not showing.** That is what is guaranteed. The launcher looks and then
  sends, and the pane can change in the instant between the two, so a dialog
  that comes up in that instant can still receive one paste or one Enter. A
  session seen at a startup dialog is diagnosed and reported with the
  configuration entry that resolves it. See `references/blockers.md`.

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
silence, and at the ceiling it distinguishes three situations:

- **Blocked (exit 4).** A known startup dialog is holding the session. The
  report names it and what settles it. Resolve that, then re-run with
  `--resume` to deliver the brief into the same session. Re-running without
  `--resume` is refused: the name is taken.
- **Not ready (exit 5).** The input box is not showing and no known dialog
  is: the pane is still starting, or shows something the launcher does not
  recognise.
- **Unconfirmed (exit 5).** The handshake was sent and not answered, with
  nothing recognisable in the way. The session may simply be slow.

In all three the session is left running. The report says what was sent:
nothing, a paste without its Enter, or the handshake without the brief. Look
at the session before doing anything: `tmux attach -t "=<name>"`.

Never respond to any of them by killing and re-spawning. A session that came up
holds a real conversation, and destroying it to tidy up an unknown throws that
away.

## References

- `references/protocol.md` — how the input box is recognised, what each send
  is checked against, the handshake format, the warnings and refusals, and the
  full exit-code contract
- `references/blockers.md` — the startup dialogs, why none is ever answered
  automatically, and how to extend the dialog and status-line tables

## Requirements

`tmux`, and the Claude Code CLI on the path. `--trust-folder` and `--bypass`
additionally need `python3`; nothing else does.
