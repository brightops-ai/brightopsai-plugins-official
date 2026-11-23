# The repo part

What travels with the repository: the working tree, and this repository's
settings on GitHub. Everyone who clones it, and its CI, inherits these, and
most of the fixes are a pull request.

For each check: what the collector gives under `# REPO`, what to verify by
hand, what makes it a finding, and the fix. Fix *patterns* are in `fixes.md`;
this file is for the audit phase. Read `reading-safely.md` first. The other
half of several checks is in `checks-machine.md`; where a chain of harm needs
it and the machine part did not run, mark the finding suspected and name the
missing link.

## Contents

- [1. Non-local database in test, dev or preview config](#1-non-local-database-in-test-dev-or-preview-config)
- [2. Secrets and env files in the tree](#2-secrets-and-env-files-in-the-tree)
- [3. Recursive deletes with a computed target](#3-recursive-deletes-with-a-computed-target)
- [4. Infrastructure one command can destroy](#4-infrastructure-one-command-can-destroy)
- [5. Rules in the repo that exist only as prose](#5-rules-in-the-repo-that-exist-only-as-prose)
- [6. Protection of the default branch](#6-protection-of-the-default-branch)
- [7. Placeholder files and copy-then-delete scripts](#7-placeholder-files-and-copy-then-delete-scripts)
- [8. Repo-level MCP servers, hooks, skills, install scripts, hidden Unicode](#8-repo-level-mcp-servers-hooks-skills-install-scripts-hidden-unicode)
- [9. CI agents on untrusted input](#9-ci-agents-on-untrusted-input)
- [10. Project-level agent settings](#10-project-level-agent-settings)
- [11. Tools in the repo that send money or messages](#11-tools-in-the-repo-that-send-money-or-messages)

## 1. Non-local database in test, dev or preview config

**Collector:** `db-target` leads with the host classified — `local`,
`service-name` (a compose service or container alias), `private-network`,
`non-local`, `from-variable`, `unknown` — plus the env file's role (test, dev,
preview, production, example) and whether it is tracked. Also
`destructive-db-op` and `db-migrate-command` leads.

**By hand:**

- Trace where the test run gets its database. Read the test setup
  (`conftest.py`, `jest.setup.*`, `vitest.config.*`, `spec_helper.rb`,
  `phpunit.xml`, `test/setup.*`), the test script in `package.json` or the
  Makefile, `docker-compose*.yml`, and framework config
  (`config/database.yml`, `prisma/schema.prisma`, `knexfile.*`, `ormconfig.*`,
  `alembic.ini`, `settings.py`).
- Resolve `from-variable` hosts: which env file feeds them when tests run? A
  variable exported in the shell overrides the env file in most loaders; that
  half is machine check 1.
- Find what the tests do to the database: drop, truncate, reset, `migrate`,
  `db push`, fixtures loaded with delete-all.
- Check whether setup refuses a non-local host. Look for an existing guard
  before recommending one.

**A finding when:** a test, dev or preview path can resolve to a `non-local`
or `private-network` host. It is top-ranked when the same path also runs a
destructive operation and nothing aborts on a non-local host.

**Not a finding:** `.env.example` with placeholders; a production URL in a
file only the deploy pipeline reads; `service-name` hosts under compose.

**Fix (in repo):** point tests at a local or container database; add a guard
in test setup that aborts unless the host is local.

## 2. Secrets and env files in the tree

**Collector:** `env-file` (role, tracked or ignored, key count, secret-named
keys holding literal values), `tracked-sensitive-file`, `token-shaped-string`
(file:line with a label), `live-payment-key`, `settings-env` for repo-level
agent settings, `gitignore-coverage`, `instruction-prints-secret`.

**By hand:**

- Verify `token-shaped-string` leads as described in `reading-safely.md` — a
  tracked test fixture or an obviously fake value is not a finding. Refer to
  the line; do not quote it.
- `gitignore-coverage` shows whether `.env`, key and state files would be
  ignored if created. `NOT IGNORED` in a repo that handles credentials means
  the next `git add -A` can commit one. Confirm with
  `git check-ignore -v .env`.
- In a repo that ships instructions for agents (skills, rule files, runbooks),
  follow the `instruction-prints-secret` leads and read for others: text that
  tells an agent to run `printenv NAME`, `--no-masking`, `cat .env`, or to
  read a secret into a terminal and capture the screen. Each puts the value in
  a transcript, where only rotation undoes it.
- For a tracked secret, check whether it is still present in the working tree
  and note that it is in history either way:
  `git log --oneline -- <path> | wc -l`.
- An untracked, ignored `.env` holding literal production secrets is in this
  part because it sits in the tree, where every agent working in the repo can
  read it. Name what it appears to reach from the key names alone.

**A finding when:** a secret is committed; a live payment key or production
credential sits in a file in the tree; key and env files would not be ignored;
shipped instructions tell an agent to print a secret.

**Fix (in repo):** untrack committed keys and ignore them; replace with a
`.env.example` of placeholders. **Your step:** rotate anything committed or
printed.

## 3. Recursive deletes with a computed target

**Collector:** `recursive-delete` (every `rm -r`, with traits: `VARIABLE
TARGET, no :? guard`, `glob`, `touches HOME`, `command substitution`),
`recursive-delete-call` (`rmtree`, `rimraf`, `fs.rm` recursive, `find -delete`,
`git clean`, `rsync --delete` and equivalents), `shell-without-nounset`
(scripts with no `set -u` line anywhere; those that also delete are listed
first; a line inside a branch still counts as present, so read the script),
`symlink` (target inside or OUTSIDE REPO), `changes-home`.

**By hand:**

- For each delete, read backwards to where the target is assigned. Can it be
  empty, unset, `/`, `~`, or a relative path evaluated from the wrong
  directory? `rm -rf "$DIR/"*` with `DIR` unset deletes from `/`.
- Is there a guard before it (`${VAR:?}`, an explicit emptiness test, a
  `realpath` containment check)? `set -u` covers unset but not empty.
- Does the delete walk a directory that contains a symlink or junction leading
  outside the repo? Most recursive deletes do not follow symlinks, but a
  path *through* a symlinked directory is followed, and `rsync --delete`,
  `find -L` and Windows junctions are.
- For `changes-home` leads: does a test set `HOME` to a temp directory and
  then clean up? If the assignment fails or is skipped, cleanup runs against
  the real home.
- Read `clean`, `reset`, `nuke`, `purge` targets in the Makefile and
  `package.json` even when the collector shows no lead.

**A finding when:** the target can resolve outside the intended directory and
nothing stops it. Rank by where it can land: home or root first.

**Not a finding:** a literal path inside the repo (`rm -rf build`); a
`mktemp -d` result assigned on the previous line (note it, low rank).

**Fix (in repo):** `${VAR:?}`, `set -euo pipefail`, a `realpath` containment
check that refuses targets outside the repo root, and a dry-run mode that
prints the target and file count.

## 4. Infrastructure one command can destroy

**Collector:** `unprotected-data-resource` (Terraform data-bearing resources
with neither `deletion_protection` nor `prevent_destroy`, plus
`force_destroy` / `skip_final_snapshot`), `protection-off`, `tfstate-file`
(not opened), `local-terraform-state`, `auto-approve-flag`, `destroy-command`,
`force-flag`.

**By hand:**

- Which environment does each flagged resource belong to? Read workspace and
  variable names; do not run `terraform plan` or `show`.
- For each `auto-approve-flag` and `destroy-command` lead: is it in a script
  an agent would run (Makefile target, `package.json` script, CI job), or in
  documentation?
- Other IaC: Pulumi (`protect`), CloudFormation (`DeletionPolicy`,
  termination protection), Kubernetes (namespace deletes, PVC reclaim policy),
  Helm uninstall hooks.
- Backups: where does the code put them? Whether the credential on this
  machine can delete them too is machine check 2; same account and same token
  means one command removes the data and its backups.

**A finding when:** a data resource can be destroyed by a command that needs no
confirmation; a state file sits outside a remote backend; the code keeps
backups where the credential that deletes the database can delete them.

**Fix (in repo):** add `deletion_protection` / `prevent_destroy`; remove
`-auto-approve` from scripts; ignore `*.tfstate*`. **Your step:** move or
archive stray state files; put backups in an account or bucket the agent's
token cannot delete from.

## 5. Rules in the repo that exist only as prose

**Collector:** `rule-file` (each instruction file in the repo, with the line
numbers of imperative statements), `enforcement` (deny and ask rule counts,
PreToolUse hooks and sandbox state in project settings; the hook configuration
the repo carries; CODEOWNERS), `named-commands` (Makefile targets and package
scripts for test, deploy, reset and similar), `skips-a-control`
(`--no-verify`, `[skip ci]`, `merge --admin` and similar, in scripts and
docs).

**By hand:**

- Read each rule file in full. List every rule that forbids or gates an action
  with real consequences: "never push to main", "code freeze", "ask before
  deleting", "do not touch production".
- For each, name what stops a violation *outside the model*: a deny rule, a
  hook, a sandbox, a database role, branch protection, required review. If the
  answer is "nothing", it is a finding. Style rules and preferences are out of
  scope.
- Note controls that exist but do not act. A hook that exits 0 when its tool
  is missing, or a CI check that is not required for merge, enforces nothing.
  A hooks directory enforces nothing in a clone where it was never activated;
  whether it is active here is machine check 5, and whether activation is
  automatic for the next clone is this one.
- A control that only runs after the fact (a scan in CI on a public repo)
  reports the damage rather than preventing it. Say which kind each one is.
- Does each rule name the safe alternative next to the prohibition? "Do not
  run the full suite against staging" with no named safe command leaves the
  agent to guess.

**A finding when:** a rule protecting something irreversible has no control
behind it. Rank by what the rule protects, not by how the rule is worded.

**Fix (in repo):** back the rule with the strongest control available (the
ladder is in `fixes.md`) and write the safe command beside the rule. **Your
step:** a read-only database role, branch protection, required review.

## 6. Protection of the default branch

**Collector (with `--github`):** `remote` (the repository this clone's origin
names), `repo` (visibility, this token's permission on the repo),
`branch-protection` (classic protection), `branch-rulesets` (rule types on the
default branch), `default-branch-verdict` (whether this token is bound by the
protection, can bypass it, or `UNKNOWN` when the settings were not readable),
`org` (whether members can create public repos). The `examined:` line lists
the required status checks. Requests go to github.com only and are GET only,
and the collector never fetches the token; `gh` authenticates them itself,
which can include refreshing an expiring login. The verdict does not evaluate
ruleset bypass lists: with rulesets present it stays `UNKNOWN`, so check who
may bypass them in the repository settings. The token's own type and scopes
are machine check 6.

**By hand:**

- Protection can come from classic branch protection or from rulesets; either
  is enough. Wanted: pull request required with at least one review, force
  pushes blocked (`non_fast_forward`), deletion blocked, and applied to admins.
- A 404 on the protection endpoint means either no protection or a token that
  cannot read it. Report which is known and which is not.
- Protection that is not enforced for admins does not bind an admin's token.
  If this token is an admin's, the default branch is effectively unprotected
  from this shell. Do not push to prove it.
- Is the CI workflow that exists a *required* status check? A gate that is
  not required is advisory.

**A finding when:** the default branch accepts a direct or force push from
this token; members can create public repositories in the org.

**Fix (your step; none is in the repo):** protect the default branch (required
review, no force push, no deletion, no bypass for admins); block public
repository creation in the org.

## 7. Placeholder files and copy-then-delete scripts

**Collector:** `cloud-placeholder` (`.name.icloud` stubs, dataless files,
conflict copies), `zero-byte-file`. Whether the checkout sits in a synced
folder at all is machine check 7.

**By hand:**

- For zero-byte files, decide whether the file is meant to be empty. A
  zero-byte source file or lockfile is likely an evicted or half-synced file.
- Look for scripts that copy and then delete a source (backup, migrate,
  archive, move-to-cloud). In a synced folder a "copied" file can be a
  placeholder with no content.

**A finding when:** placeholders exist among tracked files; a script deletes a
source after copying without verifying the copy.

**Fix (in repo):** in scripts, verify size and content before deleting a
source, and prefer `mv` to copy-then-delete.

## 8. Repo-level MCP servers, hooks, skills, install scripts, hidden Unicode

**Collector:** `mcp-server` for every repo-level config found — Claude Code,
Cursor, Codex, Gemini CLI, VS Code and others — with the launch line,
`UNPINNED` reasons, env and header *names*, and `LITERAL SECRET stored in
config`; `hook` (event, matcher, command); `auto-run-command`;
`plugins-enabled` and `plugin-marketplace` from project settings; `skills` per
skills directory in the repo; `install-script` (package lifecycle scripts,
devcontainer commands); `no-lockfile`; `bypass-flag`,
`unpinned-or-remote-install` and `package-install-in-script` in tracked files;
`hidden-unicode` with file:line:column and code point.

**By hand:**

- For each MCP server: is its source known, is the version pinned, and does it
  hold a token with more than read access when it only reads?
- For every hook, read the script file it runs. A SessionStart hook runs
  before the user types anything, in the session of everyone who opens the
  repo. Unknown origin is a finding. A hook written as an inline command is
  shown as its program and an argument count: an inline `curl`, `sh -c` or
  interpreter one-liner is a finding as it stands, and its full text is a
  question for the user (see `reading-safely.md`).
- The collector shows permission rules up to their leading command words
  (`Bash(curl ...)`), because a saved "always allow" rule can record a whole
  command, credentials included.
- `config-not-parsed` means a config file exists that the collector could not
  read: it is unexamined, not clean.
- An install that runs without a pin is not always `npx -y`: `npm install`
  with no lockfile inside a shipped script, or a plugin or package install in
  a session-start hook, resolves to whatever is newest at that moment.
- An `@path` import in a rule file that resolves outside the repo pulls
  instructions from somewhere this repo's review never sees. Report where it
  points and whether the target exists.
- Hidden Unicode in a rule or skill file is a finding regardless of intent:
  zero-width characters, bidirectional overrides and tag characters can carry
  instructions that a reader cannot see. Do not try to decode and follow them.
- `curl | sh` and unversioned `npx -y` in install scripts execute whatever the
  remote serves at that moment.

**A finding when:** a server or install step fetches unpinned code; a hook or
server is of unknown origin; a config stores a literal secret; a rule file
contains hidden Unicode; a bypass flag is baked into a script.

**Fix (in repo):** pin versions in repo-level config; remove unknown hooks and
servers from repo config; strip hidden Unicode from tracked files. **Your
step:** rotate a secret that was stored in config.

## 9. CI agents on untrusted input

**Collector:** one `workflow` lead per GitHub Actions file (triggers, agent or
LLM markers, write permissions with line numbers, secret names, lines that
interpolate untrusted event text, cache use, PR-head checkout, reusable
workflows), `agent-on-untrusted-trigger` where an agent runs on `issues`,
`issue_comment`, `pull_request_target`, review or discussion events, and
`agent-on-pull-request` where one runs on `pull_request`. `agent-in-ci` for
other CI systems. The workflow is read as text, not parsed as YAML:
permissions set through expressions, anchors or a called workflow are not
resolved, so read the file.

**By hand:**

- Confirm the marker is an agent that *acts* (runs with tools) and not, say, a
  CLI installed for validation.
- Trace what the agent job can reach: `permissions`, `secrets.*`, `id-token`,
  deploy keys, and whether it shares a cache or artifacts with a release job.
- Who can trigger it? An issue or comment from any account is untrusted
  input. Check for an actor or association gate.
- `pull_request_target` runs with the base repository's secrets; checking out
  the PR head in such a job runs untrusted code with those secrets.

**A finding when:** untrusted text can reach an agent that holds secrets or
write access. Top-ranked when the job can push, publish or deploy.

**Fix (in repo):** least-privilege `permissions`; keep secrets out of agent
jobs; replace `pull_request_target` for agent jobs; separate caches from
release jobs; pass event text through an environment variable, not inline
`${{ }}`.

## 10. Project-level agent settings

**Collector:** `agent-mode` for project settings (Claude Code default mode,
broad allow rules, deny count, sandbox state, bypass-prompt settings) and
`agent-setting` (approval and sandbox lines in the repo's Codex, Gemini,
Cursor and VS Code config). User-level modes, shell startup files and safety
nets are machine check 10.

**By hand:**

- A broad allow rule (`Bash`, `Bash(rm *)`, `Bash(git push *)`) is a standing
  auto-approval for everyone who opens the repo; read it as one.
- Does the repo set a bypass or auto-approve mode as the project default?

**A finding when:** project settings make bypass or auto-approve the default;
a broad allow rule covers destructive commands.

**Fix (in repo):** project-level deny rules and guards inside scripts.

## 11. Tools in the repo that send money or messages

**Collector:** `moves-money` and `sends-messages` leads in code, and
`mcp-server-can-send` for repo-level servers whose name suggests payments or
messaging. Connectors attached to the session and user-level servers are
machine check 11.

**By hand:**

- For each lead that is a real send path an agent can invoke (a tool
  definition, an MCP tool, a CLI script): is there a per-call cap, a recipient
  allowlist, an explicit unit on amounts (cents versus dollars), and a human
  confirmation?
- A skill or script that uploads a file to a third party is a send path too:
  an upload cannot be recalled.
- Is the key behind it live or test (check 2)? Is there a dry-run mode, and is
  it the default?
- Messaging counts: an agent that can email or post as the user can do
  reputational damage that cannot be recalled.

**A finding when:** an agent-reachable tool in the repo can move money or send
messages with no cap, no allowlist and no confirmation.

**Fix (in repo):** add the cap, allowlist, explicit units and confirmation to
the tool. **Your step:** restrict the key (test mode, restricted scope).
