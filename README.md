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
| **[1password](plugins/1password)** | 1.1.0 | Use the 1Password CLI (`op`) to read, inject, and manage secrets mid-session. Includes SSH key management via the 1Password SSH agent. |
| **[agent-teams](plugins/agent-teams)** | 1.1.0 | Orchestrate multi-agent Claude Code teams for parallel research, review, debugging, and feature development. |
| **[marketplace-scout](plugins/marketplace-scout)** | 1.0.0 | Search Facebook Marketplace for deals, grade listings A+ through F with market research, and serve an interactive dashboard. |
| **[adversarial-review](plugins/adversarial-review)** | 1.2.0 | Use Grok as an adversarial reviewer to stress-test plans, designs, and working documents via browser automation. |

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
