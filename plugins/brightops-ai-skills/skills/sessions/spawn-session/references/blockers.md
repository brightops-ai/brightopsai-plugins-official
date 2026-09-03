# Startup dialogs, and why none of them is answered automatically

A newly launched session can be held before it reads anything, by a dialog that
expects a person. This skill identifies which one, reports the configuration
entry that settles it, and sends nothing.

## The rule

**Never simulate a keypress at a dialog.** Two independent reasons, and either
alone would be sufficient.

*It is not this tool's question to answer.* The workspace-trust dialog asks
whether the CLI may read and execute the files in a directory. A tool that
answers on the operator's behalf, silently, has made a security decision that
was deliberately routed to a human.

*It does not work reliably.* Everything a scripted answer depends on varies:

- **Option order and default.** The trust dialog renders the refusing option
  *first*, and focuses it. A hardcoded "press down, press enter" is correct
  only while that stays true — and if the order is ever reversed, the same
  keystrokes select **No**, and the session exits. The tool would report "never
  started" while the truth is "we told it to quit".
- **Input timing.** Keys arriving within a short window of the dialog opening
  are discarded, and each discarded key restarts that window. A burst of
  keystrokes can be swallowed entirely, leaving a session that looks hung for
  no visible reason.
- **The highlight glyph.** Which character marks the focused option depends on
  the terminal's declared type, so navigating by reading the marker is not
  portable.
- **The control itself.** In accessibility mode the dialog is a different
  component, not an arrow-key list, and arrow keys do not apply.

Writing the configuration entry instead is deterministic, reviewable, and is
the CLI's own documented alternative to accepting the dialog interactively.

## The table

`scripts/startup-blockers.tsv` is checked-in data: one row per known dialog,
tab-separated, with `id`, a literal `pattern` that appears in the terminal, a
one-line `what`, and a `remedy`.

Patterns match **literally**. Dialog text is full of characters that mean
something in an expression — dots, brackets, question marks — and interpreting
them would let one row match terminals it was never written for. A confidently
wrong diagnosis is worse than a missing one: it sends the reader to change a
setting that was never the problem.

Order matters. The first matching row wins, so more specific dialogs belong
above more general ones.

## Adding a row

1. Reproduce the dialog and capture the terminal.
2. Choose the **shortest literal string that is unique to that dialog**. Prefer
   an option label over prose: labels are stable and specific, while
   explanatory text is reworded between releases.
3. Write the remedy as the configuration entry or the one-time interactive step
   that settles it — never as keystrokes.
4. Add a spec asserting the row matches a realistic terminal and does *not*
   match ordinary session output. The table's own explanatory header is a good
   negative case: a parser that treated comment lines as patterns would match
   almost anything.

## Version drift

Every pattern is a fact about a particular CLI release, recorded in the
launcher as the pinned version. When the installed version differs, reports
carry an advisory line saying so.

Advisory, never blocking. Refusing to spawn on a version bump would break the
tool on every routine update, which is how a safety feature becomes the first
thing someone disables. The right response to drift is to re-verify the
patterns and move the pin, not to stop working.

## What is not in the table

Dialogs asking to grant a capability — approving a tool call, a permission
prompt mid-session — are deliberately absent, and should stay absent. The table
exists so a *startup* dialog can be named and settled in advance by a person
who has read what it asks. Extending it to capability prompts would turn a
diagnostic aid into a standing "yes" to questions nobody read, which is exactly
what the rule at the top of this file forbids.
