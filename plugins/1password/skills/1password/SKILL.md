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
environment. Test for presence only; the check prints `set` or `unset`,
never the value:

```bash
if [ "${VAR_NAME:+set}" = set ]; then echo set; else echo unset; fi
```

`${VAR_NAME:+set}` expands to the word `set`, never to the value, so the check
stays safe even with shell tracing on. Do not check with `printenv VAR_NAME`,
`echo "$VAR_NAME"`, `env` or `[ -n "$VAR_NAME" ]`: each can put the value
into the transcript. Many users pre-inject secrets via
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

1. Get the item into 1Password without the value passing through the
   conversation (see "Store a new secret").
2. Have the user export it before Claude starts, in the shell wrapper or
   launch script, with tracing off. Assign first so a failed read stops the
   script instead of exporting an empty value:
   ```bash
   MY_SERVICE_API_KEY="$(op read 'op://<VAULT>/<ITEM>/credential')" || exit 1
   export MY_SERVICE_API_KEY
   ```
3. Reference as `${MY_SERVICE_API_KEY}` in the `.mcp.json` `env` block

That's it — no wrapper scripts are required by this skill. If the env var is
injected before Claude starts, `.mcp.json` expands `${VAR}` references in
`env` values.

## When you need this skill

Use this skill for mid-session secret operations:

- Reading a secret not already in the environment (e.g., a database password,
  API key for a new service)
- Getting a new secret into the vault without it passing through the
  conversation
- Injecting secrets into a config template (`op inject`)
- Wrapping a command with secrets (`op run`)
- Troubleshooting `op` auth or connectivity issues

## Workflow

1. Check if the secret is already in the environment with the presence test
   above. If it prints `set`, use the variable — no need for `op`.
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
mkdir -p "$SOCKET_DIR" && chmod 700 "$SOCKET_DIR"
SOCKET="$SOCKET_DIR/op-session.sock"
STATUS="$SOCKET_DIR/op-status"
SESSION="op-auth-$(date +%Y%m%d-%H%M%S)"

tmux -S "$SOCKET" new -d -s "$SESSION" -n shell

# Authenticate. Without app integration `op signin` prints a session token:
# assign it, check the sign-in worked, then eval it, so the token is never
# shown and a failed sign-in is not hidden. The pane writes one status line
# to a file; that line is all that leaves the session.
rm -f "$STATUS"
tmux -S "$SOCKET" send-keys -t "$SESSION":0.0 -- \
  "set +x; if s=\"\$(op signin)\"; then eval \"\$s\"; fi; unset s; if op whoami >/dev/null 2>&1; then echo 'op-auth: signed in'; else echo 'op-auth: NOT signed in'; fi >'$STATUS'" Enter

# Read the status line. Repeat if the file is not there yet (the app prompt
# may still be open).
sleep 2
cat "$STATUS"

# Run a secret-bearing command in the session and bring back only its exit
# status. Its output stays in the pane for the user.
rm -f "$STATUS"
tmux -S "$SOCKET" send-keys -t "$SESSION":0.0 -- \
  "op run --env-file=./.env -- <command>; echo \"exit: \$?\" >'$STATUS'" Enter
sleep 1
cat "$STATUS"

# Clean up when done
tmux -S "$SOCKET" kill-session -t "$SESSION"
rm -f "$STATUS"
```

Never run `capture-pane` on this session, and never send it a bare `op read`.
The pane can hold sign-in prompts and the output of secret-bearing commands;
the status file is the only channel back.

## Common operations

Run every secret-bearing command with shell tracing off. Under `set -x`,
`bash -x` or `xtrace` the shell prints each expanded value, including the
right-hand side of an assignment, an `export` and an `eval`. Start such a
command with `set +x`, and never add tracing to a script that reads secrets.

### Read a secret
Send the value straight to the command that needs it. A bare `op read`
prints the value into the transcript. `pipefail` makes a failed read fail the
pipeline instead of feeding the consumer empty input:
```bash
set -o pipefail
op read 'op://<VAULT>/<Item Name>/<field>' | <command-that-reads-stdin>
```

### Export as environment variable
Assign first and check the read, then export. A plain
`export VAR_NAME="$(op read ...)"` succeeds even when the read failed:
```bash
if VAR_NAME="$(op read 'op://<VAULT>/<Item Name>/<field>')"; then
  export VAR_NAME
else
  unset VAR_NAME
  echo "op read failed; VAR_NAME not exported" >&2
fi
```

### Store a new secret
The value must never reach the agent: not in chat, not in a tool call, not
on a command line the agent writes. Do not ask the user for it.

- **The user holds the value** (a key a service issued). Create the empty
  item — no assignment, so no secret — and have the user paste the value into
  its field in the 1Password app. If the command is refused, the user creates
  the item in the app:
  ```bash
  op item create --category=api-credential --title="<Service Name>" --vault="<VAULT>"
  ```
- **Any random value will do** (a new password or signing secret). Have
  1Password generate it, and discard the item summary:
  ```bash
  op item create --category=password --title="<Service Name>" --vault="<VAULT>" --generate-password >/dev/null
  ```
- **Verify by name.** The value goes to `grep -q`, which prints nothing:
  ```bash
  if op read 'op://<VAULT>/<Service Name>/<field>' | grep -q .; then echo present; else echo "missing or empty"; fi
  ```
- **The user pastes a value into the chat anyway.** Do not copy it into any
  command or file. Say that it is now in the transcript and should be
  rotated, and have the replacement stored as above.

### Inject into a config template
Stream the rendered config to its consumer:
```bash
set -o pipefail
op inject -i config.yml.tpl | <command-that-reads-config-on-stdin>
```
Never pass `-o` a relative path such as `config.yml`: in a repository that
writes the resolved secrets into the work tree. When the consumer needs a
file, use the temporary-directory pattern in `references/cli-examples.md`
("Secret-bearing files").

### Wrap a command with secrets
```bash
op run --env-file="./.env" -- <command>
```
Note: `op run` doesn't allocate a TTY. For interactive tools, prefer
`op read` + export instead.

## Guardrails

- Never paste secrets into logs, chat, or code.
- Never run a command whose output is a secret value: no bare `op read`, no
  `printenv`, `echo` or `env` on a secret variable, no `op run --no-masking`,
  no `--reveal`, no `cat` of a rendered config. A value that reaches the
  transcript can only be undone by rotating it. When the user asks to see a
  value, give them the command to run in their own terminal (the human-only
  section of `references/cli-examples.md`); do not run it.
- Never take a secret value into the conversation or put one on a command
  line: the user enters it in 1Password themselves, or 1Password generates it
  ("Store a new secret").
- Never write a secret into a work tree — prefer `op run`, or `op read` /
  `op inject` streamed to the consumer. When a consumer needs a key or a
  rendered config as a file, write it to a private temporary directory outside
  every git work tree, owner-only, and remove it afterwards
  (`references/cli-examples.md`, "Secret-bearing files").
- If you discover plaintext secrets in any file, flag it immediately and offer
  to migrate them to the configured vault.
- If a command returns "account is not signed in", authenticate inside tmux
  and re-try.
- If tmux is unavailable, ask the user before proceeding — don't attempt `op`
  commands that will silently fail.
