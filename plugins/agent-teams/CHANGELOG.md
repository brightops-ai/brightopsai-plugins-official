# Changelog

All notable changes to this plugin are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.2.3] - 2026-09-06

### Deprecated

- This plugin will be removed from the marketplace in a later release.
  Installed copies keep working from cache but stop receiving updates.
  It stores nothing under `${CLAUDE_PLUGIN_DATA}`, so nothing needs
  migrating. A replacement skill will be published separately by
  BrightOps AI. See [ADR 0001](../../docs/adr/0001-plugin-consolidation-scope.md).

## [1.2.2] - 2026-09-05

### Changed

- Date-stamp `references/full-docs.md` with source URL and last-revised date;
  warn in the skill when the snapshot is older than six months.

## [1.2.1] - 2026-09-05

### Added

- Discover metadata: `displayName`, `homepage`, `repository`,
  `license`, `keywords`, and a plugin `LICENSE`.

## [1.2.0] - 2026-09-05

### Added

- Baseline: released as 1.2.0. Ships the `agent-teams` skill.
