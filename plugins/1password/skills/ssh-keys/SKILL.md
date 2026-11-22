---
name: ssh-keys
description: >
  This skill should be used when the user asks to "create SSH keys", "add keys
  to remote servers", "configure the 1Password SSH agent", "1Password agent
  setup", "set up git commit signing", "add SSH keys to GitHub", "troubleshoot
  SSH auth", "manage ~/.ssh/config", or "manage agent.toml". Also trigger when
  the user mentions "SSH", "key management", "ssh-copy-id", "IdentityAgent",
  "git signing", or "add my key to a server" — even if they don't mention
  1Password.
---

# SSH Key Management via 1Password

All SSH keys are stored exclusively in 1Password. Private keys never exist on disk.
The 1Password SSH agent handles all SSH authentication via biometric approval (Touch ID).

## Architecture

- **1Password SSH Agent** handles all SSH auth via `SSH_AUTH_SOCK`
- **Agent socket (macOS):** `~/Library/Group Containers/2BUA8C4S2C.com.1password/t/agent.sock`
- **Agent socket (Linux):** `~/.1password/agent.sock`
- **Agent config:** `~/.config/1Password/ssh/agent.toml` — controls which keys the agent offers
- **SSH config:** `~/.ssh/config` — sets `IdentityAgent` globally to the 1Password socket
- Every SSH operation requires **biometric approval** (Touch ID on macOS, system auth on Linux)
- Default vault: use the vault name from the user's CLAUDE.md or project configuration

## Create a new SSH key

Discard the item summary so the generated private key cannot reach the
transcript; fetch the public key with the next command instead:

```bash
op item create --category "SSH Key" --title "<KEY-NAME>" --vault "<VAULT>" --ssh-generate-key ed25519 >/dev/null
```

## Get the public key

```bash
op item get "<KEY-NAME>" --vault <VAULT> --field "public key"
```

## Make a key available in the SSH agent

Add an entry to `~/.config/1Password/ssh/agent.toml`:

```toml
[[ssh-keys]]
item = "<KEY-NAME>"
vault = "<VAULT>"
```

Changes take effect immediately — no restart needed. Verify with `ssh-add -l`.

## Add a key to a remote host (password-free login)

1. Save public key to disk:
   ```bash
   op item get "<KEY-NAME>" --vault <VAULT> --field "public key" > ~/.ssh/<KEY-NAME>.pub
   ```
2. Fix permissions:
   ```bash
   chmod 600 ~/.ssh/<KEY-NAME>.pub
   ```
3. Copy to remote:
   ```bash
   ssh-copy-id -f -i ~/.ssh/<KEY-NAME>.pub user@host
   ```

## Add a key to GitHub (auth + signing)

Run with shell tracing off (`set +x`): a trace prints the token. Assign
first so a failed read stops here instead of exporting an empty token:

```bash
if GH_TOKEN="$(op read 'op://<VAULT>/GitHub Token/token')"; then
  export GH_TOKEN
  gh ssh-key add ~/.ssh/<KEY-NAME>.pub --title "<KEY-NAME>" --type authentication
  gh ssh-key add ~/.ssh/<KEY-NAME>.pub --title "<KEY-NAME>-signing" --type signing
else
  echo "op read failed; key not added to GitHub" >&2
fi
```

## Git commit signing

Git is configured globally to sign with SSH via 1Password:

- `gpg.format = ssh`
- `gpg.ssh.program = /Applications/1Password.app/Contents/MacOS/op-ssh-sign`
- `commit.gpgsign = true`, `tag.gpgsign = true`
- Allowed signers file: `~/.ssh/allowed_signers`

To add a new signing key to allowed_signers:

```bash
PUBLIC_KEY=$(op item get "<KEY-NAME>" --vault <VAULT> --field "public key")
echo "email@example.com $PUBLIC_KEY" >> ~/.ssh/allowed_signers
```

## Common gotchas

- **Never read the `private key` field** (`op read`, `op item get --reveal`,
  `--fields "private key"`). The 1Password SSH agent signs, so nothing needs
  the key material, and reading it prints it into the transcript.
- **Do NOT use `IdentityFile`** in `~/.ssh/config` pointing to `.pub` files — it
  causes "invalid format" errors. The 1Password agent offers keys automatically.
- Only use `IdentityFile`/`IdentitiesOnly` if using `agent.toml` to limit keys
  per host.
- Keys in vaults other than `Private` must be explicitly added to `agent.toml` to
  be served by the agent.
- The `op` CLI flag is `--categories "SSH Key"` (plural), not `--category`.
- If `ssh-add -l` shows nothing, check that the 1Password app is unlocked and
  the key is listed in `agent.toml`.
