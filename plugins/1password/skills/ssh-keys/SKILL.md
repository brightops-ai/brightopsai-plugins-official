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
The 1Password SSH agent handles SSH authentication and asks for approval before a
process may use a key.

## Architecture

- **1Password SSH Agent** handles all SSH auth via `SSH_AUTH_SOCK`
- **Agent socket (macOS):** `~/Library/Group Containers/2BUA8C4S2C.com.1password/t/agent.sock`
- **Agent socket (Linux):** `~/.1password/agent.sock`
- **Agent config:** `~/.config/1Password/ssh/agent.toml` — controls which keys the agent offers
- **SSH config:** `~/.ssh/config` — sets `IdentityAgent` globally to the 1Password socket
- **Approval is per key and remembered.** 1Password asks before a process
  uses a key. By default the approval covers that key for that application
  until 1Password locks or quits, so later commands from the same application
  are not prompted again. The user can shorten or lengthen this in the app
  ([agent security](https://www.1password.dev/ssh/agent/security)).
- Default vault: use the vault name from the user's CLAUDE.md or project configuration

## Create a new SSH key

```bash
op item create --category ssh --title "<KEY-NAME>" --vault "<VAULT>" --ssh-generate-key ed25519
```

The CLI "prints the key to stdout with the private key redacted"
([Manage SSH keys](https://www.1password.dev/cli/ssh-keys); CLI 2.20.0 or
later). Never pass `--reveal`.

## Get the public key

```bash
op item get "<KEY-NAME>" --vault "<VAULT>" --fields label="public key"
```

## Make a key available in the SSH agent

Add an entry to `~/.config/1Password/ssh/agent.toml`:

```toml
[[ssh-keys]]
item = "<KEY-NAME>"
vault = "<VAULT>"
```

Once this file exists it replaces the default, in which the agent offers
every key in the Personal, Private or Employee vault: an `agent.toml` that
lists one key offers only that key. Verify with `ssh-add -l`. If a newly
created file is not picked up, lock and unlock 1Password
([agent config file](https://www.1password.dev/ssh/agent/config)).

## Add a key to a remote host (password-free login)

1. Save the public key to disk. Read first, and write only a non-empty
   result, so a failed read does not leave an empty key file:
   ```bash
   if PUBLIC_KEY="$(op item get "<KEY-NAME>" --vault "<VAULT>" --fields label="public key")" && [ -n "$PUBLIC_KEY" ]; then
     printf '%s\n' "$PUBLIC_KEY" > "$HOME/.ssh/<KEY-NAME>.pub"
   else
     echo "could not read the public key; nothing written" >&2
   fi
   ```
2. Fix permissions:
   ```bash
   chmod 600 "$HOME/.ssh/<KEY-NAME>.pub"
   ```
3. Copy to remote:
   ```bash
   ssh-copy-id -f -i "$HOME/.ssh/<KEY-NAME>.pub" user@host
   ```

## Add a key to GitHub (auth + signing)

Give `gh` its token through `op run`: the variable holds a secret reference,
and the value reaches only the `gh` process.

```bash
GH_TOKEN="op://<VAULT>/GitHub Token/token" op run -- gh ssh-key add "$HOME/.ssh/<KEY-NAME>.pub" --title "<KEY-NAME>" --type authentication
GH_TOKEN="op://<VAULT>/GitHub Token/token" op run -- gh ssh-key add "$HOME/.ssh/<KEY-NAME>.pub" --title "<KEY-NAME>-signing" --type signing
```

## Git commit signing

Git is configured globally to sign with SSH via 1Password:

- `gpg.format = ssh`
- `gpg.ssh.program = /Applications/1Password.app/Contents/MacOS/op-ssh-sign`
- `commit.gpgsign = true`, `tag.gpgsign = true`
- Allowed signers file: `~/.ssh/allowed_signers`

To add a new signing key to allowed_signers:

```bash
if PUBLIC_KEY="$(op item get "<KEY-NAME>" --vault "<VAULT>" --fields label="public key")" && [ -n "$PUBLIC_KEY" ]; then
  printf '%s %s\n' "email@example.com" "$PUBLIC_KEY" >> "$HOME/.ssh/allowed_signers"
else
  echo "could not read the public key; allowed_signers unchanged" >&2
fi
```

## Common gotchas

- **Never read the `private key` field** (`op read`, `op item get --reveal`,
  `--fields label="private key"`). The 1Password SSH agent signs, so nothing
  needs the key material, and reading it prints it into the transcript.
- **Matching a key to a host.** The agent offers its keys one by one, and
  servers refuse after six (`Too many authentication failures`). 1Password's
  fix is an `IdentityFile` entry that points at the **public** key, with
  `IdentitiesOnly yes`; the private key stays in 1Password
  ([advanced use cases](https://www.1password.dev/ssh/agent/advanced)). Some
  SSH clients do not accept a public key there. Never point `IdentityFile` at
  a private key file for a key that lives in 1Password.
- Without an `agent.toml`, the agent offers the keys in the Personal, Private
  or Employee vault. A key in any other vault must be listed in `agent.toml`.
- `op item create` takes `--category` (singular; `ssh` for an SSH key).
  `op item list` filters with `--categories` (plural, comma-separated).
- If `ssh-add -l` shows nothing, check that the 1Password app is unlocked and
  that the key is in a default vault or listed in `agent.toml`.
