# marketplace-scout

## Overview

Search Facebook Marketplace, grade listings A+ through F against market-price
research, save results to CSV, and serve an interactive Vite + React dashboard.
Supports personal deal-finding and resale arbitrage.

## Install

Add this marketplace if it is not already configured, then install the plugin
inside Claude Code:

```
/plugin marketplace add brightops-ai/brightopsai-plugins-official
/plugin install marketplace-scout@brightopsai-plugins-official
```

This plugin declares a dependency on Playwright from `claude-plugins-official`.
Claude Code auto-installs that dependency only when the official marketplace is
already configured (the default) and this marketplace allowlists it. If
auto-install is skipped or fails — Claude Code will not pull a plugin from
another marketplace otherwise — install Playwright **first**, then
`/reload-plugins` or restart:

```
/plugin install playwright@claude-plugins-official
```

## Skills

| Invoke | What it does |
|--------|----------------|
| `/marketplace-scout:marketplace-scout` | Search Marketplace via the browser, grade listings, write CSVs, and launch the dashboard. |

The skill is model-invocable. Pass a product or category as the argument.

## Prerequisites

- The Playwright plugin from `claude-plugins-official`, installed **before**
  this plugin's browser loop can run. If the Playwright tools are missing in
  the session, stop and install as above rather than retrying the loop.
- A Facebook account, logged in manually in the Playwright browser when the
  Marketplace page shows a login form
- Node.js and `npm`, for `npm run dev` on the dashboard (default port 5173)

## Data

Persistent state lives under `${CLAUDE_PLUGIN_DATA}`, not the project cwd:

- `dashboard/` — Vite + React app, scaffolded on first run
- `data/*.csv` — search results (41-column schema)
- `data/searches.json` — search index
- `data/images/` — product photos (`{listing_id}.jpg`); Facebook CDN URLs expire
- `dashboard/public/data/` — copies of the latest CSV and search index the UI reads

Leftover `./dashboard/` or `./data/` copies in a project directory are detected
and never deleted.

## Update

`/plugin update` reads the version from this plugin's `plugin.json`. A file-only
edit with no version bump is not picked up — the plugin cache is version-keyed.
See [CHANGELOG.md](CHANGELOG.md).

## Uninstall

Uninstalling this plugin from every scope removes `${CLAUDE_PLUGIN_DATA}`,
including the dashboard, CSVs, search index, and downloaded images. Export
anything that should survive before uninstalling from the last scope.
