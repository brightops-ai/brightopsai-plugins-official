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
| **[agent-teams](plugins/agent-teams)** | 1.2.2 | Orchestrate multi-agent Claude Code teams for parallel research, review, debugging, and feature development. Guides team creation, task decomposition, and coordination. |
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

**Adding a skill.** Workflow skills go into `brightops-ai-skills`, not a new plugin each. Create
`plugins/brightops-ai-skills/skills/<category>/<skill>/SKILL.md` with YAML frontmatter, add
`references/` for anything long, and **list the path in the plugin manifest's `skills` array**.
Skills in category subdirectories are only discovered when listed — a missing entry installs
cleanly, validates cleanly, and offers nothing (verified 2026-09-05 on Claude Code 2.1.261), so
check the array against the directories in both directions.

**Adding a plugin** is for a tool integration with heavy external dependencies — a CLI, browser
automation, an MCP server:

1. Create `plugins/<name>/.claude-plugin/plugin.json` with name, version, description, and author
2. Create `plugins/<name>/skills/<skill>/SKILL.md` with YAML frontmatter
3. Add optional `references/` for detailed documentation
4. Add `plugins/<name>/README.md` (Overview, Install, Skills, Prerequisites, Data, Update, Uninstall)
5. Register in `.claude-plugin/marketplace.json`

**Before opening a pull request:**

- Bump the version in `plugin.json` only — that pin is what `/plugin update` reads —
  and add a plugin `CHANGELOG.md` entry in the same change (marketplace-level
  changes go in the root `CHANGELOG.md`). The README plugin table is a checked
  mirror of it; do not put `version` on the marketplace entry. The plugin cache
  is version-keyed, so an unbumped change is never picked up
- Run `./scripts/install-hooks.sh` once per clone to activate the gitleaks pre-commit gate —
  this repository is public, and git does not clone hooks
- Run `python3 scripts/check-marketplace.py` when the change touches a plugin
  manifest, the marketplace registry, the README plugin table, a plugin
  `README.md`, or adds a skill
- Run the tests: `cd plugins/brightops-ai-skills/lib && python3 -m unittest discover -s dream/tests -t .`
  and `plugins/brightops-ai-skills/tests/run.sh --unit`; run `evals/run.sh` when touching
  `improve-prompt`

See [CLAUDE.md](CLAUDE.md) for conventions and structure details.

## License

This project is licensed under the [MIT License](LICENSE).
See [SECURITY.md](SECURITY.md) for vulnerability reporting, secret handling, and plugin data directories.

---

<p align="center">
  Built by <a href="https://brightopsinc.ai/">BrightOps AI</a>
</p>
