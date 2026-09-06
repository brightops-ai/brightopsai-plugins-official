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
| **[1password](plugins/1password)** | 1.2.2 | Use the 1Password CLI (`op`) to read, inject, and manage secrets mid-session. Covers authentication, retrieval, injection, storage, and SSH keys via the 1Password SSH agent. |
| **[agent-teams](plugins/agent-teams)** | 1.2.3 | Deprecated; a replacement skill will be published separately. Orchestrate multi-agent Claude Code teams for parallel research, review, debugging, and feature development. |
| **[marketplace-scout](plugins/marketplace-scout)** | 1.2.0 | Search Facebook Marketplace for products, analyze listings with market research, grade them A+ through F, save to CSV, and serve an interactive dashboard. Supports deal-finding and resale arbitrage. |
| **[adversarial-review](plugins/adversarial-review)** | 1.4.0 | Use Grok (`grok.com`) as an adversarial reviewer to stress-test plans, designs, and working documents via Playwright browser automation. |
| **[brightops-ai-skills](plugins/brightops-ai-skills)** | 1.3.2 | BrightOps AI workflow skills for Claude Code: prompt shaping from rough input, scheduled memory consolidation over past sessions, and spawning verified Claude Code sessions with a starter brief. |

Install commands, namespaced invoke names, prerequisites, data directories, and
uninstall behaviour are in each plugin's `README.md` (linked under Plugin
Details).

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

`marketplace-scout` and `adversarial-review` need the Playwright plugin from
`claude-plugins-official` before their browser loops can run. Claude Code
auto-installs that dependency only when the official marketplace is already
configured (the default) and this marketplace allowlists it. If auto-install
is skipped or fails — Claude Code will not pull a plugin from another
marketplace otherwise — install Playwright first, then `/reload-plugins` or
restart:

```
/plugin install playwright@claude-plugins-official
```

## Plugin Details

### 1password

Two skills for managing secrets and SSH keys through the 1Password CLI (`op`).
See [plugins/1password/README.md](plugins/1password/README.md).

### agent-teams

**Deprecated** — will be removed in a later release; a replacement skill will be published separately.
One skill for orchestrating parallel Claude Code teams (Claude Code v2.1.178+).
See [plugins/agent-teams/README.md](plugins/agent-teams/README.md).

### marketplace-scout

Search Facebook Marketplace, grade listings, and browse them on a local
dashboard. Needs Playwright — install order is under Installation above.
See [plugins/marketplace-scout/README.md](plugins/marketplace-scout/README.md).

### adversarial-review

Cross-model adversarial review of plans and designs via Grok in the browser.
Needs Playwright — install order is under Installation above.
See [plugins/adversarial-review/README.md](plugins/adversarial-review/README.md).

### brightops-ai-skills

Workflow skills in one plugin: prompt shaping, memory consolidation, and
verified session spawn. Invoke by namespaced name, for example
`/brightops-ai-skills:improve-prompt`. Dream scheduling needs Claude Code
v2.1.196+. See [plugins/brightops-ai-skills/README.md](plugins/brightops-ai-skills/README.md).

## Contributing

Human checklist (skill vs plugin, `skills` array, version pin, tests, packaging
gates): [CONTRIBUTING.md](CONTRIBUTING.md).

Agent conventions (description shape, `dream` scheduling exception, word cap,
`${CLAUDE_PLUGIN_DATA}`): [CLAUDE.md](CLAUDE.md).

## License

This project is licensed under the [MIT License](LICENSE).
See [SECURITY.md](SECURITY.md) for vulnerability reporting, secret handling, and plugin data directories.

---

<p align="center">
  Built by <a href="https://brightopsinc.ai/">BrightOps AI</a>
</p>
