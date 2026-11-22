# Changelog

All notable changes to this plugin are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.3.1] - 2026-11-22

### Security

- The dashboard's `zod` moves from 3.25.76 to 4.6.7 (`^4.6.6` in
  `package.json`), which clears GHSA-mrhx-c7xc-m3w5, the one high-severity
  advisory `npm audit` reported on the shipped lockfile (#93). The advisory
  covers every release below 4.6.6 and names no patched 3.x, so the major was
  the only fix. `npm audit` on the new lockfile reports no advisory of any
  severity.
- The dashboard was not exposed. The advisory is about parsing an oversized
  array, set or map. The two schemas in `src/types/listing.ts` are the only
  zod code in the dashboard, and nothing calls `parse` or `safeParse` on them;
  `searches.json` is read with a type annotation only.
- If those schemas are ever used to parse, give their arrays a `.max()`. The
  fix in 4.6.6 rejects an input that is over a declared upper bound before
  walking its elements. An array schema with no upper bound, which is what
  both schemas have, still collects one issue per bad element.
- No schema code changed: the calls the two schemas make are the same in
  zod 4. Run against both releases, they accept and reject the same inputs
  with one exception, which zod's migration guide lists: `z.number()` no
  longer accepts `Infinity`.
- zod stays a single copy. `eslint-plugin-react-hooks` and
  `zod-validation-error` (lint only) accept `^3.25.0 || ^4.0.0` and share it.
- An installed `${CLAUDE_PLUGIN_DATA}/dashboard` (one that has
  `node_modules`) is left as it is and keeps the zod it was installed with,
  as in 1.3.0; given the above there is nothing to act on. To move it
  anyway, delete its `node_modules` and run the skill again: see the next
  section for when that brings in the new versions.

### Changed

- A dashboard that was scaffolded by an earlier release and never installed
  is moved to this release's pinned dependencies when `ensure-dashboard.sh`
  installs into it. That covers a scaffold from before the lockfile shipped
  whose install failed, a 1.3.0 scaffold made with `SKIP_NPM_INSTALL`, and
  an installed dashboard whose `node_modules` was deleted. Its `package.json`
  and `package-lock.json` are replaced with this release's, and the script
  says so, only when each is byte-identical to a file an earlier release
  shipped (matched by sha256 against a list in the script), so no edit is
  lost. No other file in the dashboard is touched. Without this, changing
  the shipped `package.json` would have made the script refuse every
  never-installed pre-lockfile scaffold, and a never-installed 1.3.0
  scaffold would have installed the old lockfile and zod 3.25.76.
- A `package.json` or `package-lock.json` that was edited is never
  replaced. With a lockfile of its own the dashboard installs from the two
  files it holds, as before. With no lockfile it is refused (exit 1), as
  before.
- Nothing in the dashboard is touched until `npm ci` has succeeded in the
  staging directory, so a failed install (exit 4) leaves it as it was. After
  the install the script checks again that both files are what the install
  was planned against and that no `node_modules` has appeared. If anything
  changed while `npm` ran, it exits 5 and the dashboard is byte for byte as
  it was. This also holds for a dashboard that installs from its own pair.
- A file is never replaced where it stands. It is moved out of the
  dashboard, what was moved is checked, and only then is the new file linked
  into the empty path, which cannot overwrite anything and never shows a
  partial file. Both old files go out before either new one goes in, and
  `node_modules` arrives last. If a file turns out to have been edited at
  the last moment, or a step fails, everything is put back and the run exits
  5 (4 when a file could not be written). The message names each file and
  what happened to it.
- An edit is kept even when its path has been filled by something else
  before it could be put back: it is saved beside the path as
  `<name>.set-aside.<id>` and reported.
- `SIGINT`, `SIGTERM` and `SIGHUP` that arrive during those few steps are
  held until the steps are complete or undone, then the run exits 130 or
  143. A run killed outright (`SIGKILL`, power loss) in that moment can leave
  a file out of the dashboard; it is in the staging directory beside it, and
  the next run puts it back before doing anything else. That staging
  directory is not deleted by the next run, which says when it can be.
- The lockfile is no longer written through to its final name, so an
  interrupted write cannot leave a partial `package-lock.json` (1.3.0 could).
- An unreadable `package.json` or `package-lock.json` is reported as
  unreadable (exit 1).
- Recognising an earlier release's file needs `sha256sum` or `shasum`. With
  neither, such a file counts as edited.
- What is not covered. A file that is not being replaced is checked after
  the install but not again: an edit to it in the instant between that check
  and the end of the run is not noticed. A program that already has a file
  open can still write to it after it was moved out and checked. On a
  filesystem without hard links the new file is renamed into place instead,
  and a file created at that path in the instant between the check and the
  rename can be overwritten. `node_modules` is still moved in with the
  check-then-rename that 1.3.0 uses.
- The production bundle grows from about 467 kB to 499 kB (126 kB to 138 kB
  gzipped): zod 4 is larger and both schemas are still built at load.

### Added

- `tests/test_dashboard_lockfile.py`: offline checks that the locked zod and
  the declared range stay at or above 4.6.6, that one zod copy satisfies
  every package that asks for it, that the lockfile root matches
  `package.json`, and that every package resolves from the public npm
  registry with a sha512 integrity. It also fails when `package.json` or
  `package-lock.json` changes without its sha256 being appended to the list
  in `ensure-dashboard.sh`.
- `tests/fixtures/`: the `package.json` files earlier releases shipped and
  the 1.3.0 lockfile, byte for byte, so the specs for the cases above do not
  depend on the revision under test.
- `tests/ensure-dashboard.bats` goes from 21 to 60 specs: the earlier-release
  cases, each thing that can change, fail or stop while the two files are
  exchanged, and each state a killed run can leave with what the next run
  does.

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
