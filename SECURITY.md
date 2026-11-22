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

The `1password` skill follows 1Password's guidance that an agent acts on
secrets without handling them. Its default is `op run` with secret references:
the value is resolved for one subprocess and concealed in that subprocess's
output. `op read` and `op inject` are the exception, for a consumer that
cannot take a secret from an environment variable. The skill tells the agent
not to paste secrets into logs, chat, or code, not to run a command that
prints a secret value, and not to write secret values into a work tree.

A new secret does not pass through the agent. The user enters it in the
1Password app or in an item template they edit, or 1Password generates it;
the skill forbids an assignment statement that carries a value. A rendered
config or key file goes to a private temporary directory outside every git
work tree and is removed afterwards. For agent tools and MCP servers the
skill points to 1Password Environments and to launching the server through
`op run` instead of putting a token in its config file. These are
instructions to the agent, not a technical boundary.

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

The skill does not read the document before it is scanned. It resolves the
path and project from metadata, takes a snapshot, scans the snapshot, and
opens the content only after a clean scan, from the snapshot. A document with
a secret in it is refused before its content can enter the session
transcript; on a hit the skill reports the rule and line and does not open
the file to look.

The scan, the user's approval and the upload act on the same bytes.
`scripts/snapshot-document.sh` copies the document, read-only, into a private
temporary directory and reports its sha256. That snapshot is what is scanned,
read, named in the confirmation, and uploaded. In the command just before
each send the script checks that the snapshot still has the approved sha256
and that the source has not changed since; if either fails, nothing is sent
and the cycle starts again. Snapshots are removed on every way out of a run.

Before any upload the skill runs
`plugins/adversarial-review/skills/adversarial-review/scripts/scan-secrets.sh`
on the snapshot:

- Prefers `gitleaks` on `PATH`. If the source document sits in a git work tree
  whose root has `.gitleaks.toml`, that config is passed through; otherwise
  gitleaks defaults apply.
- If gitleaks is absent, a bundled high-confidence Python fallback runs and
  prints a `FALLBACK` line. It is not a substitute for gitleaks.
- Exit 0: no pattern matched — continue to the confirmation below. Exit 1:
  hit — stop, do not open Grok, do not upload. Exit 2: scanner error — stop,
  do not upload.

A clean scan is not clearance. Do not send documents that contain secrets or
confidential material.

The skill asks the user for an explicit answer at each point where content
could leave the machine:

- After a clean scan and before opening Grok: the file, the snapshot's sha256
  and size, and the intended project. With no user to answer — a headless,
  scheduled, or delegated run — it stops here.
- Once the site is open and before a project is created or content is sent:
  the account actually signed in and the project, an existing project by its
  identifier and not its name alone. The first answer is given before the
  account is known, so it does not cover this; the question is never skipped.
- Before the re-upload that follows edits: the edited document is new content
  and gets a new snapshot, scan and confirmation.
- Before the inline fallback, which pastes the document into the chat when
  Grok cannot read the uploaded file. The answer covers the exact text to be
  pasted; a truncated version gets its own snapshot and scan first.

An approval covers one sha256 and one destination. Because the active
account can change after it was approved, the skill re-reads the account and
the project identifier on the sending tab immediately before each send
(upload, re-upload, inline paste), ahead of the byte check; a destination
that differs or cannot be read stops the send and the question is asked
again. The skill does not
pre-approve the Playwright upload tool, so the session's own permission rules
apply to each upload. The inline fallback has to go through a browser tool the
skill does pre-approve; the explicit answer is the only gate on it. The
confirmations are instructions to the agent and the permission is a default
the user can change; neither is a technical boundary, and an upload cannot be
recalled.

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

The hooks do not cover every way a commit is made. `--no-verify` skips them.
Assume a commit made by `git rebase`, `git cherry-pick` or `git revert` was not
scanned locally either: git runs `pre-commit` for only some of them. With git
2.56.1 it runs for `git cherry-pick --continue` and `git revert --continue`
after a conflict, for a commit an interactive rebase stops to `reword`, and
for a merge a `--rebase-merges` rebase re-creates with `merge -c`. It does not
run for a clean cherry-pick or revert, for a rebase's picks, `squash` and
`fixup`, for `git rebase --continue`, or for `merge -C`.

CI (`.github/workflows/ci.yml`) also runs `gitleaks detect --no-git` with
`.gitleaks.toml` on pull requests and pushes to `main`. That scan does not
depend on the hook, and it is not a scan of commits: it reads the files in
the tree it checks out, not history. It catches a value that is still in the
tree of a pull request or of `main`. It does not catch a value that a commit
added and a later commit removed; that value stays in the branch's history,
and in the repository's if the branch is merged without squashing.
