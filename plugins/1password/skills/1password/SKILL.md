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

Follow the official CLI get-started steps. Don't guess install commands.

## References

- `references/get-started.md` — install + app integration + sign-in flow
- `references/cli-examples.md` — real `op` command examples

## Existing environment setup

Before reading a secret, check whether it's already present in the
environment (`printenv VAR_NAME`). Many users pre-inject secrets via
`op read` in a shell wrapper or launch script, so the value may already be
available without needing `op` at all.

**SSH agent:**
- `SSH_AUTH_SOCK` may point to the 1Password SSH agent socket.
  If configured, SSH operations (git clone/push over SSH, etc.) work
  automatically.

**Default vault:** use the vault specified in the user's `CLAUDE.md` or
project config. If none is specified, ask the user which vault to use.
Use `<VAULT>` as a placeholder in `op://` references and commands below.

### Adding secrets for MCP servers

1. Store in 1Password: `op item create --vault="<VAULT>" --title="<ITEM>" ...`
2. Export it before Claude starts (e.g. in a shell wrapper or launch script):
   `export MY_SERVICE_API_KEY="$(op read 'op://<VAULT>/<ITEM>/credential')"`
3. Reference as `${MY_SERVICE_API_KEY}` in the `.mcp.json` `env` block

That's it — no wrapper scripts are required by this skill. If the env var is
injected before Claude starts, `.mcp.json` expands `${VAR}` references in
`env` values.

## When you need this skill

Use this skill for mid-session secret operations:

- Reading a secret not already in the environment (e.g., a database password,
  API key for a new service)
- Storing a new secret the user just generated
- Injecting secrets into a config template (`op inject`)
- Wrapping a command with secrets (`op run`)
- Troubleshooting `op` auth or connectivity issues

## Workflow

1. Check if the secret is already in the environment (`printenv VAR_NAME`).
   If it's there, use it — no need for `op`.
2. Verify CLI is present: `op --version`.
3. Try `op whoami` to check auth status. If desktop app integration is enabled
   and the app is unlocked, this may just work without tmux.
4. If `op whoami` fails or returns "not signed in", set up a tmux session
   (see below) and authenticate there.
5. For multiple accounts: use `--account` or `OP_ACCOUNT`.

## tmux session for persistent auth

Claude Code's shell tool spawns a fresh TTY per command, which can lose `op`
authentication state between calls. A persistent tmux session solves this by
keeping a single authenticated shell alive.

Use tmux when:
- `op whoami` fails outside tmux
- You need to run multiple `op` commands in sequence
- Sign-in requires interactive authorization (app prompt)

Example setup:

```bash
SOCKET_DIR="${TMPDIR:-/tmp}/claude-op-sockets"
mkdir -p "$SOCKET_DIR"
SOCKET="$SOCKET_DIR/op-session.sock"
SESSION="op-auth-$(date +%Y%m%d-%H%M%S)"

tmux -S "$SOCKET" new -d -s "$SESSION" -n shell

# Authenticate
tmux -S "$SOCKET" send-keys -t "$SESSION":0.0 -- "op signin" Enter

# Verify (wait a moment for the app prompt to complete)
sleep 2
tmux -S "$SOCKET" send-keys -t "$SESSION":0.0 -- "op whoami" Enter
sleep 1
tmux -S "$SOCKET" capture-pane -p -J -t "$SESSION":0.0 -S -50

# Run your op commands inside the session
tmux -S "$SOCKET" send-keys -t "$SESSION":0.0 -- "op read 'op://<VAULT>/MyItem/password'" Enter
sleep 1
tmux -S "$SOCKET" capture-pane -p -J -t "$SESSION":0.0 -S -10

# Clean up when done
tmux -S "$SOCKET" kill-session -t "$SESSION"
```

## Common operations

### Read a secret
```bash
op read 'op://<VAULT>/<Item Name>/<field>'
```

### Export as environment variable
```bash
export VAR_NAME="$(op read 'op://<VAULT>/<Item Name>/<field>')"
```

### Store a new secret
Prompt the user — never write the value to disk:
```bash
op item create --category=api-credential --title="<Service Name>" --vault="<VAULT>" '<field>=<value>'
```

### Inject into a config template
```bash
op inject -i config.yml.tpl -o config.yml
```

### Wrap a command with secrets
```bash
op run --env-file="./.env" -- <command>
```
Note: `op run` doesn't allocate a TTY. For interactive tools, prefer
`op read` + export instead.

## Guardrails

- Never paste secrets into logs, chat, or code.
- Never write secrets to disk — prefer `op run` / `op inject` / `op read` + export.
- If you discover plaintext secrets in any file, flag it immediately and offer
  to migrate them to the configured vault.
- If a command returns "account is not signed in", authenticate inside tmux
  and re-try.
- If tmux is unavailable, ask the user before proceeding — don't attempt `op`
  commands that will silently fail.
