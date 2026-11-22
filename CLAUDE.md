# BrightOps AI Plugins — Claude Code Plugin Marketplace

## Project Structure

`.claude-plugin/marketplace.json` — plugin registry (update when adding/removing plugins)
`plugins/<name>/.claude-plugin/plugin.json` — plugin metadata (name, version, description, author)
`plugins/<name>/skills/<skill>/SKILL.md` — skill definition with YAML frontmatter
`plugins/<name>/skills/<skill>/references/` — supporting docs loaded on demand
`plugins/<name>/skills/<category>/<skill>/SKILL.md` — categorised variant; every such path must be
listed in the plugin manifest's `skills` array. Default discovery only finds top-level `skills/`;
an omitted nested skill installs, validates, and loads with no error (verified 2026-09-05 on Claude
Code 2.1.261). Packaging gates and the
human checklist: [CONTRIBUTING.md](CONTRIBUTING.md).

## Current Plugins

- 1password — 2 skills: 1password, ssh-keys
- agent-teams — 1 skill: agent-teams
- adversarial-review — 1 skill: adversarial-review
- marketplace-scout — 1 skill: marketplace-scout
- brightops-ai-skills — 8 skills: improve-prompt, calibrate-style, dream,
  improve-memory, session-analysis, send-result, spawn-session,
  blast-radius-audit

## Adding a New Skill

BrightOps AI workflow skills go into the existing `brightops-ai-skills` plugin, not a new plugin
each. Add the skill under a category subdirectory and list its path in the plugin manifest's
`skills` array. A separate plugin is only for a tool integration with heavy external dependencies
— a CLI, browser automation, an MCP server. Steps, tests, and the PR checklist:
[CONTRIBUTING.md](CONTRIBUTING.md).

## Conventions

- SKILL.md frontmatter `description` depends on how the skill is invoked:
  - Model-invocable (no `disable-model-invocation`): third person carrying trigger phrases — "This
    skill should be used when the user asks to..." The trigger list exists to drive model matching.
  - User-invoked (`disable-model-invocation: true`): a single short line. The model cannot invoke
    the skill, so the description is only a picker label and a trigger list is dead weight.
  - **Exception — a skill meant to run on a schedule must not set the flag.**
    `disable-model-invocation` also prevents a scheduled task from firing the skill (Claude Code
    v2.1.196+), so a scheduled routine would fire and do nothing, reporting no error. `dream` is
    the case in this repo: it is person-driven but omits the flag and carries a trigger-phrase
    description deliberately. Do not "correct" it to match the other skills.
  - **Exception — `blast-radius-audit` is model-invocable and portable on purpose.** It
    is meant to be run by any agent, including spawned and delegated ones, and to work
    when its folder is copied into another agent's skills directory. Its frontmatter
    therefore carries only Agent Skills standard fields (`name`, `description`,
    `compatibility`): no `disable-model-invocation`, `argument-hint` or other Claude
    Code-only keys, and its body names no Claude-specific tool or `${CLAUDE_*}`
    variable.
- SKILL.md body uses imperative form, not second person
- Keep SKILL.md under ~2,000 words; move detailed content to references/
- No duplication between SKILL.md body and reference files
- `plugin.json` is the sole version pin. Bumping it is what makes `/plugin update`
  see a new release. Land the bump and an entry in `plugins/<name>/CHANGELOG.md` in
  the same change. A marketplace-level change (added or removed plugin, install
  command, shared tooling) gets an entry in the root `CHANGELOG.md`. The README
  plugin table is a checked mirror; marketplace entries omit `version`. Cache
  eviction (`scripts/evict-plugin-cache.sh <name> <old-version>`, never a
  hand-written `rm -rf`) and the rest of the bump procedure:
  [CONTRIBUTING.md](CONTRIBUTING.md)

## Testing

The test harness refuses to run outside a temp directory. Every suite loads
the sandbox guard in `scripts/test-support/` before its first test. The guard
points `HOME` at a fresh temp directory, defaults `CLAUDE_CONFIG_DIR`,
`CLAUDE_PLUGIN_DATA` and the spawn-session overrides beside it, and fails with
`WARNING: … Refusing.` when one of them resolves anywhere else. It exists
because one test leaked into the real plugin data directory during
development, which is silent and only found by looking.

Run the suites with the commands in [CONTRIBUTING.md](CONTRIBUTING.md). When a
refusal names a variable the shell exports, prefix the command with
`env -u <NAME>`. A new bats file loads the guard as the first line of
`setup()` (and of `setup_file()`); a new Python test directory installs it
from `__init__.py`.
`scripts/tests/test_sandbox_guard.py` fails when either is missing. What the
guard does not catch is listed in CONTRIBUTING.md (Tests).

Commands (dream unittest, the `blast-radius-audit` collector unittest, bats
`--unit` and full, `scripts/tests`, evals as manual), packaging gates (`python3 scripts/check-marketplace.py`,
`claude plugin validate . --strict`), `/reload-plugins`, and the PR checklist:
[CONTRIBUTING.md](CONTRIBUTING.md). The packaging gate is
`.github/workflows/ci.yml` (pull requests and `main`). Behavioural evals stay
manual.

## Gotchas

- Plugin cache is version-keyed — edits to files without a version bump won't be picked up
- Observed once on Claude Code 2.1.261 (2026-09-05): `claude plugin uninstall` then
  `claude plugin install` of the same plugin in the same config dir (directory marketplace)
  left the plugin listed as installed and enabled with no errors, yet subsequent sessions
  loaded no plugin until a fresh config dir was used. Cause not established; try a fresh
  config/cache before debugging the manifest.
- Never store user data inside a plugin directory; it is orphaned by the next version bump. Use
  `${CLAUDE_PLUGIN_DATA}`, which survives updates (but is removed when the plugin is uninstalled
  from all scopes)
- plugin.json is the version pin; marketplace entries omit `version`
- Remote: `brightops-ai/brightopsai-plugins-official` on GitHub (public)

## Agent skills

This block is in-repo coding-agent configuration (mattpocock-skills issue
tracker, triage, and domain conventions), not marketplace plugin-user docs —
see [docs/README.md](docs/README.md).

### Issue tracker

GitHub Issues on `brightops-ai/brightopsai-plugins-official` via the `gh` CLI.

### Triage labels

Canonical five-state vocabulary — `needs-triage`, `needs-info`,
`ready-for-agent`, `ready-for-human`, `wontfix` — label strings unchanged.

### Domain docs

Single-context: one `CONTEXT.md` and one `docs/adr/` at the repo root, created
lazily by `/grill-with-docs`.

### Long-form conventions

The `gh` recipes, the wayfinder operations, the PR-triage flag and the
domain-doc consumer rules are the same in every repo, so they live once in the
engineering-docs repo cloned beside this one and are imported here:

@../engineering-docs/agents/skills.md

A clone without that repo beside it — a cloud session, a laptop — sees only
this block. That is enough for `/to-spec`, `/to-tickets` and `/triage` on a
GitHub repo with the canonical labels. `/code-review` will notice that
`docs/agents/issue-tracker.md` is absent and offer to re-run setup; decline,
and it falls back to asking.

### Secret scanning

This repo is **public-bound**. Gitleaks hooks for `git commit` and merge
commits (`.githooks/`, activated by `./scripts/install-hooks.sh`) enforce
[`.gitleaks.toml`](.gitleaks.toml), which blocks infrastructure identifiers on
top of the default secret rules — workspace name, tailnet hosts/IDs/IPs,
home-directory paths, LAN IPs, AWS account IDs.

Two consequences for anything written here, including docs:

- **Never write a literal absolute path to the maintainer's home or workspace.**
  Use `<workspace>`, `<project-root>`, `<tailnet-host>`. Real names in design
  rationale are fine — an ADR that can't say what drove a decision is worse.
  Identifiers are what get placeholdered.
- **Example credentials must look fake** (`sk_test_REPLACE_ME`), not
  realistically shaped. If a rule fires, fix the value or add a *rule-scoped*
  allowlist; don't add a path allowlist and don't use `--no-verify` (a deny
  rule refuses it; see Guardrails below).

Git never clones hooks. A new Claude Code session runs
`./scripts/install-hooks.sh` from the SessionStart hook
`.claude/hooks/install-plugins.sh`. In any other fresh clone assume the local
pre-commit gate is inactive until that script has run. CI still
scans the tree on pull requests and `main` (`.github/workflows/ci.yml`).

The hooks fail closed: without `gitleaks` on `PATH`, or when the scan cannot
complete, they block the commit. Install gitleaks (the hook prints how).
`ALLOW_UNSCANNED_PUBLIC_COMMIT=1` is a human's override for the missing-scanner
case only; an agent never sets it. `install-hooks.sh` never replaces an
existing `core.hooksPath` unless run with `--force`.

Commits that no hook scans, so CI is the only scan for them (observed with git
2.56.1; `scripts/tests/test_commit_hook_coverage.py` holds the fixture):

- `git rebase`, including `git rebase --continue` after a conflict. The one
  exception is a commit an interactive rebase stops to `reword`.
- `git cherry-pick` and `git revert` when they apply without a conflict.

After a conflict, `git cherry-pick --continue` and `git revert --continue` do
run `pre-commit`, as `git commit` does.

### Guardrails

`permissions.deny` in [`.claude/settings.json`](.claude/settings.json) holds
tripwires for a Claude Code session opened here. A deny rule refuses a command
by its text, so it catches the usual spelling and nothing more. It is not a
security boundary, and other agents do not read the file. The second column
names the control that holds each rule when the tripwire is stepped around.

| Rule | What holds it | What the tripwire refuses | Do this instead |
|---|---|---|---|
| No push to `main` | Branch protection on `main`: pull request and one approval. Administrators are exempt (checked 2026-11-22) | `git push` and `git -C <dir> push` with `main` as its own word; `git push` with `<src>:main`, or with `refs/heads/main` as its own word or straight after a `:` or `+`; `git push` with `--all` or `--mirror` | `git push -u origin <branch>`, then `gh pr create` |
| No force push | Branch protection refuses a force push to `main`. Nothing holds other branches | `git push` with `--force` or `-f` as its own word | `git push --force-with-lease origin <branch>`, on your own branch only |
| No commit that skips the secret scan | The pre-commit hook scans what is staged. CI scans the tree on every pull request and on `main`, so a skipped hook is caught before merge | `--no-verify` anywhere after `git commit` or `git -C <dir> commit`; `-n` as its own word after `git commit` | Fix what the hook flagged, then `git commit` |
| No agent started with a permission-bypass flag | Nothing else | `claude` with `dangerously-skip-permissions` or `bypassPermissions` in its arguments; `codex` with `--yolo` or `--dangerously-bypass-approvals-and-sandbox`; `gemini` with `yolo` anywhere (`--yolo`, `--approval-mode=yolo`) or `-y` as its own word | Start it in its default permission mode |
| No printing the environment or a token | Nothing else | `env` alone, `env -0`, `env --null`; `printenv` with or without a name; `gh auth token`; `gh auth status` with `--show-token` anywhere, or `-t` as its own word | `[ -n "${VAR:-}" ]` tests one variable; `gh auth status`; `env VAR=value command` still runs |
| No reading files that hold real environment values | Nothing else | Read, Edit, Write and `cat`-style commands, at any depth, on `.env`, `.env.local`, `.env.*.local`, `.env.development`, `.env.production`, `.env.staging`, `.env.test`, `.env.dev`, `.env.prod` | Keep key names with fake values in `.env.example`, `.env.sample` or `.env.template`, which stay readable and writable |
| No send, share or delete through a connector | Nothing else | Under any account suffix (observed 2026-11-22): Gmail send, reply, forward, trash, delete draft, delete label; Slack send and schedule message; Google Drive share, trash, request access; Google Calendar create, update, delete, respond | Use the draft tool, or hand the text to the user |

Known misses, none of them matched:

- Any of the above run by path (`/usr/bin/git`), inside `bash -c` or `sh -c`,
  from a script, or by another agent.
- Pushes: a bare `git push` from a local `main`; `+main`; `git -c <key>=<value>
  push`; `git -C <dir> push` with a refspec, `--all`, `--mirror` or a force
  flag.
- Short flags joined to others: `git push -fu`, `git commit -nm`,
  `gh auth status -at`. Also `git -C <dir> commit -n`.
- Environment: `env -u NAME`, `export -p`, `set`, and any program that reads
  its own environment.
- Environment files under other names (`.env.qa`, `.envrc`), and any program
  that opens the file itself.
- Connectors other than the four named; Slack canvases and reactions.

Known false positives: a commit message that contains `--no-verify`, or `-n`
as its own word, is refused; write the message to a file and use
`git commit -F <file>`. A ref whose name contains `--all` or `--mirror` cannot
be pushed by that name. A branch whose name merely ends in `refs/heads/main`
(`feature/refs/heads/main`) and a `gh auth status --hostname` value that ends
in `-t` are no longer refused: those rules need a word boundary first
(`scripts/tests/test_agent_settings.py`).

The SessionStart hook runs for a new session only (the `startup` matcher), not
on resume, `/clear` or compaction. The registered command finds it through
`CLAUDE_PROJECT_DIR` or, when that is unset, at the root of the checkout the
session started in, so a session started in a subdirectory still runs it. It installs `mattpocock-skills` only when
`claude plugin list --json` succeeds and shows no install that applies to this
project; if the listing fails, cannot be parsed, or has a row it cannot
identify (no `id`, or a project row for the plugin with no absolute
`projectPath`), it warns and installs nothing. It never updates an installed copy and prints the installed version
to stderr. A plugin it installs loads in the next session, or after
`/reload-plugins`.

The plugin cannot be pinned: `claude plugin install` takes no version
(Claude Code 2.1.330), and a commit `ref` is refused for a reserved
marketplace name such as `claude-plugins-official`. That marketplace
auto-updates by default, so `.claude/settings.json` sets `"autoUpdate": false`
on its entry. That holds for sessions that read this file after the folder is
trusted. A session in another project on the same machine can still update the
shared on-disk copy, and this repo then loads the new version; the version line
on stderr is how that shows. Update on purpose with
`claude plugin update mattpocock-skills@claude-plugins-official`.

[`.github/CODEOWNERS`](.github/CODEOWNERS) names the reviewer for every path.
A code-owner review is required only if branch protection asks for it, which
is a repository setting that is off today (checked 2026-11-22).
