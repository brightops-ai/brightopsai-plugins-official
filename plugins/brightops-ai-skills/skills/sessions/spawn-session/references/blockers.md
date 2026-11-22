# Startup dialogs, and why none of them is answered automatically

A newly launched session can be held before it reads anything, by a dialog that
expects a person. This skill identifies which one and reports the
configuration entry that settles it. It never answers the dialog, and it
holds back input whenever the CLI's input box is not what the pane shows.

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

Where the wording is decides what it means. With no input box at the foot of
the pane, a row's wording anywhere on the pane names the dialog. With the
input box there, wording above it is earlier output and is ignored, and
wording under it counts only on a line that reads as a dialog option.

A session seen at a dialog is sent nothing. The launcher looks before each
thing it sends, not after, so the usual diagnosis is made with no input having
reached the dialog. The exception is a dialog that comes up between a look
and the send that follows it: `protocol.md` (One look before each send).

## The status-line table

`scripts/ready-prompts.tsv` is the other half of that check. The launcher
recognises the input box by its shape, a rule, the prompt line and a rule at
the foot of the pane, and requires the line under it to be a status line. The
table lists how a status line begins: the mode symbol, the mode, and `on`
(`⏵⏵ accept edits on`, `⏸ plan mode on`). The prompt glyph alone is not
evidence, because the same glyph marks the focused option in a dialog.

Three columns: `id`, the literal `pattern`, and `basis`, which is `seen` for
a row read from a real pane and `inferred` for one that was not. The rows
marked `seen` were drawn by CLI 2.1.330 in a credential-free pseudo-terminal.
The `bypass` row is inferred: starting the CLI with permissions bypassed to
look at it is refused in this repository. A bypass launch that ends not ready
says so on stderr and names that row.

If a session is plainly at its prompt and the launcher reports it not ready,
capture the pane (`tmux capture-pane -p -J -t "=<name>:"`) and compare it
with the shape above. A status line with different wording needs a row. A
box drawn differently needs a change to the launcher, not to the table.

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
