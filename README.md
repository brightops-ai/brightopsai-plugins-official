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
| **[brightops-ai-skills](plugins/brightops-ai-skills)** | 1.1.0 | BrightOps AI workflow skills, packaged as one installable set: prompt shaping from rough input, and scheduled memory consolidation over past sessions. |

## Installation

1. Clone this repository:
   ```bash
   git clone https://github.com/brightops-ai/brightopsai-plugins-official.git
   ```

2. Add the marketplace to Claude Code:
   ```
   /plugin → Marketplaces → Add → directory → <path-to-cloned-repo>
   ```

3. Install plugins via `/plugin → Discover`.

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

- **improve-prompt** — Turn rough input, dictated through speech-to-text or typed in a hurry, into a task brief another agentic coding session can act on. Cleans transcription artifacts without altering meaning, reproduces identifiers and quoted values exactly, and returns a harness-agnostic brief covering objective, context, scope, constraints and verifiable completion criteria. Output is text to copy; the skill never runs the prompt it writes. User-invoked only.
- **dream** — Consolidate what recent sessions revealed into the memory that loads next time. Runs as two modes a day apart: `full-analysis` mines session transcripts, repairs the memory defects that are mechanically certain, and writes an overview splitting applied changes from proposals awaiting sign-off; `apply-fixes` applies only the proposals that were ticked. Snapshots memory before every change. Model-invocable so a scheduled routine can fire it.
- **improve-memory** — Audit a project's auto memory for the defects that fail silently — an index past its 200-line load limit, entries pointing at deleted files, memory files no index reaches, missing or invalid type frontmatter, stale entries — repair what is certain, and propose what needs a decision. User-invoked only.
- **session-analysis** — Distil raw session transcripts into candidate episodes (interruptions, repeated tool failures, permission denials, terse turns after an edit) and analyse them for a chosen purpose. The bundled script finds structure and never decides meaning; clustering happens by what was corrected, not by how it was phrased. Runs forked. User-invoked only.
- **send-result** — Deliver a run summary to a configured destination: a file by default, or a command you configure. Never infers a destination, and never silently substitutes one. Usable by any automation. User-invoked only.

## Contributing

To add a new plugin:

1. Create `plugins/<name>/.claude-plugin/plugin.json` with name, version, description, and author
2. Create `plugins/<name>/skills/<skill>/SKILL.md` with YAML frontmatter
3. Add optional `references/` for detailed documentation
4. Register in `.claude-plugin/marketplace.json`

See [CLAUDE.md](CLAUDE.md) for conventions and structure details.

## License

This project is licensed under the [MIT License](LICENSE).

---

<p align="center">
  Built by <a href="https://brightopsinc.ai/">BrightOps AI</a>
</p>
