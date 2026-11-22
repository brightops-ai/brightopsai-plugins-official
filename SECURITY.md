# Security

This repository is a public MIT marketplace. It ships 1Password CLI workflows,
Facebook Marketplace browsing via Playwright, and document upload to grok.com.

## Reporting a vulnerability

Report through GitHub private vulnerability reporting on this repository:
Security → Advisories → Report a vulnerability, or open a draft advisory at
<https://github.com/brightops-ai/brightopsai-plugins-official/security/advisories/new>.

Do not open a public issue for a vulnerability. This project does not list a
security email.

## Example credentials

Example secrets in this repo must be obviously fake (`sk_test_REPLACE_ME`), not
realistically shaped. If a scanner rule fires, change the value or add a
rule-scoped allowlist — not a path allowlist.

## Plugin data

User data belongs in `${CLAUDE_PLUGIN_DATA}`, not inside the plugin tree. Files
written into an installed plugin directory are orphaned by the next version
bump. `${CLAUDE_PLUGIN_DATA}` survives updates and is removed when the plugin
is uninstalled from every scope.

## 1password

The `1password` skill reads vault values at runtime with `op` (`op read`,
`op run`, `op inject`). It tells the agent not to paste secrets into logs,
chat, or code, and not to write secret values into tracked files. New items
go into a vault with `op item create`; the user supplies the value. `op inject`
can render a local config from a template — that output is the user's file,
not something this marketplace tracks.

The `ssh-keys` skill keeps private SSH keys in 1Password. The 1Password SSH
agent (`SSH_AUTH_SOCK`) signs; private keys are never written to disk. Public
keys may be written under `~/.ssh/` for `ssh-copy-id` or GitHub.

## marketplace-scout

`marketplace-scout` automates browsing Facebook Marketplace with Playwright
(login in the browser, search, scrape listings, write CSV and images under
`${CLAUDE_PLUGIN_DATA}`). That automation may conflict with Facebook's terms.
The user is responsible for how they run it.

## adversarial-review

`adversarial-review` uploads the named working document to grok.com as a Grok
project source and submits a review prompt.

Before any upload it runs
`plugins/adversarial-review/skills/adversarial-review/scripts/scan-secrets.sh`
on that file:

- Prefers `gitleaks` on `PATH`. If the file sits in a git work tree whose root
  has `.gitleaks.toml`, that config is passed through; otherwise gitleaks
  defaults apply.
- If gitleaks is absent, a bundled high-confidence Python fallback runs and
  prints a `FALLBACK` line. It is not a substitute for gitleaks.
- Exit 0: continue. Exit 1: hit — stop, do not open Grok, do not upload.
  Exit 2: scanner error — stop, do not upload.

A clean scan is not clearance. Do not send documents that contain secrets or
confidential material.

## Secret scanning in this repository

Two gitleaks hooks in `.githooks/`, activated by
`./scripts/install-hooks.sh` (`core.hooksPath`), scan staged changes:
`pre-commit` for `git commit`, and `pre-merge-commit` for the commit an
automatic merge creates. Git does not clone hooks, so a fresh clone has no
local scan until that script runs; a new Claude Code session opened in the
clone runs it when the session starts. The script leaves an existing
`core.hooksPath` that points elsewhere alone and exits non-zero; in that
clone the hooks are not active.

The hooks fail closed. If `gitleaks` is not on `PATH`, they block the commit
and print install instructions. If the scan cannot complete (a missing or
malformed `.gitleaks.toml`, a broken `gitleaks`), they block and say that the
scan failed, which is different from a finding.
`ALLOW_UNSCANNED_PUBLIC_COMMIT=1` is the explicit override for a human who
accepts an unscanned commit. It applies only when the scanner is missing; it
never overrides a finding or a failed scan.

The hooks do not cover every way a commit is made. `git rebase`,
`git cherry-pick` and `git revert` create commits without running either
hook, and `--no-verify` skips them. The CI scan below is the backstop for
all of those.

CI (`.github/workflows/ci.yml`) also scans the checked-out tree on pull
requests and pushes to `main` with `gitleaks detect --no-git` and
`.gitleaks.toml`. That scan does not depend on the hook.
