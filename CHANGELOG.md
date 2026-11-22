# Changelog

All notable marketplace-level changes are documented in this file:
added or removed plugins, install-command changes, and tooling that
affects every plugin. Per-plugin notes live in `plugins/<name>/CHANGELOG.md`.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and plugin versions adhere to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
The marketplace itself carries no version of its own, so sections here are dated
rather than numbered.

## [Unreleased]

### Fixed

- `scripts/install-hooks.sh` reports the hooks active only when both
  `.githooks/pre-commit` and `.githooks/pre-merge-commit` exist and are
  executable, and the hooks directory git itself reports is `.githooks`. With
  a hook file missing it used to report the scan live. It now ignores
  `GIT_CONFIG`, which only `git config` reads and which could make it report
  a directory git does not use.
- `scripts/install-hooks.sh` leaves nothing behind when it does not succeed.
  Every check that can end in a refusal runs before anything is changed. The
  write replaces `.git/config` under git's config lock, and only if the file
  is still byte for byte what the script read; a run that fails afterwards
  puts the old bytes back the same way, and file modes are changed last. A
  refusal that said "nothing was changed" had already made the hook files
  executable. One exception is reported, not hidden: if another process
  changed `.git/config` or took its lock after the write, the file is left
  alone and the message says what was left and how to remove it. Only the
  owner's exec bit is added. The script now needs `cp`, `mv`, `rm` and `cmp`.
- `scripts/install-hooks.sh --force` no longer writes the shared repository
  config when that cannot change which value wins. It asks git for every
  `core.hooksPath` value in effect, in order, with scope and origin, so
  includes and their conditions count as git counts them. It writes when the
  winner is written in `.git/config` itself or comes from the global or
  system config, and refuses a winner from a worktree's own config, the
  command line, the environment or an included file. It used to change every
  other worktree's `core.hooksPath` and then fail. An empty value is treated
  like any other, and it refuses when git is too old (before 2.26) to say.
  Without `--force`, an empty `core.hooksPath` is no longer overwritten as if
  it were unset.
- `scripts/install-hooks.sh` compares the hooks directory exactly. A
  `core.hooksPath` of `.githooks` followed by a newline, or a relative path
  beginning with a dash, was reported as active while git ran no hook. It
  refuses a bare repository and a symlinked `.git/config`, and cannot exit 0
  without having confirmed the hooks.
- `scripts/install-hooks.sh`: when only `gitleaks version` fails, the warning
  no longer says every commit will be blocked; the hooks run their own scan.
- `scripts/install-hooks.sh --force` replaces a `core.hooksPath` that has
  several values in the repository config (`--replace-all`) instead of
  failing.
- `scripts/install-hooks.sh` and the SessionStart hook work in a checkout
  whose directory name ends in a newline.
- `scripts/evict-plugin-cache.sh` works when the cache directories are
  capitalized differently on a case-insensitive filesystem (`Plugins/Cache`).
  It used to refuse them as outside the cache. Each managed directory
  (`plugins`, `cache`, the marketplace, the plugin, the version) is now tested
  for a symlink directly, so a link is refused whatever a path resolver
  reports, and capitalization is ignored only in those five names below the
  resolved config directory.
- The guidance on what the commit hooks do not cover (`CLAUDE.md`,
  `CONTRIBUTING.md`, `SECURITY.md`, the installer's output) no longer makes a
  blanket statement about `git rebase`, `git cherry-pick` and `git revert`. It
  says to assume such a commit was not scanned locally, and lists what git 2.56.1
  was seen to do: `pre-commit` runs for `git cherry-pick --continue` and
  `git revert --continue` after a conflict, for an interactive `reword` and
  for `merge -c` under `--rebase-merges`, and not for the rest
  (`scripts/tests/test_commit_hook_coverage.py`).
- `.claude/settings.json`: the deny rules for `refs/heads/main` and
  `gh auth status -t` need a word boundary first, so a branch named
  `feature/refs/heads/main` and `gh auth status --hostname git-t` are no
  longer refused. `main`, `refs/heads/main` and `+refs/heads/main` are
  refused as the first word after `push` as well as after a remote;
  `git push main` and `git -C <dir> push main` were documented as refused and
  were not. `CLAUDE.md` (Guardrails) lists the rules, the known misses and the
  known false positives as shipped, and `scripts/tests/test_agent_settings.py`
  holds each as a command.
- The SessionStart hook `.claude/hooks/install-plugins.sh` reads the plugin
  listing as untrusted input, with a Python program it carries in the same
  file: strict JSON (no `NaN`, no duplicate keys, UTF-8), with size, nesting
  depth and number length bounded by the hook, not by the Python version;
  and in every row each field the CLI is known to emit (`id`, `scope`,
  `version`, `enabled`, `projectEnabled`, `installPath`, `projectPath`,
  `installedAt`, `lastUpdated`) must have its shape when it is there. Fields
  it does not know are left alone. Anything else makes the answer unknown: it
  warns and installs nothing. A row with no `id`, a whitespace `id`, a
  duplicate `id` key, a `NaN`, or a wrong type in another field used to
  trigger an install, and an empty `projectPath` counted as this project. A
  listing that does not answer within 20 seconds is stopped, and a project
  path is matched as a directory, so a spelling that differs only in
  capitals on a case-insensitive filesystem is the same project.
- The registered SessionStart command finds the hook from a subdirectory when
  `CLAUDE_PROJECT_DIR` is unset: it looks in the starting directory first,
  then at the root of the checkout around it. A relative `CLAUDE_PROJECT_DIR`
  that begins with a dash is no longer read as an option.
- The docs and the installer's output no longer describe the CI scan as
  covering commits the local hook did not see. CI runs
  `gitleaks detect --no-git`: it scans the files in the tree it checks out,
  not history, so it does not catch a value that one commit added and a later
  commit removed.

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

- `scripts/test-support/`: a sandbox guard that every test suite loads before
  its first test (`sandbox-guard.bash` for bats, `sandbox_guard.py` for the
  Python suites). It points `HOME` at a fresh temp directory, defaults
  `CLAUDE_CONFIG_DIR`, `CLAUDE_PLUGIN_DATA` and the spawn-session path
  overrides beside it, and refuses to run a test, with a `WARNING: … Refusing.`
  line, when one of them is not a clean absolute path resolving under a temp
  directory, or when `CLAUDE_CODE_PROJECT_DIR_NAME` is a path. The rule "tests
  never write into the real `~/.claude`" was prose until now.
  `scripts/tests/test_sandbox_guard.py` fails when a bats file or a Python
  test directory does not load the guard. CI now creates its
  `CLAUDE_CONFIG_DIR` under the system temp directory so the suites accept it.
- `.githooks/pre-merge-commit`: runs the same gitleaks gate on the commit an
  automatic merge creates, which `pre-commit` does not see. A commit made by
  `git rebase`, `git cherry-pick` or `git revert` may still go unscanned, and
  CI scans only the files still in the tree.
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
- `t3-code` plugin (0.1.0): `restart` and `1password-secrets` skills for the
  T3 Code desktop app on macOS.

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
