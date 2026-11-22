# Changelog

All notable changes to this plugin are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.3.0] - 2026-11-22

### Security

- The `1password` skill is rebuilt on one rule, taken from 1Password's own
  guidance for AI tools: an agent acts on secrets without handling them
  (#80). Before, its guardrails forbade pasting secrets into logs or chat
  while its own examples printed values into the session transcript, where
  the only remedy is rotation. Every command form now cites the 1Password
  page it comes from; rules that are this repository's are labelled as such.
- `op run` with secret references is the default way to use a secret. The
  value is resolved for one subprocess and concealed in its output. `op read`
  and `op inject` are the exception, for a consumer that cannot take a secret
  from an environment variable.
- A secret is never expanded into another program's arguments, where other
  processes can see it. The consumer reads the variable from its own
  environment; a consumer that reads standard input gets the value through
  1Password's subshell form with a shell builtin doing the expansion; one
  that needs a file gets a managed file.
- Checks read an exit status and print no item or field content: a
  fixed-word test for "set and non-empty in my environment"
  (`${VAR_NAME:+set}`, safe under `set -x`), `op item get` with all output
  discarded for "in the vault", and `op run` around `test -n` for "the
  reference resolves". This replaces `printenv VAR_NAME`. Wrapper output is
  not a boundary: `op item get` shows fields 1Password does not classify as
  sensitive, and `op run` masks only what it recognises.
- Storing a secret never puts the value on a command line or in the
  conversation. The user fills the item in the 1Password app or in an item
  JSON template they edit, or 1Password generates the value
  (`--generate-password`). The skill used to ask the user for the value and
  pass it as an assignment statement.
- Commands that print a value or take one as input (bare `op read`, the OTP
  and private-key reads, `op run --no-masking`, `--reveal`, `op inject` to
  stdout, `cat` of a mounted `.env`, assignment statements, `op account add`)
  are listed under "For a human at a terminal only — never for an agent".
- A rendered config, a key file and an item template the user edits are
  written only to a private directory under `/tmp` that is verified to be
  outside every git work tree, and removed afterwards. The check walks every
  parent without needing `git` and stops when it cannot finish, so a missing
  or failing tool cannot pass as "outside". The cleanup trap is installed
  before the write. This replaces `op inject -o config.yml` and
  `op read --out-file ./key.pem` in the current directory.
- The tmux session for persistent auth never captures the pane. It writes one
  status line (sign-in state or an exit status) to a file, and the agent
  reads only that. It used to capture the pane after a bare `op read`.
- `ssh-keys`: `gh` gets its token through `op run` instead of an exported
  `op read`; a new gotcha forbids reading the `private key` field; a public
  key is written or appended only after a successful, non-empty read.

### Added

- `references/environments.md`: 1Password Environments, mounted local `.env`
  files and their stated limits, `op run --environment`, the documented MCP
  server config (`"command": "op"`), the validation hook, and 1Password's own
  plugin for Claude Code.
- `references/authentication.md`: the documented sign-in form, the tmux
  session, and service accounts for non-interactive use (scoped, read unless
  it must write, token rotation and revocation).

### Changed

- `SKILL.md` holds the rule, the `op run` default, and when to read which
  reference; command detail moved to `references/`.
- `references/cli-examples.md` is organised by task with a source per section.
- `ssh-keys` uses the documented `--fields label="public key"`; it had
  `--field`.
- `ssh-keys` is corrected against 1Password's SSH agent pages: an approval is
  per key and remembered, not required for every operation; a public-key
  `IdentityFile` with `IdentitiesOnly yes` is the documented way to match a
  key to a host, not something to avoid; the default vaults are Personal,
  Private or Employee; `--category` and `--categories` are named with their
  commands; key creation uses the documented `--category ssh`.
- `references/authentication.md`: a set `OP_SERVICE_ACCOUNT_TOKEN` does not
  prove a service account is in use, because the Connect variables take
  precedence.
- `references/get-started.md` no longer suggests a bare `op signin` to pick
  an account, and marks `op account add` as a human-only step.

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
