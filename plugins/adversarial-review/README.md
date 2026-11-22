# adversarial-review

## Overview

Send plans, designs, and working documents to Grok (`grok.com`) for adversarial
feedback via Playwright browser automation. The loop snapshots the document,
scans the snapshot for secrets, asks for confirmation, navigates to Grok,
confirms the signed-in account, creates or finds the matching project, uploads
the snapshot, submits a structured review prompt, extracts findings with
severity tags and self-improvement notes, and integrates approved suggestions
back into the source file.

An upload cannot be recalled, so the skill asks before it sends anything:

- **Before opening Grok:** the file, the sha256 and size of its snapshot, and
  the intended project. With no user to answer — a headless, scheduled, or
  delegated run — it stops here.
- **Once the site is open:** the account actually signed in and the project,
  before a project is created or content is sent.
- **After edits:** the edited document is new content. It is snapshotted,
  scanned and confirmed again before the re-upload.
- **Inline fallback:** if Grok cannot read the uploaded file, pasting the
  content into the chat needs its own explicit answer.

What is scanned, approved and uploaded is one read-only copy in a private
temporary directory. If the source is saved after the scan, the upload is
refused and the cycle starts again. The skill does not pre-approve the
Playwright upload tool, so the session's own permission rules apply to each
upload as well.

Use this for a cross-model second opinion on a plan or design. Use Claude
Code's built-in `/code-review` for a Claude-on-Claude diff review — that path
does not need a browser.

Review prompt variants: Standard, Architecture, Implementation, Security,
UX/Product. Auto-apply is conservative by default (Minor and Nit); pass
`--aggressive` to also auto-apply Major. Critical findings always wait for
confirmation. In either mode the original is copied to
`{filename}.pre-review.md` before the first edit, and no edit is made if that
backup cannot be written.

## Install

Add this marketplace if it is not already configured, then install the plugin
inside Claude Code:

```
/plugin marketplace add brightops-ai/brightopsai-plugins-official
/plugin install adversarial-review@brightopsai-plugins-official
```

This plugin declares a dependency on Playwright from `claude-plugins-official`.
Claude Code auto-installs that dependency only when the official marketplace is
already configured (the default) and this marketplace allowlists it. If
auto-install is skipped or fails — Claude Code will not pull a plugin from
another marketplace otherwise — install Playwright **first**, then
`/reload-plugins` or restart:

```
/plugin install playwright@claude-plugins-official
```

## Skills

| Invoke | What it does |
|--------|----------------|
| `/adversarial-review:adversarial-review` | Upload a document to Grok, run the review, and apply approved edits. |

The skill is model-invocable, on requests for a Grok review or an adversarial
review that names no other reviewer; a general request for critique, or a
review by another model or a local reviewer, does not invoke it. Pass a path to the
document, and optionally `--aggressive`.

## Prerequisites

- The Playwright plugin from `claude-plugins-official`, installed **before**
  this plugin's browser loop can run. If the Playwright tools are missing in
  the session, stop and install as above rather than retrying the loop.
- A grok.com account, logged in manually in the Playwright browser when a login
  wall appears
- `gitleaks` on `PATH` is preferred for the pre-upload secret scan. Without it,
  a bundled high-confidence fallback runs and prints a `FALLBACK` line
- `sha256sum` or `shasum` for the snapshot hash; `python3` is used when neither
  is present

## Data

This plugin does not write under `${CLAUDE_PLUGIN_DATA}`. The review happens in
the Grok project in the browser; approved edits go back into the source file in
the workspace. The secret scanner is run-only and stores nothing. Snapshots
live in a private directory under the system temporary directory and are
removed at the end of a run.

## Update

`/plugin update` reads the version from this plugin's `plugin.json`. A file-only
edit with no version bump is not picked up — the plugin cache is version-keyed.
See [CHANGELOG.md](CHANGELOG.md).

## Uninstall

Uninstalling this plugin from every scope removes `${CLAUDE_PLUGIN_DATA}`. This
plugin does not store anything there. Grok projects and source-file edits are
not deleted by uninstalling.
