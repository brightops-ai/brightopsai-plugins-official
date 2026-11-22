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
cache of the config directory. A `plugins`, `cache`, marketplace, plugin or
version directory that is a symlink is refused; each is tested directly. On a
case-insensitive filesystem the capitalization of those names is not compared,
so a cache created as `Plugins/Cache` is still the cache. The dry run prints
the path and how many entries are beneath it. It honours `CLAUDE_CONFIG_DIR`.
Do not hand-write an `rm -rf` on the cache instead.

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
on purpose, in the repository config. `--force` does not touch a value set at
a level that outranks the repository config (a worktree's own config, the
command line, the environment): it changes nothing, exits 1 and names the
command that removes it. The script reports the hooks as active only when both
hook files exist and are executable and the value git will really use in that
worktree is `.githooks`.

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
`claude plugin list --json` shows it is missing; if the listing fails or has
a row the hook cannot identify, it warns and installs nothing. It never updates an installed copy and prints
the installed version to stderr. A plugin it installs loads in the next
session, or after `/reload-plugins`. The plugin cannot be pinned, so
`.claude/settings.json` turns off auto-update for its marketplace; what
that does and does not prevent is in [CLAUDE.md](CLAUDE.md) (Guardrails).
Update on purpose with
`claude plugin update mattpocock-skills@claude-plugins-official`.

`git rebase` creates commits without running either hook, and so do
`git cherry-pick` and `git revert` when they apply without a conflict. After
a conflict, `git cherry-pick --continue` and `git revert --continue` do run
`pre-commit`; `git rebase --continue` does not, and the only rebase commit a
hook sees is one an interactive rebase stops to `reword` (observed with git
2.56.1). CI (`.github/workflows/ci.yml`) scans the checked-out tree on pull
requests and `main` and is the backstop for the unscanned ones. Identifier and credential rules are in
[CLAUDE.md](CLAUDE.md) (Secret scanning) and [SECURITY.md](SECURITY.md).
Never write a literal maintainer home or workspace path; use
`<workspace>`, `<project-root>`. Example credentials must look fake
(`sk_test_REPLACE_ME`).

## Tests

The test harness refuses to run outside a temp directory. The rule "never
write into the real `~/.claude` or the real plugin data directory" is held by
the sandbox guard in `scripts/test-support/`, not by each test remembering an
override.

### The sandbox guard

Every bats file loads `sandbox-guard.bash` as the first line of `setup()`
(and of `setup_file()` when it has one), and every Python tests package
installs `sandbox_guard.py` from its `__init__.py`, so the guard runs before
any test. Importing any `tests` package therefore changes the whole process:
it rewrites `os.environ` and wraps `unittest.TestCase.run`. The guard:

- replaces `HOME` with a fresh directory under the temp directory;
- gives `CLAUDE_CONFIG_DIR`, `CLAUDE_PLUGIN_DATA`, `SPAWN_SESSIONS_DIR`,
  `SPAWN_PROJECTS_DIR` and `SPAWN_CONFIG_FILE` a default beside it when they
  are unset, so a test that forgets one lands in the sandbox;
- refuses to run when one of them is exported and is not a clean absolute
  path that resolves under a temp directory, or is no longer set and under
  one when a test starts:

```
WARNING: CLAUDE_PLUGIN_DATA is unset; this test would WRITE into the real plugin data directory. Refusing.
```

- refuses a `CLAUDE_CODE_PROJECT_DIR_NAME` that is a path (a slash, a
  backslash, `..` or `.`) and leaves a plain or unset one alone: the dream
  library joins that name onto the config directory as written.

"Clean" means no control character and no relative or `~` form: a value is
taken as written, never expanded. "A temp directory" is `TMPDIR` (which must
exist), `/tmp`, and on macOS the per-user directory `mktemp -d` uses. A
`TMPDIR` elsewhere under the home directory is fine. One that contains the
home directory, or is or is inside `~/.claude`, is refused, because a path
under it proves nothing.

The safe command is the documented one below, run with none of those
variables exported. If a shell exports one (a non-default
`CLAUDE_CONFIG_DIR`, for example), unset it for the run:

```bash
env -u CLAUDE_CONFIG_DIR -u CLAUDE_PLUGIN_DATA <the test command>
```

A value that already resolves under the temp directory is kept, which is how
CI passes its own `CLAUDE_CONFIG_DIR`.

When adding tests:

- A new bats file starts `setup()` with
  `load '../../../scripts/test-support/sandbox-guard'` (adjust the `../` to
  reach the repository root). A `setup_file()` starts with the same line.
- A new Python test directory copies `__init__.py` from an existing one and
  fixes the `parents[N]` depth.
- A script that reads a new path variable gets that variable added to both
  guard files.

`scripts/tests/test_sandbox_guard.py` fails when a bats file or a Python
test directory does not load the guard, and runs each suite against a decoy
path to prove it refuses.

What the guard does not catch:

- A test that hands a child process its own environment (`env=` in Python,
  a `NAME=value command` prefix in bats). That value is not checked.
- A bats spec that points a guarded variable at a real path after the guard
  loaded. `claude_sandbox_assert` re-runs the check.
- A Python test that points a guarded variable at a real path and restores it
  before returning. The check runs before each test, not during one.
- A Python test file run by path (`python3 tests/test_x.py`), which skips the
  package `__init__.py`. Run it through `unittest discover` or as a module.
- `CLAUDE_PLUGIN_ROOT`, which the scripts only read from.
- Anything the code under test reads without going through one of these
  variables. `lib/dream/claude_env.py` reads the repository's own
  `.claude/settings.json` and `.claude/settings.local.json` and the
  managed-policy settings file; an environment guard cannot redirect those.

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
`scripts/evict-plugin-cache.sh`, `scripts/test-support/`, `.gitignore`,
`.claude/settings.json`, `.claude/hooks/install-plugins.sh`, or the CI
workflow. Also when adding a bats file or a Python test directory
anywhere in the repository: the sandbox guard specs check that it loads the
guard, and run the bats half only when `bats` is on `PATH`. The hook
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
      marketplace checker, a hook in `.githooks/`, a `scripts/*.sh` file,
      `.claude/settings.json` or `.claude/hooks/install-plugins.sh` changed
- [ ] `evals/run.sh` when `improve-prompt` changed (manual); eval index
      check when cases changed
- [ ] User data is not stored in the plugin tree (`${CLAUDE_PLUGIN_DATA}`
      instead); no maintainer home/workspace paths; example secrets are fake
