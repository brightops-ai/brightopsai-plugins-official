# Changelog

All notable changes to this plugin are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.5.0] - 2026-11-22

### Changed

- `spawn-session`: `--bypass` together with `--trust-folder` is now refused as
  a usage error (exit 2). Trusting a workspace and launching a session with no
  supervision are separate invocations: record trust first (run once with
  `--trust-folder` and without `--bypass`, or start the CLI in the directory
  by hand and accept the prompt), then launch with `--bypass` alone. A command
  line that passed both flags must be split into those two steps.
- `spawn-session`: a `--bypass` launch in a workspace that is not trusted yet
  is refused with the same two steps, instead of advice to add
  `--trust-folder`.

### Added

- `spawn-session`: every `--bypass` launch prints a `WARNING:` line on stderr
  naming the session, the directory and the consequence. `--dry-run` prints
  it too.
- `spawn-session`: `--trust-folder` prints a `WARNING:` line on stderr when
  the trust it records covers a whole repository rather than only the
  directory given.
- Warnings go to stderr only, so `--porcelain` output on stdout is unchanged.

## [1.4.0] - 2026-11-22

### Added

- `blast-radius-audit` skill (`skills/safety/`): audits a repository and the
  developer machine for eleven classes of hazard through which an agent or a
  script could do irreversible damage, reports findings ranked by blast
  radius, and applies in-repo fixes only after approval. Ships a read-only,
  standard-library collector (`scripts/collect.py`) that reduces environment
  variables and credential files to names, paths and hosts so no secret value
  reaches the transcript. Model-invocable, with frontmatter limited to Agent
  Skills standard fields so the folder is portable to other agents.

## [1.3.2] - 2026-09-05

### Added

- `displayName` on the plugin manifest, plus a plugin `LICENSE`.

## [1.3.1] - 2026-09-05

### Added

- Baseline: released as 1.3.1. Ships `improve-prompt`, `calibrate-style`,
  `dream`, `improve-memory`, `session-analysis`, `send-result`, and
  `spawn-session`.
