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

## When to Use This vs. `/code-review`

Use this skill for cross-model review of plans, designs, and documents — it sends content to Grok, a different model, to get an independent second opinion. Use the built-in `/code-review` skill instead when reviewing a code diff with Claude itself; that skill doesn't require browser automation or leaving Claude Code.

## References

- **`references/grok-ui-navigation.md`** — Playwright selectors, URL patterns, chunked typing strategy, and response detection for Grok's UI
- **`references/adversarial-prompt-templates.md`** — Review prompt templates (standard, architecture, implementation, security) with selection logic
- **`references/feedback-integration.md`** — Severity-to-action mapping, conflict resolution rules, and document style preservation

## Workflow

### Prerequisites

Confirm the Playwright browser tools (`browser_navigate` and the rest of the `mcp__plugin_playwright_playwright__browser_*` set) are available in this session. If they are missing, stop: tell the user to run `/plugin install playwright@claude-plugins-official`, then `/reload-plugins` or restart, and invoke this skill again. Do not retry the browser loop without those tools.

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

Before any upload to Grok, scan the document with the bundled scanner — never a prose regex list:

```bash
"${CLAUDE_PLUGIN_ROOT}/skills/adversarial-review/scripts/scan-secrets.sh" "<document>"
```

The script prefers `gitleaks` when it is on PATH. If the file sits in a git work tree (`git -C <dir> rev-parse --show-toplevel`) that has a `.gitleaks.toml` at the repo root, that config is passed through; otherwise gitleaks defaults apply. If gitleaks is absent, a bundled high-confidence fallback runs and prints a `FALLBACK` line recommending gitleaks.

Exit codes:

- **0** — clean. Continue.
- **1** — hit(s). Stop. Show the `rule:` / `file:` / `line:` lines. Offer redaction. Do not open Grok, do not upload, do not paste the document. After edits, run the script again. Repeat until the scan exits 0.
- **2** — usage or scanner error. Stop, report stderr, and do not upload.

A hit blocks the upload. Never proceed to Grok until a rescan exits 0.

### 4. Verify Grok Login

Navigate to `https://grok.com` using `browser_navigate`. Take a `browser_snapshot`. If a login wall or auth prompt is detected, inform the user:

> "Grok requires login. Please log in to grok.com in the Playwright browser window, then confirm here when ready."

Wait for confirmation via AskUserQuestion before proceeding.

### 5. Navigate to Grok Projects and Upload Document

Follow `references/grok-ui-navigation.md` for selectors, the 3-step new-project dialog, Attach → "Upload a file", and how to refresh sources on an existing project.

1. Find or create the Grok project whose name matches the repo/directory from step 1.
2. Upload the document as a project source, or replace a stale copy of the same file so Grok reviews the current version.

Do not upload until step 3 exited 0 on this file.

### 6. Compose and Submit the Review Prompt

Read `references/adversarial-prompt-templates.md` and follow its selection logic and assembly instructions. Variants: Architecture, Implementation, Security, UX/Product, Standard. If the user names a variant, use it. Briefly note which variant was selected and why.

Do not copy template text into the session notes — assemble from that file. Do not inline the document; reference the uploaded filename. Set the prompt and click Submit using the `browser_evaluate` patterns in `references/grok-ui-navigation.md`.

### 7. Wait for Response

Grok streams for 30-60+ seconds. Follow the text-length stabilization procedure in `references/grok-ui-navigation.md`. Do not treat the Submit button's enabled state as completion.

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

Extract the assistant response per `references/grok-ui-navigation.md` (enumerate `.prose` / `.markdown` elements; pick by content, not a hard-coded index; save long text via the `filename` parameter).

Grok outputs findings as JSON first, then markdown. Prefer the JSON array. Each finding has `id`, `severity`, `title`, `rationale`, `suggestion`, and `self_improvement`. Weigh vague findings lower when Grok's self-improvement note says so.

### 10. Triage and Apply Suggestions

Create a backup of the original document at `{filename}.pre-review.md` before making any edits.

For each finding, classify per the mode table in Step 2. Conflict handling, edit size, and voice preservation are in `references/feedback-integration.md`.

- **Auto-apply**: Make the edit directly using the Edit tool. One suggestion per edit for clean diffs.
- **Propose to user**: Present the finding with Grok's rationale via AskUserQuestion. Apply only if approved.
- **Log only**: Suggestions that are out of scope or where Claude disagrees with Grok. Include in the summary but do not apply.

After all edits, re-read the file and do a coherence pass so integrated changes read naturally and do not conflict.

### 11. Sync Updated Document to Grok

After applying edits locally, update the project source in Grok so it always has the latest version. Repeat step 3 on the updated file; do not re-upload until that scan exits 0. Then follow `references/grok-ui-navigation.md` to replace the old project source with the current file and verify the name.

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
- Do not upload until `scan-secrets.sh` exits 0. A scanner hit is a stop, not a warning to click through.
