# Feedback Integration Rules

How to triage, classify, and merge Grok's adversarial feedback back into the source document.

## Severity-to-Action Mapping

### Conservative Mode (Default)

| Severity | Action | Rationale |
|----------|--------|-----------|
| **Critical** | Propose to user | High-impact changes need explicit approval |
| **Major** | Propose to user | Significant scope or direction changes require discussion |
| **Minor** | Auto-apply | Small, unambiguous improvements (add a note, clarify wording, mention an edge case) |
| **Nit** | Auto-apply | Typos, formatting, word choice — low risk, high clarity value |

### Aggressive Mode (`--aggressive`)

| Severity | Action | Rationale |
|----------|--------|-----------|
| **Critical** | Propose to user | Always requires human judgment, even in aggressive mode |
| **Major** | Auto-apply | User opted in to faster iteration; Major items are applied directly |
| **Minor** | Auto-apply | Same as conservative |
| **Nit** | Auto-apply | Same as conservative |

## Auto-Apply Rules

When auto-applying a suggestion:

1. Use the Edit tool with the smallest possible `old_string` that uniquely identifies the target
2. Make one edit per finding — do not batch multiple findings into one edit
3. Preserve the document's existing formatting (heading levels, list styles, indentation)
4. If the suggestion requires adding a new section, place it in the most logical location relative to existing content
5. If the suggestion requires removing content, comment on why in the summary report rather than leaving a note in the document

## Proposing Changes to the User

When presenting a finding for user approval via AskUserQuestion:

- Quote Grok's exact rationale
- Show what would change (before/after if concise, or a description if the change is structural)
- Offer clear options: "Apply this suggestion", "Skip this suggestion", "Modify and apply"
- If the user chooses "Modify and apply", ask them what they'd like changed

## Handling Conflicts

When Grok's suggestion conflicts with the document's intent:

1. **Grok misunderstands a deliberate choice** — Log the finding as "Acknowledged — deliberate design decision" and do not apply. Mention it in the summary under "Logged for Reference" with a brief note on why.

2. **Grok identifies a real issue but the suggestion is wrong** — Propose to the user with both the problem (valid) and the suggestion (questionable). Let the user decide on the fix.

3. **Grok suggests something Claude already considered** — If Claude has context showing the suggestion was already evaluated and rejected, log it. If unsure, propose to the user.

## Preserving Document Voice

When editing the document:

- Match the existing heading style (ATX `#` vs Setext underlines)
- Match bullet style (`-` vs `*` vs `+`)
- Match sentence structure and tone (technical vs conversational, terse vs detailed)
- Do not introduce formatting patterns not already present in the document
- Do not add emoji, bold emphasis, or callout boxes unless the document already uses them

## Coherence Pass

After all edits are applied:

1. Re-read the full document
2. Check for contradictions introduced by applying multiple suggestions
3. Check for redundancy (two sections now saying the same thing)
4. Check for broken references (a section was renamed or moved)
5. Fix any issues found during this pass
6. Keep edits minimal — only fix what the integration broke

## Backup and Recovery

- Before the first edit, copy the original to `{filename}.pre-review.md`
- If the user is unhappy with the result, they can restore from the backup
- After the user confirms they're satisfied, suggest deleting the backup to keep the workspace clean

## Syncing Changes Back to Grok

After applying edits locally, the Grok project source file is stale. See SKILL.md Step 11 for the full sync workflow (delete old file from project sources, re-upload updated version, verify). This is especially important when a project accumulates multiple review cycles.
