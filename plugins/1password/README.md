# 1password

## Overview

Use the 1Password CLI (`op`) to read, inject, and manage secrets mid-session.
Covers authentication, retrieval, injection, storage, and SSH keys via the
1Password SSH agent. Private SSH keys stay in 1Password; they are never written
to disk.

## Install

Add this marketplace if it is not already configured, then install the plugin
inside Claude Code:

```
/plugin marketplace add brightops-ai/brightopsai-plugins-official
/plugin install 1password@brightopsai-plugins-official
```

## Skills

| Invoke | What it does |
|--------|----------------|
| `/1password:1password` | Authenticate with `op`, read and inject secrets, store new items, rotate credentials, render config templates. |
| `/1password:ssh-keys` | Create SSH keys in 1Password, offer them through the SSH agent with biometric approval (Touch ID on macOS), copy public keys to remotes and GitHub, and set up git commit signing. |

Both skills are model-invocable.

## Prerequisites

- A 1Password subscription and the desktop app (app integration is how `op`
  stays signed in)
- The 1Password CLI (`op`) on `PATH` — follow the official install doc for the
  OS; do not guess the package name
- macOS Big Sur 11.0.0 or later for the app; Linux app integration needs PolKit
  and an auth agent
- `tmux`, when `op whoami` fails outside a persistent session — Claude Code's
  shell tool is a fresh TTY per command, which can drop `op` auth. If tmux is
  missing, the skill asks before running `op` commands that would fail silently

## Data

This plugin does not write under `${CLAUDE_PLUGIN_DATA}`. Secrets stay in
1Password. Persistent CLI auth, when needed, is a tmux session the skill
creates and tears down — not plugin data. SSH agent config (`agent.toml`) and
`~/.ssh/config` are the user's own files.

## Update

`/plugin update` reads the version from this plugin's `plugin.json`. A file-only
edit with no version bump is not picked up — the plugin cache is version-keyed.
See [CHANGELOG.md](CHANGELOG.md).

## Uninstall

Uninstalling this plugin from every scope removes `${CLAUDE_PLUGIN_DATA}`. This
plugin does not store anything there, so uninstall does not delete 1Password
vault items, `op` accounts, tmux sockets, or SSH config.
