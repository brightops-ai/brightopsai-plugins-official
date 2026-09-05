# Changelog

All notable marketplace-level changes are documented in this file:
added or removed plugins, install-command changes, and tooling that
affects every plugin. Per-plugin notes live in `plugins/<name>/CHANGELOG.md`.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and plugin versions adhere to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
The marketplace itself carries no version of its own, so sections here are dated
rather than numbered.

## [Unreleased]

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
