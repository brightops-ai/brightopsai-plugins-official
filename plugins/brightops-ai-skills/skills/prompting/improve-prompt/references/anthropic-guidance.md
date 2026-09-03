# Prompting guidance this skill builds to

```
captured: 2026-09-03
```

A distilled snapshot, not a copy. The craft rules below have been stable across
published revisions for roughly a year; the model-specific detail in the last
section has not, which is why that section holds pointers rather than claims.

## Sources

| Source | Read | Note |
|---|---|---|
| Prompting best practices — `platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices` | 2026-09-03 | The living reference. Model-specific guidance, then all-model techniques, then migration. |
| Prompt engineering overview — `platform.claude.com/docs/en/build-with-claude/prompt-engineering/overview` | 2026-09-03 | Now a stub that defers to the page above. |
| Best practices for prompt engineering — `claude.com/blog/best-practices-for-prompt-engineering` | 2026-09-03 | Published 2025-11-10. |
| Effective context engineering for AI agents — `anthropic.com/engineering/effective-context-engineering-for-ai-agents` | 2026-09-03 | Published 2025-09-29. |

The standalone prompt-improver page redirects into the living reference; there is
no separate published improvement pipeline to mirror.

## Rules applied when writing a brief

**Be explicit about the deliverable.** Above-and-beyond behaviour has to be asked
for; it is not inferred from a vague instruction. The stated test is to hand the
prompt to a colleague with no context — if they would be confused, so is an agent.

**Give the motivation, not just the constraint.** A constraint with its reason
attached generalises to neighbouring decisions; a bare prohibition does not.
Prefer "the output is read aloud, so avoid ellipses" over "never use ellipses".

**Say what to do, not what to avoid.** Positive instructions steer more reliably
than prohibitions.

**Number the steps when order or completeness matters.** Use prose when it does not.

**Put long inputs first and the instruction last.** For data-heavy briefs, leading
with the material and closing with the request measurably improves the response.

**Show, where describing is harder than demonstrating.** One example beats a
paragraph about format. Keep examples few, varied and clearly delimited; exhaustive
edge cases crowd out the task.

**Aim for minimum necessary structure.** The failure modes sit on both sides:
over-specified prompts encode brittle logic, under-specified prompts assume shared
context that does not exist. Minimal does not mean short — it means nothing present
that is not doing work.

**Let the agent report uncertainty.** Explicitly permitting "I don't know" or "this
is infeasible" reduces confident wrong answers.

## Conditional clauses

Add a clause only when its condition holds. Adding all of them by default produces
the over-specified prompt the guidance warns against and buries the task.

| Clause | Add when |
|---|---|
| Keep the change minimal — no unrequested features, refactors, abstractions, defensive validation or documentation of untouched code | The deliverable is bounded: a bug fix, a small feature, a targeted edit. This is the highest-value clause; agents reliably over-engineer without it. |
| Read the relevant files before making claims about them; do not speculate about unopened code | The brief refers to existing code, files or behaviour |
| Solve the general problem, not the test cases; do not hard-code to fixtures or build workarounds | Success is defined by tests or a conformance spec |
| Say so rather than working around it if the task is infeasible or a requirement looks wrong | The brief carries constraints that may conflict, or that the author is unsure about |
| Remove any scratch files or helper scripts created while iterating | The task plausibly needs scratch work |
| Summarise briefly after finishing | The author asked for visibility into what happened |
| Keep the response short | The author asked for brevity |

## Model-specific behaviour — pointers, not claims

Do not encode any of the following into a brief as fact, and never name a model in
the brief itself. Consult the living reference when a claim about a specific model
actually matters:

- Default verbosity and response length differ by model, in both directions, and
  have reversed between releases.
- How much a model volunteers progress updates during agentic work varies by model.
- Thinking configuration has changed across generations; older parameters are
  deprecated or rejected outright on newer models.
- Prompting that compensated for under-eager tool use in older models causes
  over-triggering in newer ones.
- Response prefill is not supported on current models.

## Refreshing this file

Re-read the sources above, update `captured`, and revise only what changed. The
craft rules move slowly; the pointer section is the part that dates. Ship the change
as a plugin version bump so installations pick it up.
