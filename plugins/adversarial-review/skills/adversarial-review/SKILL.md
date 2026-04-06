---
name: adversarial-review
description: >
  This skill should be used when the user asks to "get an adversarial review",
  "have Grok review this", "stress-test this plan", "get a second opinion on
  this design", "adversarial feedback", "red team this document", "devil's
  advocate review", "challenge this plan", "poke holes in this", "critique this
  plan", "tear this apart", "find the flaws", or "what's wrong with this plan".
  Also trigger when the user mentions "cross-model review", "external review
  of plan", or wants an LLM-vs-LLM review of architecture, implementation plans,
  checklists, or working documents. Supports conservative and aggressive
  auto-apply modes for integrating feedback.
argument-hint: "[path to plan or document] [--aggressive]"
allowed-tools:
  - mcp__plugin_playwright_playwright__browser_navigate
  - mcp__plugin_playwright_playwright__browser_snapshot
  - mcp__plugin_playwright_playwright__browser_click
  - mcp__plugin_playwright_playwright__browser_type
  - mcp__plugin_playwright_playwright__browser_wait_for
  - mcp__plugin_playwright_playwright__browser_press_key
  - mcp__plugin_playwright_playwright__browser_hover
  - mcp__plugin_playwright_playwright__browser_take_screenshot
  - mcp__plugin_playwright_playwright__browser_evaluate
  - mcp__plugin_playwright_playwright__browser_select_option
  - mcp__plugin_playwright_playwright__browser_run_code
  - mcp__plugin_playwright_playwright__browser_tabs
  - mcp__plugin_playwright_playwright__browser_file_upload
  - AskUserQuestion
  - Read
  - Write
  - Edit
  - Bash
  - Glob
  - Grep
---

# Adversarial Review

Send plans, designs, and working documents to Grok (grok.com) for critical adversarial feedback. Automate the full loop: navigate to Grok, match or create the project, upload the document, submit a structured review prompt, extract findings, and integrate approved suggestions back into the source file.

## References

- **`references/grok-ui-navigation.md`** — Playwright selectors, URL patterns, chunked typing strategy, and response detection for Grok's UI
- **`references/adversarial-prompt-templates.md`** — Review prompt templates (standard, architecture, implementation, security) with selection logic
- **`references/feedback-integration.md`** — Severity-to-action mapping, conflict resolution rules, and document style preservation

## Workflow

### 1. Identify the Document

Read the file path from the skill argument. If no path provided, ask the user via AskUserQuestion. Read the file content with the Read tool. Determine the project name:

```bash
basename $(git rev-parse --show-toplevel)
```

If not in a git repo, use the current directory name.

### 2. Parse Flags

Check the argument for `--aggressive`. This controls auto-apply behavior:

| Mode | Auto-apply | Propose to user | Always ask |
|------|-----------|----------------|------------|
| **Conservative** (default) | Minor, Nit | Major | Critical |
| **Aggressive** (`--aggressive`) | Minor, Nit, Major | Critical | — |

Critical severity items always require user confirmation regardless of mode.

### 3. Scan for Secrets

Before submitting any content to Grok, scan the document for secrets:

- API keys (`sk-`, `api_key`, `bearer`, `token`)
- Passwords (`password=`, `passwd`, `secret`)
- Connection strings, private keys, credentials

If detected, warn the user and offer to redact before proceeding. Never paste secrets into Grok.

### 4. Verify Grok Login

Navigate to `https://grok.com` using `browser_navigate`. Take a `browser_snapshot`. If a login wall or auth prompt is detected, inform the user:

> "Grok requires login. Please log in to grok.com in the Playwright browser window, then confirm here when ready."

Wait for confirmation via AskUserQuestion before proceeding.

### 5. Navigate to Grok Projects and Upload Document

Consult `references/grok-ui-navigation.md` for detailed selectors and navigation steps.

1. Locate the Projects section in Grok's sidebar — it appears as an expandable section with existing projects listed
2. Search for a project matching the repo/directory name
3. If found — open it, then update the project source file (see step 5b)
4. If not found — create a new project with that name, uploading the document as a source during creation (see `references/grok-ui-navigation.md` for the 3-step dialog flow)

**5b. Keep project sources current:**
- When an existing project is opened, check if the document file is already a project source
- If the file exists but is outdated (local edits since last upload), delete the old version from project sources and re-upload the current file
- If the file does not exist, upload it via the project sources panel
- This ensures Grok always reviews the latest version of the document

### 6. Compose and Submit the Review Prompt

Consult `references/adversarial-prompt-templates.md` to select the appropriate template. Read the document and reason about which variant fits best:

- Describes how components interact → **Architecture** variant
- Step-by-step plan with milestones → **Implementation** variant
- Focused on threats, auth, data protection → **Security** variant
- About user experience, mobile, accessibility, visual design → **UX/Product** variant
- None of the above → **Standard** variant

If the user specifies a variant, use it regardless of auto-detection. Briefly note which variant was selected and why.

The prompt has three parts:

1. **Context block** — Project name, document type, the uploaded filename (e.g., "Review the attached document (my-plan.md)"), and any constraints the user mentioned
2. **Document content** — Do NOT inline the full markdown. Instead, reference the uploaded project source file by name. Grok has access to project source files and will read them directly. This keeps the prompt concise and avoids input-length issues.
3. **Review instructions** — The adversarial review template with required output format

Use `browser_evaluate` to set the prompt text in the contenteditable input (Grok uses a contenteditable div, not a textarea). Regular `browser_type` works for short text but `browser_evaluate` is more reliable for prompts over a few hundred characters. See `references/grok-ui-navigation.md` for the exact JavaScript pattern.

After setting the text, click the Submit button (find it via `browser_evaluate` using `ariaLabel === 'Submit'`).

### 7. Wait for Response

Grok streams responses which can take 30-60+ seconds for detailed reviews. Use a polling approach:

1. Wait 15 seconds initially with `browser_wait_for` (time)
2. Use `browser_evaluate` to measure the response text length (query `.prose` or `.markdown` elements)
3. Wait another 15 seconds, then measure again
4. **Response is complete when text length stabilizes** — same length across two consecutive checks 5+ seconds apart

Do NOT rely solely on the Submit button's disabled/enabled state — it can remain disabled after generation completes. Text length stabilization is the most reliable signal.

On timeout (120 seconds total), take a `browser_take_screenshot`, report the state to the user, and offer to retry.

### 8. Handle Multi-Turn Conversation

If Grok's response is truncated (ends mid-sentence or says "continued..."):
- Type "Please continue" and wait again

If Grok asks a clarifying question:
- Extract the question text
- Relay it to the user via AskUserQuestion
- Type the user's answer back to Grok
- Wait for the next response

Cap at 3 follow-up turns to prevent infinite loops.

### 9. Extract Feedback

Use `browser_evaluate` to extract the response. Grok's page contains multiple `.prose` / `.markdown` elements — the user's message and the assistant's response are separate elements. To identify the correct one:

1. Query all `.prose, .markdown` elements
2. Enumerate them with their text length and first 80 characters
3. The assistant response is typically the largest element whose text does NOT start with the prompt content
4. It often begins with "Thought for Xs" followed by the actual findings
5. Save the extracted text to a temporary file via the `filename` parameter on `browser_evaluate`, then read it

Grok outputs findings as JSON first, then markdown. Prefer parsing the JSON array for structured data. Each finding has:
- `id` — finding number
- `severity` — Critical / Major / Minor / Nit
- `title` — short description
- `rationale` — explaining the concern
- `suggestion` — concrete fix
- `self_improvement` — Grok's self-critique of its own finding (how it could be sharper or more specific)

Use the self-improvement notes to gauge finding quality — if Grok flags its own finding as vague, weigh it lower during triage.

### 10. Triage and Apply Suggestions

Create a backup of the original document at `{filename}.pre-review.md` before making any edits.

For each finding, classify per the mode table in Step 2:

- **Auto-apply**: Make the edit directly using the Edit tool. One suggestion per edit for clean diffs.
- **Propose to user**: Present the finding with Grok's rationale via AskUserQuestion. Apply only if approved.
- **Log only**: Suggestions that are out of scope or where Claude disagrees with Grok. Include in the summary but do not apply.

After all edits, re-read the file and do a coherence pass to ensure integrated changes read naturally and don't conflict with each other.

### 11. Sync Updated Document to Grok

After applying edits locally, update the project source in Grok so it always has the latest version:

1. Navigate back to the project in Grok (use the sidebar project link)
2. Open the project sources/files panel
3. Delete the old version of the document file
4. Upload the updated local file via the Attach → "Upload a file" flow (see `references/grok-ui-navigation.md`)
5. Verify the new file appears with the correct name

This ensures future reviews in the same project reference the post-review version, not the original.

### 12. Summary Report

Output a structured summary:

```
## Adversarial Review Summary

**Source:** [filename]
**Reviewer:** Grok (grok.com)
**Mode:** Conservative | Aggressive
**Project:** [project name]

### Findings by Severity
- Critical: N
- Major: N
- Minor: N
- Nit: N

### Changes Applied
- [list with line references]

### Changes Proposed (Declined)
- [list with rationale for declining]

### Logged for Reference
- [interesting but out-of-scope findings]

### Open Questions
- [any unresolved items from the review]
```

## Guardrails

- Never auto-apply Critical severity without user confirmation, even in aggressive mode
- Always create a backup before the first edit
- Wait 2-3 seconds between Playwright actions to avoid overwhelming the UI
- If the document exceeds 15,000 characters, split into logical sections and review each separately, then perform a holistic review of the full document
- If Grok is unresponsive for 120 seconds, take a screenshot, report to user, and offer to retry
- Preserve the original document's voice and style when integrating suggestions — see `references/feedback-integration.md`
- Do not submit credentials, API keys, tokens, or passwords to Grok under any circumstances
