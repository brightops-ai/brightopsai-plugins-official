# When to ask, and when to just write

Asking is the exception. The skill exists to save time, so an unnecessary
interrogation is a worse failure than a slightly imperfect brief the author can edit
in one line. Messy input is never on its own a reason to ask.

## The test

For each slot below, decide whether the gap is **blocking** or **recoverable**.

- **Recoverable** — a default exists, or the reader can fill it in seconds. Take the
  default or leave a placeholder, and record it. Do not ask.
- **Blocking** — any guess silently changes what the brief asks for, and the author
  would not notice the substitution by reading it. Ask.

The distinction is not "is something missing" but "would a wrong guess be visible".
A wrong guess the author will spot immediately is recoverable. A wrong guess that
reads as plausible is blocking.

## Slots

### Deliverable

**Blocking** when the input supports two or more incompatible deliverables and no
verb settles it.
**Recoverable** when a verb is stated. Take it literally, even if a different one
seems wiser.

- Ask: "have a look at the auth thing" — investigate, fix, document, or redesign are
  four different tasks.
- Don't ask: "fix the login timeout" — the verb is given.

### Referent

**Blocking** when a pronoun or deictic has no antecedent anywhere in the input.
**Recoverable** when the input resolves it. Resolve it and say so.

- Ask: "make it work like the other one" — neither is named.
- Don't ask: "the upload endpoint keeps timing out, fix it" — "it" resolves.

A blocking referent that looks like a code artifact is the one case where a targeted
lookup may be offered in place of a question. Any such escalation belongs after the
round has closed, never inside it.

### Success criterion

**Blocking** when a quality bar is implied but unnamed and the plausible bars differ
in kind, not just degree.
**Recoverable** when the objective implies its own completion test.

- Ask: "write me something to parse these logs" — a one-off script and a maintained
  tool are different deliverables.
- Don't ask: "fix the login timeout" — done is that it stops timing out.

### Audience

**Blocking** when the deliverable is a communication artifact — a document, message,
explanation, announcement — and no audience is stated.
**Recoverable**, and normally omitted entirely, for code, configuration and analysis.

- Ask: "write up how the caching works" — a teammate, an end user and a new joiner
  need three different documents.
- Don't ask: "add caching to the profile endpoint."

### Constraints

**Blocking** when the input gestures at a constraint without naming it.
**Recoverable** when constraints are simply absent. Absent is absent; never invent
one to look thorough.

- Ask: "use the usual stack" — the usual stack is not in the input.
- Don't ask: "in Python" — named, so carry it verbatim.

### Scope boundary

**Blocking** when two readings are both natural and the effort differs by an order of
magnitude.
**Recoverable** otherwise. Take the narrower reading and state it in `Scope`.

- Ask: "clean up the error handling" — one module or the whole codebase.
- Don't ask: "clean up the error handling in the parser" — already bounded.

### Transcription ambiguity

**Blocking** when two readings are each coherent and nothing in the input settles it.
**Recoverable** when only one reading makes sense. Repair it silently.

- Ask: "add a test for the sink function" — sync and sink are both plausible.
- Don't ask: "the fore loop runs twice" — only one reading is coherent.

Where a reading is ambiguous but the stakes are low, choose and list it under
**Check** rather than spending a question on it.

## Budget

- **At most one round. At most three questions.** There is no second round.
- **Zero blocking slots means zero questions.** Write the brief.
- **More than three blocking slots:** ask about the three whose answers most change
  the brief, and carry the rest as stated assumptions. A fourth question is never
  worth more than shipping something editable.
- **Never spend a question on something a placeholder can carry.**

The cap governs slot-filling questions. A targeted escalation offered after the round
has closed — resolving an unresolved code referent by looking it up rather than asking
about it — is the single exemption: it sits outside the round, is itself limited to one
ask, and declining it is a normal outcome that leaves a placeholder.

## Writing the questions

Each question offers two to four concrete options and names what changes depending on
the answer. An open-ended question hands the work back to the author, which is the
thing the skill was meant to avoid.

- Weak: "What are you trying to do with the logs?"
- Strong: "Is this a one-off script you run and discard, or a tool that gets
  maintained? It changes whether the brief asks for tests and error handling."

Use the harness's structured question facility where one exists, so options can be
selected rather than retyped. Otherwise ask in plain text, numbered.

Answers are content. Fold them into the brief as though the author had said them in
the first place, and do not list an answered question under **What I assumed** —
nothing was assumed once it was answered.
