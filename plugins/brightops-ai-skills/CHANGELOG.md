# Changelog

All notable changes to this plugin are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.5.1] - 2026-11-22

### Fixed

- `spawn-session`: the handshake was pasted and submitted before the pane was
  looked at, so a session held at a startup dialog received input. The
  launcher now sends nothing until the CLI's input box is at the foot of the
  pane with a status line under it, and it looks again before each thing it
  sends: the handshake's paste, its Enter, the brief's paste, its Enter. A
  session seen at a dialog is diagnosed (exit 4) and sent nothing further.
  The pane can still change between a look and the send that follows it, so
  a dialog that comes up in that instant can receive that one paste or Enter.
- `spawn-session`: a directory whose name ended in a newline resolved to its
  sibling, which was then trusted by `--trust-folder` and used as the working
  directory. A directory whose path holds a control character, or is not
  valid UTF-8, is now refused as usage (exit 2), before the trust
  configuration is read or written, in a dry run too. The argument is checked
  as given, as the kernel resolves it, and as the shell resolves it, so `.`,
  a symbolic link and `link/..` are covered.
- `spawn-session`: a byte that is not valid UTF-8 in a directory or session
  name was printed raw in refusals and warnings. It is rendered as text
  (`\x9b`).

### Changed

- `spawn-session`: when the input box is not showing and no known dialog is,
  the run ends with exit 5 and the new verdict `not_ready`, having held back
  whatever came next. It previously sent the handshake regardless.
- `spawn-session`: `--porcelain` adds a `handshake` pair to every run that
  verifies: `not_sent`, `not_submitted` (pasted, Enter held back) or `sent`.
  `brief` gains the value `not_submitted`. A run with `--no-verify` is
  unchanged.
- `spawn-session`: a launch in a directory with a control character in its
  path used to go ahead, with the name rendered as text in the warning. It is
  now refused; rename the directory or launch elsewhere. On Linux the same
  applies to a name that is not valid UTF-8, which used to be carried
  through.
- `spawn-session`: the status lines the launcher accepts are listed in
  `scripts/ready-prompts.tsv`, each marked `seen` (read from a real CLI
  2.1.330 pane) or `inferred`. The row for a `--bypass` session is inferred;
  a bypass launch that ends not ready names it on stderr.

## [1.5.0] - 2026-11-22

### Changed

- `spawn-session`: `--bypass` together with `--trust-folder` is now refused as
  a usage error (exit 2). Trusting a workspace and launching a session with no
  supervision are separate invocations: record trust first (run once with
  `--trust-folder` and without `--bypass`, or start the CLI in the directory
  by hand and accept the prompt), then launch with `--bypass` alone. A command
  line that passed both flags must be split into those two steps. The refusal
  governs one invocation; it does not stop the two being chained.
- `spawn-session`: a `--bypass` launch in a workspace that is not trusted yet
  is refused with the same two steps, instead of advice to add
  `--trust-folder`.
- `spawn-session`: a `--bypass` launch is refused (exit 2) when workspace
  trust cannot be checked because `python3` is missing. It previously
  launched unchecked. Other postures are unchanged, and so is `--resume`,
  which launches nothing.
- `spawn-session`: refusals render control characters in the names and paths
  they quote as text (`\n`, `\x1b`), so a message is always one line.
- `spawn-session`: the remedy reported for a session held at the trust dialog
  now works for that session (a person accepts the prompt, then `--resume`),
  where it used to send the reader into an "already running" refusal.
- `spawn-session`: when tmux fails to create the session, a line says that
  nothing was launched; when the session is created but the command that
  starts the CLI cannot be sent, a line says the session is empty. The exit
  status is still tmux's.
- `spawn-session`: the `--help` exit summary lists code 5.

### Added

- `spawn-session`: every `--bypass` launch prints a `WARNING:` line on stderr
  naming the session, the directory and the consequence, before the session
  is created. `--dry-run` prints it too, unless the real run would refuse or
  would resume.
- `spawn-session`: `--trust-folder` prints a `WARNING:` line on stderr when
  the trust it records covers a whole repository rather than only the
  directory given.
- Warnings and every dry-run correction go to stderr only. stdout — the
  `--porcelain` pairs, the prose report and the dry-run plan — is unchanged.

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
