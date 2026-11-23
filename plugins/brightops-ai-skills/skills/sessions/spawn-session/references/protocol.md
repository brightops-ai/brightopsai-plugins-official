# The handshake protocol

How a spawned session is confirmed to be the session that was launched, and
what each outcome means.

## Why confirm at all

Two failures motivate the whole design, and neither is caught by checking that
a session exists.

**A message can reach the wrong session.** tmux resolves a session target by
prefix when the target is a bare name, so a brief aimed at `worker` lands in
`worker-2` if that exists. Every target here uses the exact-match `=name` form,
which disables prefix matching — but exact targeting only guarantees *where the
bytes were sent*, not *what received them*. Confirmation closes that gap.

**A busy terminal proves nothing.** A session that was already working shows
the same activity indicator before and after input arrives. Reading the pane
cannot distinguish "started your work", "queued your work behind something
else", and "ignored it entirely". Only evidence produced by that session, in
response to that specific request, settles it.

## Looking before sending

The handshake and the brief are input: each is pasted into the pane and then
submitted with Enter. Before any of that is sent the launcher looks at the
pane and decides what it shows.

Input goes only to the CLI's input box, and the evidence for the box is where
things are on the pane:

```
────────────────────────       a rule
❯ whatever is typed            the input, one line or several
────────────────────────       a rule, the last one on the pane
  a status line of the user's  any number of lines
  ⏵⏵ accept edits on …         the mode line: a row of scripts/ready-prompts.tsv
```

Three rules, applied to one capture:

1. **The box** is the last rule on the pane, the nearest rule above it, and
   the prompt glyph `❯` on the line right under that one. A dialog the CLI
   draws opens with a rule of its own, so a box left on screen above a dialog
   is not found.
2. **A dialog** is a known dialog's wording (`scripts/startup-blockers.tsv`)
   anywhere from the box's top rule down to the foot of the pane, whatever
   its line looks like: inside the box, under it, focused, numbered or in a
   sentence. Above the box the same wording is earlier output and counts for
   nothing. With no box on the pane it counts anywhere.
3. **Ready** is a box, no dialog, and a mode line somewhere under the box.

| The pane shows | State | What is sent |
|---|---|---|
| A box, no dialog, a mode line under it | ready | The next send |
| A known dialog, by rule 2 | blocked | Nothing |
| Anything else: empty, still starting, not recognised | waiting | Nothing |

What does not count:

- **Mode-line wording somewhere else.** A dialog can offer `accept edits on`
  as an option, and the shell echoes a `--pre-launch` command that contains
  it. Neither is under a box.
- **A running CLI process.** A session held at a dialog has one too.
- **A look that failed.** If tmux cannot capture the pane, what it shows is
  unknown, whatever was printed before the failure.

What does not get in the way:

- **A status line of the user's own.** It is drawn between the box and the
  mode line. It may be any number of lines and begin with anything, the
  prompt glyph included.
- **A narrow pane.** It cuts the mode line short: `⏵⏵ accept edits` at 20
  columns, `⏵⏵` at 12. A cut line counts when what is left of it is the start
  of a row and still holds the mode symbol.

A pane too short to show any line under the box is not ready, and is reported
as too short. A session the launcher creates is given 120 columns by 40 rows,
so that case arises only with `--resume` into a pane something else sized. A
client that attaches later resizes the window to itself as usual.

### One look before each send

The launcher sends four separate things: the handshake's paste, its Enter,
the brief's paste, and its Enter. Each has its own look immediately before
it. `--resume` sends the same four and looks the same way.

**The look before an Enter** has one more way to know the box, because the
launcher has just changed what the pane shows. The CLI folds a paste of five
lines or more, or one very long line, into a marker such as
`[Pasted text #1 +10 lines]`, and for about eight seconds draws
`paste again to expand` where the mode line was. So before an Enter the pane
is also ready when the box shows the paste: that marker, which is the table's
one row for inside the box, or the start of the pasted text itself, which is
how the CLI shows a short paste. Rules 1 and 2 still apply, with one
allowance: wording that is in the pasted text is the paste, not a dialog, so
a brief that mentions a dialog is still submitted. If the box shows neither,
the launcher keeps looking for twelve seconds, long enough for the hint to
clear, before it gives up.

The look before a paste has none of this. A box holding text with no mode
line under it is not ready for a paste.

When a look does not find the box, that send and everything after it is held
back and the run ends. A look that finds nothing recognisable is repeated for
a second first, because a capture can land while the CLI is redrawing; a
known dialog ends it at once.

A look counts as ready only while the CLI process is still in the session. A
CLI that has exited leaves its last frame on the pane, box and mode line
included, with the shell's prompt under it, and a paste sent then would be
typed into the shell. When the process is gone, nothing is sent and the run
ends as never started (exit 4), with the pairs saying what had been delivered
before it went.

Every tmux command in a delivery is checked. If one fails, the paste's Enter
and everything after it are not sent, and the run ends with tmux's own status
after a report of what had been delivered.

### What this guarantees, and what it does not

Nothing is sent on a look that did not find the input box, and no dialog is
ever answered. Three things are outside that:

- **The instant between a look and its send.** They are two tmux calls, and
  the pane can change between them. A dialog that comes up in that instant
  receives the one paste or the one Enter that was already on its way. The
  next look sees it, and nothing further is sent.
- **A screen that draws the same thing.** A program, a pager or an editor
  showing a copy of the input box with a mode line under it is the box as far
  as looking can tell, and input is sent to it. So is a dialog no table row
  describes, if it is drawn with a box and a mode line still on the pane.
- **A CLI that is suspended, not gone.** The process check finds a stopped
  CLI as readily as a running one. If the CLI is suspended and its last frame
  is still on the pane above a live shell, input goes to that shell.
- **A directory that changes after it is checked.** If the directory is
  removed, or replaced by a symbolic link, between the launcher's checks and
  tmux creating the session, the session starts wherever tmux then puts it.
  The launcher does not look again after the launch.

## The exchange

The launcher generates a token unique to the spawn and sends a short request
asking the session to reply with a single line containing, in order: the word
`SPAWN-ACK`, the token, `cwd=` followed by its own working directory, and
`posture=` followed by `acceptEdits`, `bypass`, or `unknown`.

The request lists those parts rather than showing them assembled. Both the
request and the reply land in the same transcript, so a request containing a
literal well-formed acknowledgement would match on the way out and confirm a
session that had not yet said anything.

The reply is read from the session's **transcript**, located by searching for
the file named after its conversation identifier — which the session publishes
in its own state file. The transcript is used rather than the terminal because
a terminal is a rendering: repainted, wrapped, and scrolled away. The
transcript is the record.

The token is what makes a stale reply harmless: an acknowledgement left in a
transcript by an earlier spawn carries a different token and is ignored.

## Judging the reply

The session reports its directory and posture from its **own** observation. An
echo of what it was told would prove nothing; the value is in the disagreement.

| Reply | Verdict | Result |
|---|---|---|
| Directory matches, posture matches | confirmed | Proceed |
| Directory differs | mismatch | **Abort.** Nothing further is sent |
| Posture differs | mismatch | **Abort.** Nothing further is sent |
| Posture `unknown` | confirmed, posture unverified | Proceed, and say so |

A directory mismatch is the wrong-session detector, and it is disqualifying: a
session answering from somewhere else is not the one that was launched.

An `unknown` posture is a weaker answer, not a contradictory one. Treating it
as failure would reject every session that cannot introspect its own launch
flags, and buy no safety in exchange.

## Timing

Two marks, doing different jobs.

At **30 seconds** the launcher reports on stderr what it sees — a recognised
startup dialog by name, that the input box has not appeared yet, or that
the handshake has gone unanswered with nothing obviously in the way. It keeps
waiting. A first turn loads configuration and starts external servers,
so a healthy session can legitimately be slow, and failing at the first sign of
slowness trains people to ignore the warning.

At the **ceiling** (`--timeout`, default 120 seconds) it decides:

- the CLI process is gone → **never started**, exit 4
- a recognised dialog is holding the session → **blocked**, exit 4
- the input box never appeared, and no known dialog is showing →
  **not ready**, exit 5; nothing was sent
- the handshake was sent and not answered, and no known dialog is showing →
  **unconfirmed**, exit 5

The outcome is chosen from a look taken at the ceiling, not from the last one
before it. A send that is held back ends the run without waiting for the
ceiling: exit 4 when a known dialog is showing, exit 5 (**not ready**)
otherwise. A dialog that a person accepts while the launcher is still waiting
for the box is followed by the handshake in the same run.

### What the report says was sent

Every run that verifies reports how far it got. `--porcelain` prints one
`key<TAB>value` pair per line, and the prose report says the same in words.
These are all the keys, and every value each can take:

| Key | Values |
|---|---|
| `name` | The session name |
| `directory` | The directory, as resolved |
| `posture` | `acceptEdits`, `bypass` |
| `verdict` | `healthy` (exit 0), `bridge_dead` (3), `launched` (0, with `--no-verify`), `no_process` (4), `blocked` (4), `not_ready` (5), `unconfirmed` (5), `mismatch` (2), `mux_error` (tmux's status) |
| `pid` | The CLI's process id, or empty when there is none |
| `identity` | Present once the session has answered: `ok`, `posture_unverified`, `mismatch_cwd`, `mismatch_posture` |
| `brief` | `delivered`; `not_submitted` (pasted, Enter not sent); `none` (not pasted: none was given, or the run ended first) |
| `handshake` | Present on every run that verifies: `not_sent` (nothing at all was sent), `not_submitted` (pasted, Enter not sent), `sent`. Absent with `--no-verify`, which attempts no handshake |
| `url` | Present when there is a remote-control bridge |

Read together they say what happened. `identity<TAB>ok` beside
`verdict<TAB>blocked` is a dialog that came up after the handshake.
`verdict<TAB>no_process` with `handshake<TAB>sent` is a CLI that exited
after it was sent. A dry run prints the plan, not pairs.

After `not_submitted` the session's input box may still hold the pasted text.
Clear it before using `--resume`, which pastes a new handshake.

If the session is plainly at its prompt and the report says it is not ready,
the installed CLI draws its input box or mode line differently: see
`blockers.md` (The status-line table).

## Warnings

Two hazards are announced by the launcher itself, on stderr, each as one line:

```
WARNING: <the fact that makes this dangerous now>; this <VERB> <what>.
```

The fact is read at run time — the session name, the directory, the repository
root — and the consequence is one verb in capitals. A line in the command's
own output reaches the caller at the step where it decides what to do next. A
caution in a document was read earlier and gives no signal that this
invocation is the one it was about.

| Printed | Line |
|---|---|
| On every launch with `--bypass`, once, immediately before the session is created | `WARNING: --bypass turns ALL permission prompts off for '<name>' in <dir>; this LAUNCHES a session that can use every credential in the environment it inherits, with nobody approving its commands. Omit --bypass to launch as acceptEdits.` |
| When `--trust-folder` is about to record trust and `<dir>` is inside a repository without being its root, before the write | `WARNING: <dir> is inside the repository <root>; this RECORDS trust for the whole repository, not only that directory.` |

A warning announces something that is about to happen, so it is printed only
when the run gets that far:

- A run that is refused prints neither.
- `--resume` creates nothing, so it prints no bypass warning. There `--bypass`
  only names the posture the existing session is expected to report.
- If tmux then fails to create the session, a second line says that nothing
  was launched, and the exit status is tmux's own.

`--dry-run` prints the same lines with `without --dry-run this` in front of the
verb, and only when the real run would reach that point. Where the real run
would refuse, or would resume, it says that on stderr instead.

One refusal a dry run cannot foresee: it asks tmux nothing, so it does not
know whether the name is already in use. The bypass warning of a dry run ends
by saying so (`A dry run does not check the name: …`), in the same line. The
real run refuses a name that is already running and launches nothing.

**One message is one line.** A session name, a directory and a repository root
come from outside, and a file name may hold a newline or a terminal escape
sequence. Every warning and every refusal renders control characters as text —
`\n`, `\t`, `\r`, `\x1b`, `\u009b` — and doubles a backslash, so a name cannot
put a second, forged line on stderr or repaint the real one. The helper that
reads and writes the trust configuration renders the configuration path the
same way in its own errors.

**Nothing here changes stdout.** Warnings, and every correction a dry run
makes, go to stderr. stdout — `--porcelain` pairs, the prose report and the
dry-run plan — is byte for byte what it was before the warnings existed, so a
caller that parses it keeps working. One consequence: the dry-run plan still
says `would spawn` under `--resume`, and still ends an untrusted preview with
`would refuse without --trust-folder` under `--bypass`. In both cases stderr
carries the accurate statement.

## Refusing a directory

A directory is refused (exit 2) when its path holds a control character or is
not valid UTF-8. The refusal comes before the trust configuration is read or
written and before tmux is asked anything, in a dry run too.

The first reason is the newline at the end of a name. Shell command
substitution drops trailing newlines, so a directory named `repo` plus a
newline resolves to `repo`, its sibling: trust would be recorded for a
directory nobody named, and the session would start there. Any other control
character breaks a different consumer of the path: the tab-separated
`--porcelain` pairs, the prose report, and the reply the session sends back,
where the directory is one space-free word.

A byte that is not part of well-formed UTF-8 is refused for the same reason
as a control character. A lone byte from 0x80 to 0x9f is the second control
block as an 8-bit terminal reads it, and it is not the encoding of any
character, so no rule about characters catches it. Valid names whose encoding
uses those byte values (`é`, `ł`, CJK, emoji) are unaffected. The check walks
bytes with the locale pinned, so it gives the same answer under `LC_ALL=C`, a
UTF-8 locale, and none. On Linux this refuses names that used to be carried
through, such as one holding a 0xff byte. macOS cannot create such names.

Four things are checked, each read with trailing newlines kept:

- the argument as given, or the current directory;
- where the argument leads when every symbolic link is followed before every
  `..`, which is how the kernel reads it;
- the absolute path the shell resolves it to;
- that path with symbolic links resolved.

The repository root, which is what trust is recorded under, is held to the
same rule. A clean-looking argument such as `.`, a symbolic link, or
`link/..` can still name such a directory.

A `#` in the path is not refused. tmux reads the directory it is given as a
format, so a directory named `a-#{session_name}` would be expanded into some
other path and the session started in the home directory. The launcher passes
the directory with every `#` doubled, which tmux reads back as one.

The shell and the kernel read `link/..` differently when `link` is a symbolic
link: the shell takes it as the directory holding the link, the kernel as the
parent of what the link points to. The launcher uses the shell's reading for
the working directory and the trust record, as it always has, and refuses
when either reading holds a control character.

The refusal prints the path with those bytes written out as text (`\n`,
`\x1b`, `\x9b`), on one line. So does every other message that quotes a
directory or a session name.

## Refusals around `--bypass`

A bypass launch is refused (exit 2), before anything is created, in three
cases.

**Together with `--trust-folder`.** Refused as a usage error, before the brief
is read, the trust configuration is opened, or tmux is asked anything. The
refusal names the two invocations that replace the one: record trust first
(run once with `--trust-folder` and without `--bypass`, or start the CLI in the
directory by hand and accept the prompt), then run again with `--bypass` and
without `--trust-folder`. It does not depend on whether the workspace is
already trusted, so the same command line never works on one machine and fails
on another.

**In a workspace that is not trusted yet.** The same two steps are named,
because the usual advice there — add `--trust-folder` — is the refused
combination.

**When trust cannot be checked.** The check needs `python3`. Without it the
launcher cannot tell a trusted workspace from an untrusted one, and a bypass
launch fails closed: the refusal names `python3`. Every other posture launches
as before, stops at the trust prompt if there is one, and is diagnosed there.

`--help` is the exception to all of it: it is acted on where it is read, prints
the usage text and exits 0, whatever follows it and whatever accepted
arguments precede it, including the refused combination. Nothing is launched.
It wins only once the parser reaches it. An argument refused first is still a
refusal: `--unknown --help` exits 2 with `unknown option`. An option that
takes a value takes `--help` as that value, so `--dir --help` is a directory
named `--help`.

### What the refusal does and does not guarantee

The refusal governs the parsed flags of **one invocation**: no single command
line both records trust for a workspace and starts an unsupervised session in
it. That is all it guarantees.

- The two supported invocations can be chained on one line
  (`… --trust-folder && … --bypass`) with no person in between. Nothing here
  detects or prevents that.
- `--pre-launch` runs an arbitrary shell command in the pane before the CLI
  starts. It is as powerful as the caller's shell and is not constrained by
  this refusal.
- Trust recorded by any other means — by hand, by an earlier run, by editing
  the CLI's configuration — satisfies the check.

The point of the separation is that each step is visible and separately
refusable — by a permission prompt, a reviewer, or a person reading the
command — not that the two cannot be automated together.

## Exit codes

| Code | Name | Meaning |
|---|---|---|
| 0 | confirmed | Identity confirmed, bridge live, brief delivered if given |
| 2 | refused | Usage error, unusable name, a directory whose path holds a control character or is not valid UTF-8, name already taken, `--bypass` with `--trust-folder`, untrusted workspace, `--bypass` when trust cannot be checked, identity mismatch |
| 3 | unreachable | Confirmed and briefed, but no remote-control bridge |
| 4 | never usable | No process appeared, or the process started and exited, or a startup dialog is showing |
| 5 | not ready, or unconfirmed | Running, no known dialog showing, and either the input box was not there for a send (not ready) or the handshake went unanswered (unconfirmed) |
| other | tmux failed | tmux's own status, when it refuses to create the session or fails a command during a delivery. The message on stderr starts "the multiplexer" |

**3 and 5 are not failures.** Exit 3 is a connectivity fault around a working
session; exit 5 is missing evidence, not evidence of a problem. In both cases
the session is running, is left strictly alone, and may hold a real
conversation. Killing and re-spawning in response destroys work in order to
tidy up an unknown — resolve the cause and use `--resume` instead.

Before any outcome that says the session is running, the launcher checks that
the CLI process is still there. A CLI that starts and exits at once is exit 4,
not exit 5.

## Resuming

`--resume` picks up a session that already exists rather than creating one: it
looks at the pane the same way before each send, re-runs the handshake with a
fresh token once the input box shows, and delivers the brief if the reply
confirms. A session seen at a dialog is sent nothing.

Nothing about a spawn's progress is written down. Whether a session exists,
whether a process is running in it, and whether it answers are all re-derived
at the moment of asking. A stored record of progress can disagree with reality;
these observations cannot.

What `--resume` does not know about the session it picks up:

- **A turn in progress.** The input box stays on screen while the CLI works,
  so the pane is ready and the handshake is pasted and submitted. The CLI
  queues it behind the turn. If the answer does not arrive in time the run
  ends unconfirmed (exit 5), and a later `--resume` sends another handshake.
- **A draft in the input box.** The launcher cannot tell text someone typed
  from the CLI's own placeholder text, so the handshake is pasted after the
  draft and the two are submitted together. Clear the box first if the draft
  matters.
- **A pane it did not size.** See "Looking before sending": too short to show
  the line under the box is not ready.

## Delivery

Both the request and the brief are delivered as a paste, never as typed input.

The terminal interface treats a paste as a single block: newlines inside it are
text. Typed input is dispatched keystroke by keystroke, where a newline is a
submission — so a multi-line brief typed in would arrive as its first line
followed by the remainder as separate messages, each acted on out of context.

Exactly one submission follows the paste, after a look of its own. If the
input box is gone by then, the paste stays unsubmitted and is reported that
way.
