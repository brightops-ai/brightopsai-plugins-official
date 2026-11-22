# Authentication

Sources:

- [`op signin`](https://www.1password.dev/cli/reference/commands/signin)
- [Use service accounts with 1Password CLI](https://www.1password.dev/service-accounts/use-with-1password-cli)
- [Service account security](https://www.1password.dev/service-accounts/security)
- [Load secrets into the environment](https://www.1password.dev/cli/secrets-environment-variables)

## Sign in

With the desktop app integration on, `op` authenticates through the app.
`op signin` "is idempotent. It only prompts for authentication if you aren't
already authenticated." The documented form sets the session in one step:

```bash
eval $(op signin --account <shorthand|signin-address|account-id|user-id>)
```

With several accounts, the CLI uses `--account`, then `OP_ACCOUNT`, then the
account most recently signed in to.

Never run a bare `op signin` as an agent, and never `op signin --raw`: the
output can be a session token. Use the `eval` form with shell tracing off,
then confirm with `op whoami`, which prints no secret. A failed sign-in shows
there.

## tmux session for persistent auth

Claude Code's shell tool starts a fresh TTY per command, which can lose `op`
authentication between calls. A persistent tmux session keeps one
authenticated shell alive. This is this repository's pattern, not
1Password's. Use it when:

- `op whoami` fails outside tmux
- several `op` commands must run in sequence
- sign-in needs interactive authorization (the app prompt)

```bash
SOCKET_DIR="${TMPDIR:-/tmp}/claude-op-sockets"
mkdir -p "$SOCKET_DIR" && chmod 700 "$SOCKET_DIR"
SOCKET="$SOCKET_DIR/op-session.sock"
STATUS="$SOCKET_DIR/op-status"
SESSION="op-auth-$(date +%Y%m%d-%H%M%S)"

# -e hands the status path to the pane as a variable (tmux 3.2 or later), so
# no path is pasted into a command line and its characters cannot break one.
tmux -S "$SOCKET" new -d -s "$SESSION" -n shell -e "OP_STATUS=$STATUS"

# Sign in with the documented form, then write one status line to a file.
# That line is all that leaves the session.
rm -f "$STATUS"
tmux -S "$SOCKET" send-keys -t "$SESSION":0.0 -- \
  'set +x; eval $(op signin); if op whoami >/dev/null 2>&1; then echo "op-auth: signed in"; else echo "op-auth: NOT signed in"; fi >"$OP_STATUS"' Enter

# Read the status line. Repeat if the file is not there yet (the app prompt
# may still be open).
sleep 2
cat "$STATUS"

# Run a command in the session and bring back only its exit status. Its
# output stays in the pane for the user.
rm -f "$STATUS"
tmux -S "$SOCKET" send-keys -t "$SESSION":0.0 -- \
  'op run --env-file=./app.env -- <command>; echo "exit: $?" >"$OP_STATUS"' Enter
sleep 1
cat "$STATUS"

# Clean up when done
tmux -S "$SOCKET" kill-session -t "$SESSION"
rm -f "$STATUS"
```

Never run `capture-pane` on this session, and never send it a bare `op read`.
The pane can hold sign-in prompts and command output; the status file is the
only channel back.

## Service accounts (non-interactive use)

For CI, scheduled runs and headless agents, 1Password recommends a service
account, to follow the principle of least privilege:

- **Scope it.** A service account is limited to the vaults and 1Password
  Environments chosen for it. Give it only the ones the job needs.
- **Read unless it must write.** It "can only read items from vaults it has
  READ access to" and can change items only where it has WRITE access.
- **The scope is fixed.** "You can't add vault access to a generated service
  account after creation." A wider job needs a new service account.
- **The token can be rotated or revoked.** Do that if it is exposed.

The CLI authenticates as a service account when `OP_SERVICE_ACCOUNT_TOKEN`
is set, unless 1Password Connect is configured: "the `OP_CONNECT_HOST` and
`OP_CONNECT_TOKEN` environment variables take precedence over
`OP_SERVICE_ACCOUNT_TOKEN`", and have to be cleared to use the service
account. So a set token does not prove which identity is in use:

- Check all three names with the fixed-word presence test in SKILL.md.
- `op user get --me` shows the account actually in use (for a service
  account, `Type: SERVICE_ACCOUNT`) and prints no secret.

The token is itself a secret. The platform's secret store or the user sets
it; an agent never types, prints or writes it.

- With access to more than one vault, `op item` commands need `--vault`.
- Service accounts need 1Password CLI 2.18.0 or later.
