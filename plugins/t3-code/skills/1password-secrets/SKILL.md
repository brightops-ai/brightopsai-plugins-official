---
name: 1password-secrets
description: >-
  This skill should be used when the user asks to set up or use 1Password
  secrets in T3 Code on a Mac: a service account token in the T3 Code
  environment, and op:// references that T3 Code resolves into each provider's
  variables. Also use for a repeating "1Password Access Requested" prompt from
  T3 Code, setting up 1Password on a new T3 Code machine, adding or changing a
  secret agents need, removing this setup, or an `op` command that fails or
  prompts inside a T3 Code thread.
compatibility: macOS, the T3 Code desktop app or background service on the same Mac, the 1Password CLI (op), and a 1Password service account with read access to one vault.
---

# 1Password in T3 Code

**Target state:** every T3 Code session starts with `OP_SERVICE_ACCOUNT_TOKEN` and the secrets it needs already in its environment, and `op` runs headless as a service account.

Three parts make it work:

- **Token in the T3 Code server's environment.** Agents inherit the server's environment, so one token there reaches every session.
- **References file.** `~/.config/claude/op.env` holds one `NAME=op://vault/item/field` per line. References only.
- **T3 Code provider variables.** Either Settings → Secrets or the sync script writes those references into T3 Code's settings; T3 Code resolves them with `op` when a provider session starts.

Never print a token or a resolved value, and never put one in a command line. Check state with `op_check.sh`, which prints only `ok:` or `FAIL:` lines. Every command below uses quoted variables set on a preceding line; keep that form.

## Bundled files

| File | Use |
|---|---|
| `${CLAUDE_SKILL_DIR}/scripts/t3_op_env_sync.py` | Run. Writes the references into `settings.json`. Options: `--show-target`, `--list-references`, `--dry-run`, `--replace`, `--remove=NAME`, `--remove-all`, `--account=HOST`. Read `--help`; do not load the file. |
| `${CLAUDE_SKILL_DIR}/scripts/op_check.sh` | Run: `keychain`, `launchd`, `refs`, `session [NAME ...]`. Prints `ok:` or `FAIL:` lines only. |
| `${CLAUDE_SKILL_DIR}/scripts/op_token.sh` | Run: `keychain`, `service-env`, `remove-service-env`. Moves the token from a private file to the keychain or `service.env` without printing it or putting it in argv. |
| `${CLAUDE_SKILL_DIR}/assets/local.op-token-login-env.plist` | Copy to `~/Library/LaunchAgents/`; never edit in place. Read its comment first. |
| `${CLAUDE_SKILL_DIR}/references/settings-format.md` | Read when the exact settings shape or the ownership rules matter. |
| `${CLAUDE_SKILL_DIR}/references/undo.md` | Read to remove this setup. |

## Facts that shape the setup

- With a service account token set, `op` ignores the provider's account field; any sign-in address such as `my.1password.com` works.
- Reference segments may hold letters, digits, spaces, `.`, `_`, `-`. For an item whose name has other characters, use the item ID.
- T3 Code waits up to 45 seconds for 1Password, then treats the secret as unreadable.
- `OP_CONNECT_HOST` and `OP_CONNECT_TOKEN` must not be set in the same environment as the token.
- Agents can read anything the service account can. Scope it to one vault of agent secrets.
- Service accounts cannot reach Personal, Private or Employee vaults, and vault access is fixed when the account is created.
- The supported setup is a T3 Code server on the same Mac as these files.

## Setup on a new machine

1. **Check prerequisites.** `op --version` works, and the user has a service account with read access to the vault that holds the agents' secrets. Creating it is the user's step at 1password.com.
   Done when `op` is installed and the user confirms the service account exists.

2. **Resolve the target, once.** Carry the result through every later step.
   - **T3 home:** `$T3CODE_HOME` when set in the session, otherwise `~/.t3`. Set `T3_HOME` to it.
   - **Route:** run `t3 service status`. No installed service means the **desktop** route (the app launched from the Dock is the server). An installed service that the desktop app is not the server for means the **service** route. When both exist, or the desktop is connected to a remote server, stop and ask the user which server owns this thread; do not guess.
   - **Settings:** run the command below. Use its path and provider names for the dry run, the apply and the validation.

   ```bash
   T3_HOME="${T3CODE_HOME:-$HOME/.t3}"
   T3CODE_HOME="$T3_HOME" python3 "${CLAUDE_SKILL_DIR}/scripts/t3_op_env_sync.py" --show-target
   ```

   Done when the T3 home, the route, the settings path, `exists: yes` and the provider names are known.

3. **Choose the two routes.** They are independent; resolve both, and neither skips a later step.
   - **Token route** follows step 2: service (`service.env`, applied by `t3 service restart`) or desktop (the login agent).
   - **Variables route:** Settings → Secrets when the page exists (T3 Code says it "is in preview and is not in every build yet"): add a provider, then pick it as the source of each provider variable. Otherwise the sync script, steps 6 to 8.

   Whatever the variables route, the token step and a restart still happen, and validation checks the variables that route configured.
   Done when both routes are named to the user.

4. **Store the token in the keychain.** Get it with `request_secret` (`delivery: "file"`), never through chat; the result is a private file.

   ```bash
   TOKEN_FILE="the private file path returned by request_secret"
   sh "${CLAUDE_SKILL_DIR}/scripts/op_token.sh" keychain "$TOKEN_FILE"
   ```

   Done when `op_token.sh` printed `ok:` and `sh "${CLAUDE_SKILL_DIR}/scripts/op_check.sh" keychain` prints `ok: keychain item op_service_account exists and starts with ops_`.

5. **Put the token where the server reads it.**
   - **Service route:**

     ```bash
     sh "${CLAUDE_SKILL_DIR}/scripts/op_token.sh" service-env "$TOKEN_FILE" "$T3_HOME"
     ```

     Done when it printed `ok:`; `t3 service restart` applies it in step 8.
   - **Desktop route (login agent).** State to the user that this is this plugin's own mechanism, observed working on T3 Code 0.1.11 and not documented by T3 Code; that `launchctl setenv` passes the token as a process argument once per login (visible to process inspection and endpoint monitoring); and that it exports the token to every app opened after login. Require the user's explicit yes, then install it (first install uses `bootstrap`, a repeat uses `kickstart -k`):

     ```bash
     AGENT_DIR="$HOME/Library/LaunchAgents"
     AGENT_PLIST="$AGENT_DIR/local.op-token-login-env.plist"
     mkdir -p "$AGENT_DIR"
     cp "${CLAUDE_SKILL_DIR}/assets/local.op-token-login-env.plist" "$AGENT_PLIST"
     launchctl bootstrap "gui/$(id -u)" "$AGENT_PLIST"
     ```

     ```bash
     launchctl kickstart -k "gui/$(id -u)/local.op-token-login-env"
     ```

     Done when `op_check.sh launchd` prints `ok: launchd value matches the keychain value`.

6. **Write the references file** (script route only). Create it private, then add one line per secret; copy each reference from 1Password ("Copy Secret Reference"); IDs work in place of names.

   ```bash
   OP_ENV="$HOME/.config/claude/op.env"
   mkdir -p "$HOME/.config/claude"
   touch "$OP_ENV" && chmod 600 "$OP_ENV"
   ```

   Done when `op_check.sh refs` prints one `ok: NAME resolves` per line. A file that holds a literal value fails here, before `op` is called.

7. **Dry-run the sync** (script route only). Run it with `--dry-run` and every provider name from step 2, each as its own argument (the example names two). Add `--account=HOST` only to set the account of a newly added secret provider. A variable of the same name that holds a literal value or another provider's reference stops the run; add `--replace` only after the user agrees to overwrite it.

   ```bash
   T3CODE_HOME="$T3_HOME" python3 "${CLAUDE_SKILL_DIR}/scripts/t3_op_env_sync.py" --dry-run claudeAgent codex
   ```

   Done when the dry run lists every provider with the expected reference count. Keep the exact argument list that passed: step 8 applies it unchanged, minus `--dry-run`.

8. **Restart, and apply.** Resolve this skill's and the restart skill's directories to absolute paths first: the detached script has no `CLAUDE_SKILL_DIR`.
   - **Desktop route:** follow the `t3-code:restart` skill. Where the sync is needed, give it the sync as the `--` command, with the same options and provider names that passed the dry run in step 7 (`--replace` and `--account=HOST` included when they were used); where Settings → Secrets was used, give no command. Done when its log holds `result: ok`.

     ```bash
     SYNC="the absolute path of this skill's scripts/t3_op_env_sync.py"
     RESTART="the absolute path of the restart skill's scripts/restart.sh"
     sh "$RESTART" --notify "$THREAD_ID" --log "$LOG" -- /usr/bin/env T3CODE_HOME="$T3_HOME" python3 "$SYNC" claudeAgent codex
     ```

   - **Service route:** run the `t3-code:restart` skill's pause handshake (its steps 1 to 3), then the sync if the script route is used (same arguments as the dry run), then `t3 service restart`. That restart ends this turn too, and nothing messages this thread afterwards: there is no restart log and no callback on this route. So before running it, write the paused root thread ids and what remains (validate, then resume them) to a file, and tell the user to send any message in this thread once the service is back. On that message, validate (step 9) and send the resume messages (the restart skill's steps 6 and 7).
     With the sync, the server is running while its settings file changes: tell the user to make no settings change in the app during the run. The script aborts if the file changes under it. A save by T3 Code in the same instant as the write is overwritten and cannot be recovered from the backup, which holds the settings as they were before the run.

9. **Validate in a session started after the restart.** Pass the names the variables route configured; with the script route and a references file, the names can be omitted.

   ```bash
   sh "${CLAUDE_SKILL_DIR}/scripts/op_check.sh" session API_KEY OTHER_KEY
   ```

   Done when it prints `ok:` for the token, for `op whoami` as a service account, for every name given, and for no `OP_CONNECT_*` variable, and `--show-target` reports `secret provider onepassword: yes`.

## Day-to-day use

- **Inside a T3 Code session**, read secrets from the environment by name. Validate without printing a value: `op_check.sh session NAME…` after a Settings → Secrets setup, `op_check.sh refs` where a references file exists.
- **Give a value to a command** through its environment (the variable is already set; `op run -- COMMAND` for anything else) or on its standard input. Keep a resolved value out of command arguments, where process inspection sees it, and out of any command whose output returns to the agent.
- **Add or change a secret:** edit `op.env`, then run the sync while none of those providers' threads are mid-run (or through `t3-code:restart`). Sessions started earlier keep their old environment.
- **Rotate the token:** repeat steps 4 and 5 (desktop route: `kickstart -k`), then restart T3 Code with `t3-code:restart`.
- **Terminals outside T3 Code** can read the token from the keychain in the shell profile:

  ```bash
  export OP_SERVICE_ACCOUNT_TOKEN="$(security find-generic-password -a "$USER" -s op_service_account -w 2>/dev/null)"
  ```

## Diagnosing

| Symptom | Cause | Fix |
|---|---|---|
| "1Password Access Requested … T3 Code" prompt keeps returning | The session has no service account token, so `op` falls back to the desktop app, which authorises one terminal session at a time and expires after 10 minutes. | Steps 4, 5 and 8. |
| Token set in a terminal but empty in T3 Code | It is exported from `.zshrc`, which a GUI app and non-interactive agent shells never read. | Step 5, then restart. |
| `op` says the item or vault is not found | The service account reads only the vaults it was granted. | Move the item into the granted vault, or see the next row. |
| Another vault must be readable | Vault access is fixed when the service account is created. | Create a replacement service account with the access, store its token (steps 4, 5, 8), then revoke the old one. |
| A variable is empty in a new session | The reference failed to resolve (including after 45 seconds), or the sync has not run since the edit. | `op_check.sh refs`, re-run the sync, start a new session. |
| `op` ignores the token | `OP_CONNECT_HOST` or `OP_CONNECT_TOKEN` is set beside it. | Unset both; `op_check.sh session`. |
| `op_check.sh` reports a rejected references file | A line is not `NAME=op://vault/item/field`, or holds a literal value. | Fix the line the message names; nothing reached `op`. |
| No Secrets page in T3 Code Settings | "The Secrets settings page is in preview and is not in every build yet." | Use the sync script; it writes the same settings the page would. |

To remove this setup, read `${CLAUDE_SKILL_DIR}/references/undo.md`.
