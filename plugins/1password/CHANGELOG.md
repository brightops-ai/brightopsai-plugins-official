# Changelog

All notable changes to this plugin are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.3.0] - 2026-11-22

### Security

- No instruction in either skill prints a secret value any more (#80). A
  value that reaches a session transcript can only be undone by rotating it.
  - `1password`: the "already in the environment?" check is a presence test
    that prints `set` or `unset`, replacing `printenv VAR_NAME`.
  - `1password`: the tmux example wraps the consumer in `op run` instead of
    sending a bare `op read` and capturing the pane, and signs in with
    `eval "$(op signin)"` so a session token is not left in the pane.
  - `1password`: "Read a secret" pipes `op read` to its consumer;
    `op item create` examples discard the item summary.
  - `references/cli-examples.md`: commands that print a value (bare
    `op read`, the OTP and private-key reads, `op run --no-masking`,
    `op inject` to stdout) moved under "For a human at a terminal only —
    never for an agent". The key-file example writes to a `mktemp -d`
    directory outside the work tree instead of `./key.pem`.
  - `ssh-keys`: key creation discards the item summary, and a new gotcha
    forbids reading the `private key` field.

### Added

- `1password` guardrail: never run a command whose output is a secret value;
  when the user asks to see one, hand them the command to run in their own
  terminal.

## [1.2.2] - 2026-09-05

### Changed

- Align the `ssh-keys` skill description with the model-invocable
  trigger-phrase convention used by `1password`.

## [1.2.1] - 2026-09-05

### Added

- Discover metadata: `displayName`, `homepage`, `repository`,
  `license`, `keywords`, and a plugin `LICENSE`.

## [1.2.0] - 2026-09-05

### Added

- Baseline: released as 1.2.0. Ships the `1password` and `ssh-keys` skills.
