# BrightOps AI Plugins — Claude Code Plugin Marketplace

## Project Structure

`.claude-plugin/marketplace.json` — plugin registry (update when adding/removing plugins)
`plugins/<name>/.claude-plugin/plugin.json` — plugin metadata (name, version, description, author)
`plugins/<name>/skills/<skill>/SKILL.md` — skill definition with YAML frontmatter
`plugins/<name>/skills/<skill>/references/` — supporting docs loaded on demand
`plugins/<name>/skills/<category>/<skill>/SKILL.md` — categorised variant; every such path must be
listed in the plugin manifest's `skills` array. Default discovery only finds top-level `skills/`;
an omitted nested skill installs, validates, and loads with no error (verified 2026-09-05 on Claude
Code 2.1.261). Packaging gates and the
human checklist: [CONTRIBUTING.md](CONTRIBUTING.md).

## Current Plugins

- 1password — 2 skills: 1password, ssh-keys
- agent-teams — 1 skill: agent-teams
- adversarial-review — 1 skill: adversarial-review
- marketplace-scout — 1 skill: marketplace-scout
- brightops-ai-skills — 7 skills: improve-prompt, calibrate-style, dream,
  improve-memory, session-analysis, send-result, spawn-session

## Adding a New Skill

BrightOps AI workflow skills go into the existing `brightops-ai-skills` plugin, not a new plugin
each. Add the skill under a category subdirectory and list its path in the plugin manifest's
`skills` array. A separate plugin is only for a tool integration with heavy external dependencies
— a CLI, browser automation, an MCP server. Steps, tests, and the PR checklist:
[CONTRIBUTING.md](CONTRIBUTING.md).

## Conventions

- SKILL.md frontmatter `description` depends on how the skill is invoked:
  - Model-invocable (no `disable-model-invocation`): third person carrying trigger phrases — "This
    skill should be used when the user asks to..." The trigger list exists to drive model matching.
  - User-invoked (`disable-model-invocation: true`): a single short line. The model cannot invoke
    the skill, so the description is only a picker label and a trigger list is dead weight.
  - **Exception — a skill meant to run on a schedule must not set the flag.**
    `disable-model-invocation` also prevents a scheduled task from firing the skill (Claude Code
    v2.1.196+), so a scheduled routine would fire and do nothing, reporting no error. `dream` is
    the case in this repo: it is person-driven but omits the flag and carries a trigger-phrase
    description deliberately. Do not "correct" it to match the other skills.
- SKILL.md body uses imperative form, not second person
- Keep SKILL.md under ~2,000 words; move detailed content to references/
- No duplication between SKILL.md body and reference files
- `plugin.json` is the sole version pin. Bumping it is what makes `/plugin update`
  see a new release. Land the bump and an entry in `plugins/<name>/CHANGELOG.md` in
  the same change. A marketplace-level change (added or removed plugin, install
  command, shared tooling) gets an entry in the root `CHANGELOG.md`. The README
  plugin table is a checked mirror; marketplace entries omit `version`. Cache
  eviction and the rest of the bump procedure: [CONTRIBUTING.md](CONTRIBUTING.md)

## Testing

Tests must never write into the real `~/.claude`; sandbox `CLAUDE_PLUGIN_DATA`
and pass explicit directories. One test leaked into the real plugin data
directory during development, which is silent and only found by looking.

Commands (dream unittest, bats `--unit` and full, `scripts/tests`, evals as
manual), packaging gates (`python3 scripts/check-marketplace.py`,
`claude plugin validate . --strict`), `/reload-plugins`, and the PR checklist:
[CONTRIBUTING.md](CONTRIBUTING.md). The packaging gate is
`.github/workflows/ci.yml` (pull requests and `main`). Behavioural evals stay
manual.

## Gotchas

- Plugin cache is version-keyed — edits to files without a version bump won't be picked up
- Observed once on Claude Code 2.1.261 (2026-09-05): `claude plugin uninstall` then
  `claude plugin install` of the same plugin in the same config dir (directory marketplace)
  left the plugin listed as installed and enabled with no errors, yet subsequent sessions
  loaded no plugin until a fresh config dir was used. Cause not established; try a fresh
  config/cache before debugging the manifest.
- Never store user data inside a plugin directory; it is orphaned by the next version bump. Use
  `${CLAUDE_PLUGIN_DATA}`, which survives updates (but is removed when the plugin is uninstalled
  from all scopes)
- plugin.json is the version pin; marketplace entries omit `version`
- Remote: `brightops-ai/brightopsai-plugins-official` on GitHub (public)

## Agent skills

`docs/agents/` is in-repo coding-agent configuration (mattpocock-skills issue
tracker, triage, and domain conventions), not marketplace plugin-user docs —
see [docs/README.md](docs/README.md).

### Issue tracker

GitHub Issues on `brightops-ai/brightopsai-plugins-official` via the `gh` CLI. See
[docs/agents/issue-tracker.md](docs/agents/issue-tracker.md).

### Triage labels

Canonical five-state vocabulary — `needs-triage`, `needs-info`,
`ready-for-agent`, `ready-for-human`, `wontfix` — label strings unchanged. See
[docs/agents/triage-labels.md](docs/agents/triage-labels.md).

### Domain docs

Single-context: one `CONTEXT.md` and one `docs/adr/` at the repo root, created
lazily by `/grill-with-docs`. See [docs/agents/domain.md](docs/agents/domain.md).

### Secret scanning

This repo is **public-bound**. A gitleaks pre-commit hook
(`.githooks/pre-commit`, activated by `./scripts/install-hooks.sh`) enforces
[`.gitleaks.toml`](.gitleaks.toml), which blocks infrastructure identifiers on
top of the default secret rules — workspace name, tailnet hosts/IDs/IPs,
home-directory paths, LAN IPs, AWS account IDs.

Two consequences for anything written here, including docs:

- **Never write a literal absolute path to the maintainer's home or workspace.**
  Use `<workspace>`, `<project-root>`, `<tailnet-host>`. Real names in design
  rationale are fine — an ADR that can't say what drove a decision is worse.
  Identifiers are what get placeholdered.
- **Example credentials must look fake** (`sk_test_REPLACE_ME`), not
  realistically shaped. If a rule fires, fix the value or add a *rule-scoped*
  allowlist; don't add a path allowlist and don't use `--no-verify`.

Git never clones hooks, so in a fresh clone assume the local pre-commit
gate is inactive until `./scripts/install-hooks.sh` has run. CI still
scans the tree on pull requests and `main` (`.github/workflows/ci.yml`).
