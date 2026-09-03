---
name: calibrate-style
description: Seed the improve-prompt vocabulary by collecting a few samples of how you actually speak and type.
disable-model-invocation: true
argument-hint: "[--reset]"
---

# Calibrate Style

Collect a short set of samples and turn them into vocabulary entries, so
`improve-prompt` starts out knowing how this author phrases things rather than
learning it over many runs.

Entirely optional. `improve-prompt` works with an empty vocabulary and simply asks
more questions early on. Say so plainly if the author seems unsure whether they need
this: the payoff is fewer questions later, not a working skill versus a broken one.

## What this can and cannot learn

It reads transcripts, never audio. It cannot learn an accent or a pronunciation.
What it learns is how a particular dictation tool fails on this particular person's
speech — which is a property of that pairing. Change dictation tool and the
transcription entries may stop applying, which is why the tool's name is recorded
with them.

Say this before collecting anything. An author who expects it to learn their voice
will be misled by what it actually does.

## References

- `../improve-prompt/references/vocabulary-schema.md` — the file, its sections, and
  what may be stored

## Collecting

With `--reset`, confirm first, then start from an empty vocabulary. Without it,
merge into whatever exists.

Ask for six samples, one at a time, waiting for each. Say which mode each is for —
dictated samples must actually be dictated through the author's usual tool, or they
teach nothing about transcription. If the author types a sample meant to be spoken,
note it and do not derive transcription entries from it.

Dictated:

1. A request you would genuinely make to a coding agent about something you are
   working on now.
2. A request where you change your mind partway through.
3. A request naming several specific things — file names, functions, flags,
   versions.
4. A request with a constraint you actually care about.

Typed:

5. A rough request typed the way you would type it in a hurry.
6. A request using whatever shorthand you normally use for tools and projects.

Sample 3 matters most. It is the only one that reliably exposes how the dictation
tool mangles technical text, which is the highest-value thing in the vocabulary.

Six is a deliberate ceiling. A longer interview gets abandoned halfway, and a
half-finished calibration is worse than none because it looks complete.

## Reading the samples

Derive, per `vocabulary-schema.md`:

- **Speaking style** — filler words, restart patterns, how sentence boundaries are
  marked, whether punctuation is dictated.
- **Typing style** — capitalisation, abbreviations, recurring typos, punctuation
  habits.
- **Transcription slips** — from sample 3, where a spoken identifier arrived as
  ordinary words. Record what was heard and what was meant, only where the author
  confirms the intended form.
- **Terms and idioms** — from samples 1 and 6, phrases standing in for a name, and
  expressions an outsider would read differently.
- **Standing preferences** — anything said about how output should look.

Store conventions of expression only. The samples describe real work; the vocabulary
must not retain what that work was. Record that a phrase means a project name, not
what the project does.

## Calibrating the question threshold

Take a genuine ambiguity from the samples — a phrase with two coherent readings —
and show the author both readings, asking which they meant and whether they would
have wanted to be asked. Where nothing ambiguous arose, say so and skip it rather
than inventing one.

The answer sets how readily `improve-prompt` spends a question on this author. Record
it under standing preferences.

## Confirming before writing

Show everything derived, grouped by section, and wait. Nothing is written until the
author has seen it. They may edit, drop, or correct any entry.

Entries surviving review are confirmed and go straight to their sections, skipping
the candidate area — the author reviewed them, which is stronger evidence than a
sighting count. Anything they were unsure about becomes a candidate instead.

Then write, and report in one closing line what was added, merged and dropped.
