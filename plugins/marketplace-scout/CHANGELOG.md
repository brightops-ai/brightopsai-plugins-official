# Changelog

All notable changes to this plugin are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.2.0] - 2026-09-05

### Changed

- Scaffold the dashboard and store CSVs, `searches.json`, and images under
  `${CLAUDE_PLUGIN_DATA}` instead of `./dashboard/` and `./data/` in the
  project cwd. Leftover cwd copies are detected and never deleted.

## [1.1.3] - 2026-09-05

### Changed

- Move CSV schema, grading output rules, `searches.json` shape, and
  anti-detection timings out of `SKILL.md` into `references/csv-schema.md`
  and `references/anti-detection.md`.

## [1.1.2] - 2026-09-05

### Added

- Declares a dependency on `playwright` from `claude-plugins-official`.
  No semver pin: upstream `plugin.json` has no version, and the MCP
  tool-name prefix is not version-sensitive.

## [1.1.1] - 2026-09-05

### Added

- Discover metadata: `displayName`, `homepage`, `repository`,
  `license`, `keywords`, and a plugin `LICENSE`.

## [1.1.0] - 2026-09-05

### Added

- Baseline: released as 1.1.0. Ships the `marketplace-scout` skill.
