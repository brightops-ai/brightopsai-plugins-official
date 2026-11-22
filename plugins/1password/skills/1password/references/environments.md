# 1Password Environments and agent tools

This is 1Password's recommended way to give an agent's tools and MCP servers
their keys. The steps live on 1Password's pages; this file says which page
answers what, and the limits those pages state. It adds no setup steps of its
own. Sources:

- [Secure secrets for AI agents and tools](https://www.1password.dev/get-started/secure-ai-access)
- [1Password Environments](https://www.1password.dev/environments)
- [Access secrets through local .env files](https://www.1password.dev/environments/local-env-file)
- [Load secrets into the environment](https://www.1password.dev/cli/secrets-environment-variables)
- [Validate local .env files with the agent hook](https://www.1password.dev/environments/agent-hook-validate)
- [Use Claude Code with 1Password Environments](https://www.1password.dev/environments/claude-plugin)

## What an Environment is

A 1Password Environment holds the secrets for one project or stage as
name/value pairs, apart from the vaults. The user creates it in the 1Password
desktop app and adds the secrets there, or imports an existing `.env` file.
An Owner or Administrator has to turn the Environments policy on.

Two ways to use one on a developer machine:

## Mounted local `.env` file

1Password mounts a `.env` file at a path the user chooses. It is a UNIX named
pipe: the contents "are never stored on disk and are only available at the
moment you access them", after an authorization prompt.

Limits the page states:

- 1Password for Mac and Linux only.
- "Once the file is unlocked, every process can read it until you lock
  1Password or disable the `.env` file in 1Password." It is not a per-process
  grant.
- Not designed for concurrent readers; a second reader can fail.
- Tools that watch `.env` for changes (Vite is the example) can restart in a
  loop unless told to ignore the file.

For an agent:

- Never `cat` or otherwise read the mounted file. 1Password's "Verify with
  your terminal" step is `cat .env`; that is a step for the user.
- Let the application read it through its `.env` library.

## `op run --environment`

```bash
op run --environment <environmentID> -- <command>
```

The Environment ID comes from the app (**Manage environment** > **Copy
environment ID**). It is a name, not a secret. An Environment can be combined
with an env file of secret references:

```bash
op run --environment <environmentID> --env-file="./extra.env" -- <command>
```

Precedence, highest first: Environments, env files, shell variables. The
secret-references page labels Environment support in the CLI a beta feature.

## MCP servers

Do not put a token in an MCP config file. Launch the server through `op run`
and remove the hardcoded secrets from the `env` block:

```json
{
  "mcpServers": {
    "<server>": {
      "command": "op",
      "args": [
        "run", "--environment", "<environmentID>", "--",
        "npx", "-y", "<mcp-server-package>"
      ]
    }
  }
}
```

`op run` injects the secrets into the server's process, so they do not need
re-declaring in `env`; non-secret settings can stay there. 1Password adds
that `op run` with secret references works too. A host launched as a GUI app
may not inherit the shell's `PATH`; use the full path of `op` as the command
(`which op`).

Exporting a key before the agent starts and referring to it as `${VAR}` in
the config also works, but the key then sits in the environment of every
process the session starts. Prefer the `op run` form.

## After setup

Remove plaintext API keys from local `.env` files and shell profiles
(`~/.zshrc`, `~/.bashrc`).

## Validation hook and the 1Password plugin

- **Agent hook.** 1Password publishes a hook that checks the mounted `.env`
  files are set up before the agent executes shell commands, and blocks with
  instructions if they are not. It supports Claude Code, Cursor, GitHub
  Copilot and Windsurf, needs `sqlite3`, and skips its checks on Windows.
  Install it from the page above.
- **1Password Developer Tools plugin for Claude Code (beta).** 1Password's
  own plugin adds an MCP configuration for the 1Password Environments MCP
  server and an Environments agent skill. That server "doesn't read or return
  secrets to the AI agent"; every action needs an authorization prompt. Point
  the user at the page above for managing Environments from Claude Code.
