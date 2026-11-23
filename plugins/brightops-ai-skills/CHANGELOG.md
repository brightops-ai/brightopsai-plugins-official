# Changelog

All notable changes to this plugin are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.5.2] - 2026-11-22

### Fixed

- `spawn-session`: the handshake was pasted and submitted before the pane was
  looked at, so a session held at a startup dialog received input. The
  launcher now sends only to the CLI's input box, and looks at the pane
  before each thing it sends: the handshake's paste, its Enter, the brief's
  paste, its Enter. A session seen at a dialog is diagnosed (exit 4) and sent
  nothing further. The pane can still change between a look and the send that
  follows it, so a dialog that comes up in that instant can receive that one
  paste or Enter.
- `spawn-session`: a directory whose name ended in a newline resolved to its
  sibling, which was then trusted by `--trust-folder` and used as the working
  directory. A directory whose path holds a control character, or is not
  valid UTF-8, is now refused as usage (exit 2), before the trust
  configuration is read or written, in a dry run too. The argument is checked
  as given, as the kernel resolves it, and as the shell resolves it, so `.`,
  a symbolic link and `link/..` are covered.
- `spawn-session`: a directory whose name holds tmux format syntax, such as
  `a-#{session_name}`, started the session in the home directory while trust
  was recorded for the directory named. The directory is now passed to tmux
  so that it is not expanded.
- `spawn-session`: a byte that is not valid UTF-8 in a directory or session
  name was printed raw in refusals and warnings. It is rendered as text
  (`\x9b`).
- `spawn-session`: when the CLI's transcript directory did not exist yet, as
  on a machine's first session, a verified launch ended with status 1 and no
  output while waiting for the reply. It now waits and reports as usual.

### Changed

- `spawn-session`: when the input box is not showing and no known dialog is,
  the run ends with exit 5 and the new verdict `not_ready`, having held back
  whatever came next. It previously sent the handshake regardless.
- `spawn-session`: `--porcelain` adds a `handshake` pair to every run that
  verifies: `not_sent`, `not_submitted` (pasted, Enter held back) or `sent`.
  `brief` gains the value `not_submitted`, and `verdict` gains `not_ready`,
  `mismatch` and `mux_error`. An acknowledgement from the wrong session now
  prints its report before the exit 2. A run with `--no-verify` is unchanged.
- `spawn-session`: a tmux command that fails during a delivery ends the run
  with tmux's own status after a report of what had been delivered. A CLI
  that starts and exits at once is reported as never started (exit 4), where
  it could be reported as running.
- `spawn-session`: a session the launcher creates is 120 columns by 40 rows
  until a client attaches, instead of the tmux server's default size.
- `spawn-session`: a launch in a directory with a control character in its
  path used to go ahead, with the name rendered as text in the warning. It is
  now refused; rename the directory or launch elsewhere. On Linux the same
  applies to a name that is not valid UTF-8, which used to be carried
  through.
- `spawn-session`: the mode lines the launcher accepts under the input box
  are listed in `scripts/ready-prompts.tsv`, each marked `seen` (read from a
  real CLI 2.1.330 pane) or `inferred`. The row for a `--bypass` session is
  inferred; a bypass launch that ends not ready names it on stderr.

## [1.5.1] - 2026-11-22

### Fixed

- `spawn-session`: the helper that reads and writes the trust configuration
  renders control characters in the configuration path and the action it
  quotes (`\n`, `\x1b`, a doubled backslash), as every other message already
  did. A configuration path containing a newline used to split its refusal
  into two lines on stderr.
- `spawn-session`: the warning of a `--bypass --dry-run` now ends by saying
  that a dry run does not check the name, and that the real run refuses a name
  already in use. The preview used to promise a launch the real run would
  refuse. It is still one line on stderr, and stdout is unchanged.

### Changed

- `spawn-session`: the usage text and `references/protocol.md` describe
  `--help` as it behaves: acted on where it is read. An argument the parser
  refuses first still exits 2 (`--unknown --help`), and an option that takes a
  value takes `--help` as that value. Behaviour is unchanged; the text used to
  say `--help` wins over every other argument.

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
