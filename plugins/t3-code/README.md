# t3-code

## Overview

Operate the T3 Code desktop app from inside its own agent threads. One skill
restarts the app without losing other threads' work: it pauses the busy
threads, restarts with a detached script, validates, and tells them to resume.
The other gives every T3 Code session 1Password secrets through a service
account token and `op://` references that T3 Code resolves into each
provider's variables. The setup follows T3 Code's official docs and adds a
login agent for the Dock-launched app, which they do not cover:

- <https://github.com/pingdotgg/t3code/blob/main/docs/user/secrets.md>
- <https://github.com/pingdotgg/t3code/blob/main/docs/user/secrets-1password-service-account.md>
- <https://github.com/pingdotgg/t3code/blob/main/docs/user/background-service.md>
- <https://github.com/pingdotgg/t3code/blob/main/docs/user/updating.md>

## Install

Add this marketplace if it is not already configured, then install the plugin
inside Claude Code:

```
/plugin marketplace add brightops-ai/brightopsai-plugins-official
/plugin install t3-code@brightopsai-plugins-official
```

## Skills

| Invoke | What it does |
|--------|----------------|
| `/t3-code:restart` | Pause the other busy threads, quit and reopen T3 Code with a detached script (optionally running a command while it is closed), validate, and tell the paused threads to resume. |
| `/t3-code:1password-secrets` | Set up a service account token in T3 Code's environment, store and check it without printing it, and sync `op://` references into T3 Code's per-provider variables; diagnose `op` prompts and empty variables. |

Both skills are model-invocable.

## Prerequisites

- macOS and the T3 Code desktop app (or its background service) on the same
  Mac as the skills.
- `restart`: the `t3` CLI, `perl`, and a thread that has the T3 thread tools.
- `1password-secrets`: the 1Password CLI (`op`), `python3`, and a 1Password
  service account with read access to one vault.

## Data

This plugin does not write under `${CLAUDE_PLUGIN_DATA}`. The skills write
these files outside the plugin, in the user's own locations:

- `~/Library/LaunchAgents/local.op-token-login-env.plist`, the login agent
  that exports the token (Dock route only; the plist's comment states the
  exposure)
- a macOS keychain item `op_service_account`, holding the service account
  token, written by `op_token.sh` through `security -i` on stdin
- `service.env` in T3 Code's home (`~/.t3` by default), one
  `OP_SERVICE_ACCOUNT_TOKEN=` line, when T3 Code runs as the background
  service; `op_token.sh` rewrites it atomically through a `0600` temporary file
  in the same directory
- `~/.config/claude/op.env`, the references file (references only, no values)
- T3 Code's `settings.json` under its data directory, plus a `0600`
  `settings.json.bak-*` backup of the original before every change and an
  empty `settings.json.lock` file beside it, kept after each run so the lock
  stays meaningful (safe to leave)
- a restart log at the path the agent passes to `restart.sh`, created
  privately and never overwritten

## Update

`/plugin update` reads the version from this plugin's `plugin.json`. A file-only
edit with no version bump is not picked up — the plugin cache is version-keyed.
See [CHANGELOG.md](CHANGELOG.md).

## Uninstall

Uninstalling this plugin from every scope removes `${CLAUDE_PLUGIN_DATA}`,
which holds nothing. It does not undo what the skills wrote. To remove the
1Password setup by hand, in this order. `SKILL_DIR` is the installed
`1password-secrets` skill directory and `T3_HOME` is `$T3CODE_HOME` when set,
otherwise `~/.t3`:

1. Variables. If they were created in Settings → Secrets, remove the source
   from each provider variable there and delete the provider. If they were
   created with the sync script, remove every managed variable while T3 Code is
   closed (or with no settings change in the app during the run, on the service
   route), then delete the references file. A wholesale restore of a backup
   would discard later settings changes.

   Name the provider instances that `--show-target` lists, each as its own
   argument (the example names one). The references file is deleted only when
   the removal succeeded.

   ```bash
   OP_ENV="${T3_OP_ENV:-$HOME/.config/claude/op.env}"
   T3CODE_HOME="$T3_HOME" python3 "$SKILL_DIR/scripts/t3_op_env_sync.py" --show-target
   T3CODE_HOME="$T3_HOME" T3_OP_ENV="$OP_ENV" python3 "$SKILL_DIR/scripts/t3_op_env_sync.py" --remove-all claudeAgent && rm "$OP_ENV"
   ```

2. Desktop route (login agent):

   ```bash
   launchctl bootout "gui/$(id -u)/local.op-token-login-env"
   rm "$HOME/Library/LaunchAgents/local.op-token-login-env.plist"
   launchctl unsetenv OP_SERVICE_ACCOUNT_TOKEN
   ```

   Service route:

   ```bash
   sh "$SKILL_DIR/scripts/op_token.sh" remove-service-env "$T3_HOME"
   t3 service restart
   ```

3. Delete the keychain item:

   ```bash
   security delete-generic-password -a "$USER" -s op_service_account
   ```

4. Delete any token export from a shell profile.
5. Delete the `settings.json.bak-*` files beside T3 Code's `settings.json`; the
   backups may hold older literal credentials. Leave `settings.json.lock`: it
   is an empty file and safe to keep.
6. Quit apps opened since login; they still hold the token.
7. Revoke the service account in 1Password when it is no longer needed.
