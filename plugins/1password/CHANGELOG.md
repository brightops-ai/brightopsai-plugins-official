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
- A new secret no longer passes through the agent. The skill used to ask the
  user for the value and put it on an `op item create` command line. Now the
  user enters it in the 1Password app (the agent can create the empty item),
  or 1Password generates it with `--generate-password`; the agent verifies
  the item and field by name. Value-on-the-command-line examples moved to the
  human-only section.
- Shell tracing and hidden failures:
  - The presence check expands `${VAR_NAME:+set}`, a fixed word, so it stays
    safe under `set -x`.
  - `Common operations` states once that secret-bearing commands run with
    tracing off.
  - Every read is assigned and checked before it is exported or eval'd
    (`export VAR="$(...)"` and `eval "$(...)"` succeed when the read fails);
    piped reads set `pipefail`. Covers sign-in, the MCP launch-script
    example and the `GH_TOKEN` read in `ssh-keys`.
  - The tmux example no longer captures the pane at all: the pane writes one
    status line (sign-in state or an exit status) to a file and the agent
    reads only that.
  - `references/get-started.md` no longer suggests a bare `op signin` to pick
    an account, and marks `op account add` as a human-only step.
- `op inject` streams to its consumer instead of `-o config.yml` in the
  current directory. When a key or rendered config must be a file, one
  pattern in `references/cli-examples.md` covers both: a checked `mktemp -d`,
  a refusal when that directory is inside a git work tree, a cleanup trap
  installed before the write (also run on failure or interrupt), and a stop
  when the read fails.

### Added

- `1password` guardrail: never run a command whose output is a secret value;
  when the user asks to see one, hand them the command to run in their own
  terminal.
- `1password` guardrail: never take a secret value into the conversation or
  onto a command line. If the user pastes one into the chat, do not reuse it;
  say it should be rotated.

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
