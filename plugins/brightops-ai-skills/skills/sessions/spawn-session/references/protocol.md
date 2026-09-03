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

At **30 seconds** the launcher looks at the terminal and reports what it sees —
a recognised startup dialog by name, or that nothing is obviously in the way.
It keeps waiting. A first turn loads configuration and starts external servers,
so a healthy session can legitimately be slow, and failing at the first sign of
slowness trains people to ignore the warning.

At the **ceiling** (`--timeout`, default 120 seconds) it decides:

- a recognised dialog is holding the session → **blocked**, exit 4
- no answer and nothing recognisable → **unconfirmed**, exit 5

## Exit codes

| Code | Name | Meaning |
|---|---|---|
| 0 | confirmed | Identity confirmed, bridge live, brief delivered if given |
| 2 | refused | Usage error, unusable name, name already taken, identity mismatch |
| 3 | unreachable | Confirmed and briefed, but no remote-control bridge |
| 4 | never usable | No process appeared, or a startup dialog is holding it |
| 5 | unconfirmed | Running, no answer within the ceiling, nothing recognisable |

**3 and 5 are not failures.** Exit 3 is a connectivity fault around a working
session; exit 5 is missing evidence, not evidence of a problem. In both cases
the session is running, is left strictly alone, and may hold a real
conversation. Killing and re-spawning in response destroys work in order to
tidy up an unknown — resolve the cause and use `--resume` instead.

## Resuming

`--resume` picks up a session that already exists rather than creating one: it
re-runs the handshake with a fresh token and delivers the brief if the reply
confirms.

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
