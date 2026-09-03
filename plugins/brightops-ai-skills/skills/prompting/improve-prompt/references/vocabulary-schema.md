# The local vocabulary

A record of how one person phrases things, so the skill asks fewer questions the
longer it is used. It is deliberately slow to learn, because a wrong entry becomes a
permanent lens that distorts every later brief without ever announcing itself.

## Where it lives

`${CLAUDE_PLUGIN_DATA}/vocabulary.md`, seeded from `vocabulary.seed.md` on first
run. Never write it inside the plugin directory: installed plugins live in a
version-keyed cache, so anything stored there is orphaned by the next update.

`${CLAUDE_PLUGIN_DATA}` is removed when the plugin is uninstalled from every scope,
which is why `--export` exists. Mention that once, on the first write, and never
again.

## What may be stored

Conventions of expression only — how this person says things.

Never store what they were working on. No task content, no code, no file contents,
no error text, no credentials, no customer or personal data. A term entry records
that a phrase maps to a name; it does not record the project that name belongs to
in any more detail than the phrase itself already carries. If an entry would only
make sense to someone who had read the task, it does not belong here.

## Shape

Markdown, fixed headings, one entry per line, every entry dated and sourced.

```
# Vocabulary
<!-- schema: 1 -->

## Profile
- updated: YYYY-MM-DD
- runs: N
- dictation tool: <name, or unknown>

## Terms
| Phrase | Means | Since | Source |

## Transcription slips
| Heard | Actual | Since | Source |

## Idioms
| Phrase | Reading | Since | Source |

## Speaking style
- <observation>

## Typing style
- <observation>

## Standing preferences
- <preference>

## Candidates
| Entry | Kind | Sightings | First seen |
```

`Source` is one of `answer` (a clarifying question was answered), `correction` (the
author corrected the output), or `promoted` (reached its sighting threshold).

## What may take effect

Only confirmed entries influence a brief. An entry becomes confirmed when one of
these happens:

1. **A clarifying question is answered.** The answer is confirmation — the author
   said it in as many words.
2. **The author corrects the output.** The correction is confirmation.
3. **A candidate reaches its sighting threshold.**

Anything else is an observation, and observations go to `Candidates` with a sighting
count. A candidate influences nothing. This is the safety valve: it makes learning
slow enough to be right.

## Promotion thresholds

| Kind | Sightings | Why |
|---|---|---|
| Speaking style, typing style, idiom | 2 | A wrong style entry produces slightly awkward phrasing, which is cheap and visible |
| Term meaning, transcription slip | 3 | A wrong term silently rewrites what the brief asks for, which is neither |

Increment a candidate's count when the same pattern appears again in a later run.
Never increment twice from one input.

## Precedent

The current input always wins. Where the input contradicts a stored entry — the
phrase is used differently, or the author spells out something the vocabulary maps
elsewhere — follow the input, and demote the contradicted entry back to a candidate
with its count reset. An entry that has started to go wrong should stop influencing
briefs immediately, not after it has been wrong three more times.

## Size

Cap at 150 entries. At the cap, evict least-recently-used candidates first, then
least-recently-used confirmed entries, and say so in the footer. A vocabulary that
grows without bound eventually costs more context than the questions it saves.

## Using it

Consult the vocabulary while classifying gaps, before deciding anything is blocking.
A stored term that resolves a referent turns a blocking gap into a recoverable one:
resolve it, do not ask, and record it under **What I assumed** marked as coming from
the vocabulary, so a stale entry is visible and correctable rather than silent.

## Reporting

Every run that writes reports it in a single closing line, naming what changed:

```
Learned: 1 term (confirmed), 1 candidate (2/3 sightings).
```

Never write silently. A vocabulary that changes without saying so is one the author
cannot audit, and the whole design depends on it being auditable.

## Operations

| Argument | Effect |
|---|---|
| `--vocab` | Print the vocabulary and exit, changing nothing |
| `--forget <phrase>` | Remove the matching entry or candidate, report what went |
| `--export <path>` | Write a copy to a durable location outside the plugin data directory |

None of these produce a brief.
