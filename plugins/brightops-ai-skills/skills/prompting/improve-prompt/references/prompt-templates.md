# Brief skeleton and worked examples

## Skeleton

```
<one-line objective: the deliverable, stated as an outcome>

Context
<what the agent cannot discover for itself: why this is being done, what
constrains it and why, what has already been tried>

Scope
In: <what this task covers>
Out: <what it explicitly does not cover>

Constraints
- <hard requirement, with its reason where one was given>

Done when
- <verifiable criterion>

Notes
- <assumption, placeholder, or doubt worth flagging>
```

Drop any section that would be empty. `Notes` is usually absent. `Scope: out` and
`Done when` are the two that most often need writing rather than extracting, and
they are the two that most change agent behaviour — the first bounds the work, the
second makes finishing checkable.

Order matters when the brief carries bulk material such as a log, a spec or a long
error: put that material first and the instruction last.

## Worked example — dictated, bounded fix

<example>
Rough input (dictated):

"ok so um the thing where when you upload a file bigger than like ten megs it
just it dies with a five hundred, no wait it's not a five hundred it's a timeout,
anyway it needs to not do that, um and don't go rewriting the whole upload path
I just want the timeout handled, oh and the retry thing should stay how it is"

Brief:

Fix the failure that occurs when uploading files larger than 10 MB.

Context
Uploads above roughly 10 MB currently fail with a timeout. Only the timeout
handling is in question; the surrounding upload path is considered working and
should be left alone.

Scope
In: the timeout that fires on large uploads.
Out: restructuring the upload path; changing existing retry behaviour, which
should keep its current semantics.

Constraints
- Keep the change minimal. Do not add unrequested features, refactors,
  abstractions, or defensive validation, and do not document code you did not
  change.
- Read the relevant upload and timeout handling before making claims about it;
  do not speculate about code you have not opened.

Done when
- An upload larger than 10 MB completes rather than timing out.
- Existing retry behaviour is unchanged.

Notes
- The size threshold was given approximately ("like ten megs") and is recorded
  here as 10 MB.
</example>

Note what the brief did not do. It did not mention the 500 the author corrected
themselves out of. It did not invent a specific timeout value, a file name, or a
target upload size beyond the one stated. It kept the hedge on the threshold
rather than hardening it, and recorded that hedge under `Notes`.

## Worked example — typed, unbounded build

<example>
Rough input (typed):

"need a cli that reads the csv exports and spits out a summary per region,
should be fast enough to run in ci, python"

Brief:

Build a command-line tool that reads CSV exports and produces a per-region
summary.

Context
The tool runs in CI, so start-up and execution time matter more than
interactivity or presentation.

Scope
In: reading the CSV exports, aggregating by region, emitting a summary.
Out: [ANY OUTPUT FORMAT OR DESTINATION BEYOND STDOUT — unspecified].

Constraints
- Python.
- Fast enough to run inside CI without becoming a bottleneck.

Done when
- Running the tool against the CSV exports prints a summary for each region.
- Runtime is acceptable for CI use.

Notes
- The export file location and schema were not given; the brief leaves them for
  the agent to discover or the author to fill in.

Then, outside the block:

**What I assumed**
- Output goes to stdout. Landed in Scope: out, as a placeholder rather than a
  decision — replace it if the summary belongs in a file or a report.
</example>

Here the deliverable was clear, so no question was warranted, but two genuine gaps
existed. Both were left visible — one as a placeholder, one as a note — rather than
being filled with a plausible guess. "Fast enough for CI" was kept in the author's
terms instead of being converted into an invented millisecond budget.
