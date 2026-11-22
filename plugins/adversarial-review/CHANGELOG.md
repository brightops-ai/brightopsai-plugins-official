# Changelog

All notable changes to this plugin are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.5.0] - 2026-11-22

### Added

- Upload confirmation (#82). After a clean scan and before opening Grok, the
  skill asks the user to confirm the exact file and the destination and
  uploads only on an explicit yes. With no user to answer — a headless,
  scheduled, or delegated run — it stops without uploading.
- `scripts/snapshot-document.sh`: the scan, the approval and the upload act on
  one read-only copy of the document in a private temporary directory.
  `create` prints its path, sha256 and size; `check` refuses (exit 1) when the
  snapshot no longer has the approved sha256 or the source was saved since;
  `remove` deletes it. An approval covers one sha256 and one destination.
- A second confirmation once Grok is open, naming the account actually signed
  in and the project, before a project is created or content is sent. The
  first question is asked before the account is known.
- The post-edit re-upload is new content: new snapshot, new scan, new
  confirmation.
- The inline-paste fallback needs its own explicit answer and is built from
  the approved snapshot. No pre-approved browser tool may send document
  content otherwise.
- The document is not read before it is scanned. The skill used to read the
  whole file in its first step, two steps before the scan, so a secret in it
  was in the transcript before the scanner could refuse it. Step 1 now uses
  metadata only; the content is opened after a clean scan, from the snapshot;
  on a hit the skill does not open the file to look; the source is checked
  against the snapshot before it is opened for edits.
- `check` runs as the last command before each send, upload or paste, after
  the project is open and the file chooser is up, so the approval cannot go
  stale during setup.
- The destination is named by account and project identifier
  (`/project/{uuid}`), not by project name alone, and the destination
  question is never skipped.
- The inline fallback confirms the exact payload: full or truncated, its
  size and sha256. A truncated or summarised payload gets its own snapshot
  and scan.
- Snapshots are removed on every way out of a run, not only at the end.
- `snapshot-document.sh remove` deletes the one snapshot file and then its
  directory only if empty. It used to trust the directory's name and delete
  it recursively. `create` and `check` report a digest only when the hash
  tool succeeded and produced 64 hex digits.
- `references/upload-gate.md`: the wording of each confirmation, the
  inline-fallback procedure, and cleanup.
- `scan-secrets.sh <file> [<origin>]`: the optional second argument is where
  the repo `.gitleaks.toml` is looked up, so a snapshot outside the
  repository is scanned with the document's own rules.
- `scan-secrets.sh` prints a `WARNING` on a clean scan: a clean scan is not
  clearance, confirm the file and destination with the user, stop if no user
  can answer. Exit codes are unchanged.

### Changed

- The description triggers only on requests for a Grok review or an
  adversarial review that names no other reviewer. General phrases ("critique
  this plan", "find the flaws", "poke holes in this" and similar) and
  "cross-model review" no longer invoke a skill that uploads a document.
- `SKILL.md` is under 2,000 words including frontmatter. The mode table and
  the summary format live in `references/feedback-integration.md`; a test
  holds the limit.
- `browser_file_upload` is no longer in the skill's `allowed-tools`, so the
  skill does not pre-approve the upload; the session's permission rules
  apply. Expect a permission prompt per upload unless the tool is already
  allowed.
- `--aggressive`: the flag's description now states that the backup at
  `{filename}.pre-review.md` is taken before the first edit in both modes.
  The backup is checked against the original, an existing backup is not
  overwritten, and no edit is applied if the backup cannot be written.

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
