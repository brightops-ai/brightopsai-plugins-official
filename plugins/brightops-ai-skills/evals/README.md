# Behavioural evals for `improve-prompt`

Every guarantee this skill makes is an assertion about prose. Nothing errors when
one stops holding, so a regression is silent and surfaces later as a worse prompt.
These cases make the guarantees checkable.

## Running

```
./evals/run.sh              # every case
./evals/run.sh referent     # cases whose name matches a substring
./evals/check-index.sh      # cases on disk vs the table below (any cwd)
```

Each case drives the skill through headless `claude -p`, with `SKILL.md` and its
reference files injected, and asserts on the output. Exit status is 0 only when
every case passes. Overrides: `EVAL_MODEL`, `EVAL_RUNS`, `EVAL_TIMEOUT`,
`EVAL_MAX_TURNS`.

Runs cost tokens and take a few minutes. This is not a pre-commit gate; run it
when changing `SKILL.md` or a reference file.

## Adding a case

Create `cases/<name>/` holding `input.txt` and `expect.json`. No change to the
skill is needed. Fields:

| Field | Meaning |
|---|---|
| `questions` | `none` or `1-3` — how many questions the input should draw |
| `must_contain` | substrings that must survive verbatim **in the brief** |
| `must_contain_any`, `must_contain_any_2` | at least one of each set present in the brief |
| `must_not_contain` | substrings that must not appear in the brief |
| `must_not_contain_anywhere` | substrings that must not appear anywhere in the output |
| `case_sensitive` | compare exactly; use for identifiers |
| `assumptions` | `required`, `forbidden`, or `optional` |

Content assertions target the brief rather than the whole output on purpose. The
blocks beneath the brief legitimately mention things the brief must not contain —
disclosing a superseded instruction is wanted behaviour, not a leak.

A run that fails for a non-behavioural reason — an exhausted turn budget, an empty
response — is reported as ERROR, never as a failed assertion. A harness problem
dressed as a behavioural regression sends you debugging the wrong thing.

## What the cases cover

| Case | Guarantee |
|---|---|
| `clean-typed` | Tidy input with no gaps draws no questions |
| `dictated-disfluent` | Transcription artifacts removed, meaning kept, still no questions |
| `self-correction` | A superseded instruction does not resurface as a rejected alternative |
| `accumulation` | Two hedged causes both survive; neither is dropped as superseded |
| `identifier-rich` | Identifiers, filenames and flags survive verbatim, including case |
| `mangled-identifier` | A mangled identifier's input spelling survives rather than being silently corrected |
| `ambiguous-referent` | A referent with no antecedent draws a question, within budget |
| `hedge-preserved` | A hedged cause stays hedged rather than being promoted to a finding |
| `negation-preserved` | Mid-run-on prohibitions both survive rather than being dropped |

## What it deliberately does not cover

- **Whether a brief is any good.** The suite checks observable guarantees, not
  quality. A brief can satisfy every case and still be a poor brief; that stays a
  human judgement.
- **Prompt wording.** Assertions avoid the generated phrasing so that rewording a
  template does not fail the suite. The cost is that a genuine wording regression
  can pass.
- **Packaging.** Cases inject the skill directly, so they say nothing about whether
  the plugin installs or the skill resolves under its namespaced name. That install
  proof is recorded in [CLAUDE.md](../../../CLAUDE.md) (Project Structure).
- **Model variation.** Default is one run per case. Raise `EVAL_RUNS` to sample
  nondeterminism; a single green run is not proof of stability.
- **The repository escalation.** Resolving a code referent by lookup needs a
  repository and an interactive path answer, so no case exercises it. Its boundary —
  that the skill searches for one name and does not start doing the work — is
  unverified here.
- **The vocabulary.** Cases run against whatever vocabulary the machine happens to
  hold, and none asserts on learning, promotion or eviction. A polluted vocabulary
  would change results without failing a case.
- **The interactive question experience.** Headless runs render questions as text,
  so option quality and selection behaviour are unverified.

## Porting to the first-party harness

`claude plugin eval` is the first-party runner and should replace this one once
available — it is gated behind early access and was not enabled when this was
written. Cases here are deliberately plain input plus declared expectations, so
porting is a translation of `expect.json` into that harness's grader format.
