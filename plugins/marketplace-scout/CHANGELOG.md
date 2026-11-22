# Changelog

All notable changes to this plugin are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.3.0] - 2026-11-22

### Security

- Ship `package-lock.json` beside the dashboard's `package.json` and install
  with `npm ci --ignore-scripts` instead of `npm install` (#81). A first run
  now installs exactly the pinned, integrity-checked versions and runs no
  dependency's install script with the user's environment. Before, every new
  install resolved the caret ranges to the newest matching releases.
- `ensure-dashboard.sh` exits 1 before creating anything when the plugin's
  dashboard assets have no `package-lock.json`.
- No install script is allowed or needed: `npm ci --ignore-scripts`,
  `npm run build` and `npm run dev` were checked on macOS arm64 with Node 26.
  The only locked package that declares one is the optional `fsevents`, which
  ships a prebuilt binary.
- An already scaffolded `${CLAUDE_PLUGIN_DATA}/dashboard` that has
  `node_modules` is left as it is; the lockfile applies to new scaffolds.

### Fixed

- A failed install no longer poisons the target. `ensure-dashboard.sh` used
  to create the target before installing and then accept any existing target,
  so one failed `npm` run made every later run report success with nothing
  installed. The scaffold and the install now happen in a sibling staging
  directory and are renamed into place only after both succeed. A failed or
  interrupted run exits 4 (interrupts: 130 or 143), leaves the target as it
  was, and removes its staging directory; the next run tries again.
- A target without `node_modules` is now completed on a later run instead of
  being reported as present. This is what an ordinary run does after a
  scaffold made with `SKIP_NPM_INSTALL`: it installs the dependencies into
  that target and touches no other file. A complete target is never
  reinstalled or overwritten.
- A target scaffolded before the lockfile shipped, with no `node_modules`,
  gets the plugin's lockfile only if its `package.json` is still the
  plugin's; otherwise the script exits 1 and does not install unpinned.
- A destination that appears while a run is working is never nested into.
  `mv` moves its source into a directory that already exists, so a target or
  `node_modules` created between the existence check and the move used to
  end up holding the scaffold as a subdirectory, with exit 0. The move now
  uses a source name no destination can contain, checks the result, takes
  anything nested back out, and exits 5.
- Symlinks and unexpected entry types are refused (exit 1) instead of
  followed or misread: a target that is a symlink or not a directory, a
  `package.json` or `package-lock.json` that is a symlink (a dangling link
  used to have the lockfile written through it to wherever it pointed), and a
  `node_modules` that is a symlink or a regular file (which used to count as
  installed). A lockfile is written only where nothing exists.
  The target path is normalised first: a trailing `/` or `/.` resolves
  through a symlink, so `link/` used to pass where `link` was refused.

## [1.2.0] - 2026-09-05

### Changed

- Scaffold the dashboard and store CSVs, `searches.json`, and images under
  `${CLAUDE_PLUGIN_DATA}` instead of `./dashboard/` and `./data/` in the
  project cwd. Leftover cwd copies are detected and never deleted.

## [1.1.3] - 2026-09-05

### Changed

- Move CSV schema, grading output rules, `searches.json` shape, and
  anti-detection timings out of `SKILL.md` into `references/csv-schema.md`
  and `references/anti-detection.md`.

## [1.1.2] - 2026-09-05

### Added

- Declares a dependency on `playwright` from `claude-plugins-official`.
  No semver pin: upstream `plugin.json` has no version, and the MCP
  tool-name prefix is not version-sensitive.

## [1.1.1] - 2026-09-05

### Added

- Discover metadata: `displayName`, `homepage`, `repository`,
  `license`, `keywords`, and a plugin `LICENSE`.

## [1.1.0] - 2026-09-05

### Added

- Baseline: released as 1.1.0. Ships the `marketplace-scout` skill.
