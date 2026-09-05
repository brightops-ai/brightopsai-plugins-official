# adversarial-review

## Overview

Send plans, designs, and working documents to Grok (`grok.com`) for adversarial
feedback via Playwright browser automation. The loop navigates to Grok, creates
or finds the matching project, uploads the document, submits a structured
review prompt, extracts findings with severity tags and self-improvement notes,
and integrates approved suggestions back into the source file.

Use this for a cross-model second opinion on a plan or design. Use Claude
Code's built-in `/code-review` for a Claude-on-Claude diff review — that path
does not need a browser.

Review prompt variants: Standard, Architecture, Implementation, Security,
UX/Product. Auto-apply is conservative by default (Minor and Nit); pass
`--aggressive` to also auto-apply Major. Critical findings always wait for
confirmation.

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

The skill is model-invocable. Pass a path to the document, and optionally
`--aggressive`.

## Prerequisites

- The Playwright plugin from `claude-plugins-official`, installed **before**
  this plugin's browser loop can run. If the Playwright tools are missing in
  the session, stop and install as above rather than retrying the loop.
- A grok.com account, logged in manually in the Playwright browser when a login
  wall appears
- `gitleaks` on `PATH` is preferred for the pre-upload secret scan. Without it,
  a bundled high-confidence fallback runs and prints a `FALLBACK` line

## Data

This plugin does not write under `${CLAUDE_PLUGIN_DATA}`. The review happens in
the Grok project in the browser; approved edits go back into the source file in
the workspace. The secret scanner is run-only and stores nothing.

## Update

`/plugin update` reads the version from this plugin's `plugin.json`. A file-only
edit with no version bump is not picked up — the plugin cache is version-keyed.
See [CHANGELOG.md](CHANGELOG.md).

## Uninstall

Uninstalling this plugin from every scope removes `${CLAUDE_PLUGIN_DATA}`. This
plugin does not store anything there. Grok projects and source-file edits are
not deleted by uninstalling.
