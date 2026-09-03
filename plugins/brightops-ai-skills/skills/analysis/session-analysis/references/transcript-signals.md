# What the transcripts hold, and what the signals mean

## Record shapes

Session transcripts are JSON Lines under the project directory, one record per
line. The records that matter:

| `type` | Carries |
|---|---|
| `user` | A human turn, or a `tool_result` block returning to the assistant |
| `assistant` | Assistant text and `tool_use` blocks |

Every record carries `timestamp`, `sessionId`, `uuid`, `parentUuid`, and usually
`cwd` and `gitBranch`. `isSidechain` marks subagent traffic, which is skipped:
it reflects an agent's own work, not the user's guidance.

`message.content` is a string or a list of blocks. Blocks of interest are
`text`, `tool_use` (with `name` and `input`) and `tool_result` (with
`is_error`).

## The four signals

**`interrupted`** — the marker `[Request interrupted by user]`. The strongest
signal available, and entirely phrasing-independent: the user stopped the run,
which means the approach was wrong at that moment. Carries the tool call that
was in flight.

**`permission-denied`** — a tool result saying the user refused. Evidence of a
boundary that was never stated as a rule.

**`tool-failure`** — a tool result flagged `is_error`. Clustered by tool plus a
digit-normalised signature of the message, so "3 tests failed" and "7 tests
failed" count as one recurring failure rather than two. `occurrences` carries the
count.

**`quick-turn-after-edit`** — a short human turn immediately following an
`Edit`, `Write`, `MultiEdit` or `NotebookEdit`. The weakest signal and the
noisiest. It is included because corrections cluster there, not because a short
turn is a correction.

## What these are not

None of these is a correction. The script does not use the word, and neither
should a reading of the digest that stops at the episode kind.

Lexical detection was measured and rejected. Across 43 real transcripts, a
regular expression for correction-like phrasing matched 6.3% of human turns, and
inspection showed most matches were ordinary conversation — "you can stop it
now", "we don't even need the inbox anymore", "do I have any stray sessions
running". Recall was unknowable and precision was poor.

Structure is detectable. Meaning is not. That is the whole reason the split
exists.

## Budget and window

Extraction is bounded by a token budget rather than an episode count, because a
three-line interrupt and a 400-line error dump are not the same cost. When the
budget binds, the newest episodes are kept and `truncated` is set.

Transcripts are deleted after the configured retention period. When the
requested window opens before the oldest surviving transcript, `retention_gap`
says so. Report it: analysing less data is fine, reporting on less data as
though it were all of it is not.
