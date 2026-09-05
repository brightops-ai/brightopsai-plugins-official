<p align="center">
  <img src="https://brightopsinc.ai/logo-bulb-sm.png" alt="BrightOps AI" width="80" />
</p>

<h1 align="center">BrightOps AI Plugins</h1>

<p align="center">
  Official plugin marketplace for <a href="https://claude.ai/code">Claude Code</a> by <a href="https://brightopsinc.ai/">BrightOps AI</a>.
</p>

<p align="center">
  <em>Intelligent software. Total data ownership.</em>
</p>

---

## Plugins

| Plugin | Version | Description |
|--------|---------|-------------|
| **[1password](plugins/1password)** | 1.2.0 | Use the 1Password CLI (`op`) to read, inject, and manage secrets mid-session. Includes SSH key management via the 1Password SSH agent. |
| **[agent-teams](plugins/agent-teams)** | 1.2.0 | Orchestrate multi-agent Claude Code teams for parallel research, review, debugging, and feature development. |
| **[marketplace-scout](plugins/marketplace-scout)** | 1.1.0 | Search Facebook Marketplace for deals, grade listings A+ through F with market research, and serve an interactive dashboard. |
| **[adversarial-review](plugins/adversarial-review)** | 1.3.0 | Use Grok as an adversarial reviewer to stress-test plans, designs, and working documents via browser automation. |
| **[brightops-ai-skills](plugins/brightops-ai-skills)** | 1.3.1 | BrightOps AI workflow skills, packaged as one installable set: prompt shaping from rough input, scheduled memory consolidation over past sessions, and spawning verified Claude Code sessions with a starter brief. |

## Installation

Add the marketplace, then install the plugins you want — inside Claude Code:

```
/plugin marketplace add brightops-ai/brightopsai-plugins-official
/plugin install brightops-ai-skills@brightopsai-plugins-official
```

or from a shell:

```bash
claude plugin marketplace add brightops-ai/brightopsai-plugins-official
claude plugin install brightops-ai-skills@brightopsai-plugins-official
```

`/plugin → Discover` lists everything the marketplace offers. To work on the plugins
themselves, clone the repository and add the checkout as a directory marketplace
instead: `/plugin marketplace add <path-to-clone>`.

## Plugin Details

### 1password

Two skills for managing secrets and SSH keys through 1Password CLI:

- **1password** — Read, inject, store, and rotate secrets mid-session using `op`. Supports persistent auth via tmux, environment variable injection, and config template rendering.
- **ssh-keys** — Create and manage SSH keys stored exclusively in 1Password. Covers key creation, remote server setup, GitHub integration, and git commit signing — all backed by biometric approval (Touch ID).

### agent-teams

One skill for orchestrating parallel Claude Code teams:

- **agent-teams** — Guides team creation, task decomposition, file ownership partitioning, and inter-agent coordination. Includes ready-to-use templates for parallel code review, competing debug hypotheses, cross-layer feature development, and large-scale refactoring.

### marketplace-scout

One skill for finding deals on Facebook Marketplace:

- **marketplace-scout** — Search Facebook Marketplace via Playwright browser automation, grade listings A+ through F using market price research, save results to CSV, and launch an interactive Vite + React dashboard for browsing, filtering, and identifying resale arbitrage opportunities.

### adversarial-review

One skill for cross-model adversarial reviews:

- **adversarial-review** — Send plans, designs, and working documents to Grok (grok.com) for adversarial feedback via Playwright browser automation. Navigates to Grok, creates or finds the matching project, uploads the document, submits a structured review prompt (with 5 template variants: Standard, Architecture, Implementation, Security, UX/Product), extracts findings with severity tags and self-improvement notes, and integrates approved suggestions back into the source file. Supports conservative (default) and aggressive auto-apply modes.

### brightops-ai-skills

The home for BrightOps AI workflow skills — one plugin holding many skills, rather than a plugin per skill. Skills are grouped into category subdirectories and listed explicitly in the plugin manifest.

Invoke a skill by its namespaced name, for example `/brightops-ai-skills:improve-prompt`. All
are user-invoked except `dream`, which stays model-invocable so a scheduled routine can fire it.

- **improve-prompt** — Turn rough input, dictated through speech-to-text or typed in a hurry, into a task brief another agentic coding session can act on. Cleans transcription artifacts without altering meaning, reproduces identifiers and quoted values exactly, and returns a harness-agnostic brief covering objective, context, scope, constraints and verifiable completion criteria. Output is text to copy; the skill never runs the prompt it writes. User-invoked only.
- **calibrate-style** — Optional setup for `improve-prompt`. Collects a handful of dictated and typed samples, derives speaking and typing style, transcription slips, shorthand and standing preferences, shows everything for review before writing, and seeds the vocabulary so the improver asks fewer questions from the start. User-invoked only.
- **dream** — Consolidate what recent sessions revealed into the memory that loads next time. Runs as two modes a day apart: `full-analysis` mines session transcripts, repairs the memory defects that are mechanically certain, and writes an overview splitting applied changes from proposals awaiting sign-off; `apply-fixes` applies only the proposals that were ticked. Snapshots memory before every change. Model-invocable so a scheduled routine can fire it.
- **improve-memory** — Audit a project's auto memory for the defects that fail silently — an index past its 200-line load limit, entries pointing at deleted files, memory files no index reaches, missing or invalid type frontmatter, stale entries — repair what is certain, and propose what needs a decision. User-invoked only.
- **session-analysis** — Distil raw session transcripts into candidate episodes (interruptions, repeated tool failures, permission denials, terse turns after an edit) and analyse them for a chosen purpose. The bundled script finds structure and never decides meaning; clustering happens by what was corrected, not by how it was phrased. Runs forked. User-invoked only.
- **send-result** — Deliver a run summary to a configured destination: a file by default, or a command you configure. Never infers a destination, and never silently substitutes one. Usable by any automation. User-invoked only.
- **spawn-session** — Start a named Claude Code session in tmux with remote control enabled, in a chosen directory and permission posture, then hand it a starter brief. Confirms the session is the one that was launched — by a token it must echo back through its own transcript, not by reading the terminal — and refuses to deliver the brief if it answers from anywhere else. Multi-line briefs are pasted rather than typed, so they arrive whole. A session held at a startup dialog is diagnosed by name with the setting that resolves it; nothing is ever typed at a prompt. User-invoked only.

## Contributing

**Adding a skill.** Workflow skills go into `brightops-ai-skills`, not a new plugin each. Create
`plugins/brightops-ai-skills/skills/<category>/<skill>/SKILL.md` with YAML frontmatter, add
`references/` for anything long, and **list the path in the plugin manifest's `skills` array**.
Skills in category subdirectories are only discovered when listed — a missing entry installs
cleanly, validates cleanly, and offers nothing, so check the array against the directories
in both directions.

**Adding a plugin** is for a tool integration with heavy external dependencies — a CLI, browser
automation, an MCP server:

1. Create `plugins/<name>/.claude-plugin/plugin.json` with name, version, description, and author
2. Create `plugins/<name>/skills/<skill>/SKILL.md` with YAML frontmatter
3. Add optional `references/` for detailed documentation
4. Register in `.claude-plugin/marketplace.json`

**Before opening a pull request:**

- Bump the version in **both** `plugin.json` and `marketplace.json`; the plugin cache is
  version-keyed, so an unbumped change is never picked up
- Run `./scripts/install-hooks.sh` once per clone to activate the gitleaks pre-commit gate —
  this repository is public, and git does not clone hooks
- Run `python3 scripts/check-marketplace.py` when the change touches a plugin
  manifest, the marketplace registry, the README plugin table, or adds a skill
- Run the tests: `cd plugins/brightops-ai-skills/lib && python3 -m unittest discover -s dream/tests -t .`
  and `plugins/brightops-ai-skills/tests/run.sh --unit`; run `evals/run.sh` when touching
  `improve-prompt`

See [CLAUDE.md](CLAUDE.md) for conventions and structure details.

## License

This project is licensed under the [MIT License](LICENSE).

---

<p align="center">
  Built by <a href="https://brightopsinc.ai/">BrightOps AI</a>
</p>
