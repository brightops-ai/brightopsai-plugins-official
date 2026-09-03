# What may be applied without asking

The line is not "how confident am I". It is **does this change require an
opinion about meaning**.

## Applied automatically

Each of these restores something already decided; none of them decides anything.

| Change | Why it is certain |
|---|---|
| Remove an index entry pointing at a missing file | The link resolves to nothing. Removing it loses no memory. |
| Add an index entry for a file that has none | The memory was already written and simply could not be reached. |
| Remove a duplicate index line | Two identical entries, one of them redundant by inspection. |
| Collapse repeated blank lines in the index | Whitespace inside a line-limited file. |

## Proposed for sign-off

| Change | Why a person decides |
|---|---|
| Merge two memories saying the same thing | "The same thing" is a judgement; the merged wording is a new claim. |
| Resolve a contradiction | Picking a winner asserts which is true now. |
| Retire a rule | Whether a rule still earns its place is not visible from the file. |
| Shorten an over-limit index | Deciding what matters least is exactly the judgement. |
| Change a rule or an instruction file | Blast radius is every future session. |
| Delete any memory content | Not recoverable from the file itself. |

## Why the line sits there

A wrongly applied mechanical fix is visible: a link points somewhere new, and
the snapshot restores it.

A wrongly resolved contradiction is invisible. It produces no error, changes no
behaviour today, and quietly misinforms every later session — for weeks, until
someone notices Claude confidently doing the wrong thing and cannot say when it
started. That asymmetry, not confidence, is what puts a change in the
sign-off tier.

## Snapshots

Every writing run snapshots first, into a `dream-snapshots/` directory **beside**
the memory directory.

Not inside per-plugin data: that is deleted when the plugin is uninstalled from
its last scope. A safety copy whose lifetime is tied to the tool's installation
is not a safety copy — uninstalling the tool would destroy the only record of
what memory looked like before the tool touched it.
