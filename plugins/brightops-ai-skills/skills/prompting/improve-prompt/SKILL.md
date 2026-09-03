---
name: improve-prompt
description: Turn rough dictated or hastily typed input into a well-formed prompt for an agentic coding harness.
disable-model-invocation: true
argument-hint: "[rough text] [--vocab] [--forget <phrase>] [--export <path>]"
---

# Improve Prompt

Turn rough input — dictated through speech-to-text, or typed in a hurry — into a task brief that another agentic coding session can act on directly.

The output is text to copy. This skill never runs the prompt it writes, and never attempts the work that prompt describes. Run it in a session separate from the target project and paste the result where the work belongs.

## References

- `references/anthropic-guidance.md` — the prompting rules the brief is built to, with sources and capture date
- `references/clarify-triggers.md` — which gaps justify a question and which do not
- `references/dictation-repair.md` — artifact versus content, self-correction, mis-transcription
- `references/vocabulary-schema.md` — what the vocabulary stores, and what may act on a brief
- `references/prompt-templates.md` — the brief skeleton, and worked examples by task kind

## Invariants

These override every other instruction here.

**Rewriting is not reinterpreting.** Fix how something was said; never change what was said. Disfluencies, false starts, run-ons and missing punctuation are artifacts of the channel and go. Hedges, priority markers and emphasis are content and stay — never promote "maybe" into "must", never drop a constraint because it arrived mid-ramble. Where the input corrects itself, the later statement wins and the superseded one is not named in the brief's objective, constraints, scope or completion criteria — not even as a contrast such as "use this, not that", which invents a rejection the author never made.

**The brief is harness-agnostic.** It will be pasted into Claude Code, Cursor, or another agent. Name no harness-specific tool, slash command, model identifier or API. Add no role line and no XML scaffolding by default — the receiving harness already has a system prompt, and a second one fights it.

**Nothing is invented.** No file names, versions, thresholds, acceptance criteria or constraints that the input did not contain. A gap is either carried as a labelled placeholder or recorded as an assumption. It is never quietly filled.

**Identifiers are reproduced, not corrected.** File names, symbols, flags, quoted strings, error text, numbers with units and proper nouns are copied exactly. Where one looks mis-transcribed, keep it as given and note the doubt beneath the brief.

## Workflow

### 1. Take the input

`--vocab`, `--forget <phrase>` and `--export <path>` are vocabulary operations, not briefs: carry out the one requested, report what happened, and stop. `references/vocabulary-schema.md` defines each.

Otherwise use the argument as the rough text, or ask for it and wait.

### 2. Load the guidance and the vocabulary

Read `references/anthropic-guidance.md`. Compare its `captured` date against today. Six months or older, append the staleness line described under **Output**. Twelve months or older, also state that any model-specific claim should be re-verified before it is relied on.

Then read `${CLAUDE_PLUGIN_DATA}/vocabulary.md`, creating it from `references/vocabulary.seed.md` if absent. It records how this author phrases things. Only confirmed entries may act on the brief; candidates are observations awaiting a threshold and influence nothing. Working without a vocabulary is normal and changes nothing else about the run.

### 3. Extract, then classify every gap

Work out, from the input alone: the deliverable, the subject it acts on, any stated constraints, any stated definition of done, and whether the input is dictated or typed. Infer the mode from the text and never ask about it; `references/dictation-repair.md` gives the signals for each, and the rules for separating what the channel introduced from what the author meant. Apply that repair before anything else, so the rest of the work reads intent rather than noise.

Consult the vocabulary first: a stored term that resolves a referent turns a blocking gap into a recoverable one, so resolve it rather than asking, and mark it as vocabulary-sourced under **What I assumed** so a stale entry stays visible. Where the input contradicts a stored entry, the input wins and the entry is demoted.

Then take every remaining gap to `references/clarify-triggers.md`, which gives the test for each slot. A gap is blocking when a wrong guess would read as plausible and pass unnoticed; it is recoverable when a default exists or a wrong guess would be spotted immediately. Missing something is not by itself a reason to ask.

Recoverable gaps become one of two things:

- **Placeholder** when the reader can fill it in seconds and nothing else depends on it. Write it as `[LIKE THIS]` inside the brief.
- **Assumption** when a reasonable default exists and the brief reads incoherently without it. Take the default, and list it under **What I assumed**.

Prefer the narrower reading of scope. State the reading you took.

### 4. Ask once, and only if something blocks

No blocking gap means no questions. Skip this step and write the brief. This is the common case, and asking anyway is the failure this skill exists to avoid — messiness alone never earns a question.

Otherwise ask a single round of at most three questions. Each offers two to four concrete options and names what changes depending on the answer; an open-ended question hands the work back to the author. Use the harness's structured question facility where one exists, otherwise plain numbered text.

Where more than three gaps block, ask about the three whose answers most change the brief and carry the rest as stated assumptions. There is no second round of slot-filling questions; the only thing that may follow the round is a targeted escalation, itself limited to one ask.

Fold answers into the brief as though the author had said them first. An answered question is not an assumption and does not appear under **What I assumed**.

### 5. Fill the skeleton

Use the skeleton in `references/prompt-templates.md`: objective, context, scope in and out, constraints, done when, notes. Omit a section only when it would be empty; never pad one to fill it.

Two sections carry the most weight and deserve the most care. **Scope: out** is what prevents an agent expanding a small change into a refactor. **Done when** must be verifiable by the receiving agent — a criterion nobody can check is decoration.

### 6. Add conditional clauses, never boilerplate

`references/anthropic-guidance.md` lists clauses that measurably improve agent behaviour, each with the condition that earns it. Add one only when its condition is met. Adding all of them every time produces the brittle, over-specified prompt the guidance itself warns against, and buries the actual task.

### 7. Record what was confirmed

Update the vocabulary only from confirmation: a question the author answered, a correction they made, or a candidate that has now reached its threshold. Everything else is an observation and goes to `Candidates` with a sighting count. Store conventions of expression only — never task content, code or secrets. `references/vocabulary-schema.md` holds the thresholds, the cap and the eviction order.

### 8. Emit

## Rewrite boundary

**Reproduce exactly:** code, file paths, symbols, flags, URLs, error text, quoted phrases, proper nouns, numbers with units, and any value the input gave as a constraint.

**Rewrite freely:** ordering, sentence structure, punctuation, filler removal, section headings, and turning a spoken sequence into numbered steps.

**Add only with a visible note:** success criteria, audience, output format, and scope boundaries that the input implied but did not state. Each of these appears under **What I assumed** or it does not appear at all.

## Output

Emit exactly this shape, in this order.

First, the brief, in a single fenced block containing the brief and nothing else. No preamble inside the fence, no trailing commentary, no explanation of choices. The block is a copy target; anything else in it has to be deleted by hand.

`Notes` inside the brief and **What I assumed** outside it are not the same list
and must not repeat each other. They have different readers. `Notes` tells the
receiving agent something it needs while doing the work — a threshold that was
approximate, a gap left unfilled, a hypothesis that is not yet a finding. **What I
assumed** tells the author what was decided on their behalf, so they can correct it
before pasting. A value the author might want to change goes outside; a caveat the
agent must work under goes inside.

Then, outside the fence, and only when they have content:

**What I assumed** — one line per assumption, each naming the assumption and the section of the brief it landed in, so a wrong one can be corrected in place rather than by re-reading the whole brief.

**Check** — identifiers that may be mis-transcribed, and readings chosen between two coherent alternatives.

**Guidance snapshot** — the staleness line, when step 2 called for it: state the capture date and that a plugin update may carry newer guidance.

**Learned** — one line naming what the vocabulary gained or lost, whenever step 7 wrote anything. Never write silently; a vocabulary the author cannot audit is one they cannot correct.

Say nothing else. No summary of what changed, no offer to iterate, no restatement of the brief in prose. The user reads the brief, not a description of it.
