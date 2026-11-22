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

The handshake is input: it is pasted into the pane and submitted. So before it
is sent the launcher looks at the pane, once a second, and classifies what it
sees.

| The pane shows | State | What is sent |
|---|---|---|
| A known startup dialog (`scripts/startup-blockers.tsv`) | blocked | Nothing |
| The input prompt (`scripts/ready-prompts.tsv`) and no known dialog | ready | The handshake |
| Neither: empty, still starting, or not recognised | waiting | Nothing |

Readiness is a positive finding. "No known dialog" also describes a pane that
is still starting, and one showing a dialog the table has no row for; input
sent then is typed at whatever comes up next. A dialog wins over a prompt,
because a dialog drawn over an earlier screen can leave the prompt's text
visible beside it.

A running CLI process is not the signal. A session held at a dialog has a
live process too.

If the pane never becomes ready within `--timeout`, the run ends and nothing
has been sent to the session: no paste, no keypress. See Timing for which exit
code that is.

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
startup dialog by name, that the input prompt has not appeared yet, or that
the handshake has gone unanswered with nothing obviously in the way. It keeps
waiting. A first turn loads configuration and starts external servers,
so a healthy session can legitimately be slow, and failing at the first sign of
slowness trains people to ignore the warning.

At the **ceiling** (`--timeout`, default 120 seconds) it decides:

- a recognised dialog is holding the session → **blocked**, exit 4
- the input prompt never appeared, and nothing recognisable is in the way →
  **unconfirmed**, exit 5; the handshake was not sent
- the handshake was sent and not answered, and nothing recognisable is in the
  way → **unconfirmed**, exit 5

When the run ends before the handshake is sent, the prose report says that
nothing was sent, and `--porcelain` adds the pair `handshake<TAB>not_sent`.
The pair is absent from every other report. A dialog that a person accepts
while the launcher is still waiting is followed by the handshake in the same
run.

If the session is plainly at its prompt and the report still says the prompt
never appeared, the status-line wording has moved in the installed CLI: see
`blockers.md` (The prompt table).

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

**One message is one line.** A session name, a directory and a repository root
come from outside, and a file name may hold a newline or a terminal escape
sequence. Every warning and every refusal renders control characters as text —
`\n`, `\t`, `\r`, `\x1b`, `\u009b` — and doubles a backslash, so a name cannot
put a second, forged line on stderr or repaint the real one.

**Nothing here changes stdout.** Warnings, and every correction a dry run
makes, go to stderr. stdout — `--porcelain` pairs, the prose report and the
dry-run plan — is byte for byte what it was before the warnings existed, so a
caller that parses it keeps working. One consequence: the dry-run plan still
says `would spawn` under `--resume`, and still ends an untrusted preview with
`would refuse without --trust-folder` under `--bypass`. In both cases stderr
carries the accurate statement.

## Refusing a directory

A directory is refused (exit 2) when its path holds a newline or any other
control character. The refusal comes before the trust configuration is read
or written and before tmux is asked anything, in a dry run too.

The reason is the newline at the end of a name. Shell command substitution
drops trailing newlines, so a directory named `repo` plus a newline resolves
to `repo`, its sibling: trust would be recorded for a directory nobody named,
and the session would start there. Any other control character breaks a
different consumer of the path: the tab-separated `--porcelain` pairs, the
prose report, and the reply the session sends back, where the directory is
one space-free word.

Three things are checked: the argument as given (or the current directory),
the absolute path it resolves to, and that path with symbolic links resolved.
The last two are read with trailing newlines kept. A clean-looking argument
such as `.` or a symbolic link can still name such a directory. The
repository root, which is what trust is recorded under, is held to the same
rule.

The refusal prints the path with its control characters written out as text
(`\n`, `\x1b`), on one line.

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
the usage text and exits 0 whatever else is on the line, including the refused
combination. Nothing is launched.

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
| 2 | refused | Usage error, unusable name, a directory with a control character in its path, name already taken, `--bypass` with `--trust-folder`, untrusted workspace, `--bypass` when trust cannot be checked, identity mismatch |
| 3 | unreachable | Confirmed and briefed, but no remote-control bridge |
| 4 | never usable | No process appeared, or a startup dialog is holding it |
| 5 | unconfirmed | Running, nothing recognisable in the way, and within the ceiling either the input prompt never appeared (nothing was sent) or the handshake went unanswered |

**3 and 5 are not failures.** Exit 3 is a connectivity fault around a working
session; exit 5 is missing evidence, not evidence of a problem. In both cases
the session is running, is left strictly alone, and may hold a real
conversation. Killing and re-spawning in response destroys work in order to
tidy up an unknown — resolve the cause and use `--resume` instead.

## Resuming

`--resume` picks up a session that already exists rather than creating one: it
looks at the pane the same way, re-runs the handshake with a fresh token once
the prompt shows, and delivers the brief if the reply confirms. A session
still held at a dialog is sent nothing.

Nothing about a spawn's progress is written down. Whether a session exists,
whether a process is running in it, and whether it answers are all re-derived
at the moment of asking. A stored record of progress can disagree with reality;
these observations cannot.

## Delivery

Both the request and the brief are delivered as a paste, never as typed input.

The terminal interface treats a paste as a single block: newlines inside it are
text. Typed input is dispatched keystroke by keystroke, where a newline is a
submission — so a multi-line brief typed in would arrive as its first line
followed by the remainder as separate messages, each acted on out of context.

Exactly one submission follows the paste.
