# Changelog

All notable changes to this plugin are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.4.0] - 2026-09-05

### Added

- Secret scan before every Grok upload: `scan-secrets.sh` prefers
  `gitleaks` (repo `.gitleaks.toml` when the file is in a git work tree),
  otherwise a bundled high-confidence fallback. A hit names the rule and
  file and blocks the upload.

### Changed

- Skill step 3 no longer carries a prose regex list; the scanner is the
  source of patterns. Selector and prompt detail stay in the reference
  files.

## [1.3.2] - 2026-09-05

### Added

- Declares a dependency on `playwright` from `claude-plugins-official`.
  No semver pin: upstream `plugin.json` has no version, and the MCP
  tool-name prefix is not version-sensitive.

## [1.3.1] - 2026-09-05

### Added

- Discover metadata: `displayName`, `homepage`, `repository`,
  `license`, `keywords`, and a plugin `LICENSE`.

## [1.3.0] - 2026-09-05

### Added

- Baseline: released as 1.3.0. Ships the `adversarial-review` skill.
