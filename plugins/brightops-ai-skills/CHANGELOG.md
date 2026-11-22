# Changelog

All notable changes to this plugin are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.4.0] - 2026-11-22

### Added

- `blast-radius-audit` skill (`skills/safety/`): audits a repository and the
  developer machine for eleven classes of hazard through which an agent or a
  script could do irreversible damage, reports findings ranked by blast
  radius, and applies in-repo fixes only after approval. Ships a read-only,
  standard-library collector (`scripts/collect.py`) whose output is built
  from names, paths, hosts and fixed text rather than file content, with a
  `--keys` mode that lists a config file's key names, and
  `scripts/strip_hidden_unicode.py`, which lists and removes hidden Unicode
  without touching anything else in the file. Model-invocable, with frontmatter limited to Agent
  Skills standard fields so the folder is portable to other agents.

## [1.3.2] - 2026-09-05

### Added

- `displayName` on the plugin manifest, plus a plugin `LICENSE`.

## [1.3.1] - 2026-09-05

### Added

- Baseline: released as 1.3.1. Ships `improve-prompt`, `calibrate-style`,
  `dream`, `improve-memory`, `session-analysis`, `send-result`, and
  `spawn-session`.
