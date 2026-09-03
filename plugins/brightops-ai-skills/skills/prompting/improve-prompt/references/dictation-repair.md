# Repairing dictated and hastily typed input

The governing invariant is in `SKILL.md`: rewriting is not reinterpreting. This
file is the detail — what counts as a channel artifact, what counts as content, and
how to tell them apart when they look alike.

## Inferring the mode

Never ask which it is. The text says.

**Dictated** reads as one long breath: little or no punctuation, filler ("um", "uh",
"like", "you know", "I mean"), restarts ("the the", "it needs it needs"), spoken
connectives carrying the sentence boundaries ("so", "and then", "anyway", "ok so"),
numbers and symbols spelled out as words, and no capitalisation beyond what the
transcriber guessed.

**Typed rough** reads as clipped: lower case, dropped articles and subjects
("needs a flag for that"), abbreviations, adjacent-key typos and transpositions,
missing apostrophes, and trailing thoughts after commas.

Both can appear together — a dictated passage pasted next to a typed afterthought.
Treat each passage on its own evidence.

## Artifact or content

Remove, because the channel put it there:

- Filler and hesitation: um, uh, er, like, you know, I mean, sort of, kind of —
  **only** where they carry no meaning. "sort of" as hedging a claim is content.
- Restarts and stutters: "the the", "it needs — it needs"
- Discourse openers that carry nothing: "ok so", "right so", "anyway", "yeah"
- Run-on structure: split into sentences at the boundaries the connectives mark
- Missing or guessed punctuation, and absent capitalisation
- Typos, transpositions and dropped apostrophes in ordinary words

Keep, because the author put it there:

- **Hedges** — maybe, I think, probably, might, roughly, about, like ten. These
  record confidence. Promoting one to a certainty invents a finding the author did
  not make. "I think it's the images" becomes a possible cause, never the cause.
- **Priority markers** — mostly, mainly, the important bit is, don't worry about.
  These are scope instructions in disguise.
- **Emphasis** — repetition for stress, "really", "definitely", "whatever you do".
  Carry the force into the brief's wording even though the word itself may go.
- **Negations and prohibitions** — "don't touch", "leave alone", "not the". These
  are the most damaging thing to drop and the easiest to lose in a run-on.

## Self-correction

Spoken input revises itself in flight. Two shapes that look alike and are not:

**Replacement** — "use Redis, no wait, actually Postgres". Markers: no wait,
scratch that, sorry, I mean, actually, rather. The later value wins outright.

The superseded value must not appear in `Objective`, `Constraints`, `Scope` or
`Done when` — not even as a contrast. "Use Postgres, not Redis" is the failure:
the author changed their mind, they did not run a comparison, so the brief invents
a deliberation and hands the agent a rejection it was never told to make. It is
also the more dangerous reading if the correction was itself misheard, because the
wrong store now carries emphasis.

It may appear in `Notes` only where it carries information the agent needs anyway —
a genuine technical consequence, not a contrast. That the value was dropped belongs
under **Check**, where the author can catch a misheard correction in one glance.

**Accumulation** — "it's the images, or it might be the fonts too". Markers: too,
also, and maybe, as well. Nothing is superseded. Both survive, both hedged.

When the markers are absent and both readings are open, treat it as accumulation —
keeping an extra hedged possibility is cheaper than silently deleting a requirement.

## Reproduce exactly

Copy these through untouched, including case and punctuation: identifiers and
symbol names, file names and paths, command flags, URLs, quoted strings, error
text, version numbers, and numbers with units. Proper nouns too, including product
and library names.

## Mis-transcription

Speech-to-text mangles technical text in predictable ways. Recognising the shape is
not permission to rewrite it.

| Heard as | Likely |
|---|---|
| words where an identifier belongs — "use effect", "get status" | `useEffect`, `git status` |
| "dash" / "dash dash" | `-` / `--` |
| "dot t s x", "underscore" | `.tsx`, `_` |
| a spelled-out number with a unit | the numeral and unit |
| a common word where a domain term belongs | the domain term |

**Flag, never silently correct.** Where an identifier looks mangled, keep the input's
form in the brief and note the suspicion under **Check**. A silently "fixed"
identifier that was actually right sends the receiving agent to a symbol that does
not exist, and nothing in the brief reveals the substitution.

The exception is a repair with exactly one coherent reading — "the fore loop runs
twice" is a `for` loop and nothing else. Repair those silently; noting them is noise.

## Homophones

Apply the coherence test. One coherent reading, repair it and say nothing. Two
coherent readings and the stakes are low, choose the likelier, and record the choice
under **Check** so the author can overturn it in one glance. Two coherent readings
that change what gets built is a blocking gap — see `clarify-triggers.md`.
