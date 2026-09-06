# Changelog

All notable marketplace-level changes are documented in this file:
added or removed plugins, install-command changes, and tooling that
affects every plugin. Per-plugin notes live in `plugins/<name>/CHANGELOG.md`.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and plugin versions adhere to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
The marketplace itself carries no version of its own, so sections here are dated
rather than numbered.

## [Unreleased]

### Deprecated

- `agent-teams` is deprecated and will be removed from the marketplace in
  a later release. Installed copies keep working from cache but stop
  receiving updates. A replacement skill will be published separately by
  BrightOps AI. See [ADR 0001](docs/adr/0001-plugin-consolidation-scope.md).

### Added

- GitHub Actions workflow `.github/workflows/ci.yml`: plugin validate,
  marketplace check, unit tests, shellcheck, gitleaks tree scan, and eval
  index completeness on pull requests and `main`. Behavioural evals stay
  manual.
- `CONTRIBUTING.md`: human contributing guide (skill vs plugin, categorised
  `skills` array, `plugin.json` version pin, `/reload-plugins` and the
  version-keyed cache, hooks, tests, packaging gates). Root README
  Contributing is a short pointer; `CLAUDE.md` keeps agent rules and links
  to the checklist.
- `SECURITY.md`: vulnerability reporting via GitHub Security Advisories,
  fake example credentials, `${CLAUDE_PLUGIN_DATA}`, 1Password/`op` handling,
  Facebook Marketplace terms responsibility, grok.com upload plus pre-upload
  secret scan, the gitleaks pre-commit gate (inactive until
  `./scripts/install-hooks.sh`, skipped if `gitleaks` is missing), and CI
  tree scan on pull requests and `main`.

## [2026-09-05] - Plugin READMEs

### Added

- `plugins/<name>/README.md` for every plugin: install command, namespaced
  invoke names, prerequisites, `${CLAUDE_PLUGIN_DATA}` contents, update, and
  uninstall. Version floors: `agent-teams` needs Claude Code v2.1.178+; `dream`
  scheduling needs v2.1.196+.
- `scripts/check-marketplace.py` fails when a plugin README is missing, omits
  the required headings, or when the catalog README does not link to it.

### Changed

- Root README Plugin Details sections are short summaries that point at those
  files, so prerequisite lists are not copied in a second place.

## [2026-09-05] - Playwright dependency

### Added

- `allowCrossMarketplaceDependenciesOn` includes `claude-plugins-official`
  so `marketplace-scout` and `adversarial-review` can declare Playwright as
  a cross-marketplace dependency.

## [2026-09-05] - Manifest metadata

### Added

- Marketplace `$schema`, owner URL, and `category`/`tags` on every plugin
  entry so `/plugin` Discover matches official listings.
- `scripts/check-marketplace.py` now fails when those fields drift, or when
  a marketplace description does not match `plugin.json`.

## [2026-09-05] - Baseline

### Added

- Catalog baseline: five plugins, versions from each `plugin.json` —
  1password 1.2.0, agent-teams 1.2.0, marketplace-scout 1.1.0,
  adversarial-review 1.3.0, brightops-ai-skills 1.3.1.
- Install command: `/plugin marketplace add brightops-ai/brightopsai-plugins-official`.
- Shared tooling: `scripts/check-marketplace.py` consistency check.
