---
name: 1password
description: >
  This skill should be used when the user asks to read, inject, or manage
  secrets using the 1Password CLI (op). Covers authenticating with op, reading
  secrets from 1Password vaults, injecting credentials into config files,
  storing new secrets, troubleshooting op CLI issues, secret rotation, or
  credential management — even if the user does not explicitly say "1password".
homepage: https://developer.1password.com/docs/cli/get-started/
---

# 1Password CLI

## The rule

An agent acts on secrets without handling them. 1Password's guidance for AI
tools is to load credentials "without exposing them in plaintext or allowing
agents to directly handle your secrets"
([Secure secrets for AI agents and tools](https://www.1password.dev/get-started/secure-ai-access)).
Everything below follows from that:

- A secret value goes from 1Password straight to the process that needs it.
  It never enters the conversation, a tool call, a command line, a log, or a
  file the agent reads.
- The agent handles names only: secret references
  (`op://<vault>/<item>/<field>`), item titles, Environment IDs, variable
  names.
- Use the forms 1Password documents. Do not improvise a credential-handling
  pattern. If no documented form fits, stop and ask the user.

Follow the official install steps; don't guess install commands.

## References

- `references/get-started.md` — installing the CLI and turning on app
  integration. Read when `op` is missing.
- `references/authentication.md` — sign-in, the tmux session for persistent
  auth, service accounts. Read when `op whoami` fails or the run is
  non-interactive.
- `references/cli-examples.md` — the exact command forms with their sources:
  `op run`, checks, storing a secret, config and key files, and the commands
  only a human may run. Read before running anything beyond the default below.
- `references/environments.md` — 1Password Environments, mounted `.env`
  files, MCP server config, the validation hook. Read when giving an agent's
  tools or an MCP server their keys.

## Default: `op run` with secret references

`op run` resolves secret references for one subprocess and conceals them in
that subprocess's output. The reference goes in an environment variable or an
env file; the value never passes through the shell or the agent:

```bash
op run --env-file="./app.env" -- <command>
MY_VAR="op://<VAULT>/<ITEM>/<field>" op run -- <command>
```

- **The env file holds references, not values**, so it can be committed.
- **The consumer reads the variable itself**, from its environment. Never
  expand a secret into a command's arguments (`--password "$MY_VAR"`):
  process arguments are visible to other processes on the machine, which is
  what 1Password's item reference says of command arguments.
- **A consumer that reads standard input** gets the value through 1Password's
  subshell form. `op run` substitutes before the inner shell expands, and a
  shell builtin does the expansion, so the value is in no argument list:
  `MY_VAR="op://<VAULT>/<ITEM>/<field>" op run -- sh -c 'printf "%s" "$MY_VAR" | <command-that-reads-stdin>'`.
- **Masking is not a boundary.** A secret the subprocess prints usually shows
  as `<concealed by 1Password>`, but a value 1Password does not treat as
  concealed prints in full. Do not print a secret through `op run` to look at
  it. `--no-masking` is a deliberate reveal and is for a human only.
- **Scope.** `op run` gives the value to one process for its lifetime.
  `export` leaves it in the shell and every child, and 1Password says to
  "assume that processes on your computer can access the environment of other
  processes run by the same user". Prefer `op run` to `export`.

## Check without revealing

A check reads an exit status. It never prints item or field content.

- **Already in this environment, and non-empty?** Many users pre-inject
  secrets in a launch script. Expand a fixed word, never the value; this
  prints `set` for a non-empty variable and `unset` otherwise:
  ```bash
  if [ "${VAR_NAME:+set}" = set ]; then echo set; else echo unset; fi
  ```
  Not `printenv VAR_NAME`, `echo "$VAR_NAME"`, `env` or `[ -n "$VAR_NAME" ]`.
- **Is the item in the vault?** Discard all output and test the status:
  ```bash
  if op item get "<ITEM>" --vault "<VAULT>" >/dev/null 2>&1; then echo found; else echo "not found"; fi
  ```
- **Does the reference resolve to a non-empty value?** The child tests the
  variable and prints nothing:
  ```bash
  if MY_VAR="op://<VAULT>/<ITEM>/<field>" op run -- sh -c 'test -n "$MY_VAR"' >/dev/null 2>&1; then echo resolves; else echo "does not resolve"; fi
  ```

The output is discarded on purpose: `op item get` shows every field 1Password
does not classify as sensitive, and `op run` masks only what it recognises. A
failure can also mean "not signed in"; `op whoami` tells the two apart.

## Store a new secret

Never write an assignment statement that carries a value
(`'password=<value>'`). 1Password: "Command arguments get logged in your
command history, and can be visible to other processes on your machine."
Do not ask the user for the value. One of:

1. **The user fills the item themselves**, in the 1Password app or in an item
   JSON template they edit (`references/cli-examples.md`, "Store").
2. **1Password generates the value**, when a new random one is acceptable:
   `--generate-password[=recipe]` on a Login or Password item.

If the user pastes a value into the chat anyway, do not copy it into any
command or file. Say that it is now in the transcript and should be rotated,
and have the replacement stored as above.

## When `op run` does not fit

`op read` and `op inject` put a value on stdout or in a file, so each use
needs a reason: the consumer cannot take the secret from an environment
variable. The forms are in `references/cli-examples.md`.

- Never run a bare `op read`; send its output to the consumer.
- Run these with shell tracing off (`set +x`): under `set -x` the shell
  prints every expanded value, including in an assignment, `export` or `eval`.
- A rendered config or key file is deleted when no longer needed (1Password's
  rule) and is written outside every git work tree (this repository's rule).
  Use only the guarded block in `references/cli-examples.md`, which stops when
  it cannot verify the location.

## Keys for agent tools and MCP servers

1Password's recommended setup is a 1Password Environment, used through a
mounted local `.env` file or `op run --environment <environmentID> --
<command>`. An MCP server that needs a token is launched through `op run`
(`"command": "op"`) instead of carrying the token in its config file. After
setup, plaintext keys come out of local `.env` files and shell profiles. The
forms, limits and links are in `references/environments.md`.

## Authentication

1. Verify the CLI is present: `op --version`.
2. Check auth: `op whoami`. With desktop app integration on and the app
   unlocked this usually works as is.
3. If it fails, sign in inside a persistent tmux session
   (`references/authentication.md`). Claude Code's shell tool starts a fresh
   TTY per command, which can drop `op` auth between calls. If tmux is
   unavailable, ask the user before running `op` commands that will fail.
4. For a non-interactive run, use a service account scoped to the vaults or
   Environments it needs, with read access unless it must write
   (`references/authentication.md`).
5. For multiple accounts, pass `--account` or set `OP_ACCOUNT`.

**Default vault:** use the vault named in the user's `CLAUDE.md` or project
config. If none is named, ask. `<VAULT>` is a placeholder throughout.

**SSH agent:** `SSH_AUTH_SOCK` may point at the 1Password SSH agent socket, in
which case SSH operations work without `op`. See the `ssh-keys` skill.

## Guardrails

- Never paste secrets into logs, chat, or code.
- Never run a command whose output is a secret value: no bare `op read`, no
  `printenv`, `echo` or `env` on a secret variable (also not under `op run`),
  no `op run --no-masking`, no `--reveal`, no `op item get` whose output is
  kept, no `cat` of a rendered config or a mounted `.env` file. A
  value that reaches the transcript can only be undone by rotating it. When
  the user asks to see a value, give them the command to run in their own
  terminal (the human-only section of `references/cli-examples.md`).
- Never take a secret value into the conversation or put one on a command
  line, as an assignment statement or as another program's argument.
- If plaintext secrets turn up in any file, flag it and offer to move them
  into the configured vault or an Environment.
- If a command returns "account is not signed in", authenticate
  (`references/authentication.md`) and retry.
