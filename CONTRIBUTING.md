# Contributing

This file is the human checklist for changing this marketplace. The root
[README](README.md) is the user catalog (install, plugin table). Agent
conventions — description shape, the `dream` scheduling exception, the
SKILL.md word cap, `${CLAUDE_PLUGIN_DATA}` — live in [CLAUDE.md](CLAUDE.md).
Vulnerability reporting is in [SECURITY.md](SECURITY.md).

## Skill vs plugin

Put BrightOps AI workflow skills in the existing `brightops-ai-skills`
plugin, not a new plugin each. One author-branded plugin holding many
skills is the pattern used by comparable collections, and it means a user
installs once.

Add the skill under a category subdirectory:

`plugins/brightops-ai-skills/skills/<category>/<skill>/SKILL.md`

A separate plugin is warranted only for a tool integration with heavy
external dependencies — a CLI, browser automation, an MCP server — not for
a skill that is mostly a procedure.

### Adding a plugin

1. Create `plugins/<name>/.claude-plugin/plugin.json` with name, version,
   description, and author (plus the Discover fields the marketplace check
   requires: `displayName`, `homepage`, `repository`, `license`, `keywords`).
2. Create `plugins/<name>/skills/<skill>/SKILL.md` with YAML frontmatter
   (`name` and `description` required).
3. Add optional `references/`, `scripts/`, `assets/` under the skill.
4. Add `plugins/<name>/README.md` with `## Overview`, `## Install`,
   `## Skills`, `## Prerequisites`, `## Data`, `## Update`, `## Uninstall`.
5. Register the plugin in `.claude-plugin/marketplace.json` (no `version`
   on the entry — `plugin.json` is the pin).
6. Add a row to the root README plugin table and a Plugin Details pointer
   at `plugins/<name>/README.md`.

## Categorised skills and the `skills` array

Default discovery only finds skills at the top level of `skills/`. A skill
in a category subdirectory must be listed in that plugin's
`plugins/<name>/.claude-plugin/plugin.json` `skills` array. An omitted
nested skill installs, validates, and loads with no error — and offers
nothing (verified 2026-09-05 on Claude Code 2.1.261; top-level skills stay
auto-discovered alongside the array). `scripts/check-marketplace.py` fails on
that omission.

List paths relative to the plugin root, for example:

```json
"skills": [
  "./skills/prompting/improve-prompt",
  "./skills/memory/dream"
]
```

Check the array against the directories in both directions: every nested
`SKILL.md` is listed, and every listed path has a `SKILL.md`.

## Version pin and changelog

`plugin.json` `version` is the sole pin. Bumping it is what `/plugin update`
reads. In the same change:

- Add an entry to `plugins/<name>/CHANGELOG.md`.
- A marketplace-level change (added or removed plugin, install command,
  shared tooling) also gets an entry in the root `CHANGELOG.md`.

Do not put `version` on the marketplace entry. The root README plugin table
is a checked mirror of `plugin.json`; a stale marketplace copy is silent
pin drift, not a second source of truth.

## Reloading and the version-keyed cache

After editing an installed checkout, run `/reload-plugins` in Claude Code.

The plugin cache is version-keyed under
`~/.claude/plugins/cache/brightopsai-plugins-official/<name>/<version>/`.
Edits to files without a version bump are never picked up. After bumping
`plugin.json`, remove the old version directory with the eviction script.
Preview first, then run it for real:

```bash
scripts/evict-plugin-cache.sh --dry-run <name> <old-version>
scripts/evict-plugin-cache.sh <name> <old-version>
```

The script refuses an empty or malformed plugin name or version and any
target that does not resolve to that one directory inside the marketplace
cache of the config directory. A cache root, plugin directory or version
directory that is a symlink is refused. The dry run prints the resolved path
and how many entries are beneath it. It honours `CLAUDE_CONFIG_DIR`. Do not
hand-write an `rm -rf` on the cache instead.

If a change still does not appear, look in that cache tree before debugging
the manifest.

## Secret-scanning hook

This repository is public. Git does not clone hooks. Once per clone, from
the repository root:

```bash
./scripts/install-hooks.sh
```

That points `core.hooksPath` at `.githooks/` so the gitleaks scan runs on
`git commit` (`pre-commit`) and on merge commits (`pre-merge-commit`). The
script is safe to re-run: when the hooks are already active it writes
nothing. If `core.hooksPath` already names another directory it changes
nothing and exits 1; `./scripts/install-hooks.sh --force` replaces that value
on purpose. It reports the hooks as active only after reading back the
value git will really use in that worktree.

The hooks fail closed: if `gitleaks` is not on `PATH` they block the commit
and print how to install it (`brew install gitleaks` on macOS; on Linux the
pinned release CI uses, verified by checksum). A scan that cannot complete
(for example a missing or malformed `.gitleaks.toml`) also blocks, and is
reported as a failed scan, not as a finding. A human who accepts the risk
can set `ALLOW_UNSCANNED_PUBLIC_COMMIT=1` for one commit; it applies only
when the scanner is missing and never overrides a finding or a failed scan.
Agents must not set it, and nobody should reach for `--no-verify`.

A new Claude Code session opened in the clone runs the same script, from
the SessionStart hook `.claude/hooks/install-plugins.sh` (registered for
the `startup` source, so not on resume, `/clear` or compaction). That hook
also installs the `mattpocock-skills` plugin, only when
`claude plugin list --json` shows it is missing; if the listing fails, it
warns and installs nothing. It never updates an installed copy and prints
the installed version to stderr. A plugin it installs loads in the next
session, or after `/reload-plugins`. The plugin cannot be pinned, so
`.claude/settings.json` turns off auto-update for its marketplace; what
that does and does not prevent is in [CLAUDE.md](CLAUDE.md) (Guardrails).
Update on purpose with
`claude plugin update mattpocock-skills@claude-plugins-official`.

`git rebase`, `git cherry-pick` and `git revert` create commits without
running either hook. CI (`.github/workflows/ci.yml`) scans the checked-out
tree on pull requests and `main` and is the backstop for those. Identifier and credential rules are in
[CLAUDE.md](CLAUDE.md) (Secret scanning) and [SECURITY.md](SECURITY.md).
Never write a literal maintainer home or workspace path; use
`<workspace>`, `<project-root>`. Example credentials must look fake
(`sk_test_REPLACE_ME`).

## Tests

Never write into the real `~/.claude` or the real plugin data directory.
Sandbox `CLAUDE_PLUGIN_DATA` and pass explicit temp directories.

### dream (Python unittest, stdlib only)

```bash
cd plugins/brightops-ai-skills/lib && python3 -m unittest discover -s dream/tests -t .
```

### spawn-session (bats)

`--unit` is the pure specs: no multiplexer binary required. The full run
drives a private tmux server and needs `tmux`, `bats`, and `shellcheck`.
`tests/run.sh` also shellchecks the plugin's shell files.

```bash
plugins/brightops-ai-skills/tests/run.sh --unit
plugins/brightops-ai-skills/tests/run.sh
```

### blast-radius-audit collector (Python unittest, stdlib only)

Builds a throwaway repository and a throwaway home directory with planted
hazards, then asserts the leads and that no planted secret reaches the
output. It never reads the real home directory. Needs `git`.

```bash
cd plugins/brightops-ai-skills && python3 -m unittest discover -s tests -t .
```

### Repository tooling (`scripts/tests`)

When touching `scripts/check-marketplace.py` or its fixtures, the
hooks in `.githooks/`, `scripts/install-hooks.sh`,
`scripts/evict-plugin-cache.sh`, `.gitignore`, or the CI workflow. The hook
and installer specs work in a throwaway repository and the eviction specs
run in a temp `CLAUDE_CONFIG_DIR`:

```bash
python3 -m unittest discover -s scripts/tests -t scripts
```

### Evals (manual)

Behavioural evals for `improve-prompt` cost tokens and are not a CI or
pre-commit gate. Run them when changing that skill's `SKILL.md` or
`references/`:

```bash
plugins/brightops-ai-skills/evals/run.sh
```

When adding or renaming a case under `evals/cases/`, run
`plugins/brightops-ai-skills/evals/check-index.sh` so the table in
`evals/README.md` matches disk. CI runs that index check; it does not
run `evals/run.sh`.

## Packaging gates

The packaging gate is `.github/workflows/ci.yml`. It runs on pull
requests and pushes to `main`: plugin validate, the marketplace
consistency check, unit tests, shellcheck, a gitleaks tree scan, and
eval index completeness. Behavioural evals (`evals/run.sh`) stay manual.

Run the same commands locally from the repository root before opening a
pull request that touches a plugin manifest, the marketplace registry, the
README plugin table, a plugin `README.md`, or that adds a skill — and when
in doubt:

```bash
python3 scripts/check-marketplace.py
claude plugin validate . --strict
```

`claude plugin validate` needs no login; `CLAUDE_CONFIG_DIR` may be an
empty temp directory.

## Pull-request checklist

- [ ] Skill vs plugin: workflow skills landed in `brightops-ai-skills` under
      a category directory; a new plugin only for a heavy tool integration
- [ ] Every categorised skill path is in the plugin manifest `skills` array
- [ ] `plugin.json` version bumped (sole pin) and `plugins/<name>/CHANGELOG.md`
      updated in the same change; marketplace-level notes in the root
      `CHANGELOG.md`; no `version` on the marketplace entry
- [ ] Root README plugin table matches `plugin.json` versions; new plugins
      have a plugin `README.md` with the required headings
- [ ] `./scripts/install-hooks.sh` has been run in this clone
- [ ] `python3 scripts/check-marketplace.py` and
      `claude plugin validate . --strict` pass
- [ ] dream unittest and `plugins/brightops-ai-skills/tests/run.sh --unit`
      pass; full bats when the change needs the live tmux specs
- [ ] `blast-radius-audit` collector unittest passes when that skill's
      `scripts/` changed; any new output path is covered by the leak test
- [ ] `python3 -m unittest discover -s scripts/tests -t scripts` when the
      marketplace checker, a hook in `.githooks/` or a `scripts/*.sh` file
      changed
- [ ] `evals/run.sh` when `improve-prompt` changed (manual); eval index
      check when cases changed
- [ ] User data is not stored in the plugin tree (`${CLAUDE_PLUGIN_DATA}`
      instead); no maintainer home/workspace paths; example secrets are fake
