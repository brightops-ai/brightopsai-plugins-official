# Changelog

All notable marketplace-level changes are documented in this file:
added or removed plugins, install-command changes, and tooling that
affects every plugin. Per-plugin notes live in `plugins/<name>/CHANGELOG.md`.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and plugin versions adhere to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
The marketplace itself carries no version of its own, so sections here are dated
rather than numbered.

## [Unreleased]

### Changed

- `.githooks/pre-commit` fails closed: without `gitleaks` on `PATH` the commit
  is blocked instead of going through unscanned.
  `ALLOW_UNSCANNED_PUBLIC_COMMIT=1` is the explicit override for a human who
  accepts the risk; it never overrides a finding. The hook and
  `scripts/install-hooks.sh` no longer suggest piping an install script into
  `sh`; they print the pinned release and checksum that CI uses, plus
  `brew install gitleaks`.
- A scan that cannot complete (missing or malformed `.gitleaks.toml`, broken
  `gitleaks`) is reported as a failed scan and still blocks; it is no longer
  described as a finding.
- `scripts/install-hooks.sh` leaves an existing `core.hooksPath` that points
  elsewhere alone and exits 1; `--force` replaces it. It writes nothing when
  the hooks are already active, and reports them active only after reading
  back the effective value.
- `.gitignore` ignores `.env`, `.env.*` (except `.env.example`), `*.pem` and
  `*.key`.

### Deprecated

- `agent-teams` is deprecated and will be removed from the marketplace in
  a later release. Installed copies keep working from cache but stop
  receiving updates. A replacement skill will be published separately by
  BrightOps AI. See [ADR 0001](docs/adr/0001-plugin-consolidation-scope.md).

### Security

- `.claude/settings.json` gains a `permissions.deny` block for Claude Code
  sessions in this repo: pushes to `main`, `git push --force`, hook-skipping
  commits, agents started with a permission-bypass flag, printing the
  environment or a GitHub token, reading environment files that hold real
  values, and connector tools that send, share or delete. The rules are
  tripwires, not a boundary; `CLAUDE.md` (Guardrails) names what holds each
  rule, what the tripwire refuses and what it misses.
- `.github/CODEOWNERS` names the repository owner for every path.
- The SessionStart hook `.claude/hooks/install-plugins.sh` now runs for new
  sessions only, activates the tracked git hooks
  (`scripts/install-hooks.sh`), and installs `mattpocock-skills` only when
  the plugin listing shows it is missing, printing the installed version to
  stderr. It used to re-resolve the plugin on every session event.
  Auto-update is off for the `claude-plugins-official` marketplace in
  sessions that read this repo's settings.

### Added

- `.githooks/pre-merge-commit`: runs the same gitleaks gate on the commit an
  automatic merge creates, which `pre-commit` does not see. `git rebase`,
  `git cherry-pick` and `git revert` still run no hook; CI is the backstop.
- `scripts/evict-plugin-cache.sh <plugin> <old-version>`: removes one old
  version from the plugin cache after a version bump. It validates both
  arguments, refuses a target that does not resolve inside the marketplace
  cache, and has a `--dry-run`. It replaces the hand-filled `rm -rf` in
  `CONTRIBUTING.md`.
- GitHub Actions workflow `.github/workflows/ci.yml`: plugin validate,
  marketplace check, unit tests, shellcheck, gitleaks tree scan, and eval
  index completeness on pull requests and `main`. Behavioural evals stay
  manual.
- `CONTRIBUTING.md`: human contributing guide (skill vs plugin, categorised
  `skills` array, `plugin.json` version pin, `/reload-plugins` and the
  version-keyed cache, hooks, tests, packaging gates). Root README
  Contributing is a short pointer; `CLAUDE.md` keeps agent rules and links
  to the checklist.
- `SECURITY.md`: vulnerability reporting via GitHub Security Advisories,
  fake example credentials, `${CLAUDE_PLUGIN_DATA}`, 1Password/`op` handling,
  Facebook Marketplace terms responsibility, grok.com upload plus pre-upload
  secret scan, the gitleaks pre-commit gate (inactive until
  `./scripts/install-hooks.sh`, blocking if `gitleaks` is missing), and CI
  tree scan on pull requests and `main`.

## [2026-09-05] - Plugin READMEs

### Added

- `plugins/<name>/README.md` for every plugin: install command, namespaced
  invoke names, prerequisites, `${CLAUDE_PLUGIN_DATA}` contents, update, and
  uninstall. Version floors: `agent-teams` needs Claude Code v2.1.178+; `dream`
  scheduling needs v2.1.196+.
- `scripts/check-marketplace.py` fails when a plugin README is missing, omits
  the required headings, or when the catalog README does not link to it.

### Changed

- Root README Plugin Details sections are short summaries that point at those
  files, so prerequisite lists are not copied in a second place.

## [2026-09-05] - Playwright dependency

### Added

- `allowCrossMarketplaceDependenciesOn` includes `claude-plugins-official`
  so `marketplace-scout` and `adversarial-review` can declare Playwright as
  a cross-marketplace dependency.

## [2026-09-05] - Manifest metadata

### Added

- Marketplace `$schema`, owner URL, and `category`/`tags` on every plugin
  entry so `/plugin` Discover matches official listings.
- `scripts/check-marketplace.py` now fails when those fields drift, or when
  a marketplace description does not match `plugin.json`.

## [2026-09-05] - Baseline

### Added

- Catalog baseline: five plugins, versions from each `plugin.json` —
  1password 1.2.0, agent-teams 1.2.0, marketplace-scout 1.1.0,
  adversarial-review 1.3.0, brightops-ai-skills 1.3.1.
- Install command: `/plugin marketplace add brightops-ai/brightopsai-plugins-official`.
- Shared tooling: `scripts/check-marketplace.py` consistency check.
