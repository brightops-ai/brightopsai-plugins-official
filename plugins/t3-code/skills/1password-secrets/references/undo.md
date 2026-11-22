# Undo

Remove the setup in this order. Set `T3_HOME` as in step 2 of the skill. `${CLAUDE_SKILL_DIR}` below is the `1password-secrets` skill directory; use its absolute path when the shell has no such variable.

1. **Variables.**
   - Created with Settings → Secrets: in Settings → Secrets, remove the source from each provider variable, then delete the provider.
   - Created with the sync script: while T3 Code is closed (desktop route) or with no settings change in the app during the run (service route), remove every managed variable, then delete the references file. Name the provider instances that `--show-target` lists, each as its own argument (the example names one). The run needs the file, so it is deleted only when the removal succeeded. A wholesale backup restore would discard later settings changes.

     ```bash
     OP_ENV="${T3_OP_ENV:-$HOME/.config/claude/op.env}"
     T3CODE_HOME="$T3_HOME" python3 "${CLAUDE_SKILL_DIR}/scripts/t3_op_env_sync.py" --show-target
     T3CODE_HOME="$T3_HOME" T3_OP_ENV="$OP_ENV" python3 "${CLAUDE_SKILL_DIR}/scripts/t3_op_env_sync.py" --remove-all claudeAgent && rm "$OP_ENV"
     ```

     If the file is already gone, remove each name with `--remove=NAME`.
2. **Token in the server's environment.**
   - Desktop route (login agent):

     ```bash
     launchctl bootout "gui/$(id -u)/local.op-token-login-env"
     rm "$HOME/Library/LaunchAgents/local.op-token-login-env.plist"
     launchctl unsetenv OP_SERVICE_ACCOUNT_TOKEN
     ```

   - Service route:

     ```bash
     sh "${CLAUDE_SKILL_DIR}/scripts/op_token.sh" remove-service-env "$T3_HOME"
     t3 service restart
     ```

3. **Keychain item:**

   ```bash
   security delete-generic-password -a "$USER" -s op_service_account
   ```

4. Delete any token export from a shell profile.
5. Delete the `settings.json.bak-*` files beside `settings.json`; they may hold older literal credentials. Leave `settings.json.lock`: it is an empty file and safe to keep.
6. Quit apps opened since login; they still hold the token.
7. Revoke the service account in 1Password when it is no longer needed.
