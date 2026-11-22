# Fix patterns

Read this when applying approved fixes. Each pattern is a starting point to
adapt to the repo's language and conventions, not text to paste. Fixes outside
the repo root are never applied; they are written up as manual steps.

## Contents

- [The warning format](#the-warning-format)
- [The control ladder](#the-control-ladder)
- [1. Database guard in test setup](#1-database-guard-in-test-setup)
- [2. Committed keys](#2-committed-keys)
- [3. Guarded recursive delete](#3-guarded-recursive-delete)
- [4. Infrastructure protection](#4-infrastructure-protection)
- [5. Backing a prose rule](#5-backing-a-prose-rule)
- [6. GitHub (manual)](#6-github-manual)
- [7. Copy-then-delete in synced folders](#7-copy-then-delete-in-synced-folders)
- [8. MCP servers, hooks, hidden Unicode](#8-mcp-servers-hooks-hidden-unicode)
- [9. CI agent jobs](#9-ci-agent-jobs)
- [10. Agent modes (mostly manual)](#10-agent-modes-mostly-manual)
- [11. Caps on money and messages](#11-caps-on-money-and-messages)

## The warning format

For any risky command that has to stay, make the command itself say what is
about to happen. Print to stderr, before acting:

```
WARNING: <the fact that makes this dangerous right now>; this <VERB> <what>.
```

- State the *current* fact, read at run time, not a general caution:
  `DATABASE_URL host is db.example.com (not local)` rather than
  `be careful with databases`.
- Put the consequence in capitals as one verb: DROPS, DELETES, OVERWRITES,
  FORCE-PUSHES, CHARGES, SENDS.
- Say how to proceed safely or how to opt in on purpose.

```
WARNING: DATABASE_URL is production; this DROPS tables. Aborting. Use `make test-local`.
WARNING: target resolves outside the repo root; this DELETES 1,204 files. Refusing.
WARNING: workspace is prod; this DESTROYS aws_db_instance.main. Re-run with CONFIRM=prod.
WARNING: amount is 5000 USD (cap 100 USD); this CHARGES a live card. Refusing.
```

Why this and not another paragraph in the rule file: the warning arrives in
the agent's context in the tool result, at the step where it decides what to
do next. A rule in an instruction file was read at session start, competes
with everything since, and gives no signal that *this* command is the one it
was about. Where both are possible, add the warning and keep the rule short.

A warning is the floor, not the ceiling. If the command can refuse, make it
refuse; warn-and-continue is for cases where a human may legitimately proceed.

## The control ladder

When backing a rule or closing a hazard, use the highest rung available.
Higher rungs hold no matter what the model decides to run.

1. **The capability is absent.** The credential cannot do it: a read-only
   database role, a token scoped to one repo, backups in an account the token
   cannot delete from. (Usually manual.)
2. **A server-side rule refuses.** Branch protection, required review,
   deletion protection on the resource, org policy. (Manual, or in-repo for
   infrastructure code.)
3. **The OS refuses.** An agent sandbox confining writes and network to the
   project.
4. **The script refuses.** A guard in the script or test setup that aborts on
   a bad target. In-repo, travels with the code, works for every agent and
   every human.
5. **A hook inspects the command.** A pre-tool-use hook that blocks on the
   full command text.
6. **A deny rule in agent settings.** Catches the invocation an agent usually
   writes. It is not a boundary: `Bash(rm *)` does not stop `/bin/rm` or
   `bash -c 'rm ...'`. Use it as a tripwire alongside a higher rung, never as
   the only control on something irreversible.
7. **A warning in the command's output.**
8. **Prose.** Keep it, shorten it, and name the safe command beside it.

Rungs 4, 5 and 6 are the ones an in-repo fix can usually install. Say in the
report which rung each fix reaches, so the user can see what is still held
only by the lower ones.

## 1. Database guard in test setup

Put the guard where every test run passes through it (the framework's global
setup), not in a helper that tests may skip. Parse the host; do not
string-match the whole URL.

```python
# conftest.py
import os
from urllib.parse import urlsplit

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "db", "postgres"}  # compose service names

def pytest_configure(config):
    url = os.environ.get("DATABASE_URL", "")
    host = urlsplit(url).hostname or ""
    if host not in LOCAL_HOSTS:
        raise SystemExit(
            f"WARNING: DATABASE_URL host is '{host}' (not local); the test suite "
            "DROPS and recreates tables. Aborting. Run `make test-local`."
        )
```

```js
// jest.globalSetup.js / vitest globalSetup
const LOCAL_HOSTS = new Set(["localhost", "127.0.0.1", "::1", "db", "postgres"]);
module.exports = async () => {
  const host = new URL(process.env.DATABASE_URL ?? "postgres://invalid").hostname;
  if (!LOCAL_HOSTS.has(host)) {
    throw new Error(
      `WARNING: DATABASE_URL host is '${host}' (not local); tests TRUNCATE every table. ` +
      "Aborting. Run `npm run test:local`.");
  }
};
```

Then point the test config at a local or container database, in the file the
test runner actually loads, and add the safe command (`make test-local`,
`npm run test:local`) so there is something to name. Print the host, never the
URL: the URL carries the password.

Verify with a unit test that sets a fake non-local host and asserts the abort.
Do not verify by running the suite.

## 2. Committed keys

```bash
git rm --cached -- path/to/key.pem .env      # untrack; the file stays on disk
printf '%s\n' '.env' '.env.*' '!.env.example' '*.pem' '*.key' >> .gitignore
```

Add a `.env.example` holding key names with obviously fake values
(`STRIPE_SECRET_KEY=sk_test_REPLACE_ME`). Check `.gitignore` for existing
entries before appending.

Manual, always, and say so plainly: **rotate the key.** Untracking does not
remove it from history, from clones, or from any CI log. Rewriting history is
also manual and optional; rotation is not.

## 3. Guarded recursive delete

```bash
#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"

safe_rm() {                        # safe_rm <path> ; DRY_RUN=1 to preview
  local target
  target="$(realpath -- "${1:?safe_rm: empty path}")" || {
    echo "WARNING: cannot resolve '$1'; refusing to delete an unresolved path." >&2
    return 1
  }
  case "$target" in
    "$REPO_ROOT"/.git|"$REPO_ROOT"/.git/*)
       echo "WARNING: '$target' is repository metadata; this DELETES history. Refusing." >&2
       return 1 ;;
    "$REPO_ROOT"/?*) ;;            # strictly inside the repo, never the root itself
    *) echo "WARNING: '$target' is outside $REPO_ROOT; this DELETES files there. Refusing." >&2
       return 1 ;;
  esac
  local count
  count="$(find "$target" -type f 2>/dev/null | wc -l | tr -d ' ')"
  if [[ "${DRY_RUN:-0}" == "1" ]]; then
    echo "dry run: would delete $target ($count files)"; return 0
  fi
  echo "deleting $target ($count files)" >&2
  rm -rf -- "$target"
}
```

- `${VAR:?message}` aborts on unset *and* empty; `set -u` alone covers only
  unset.
- `realpath` resolves symlinks, so a link pointing outside the repo fails the
  containment test. On a system without `realpath`, use
  `python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))'`.
- `--` stops a path beginning with `-` being read as an option.
- POSIX `sh` has no `pipefail`; use `set -eu` there.
- Containment in the repo is the outer limit, not the goal. Where the script
  only ever cleans known output directories, compare the target against that
  short list (`build`, `dist`, `.cache`) and refuse everything else: a
  descendant of the repo can still be the source tree.

Python: resolve with `Path(target).resolve()`, require
`repo_root in resolved.parents`, and print the target and file count before
`shutil.rmtree`. Node: the same with `fs.realpathSync` and
`path.relative(root, target)` not starting with `..`.

For tests that redirect `HOME`: assign it from `mktemp -d` in the same
statement that guards it, and make cleanup refuse unless the path is under the
system temp directory.

Verify with `DRY_RUN=1`, `bash -n`, and `shellcheck` if present.

## 4. Infrastructure protection

```hcl
resource "aws_db_instance" "main" {
  deletion_protection = true
  skip_final_snapshot = false

  lifecycle {
    prevent_destroy = true
  }
}
```

- `deletion_protection` is enforced by the provider's API (rung 2);
  `prevent_destroy` is enforced by Terraform only (rung 4) and is the fallback
  for resource types with no protection attribute, such as buckets. Use both
  where both exist.
- In scripts, replace `terraform apply -auto-approve` with a saved plan:
  `terraform plan -out=tfplan`, a person reads the plan, then
  `terraform apply tfplan`. The saved plan makes what is applied equal to what
  was reviewed; it is the review between the two commands that is the control,
  so do not chain them in one script.
- Add `*.tfstate`, `*.tfstate.*` and `.terraform/` to `.gitignore`; untrack
  any tracked state with `git rm --cached`.
- Where a destroy script must stay, gate it on an explicit environment name
  and print the warning with the workspace in it.

Do not run `terraform plan` or `apply` to check the change, and do not run
`terraform init` against the real backend. `terraform fmt -check` needs
nothing and is the default check. `terraform init -backend=false` followed by
`terraform validate` goes further but downloads providers, so ask first.
Manual: relocate or archive stray state files; move backups out of the token's
reach.

## 5. Backing a prose rule

For each rule, pick the control from the ladder and then rewrite the rule so
the safe path is named.

| Rule in prose | Control to install |
|---|---|
| "Never push to main" | Branch protection (manual, rung 2); a `pre-push` hook in the repo's hook directory (rung 4) |
| "Never run tests against staging/production" | The test-setup guard above (rung 4) |
| "Ask before deleting / never `rm -rf`" | `safe_rm` in scripts (rung 4); sandbox (manual, rung 3); deny rule as tripwire (rung 6) |
| "Code freeze" | Branch protection or a required status check that fails during the freeze (manual, rung 2) |
| "Do not read `.env`" | `Read(./.env)` and `Read(./.env.*)` deny rules (rung 6) |
| "Do not touch production data" | Read-only database role for the dev machine (manual, rung 1) |

Claude Code project settings, shared through git (`.claude/settings.json`):

```json
{
  "permissions": {
    "deny": [
      "Bash(git push --force *)",
      "Bash(terraform destroy *)",
      "Read(./.env)",
      "Read(./.env.*)"
    ]
  }
}
```

Merge into the existing file; never replace it. Other agents have their own
equivalents (Codex `approval_policy` and `sandbox_mode`, Cursor and Gemini
allow/deny lists) — add them only where the repo already carries that agent's
config, and say which agents the control does *not* cover. A guard in the
script covers all of them, which is why rung 4 is preferred.

If the repo has a hooks directory that is not active in this clone
(`core.hooksPath` unset), activating it changes the clone's git configuration.
That is not a file in the repo, every worktree of the clone shares it, and in
a linked worktree it lives outside the working directory: list it as a manual
step and name the command the repo documents for it. What *is* an in-repo fix
is making activation automatic (a `prepare` script, a session-start hook that
calls the repo's installer) so the next clone does not depend on memory.

Then the rule itself:

```markdown
<!-- before -->
Never run the test suite against a shared database.

<!-- after -->
Run tests with `make test-local`. Test setup aborts if the database host is not local.
```

## 6. GitHub (manual)

Write these as steps for the user; do not run them.

- Protect the default branch: Settings -> Rules -> Rulesets -> new branch
  ruleset targeting the default branch, with "Require a pull request before
  merging" (at least 1 approval), "Block force pushes" and "Restrict
  deletions", and no bypass for admins.
- Replace the token: create a fine-grained personal access token limited to
  this repository with only the permissions in use (typically Contents and
  Pull requests: read and write), then `gh auth login` with it and revoke the
  old one.
- In the org: Settings -> Member privileges -> Repository creation -> untick
  Public.

## 7. Copy-then-delete in synced folders

Prefer a move on the same filesystem; it is atomic and has no window where
both or neither exist:

```bash
mv -- "$src" "$dst"
```

Where a copy is unavoidable, prove the copy before removing the source:

```bash
cp -p -- "$src" "$dst"
[[ -s "$dst" ]] || { echo "WARNING: copy of $src is empty; deleting the source LOSES it. Refusing." >&2; exit 1; }
cmp -s -- "$src" "$dst" || { echo "WARNING: copy of $src differs; deleting the source LOSES it. Refusing." >&2; exit 1; }
rm -- "$src"
```

A size check alone passes for a cloud placeholder that reports the full size;
compare content. Moving the repo out of the synced folder is manual.

## 8. MCP servers, hooks, hidden Unicode

Pin repo-level servers to an exact version:

```json
{ "command": "npx", "args": ["-y", "@scope/server@1.4.2"] }
```

Look the version up from the lockfile or the currently installed copy rather
than guessing. For `uvx` use `package==1.4.2`; for containers use a tag or,
better, a digest.

Remove a hook, server or skill from repo config only when the user approved
that specific finding. Move a literal secret out of a config file into an
environment reference (`"${VAR}"`) and list rotation as manual.

Strip hidden Unicode from a tracked file with the bundled script. List first,
show the list to the user, then apply to an approved file:

```bash
python3 <skill-dir>/scripts/strip_hidden_unicode.py path/to/RULES.md            # lists positions, changes nothing
python3 <skill-dir>/scripts/strip_hidden_unicode.py path/to/RULES.md --apply    # removes exactly those
```

It removes the characters the collector reports and nothing else: a zero-width
joiner inside an emoji sequence and a leading byte-order mark are kept, line
endings and permission bits are preserved, the write is atomic, and links are
refused.

Check `git diff` afterwards. User-level config and read-only tokens are
manual.

## 9. CI agent jobs

```yaml
on:
  pull_request:            # not pull_request_target for a job that runs an agent

permissions:
  contents: read           # top level: least privilege for every job

jobs:
  agent:
    if: contains(fromJSON('["OWNER","MEMBER","COLLABORATOR"]'), github.event.pull_request.author_association)
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: write # only what the agent's output needs
    steps:
      - uses: actions/checkout@<full commit SHA>   # pin third-party and first-party actions alike
      - name: Run agent
        env:
          PR_TITLE: ${{ github.event.pull_request.title }}   # untrusted text via env,
        run: ./scripts/agent.sh "$PR_TITLE"                   # never inline in the script
```

- The fragment above shows the shape, not a complete workflow. Quoting
  `"$PR_TITLE"` stops shell injection only: the text is still untrusted input
  to the agent, so the agent must be told it is data and must not hold
  anything worth stealing.
- The checkout is the PR's code. A script it runs (`scripts/agent.sh`) is
  therefore PR-controlled; take the agent's own script and configuration from
  the base branch when PRs are not fully trusted.
- Keep deploy keys, publish tokens and cloud credentials out of the agent
  job; put release in a separate job that does not consume the agent's
  outputs or cache.
- Give agent jobs their own cache key prefix, or no cache.
- Do not check out the PR head in a `pull_request_target` job.

Verify with a YAML parse and, if available, `actionlint`. Do not trigger the
workflow.

## 10. Agent modes (mostly manual)

In repo: project-level deny rules and script guards from sections 3 and 5.

Manual steps to write up, per agent in use:

- Claude Code: remove bypass aliases from shell startup files; set
  `"permissions": {"disableBypassPermissionsMode": "disable"}` and
  `"sandbox": {"enabled": true}` in user settings; narrow broad allow rules.
- Codex: `approval_policy` other than `never`; `sandbox_mode` set to
  `workspace-write`, not `danger-full-access`.
- Replace shell aliases used as safety nets (`alias rm='rm -i'`) with guards
  in scripts or agent deny rules: an alias is loaded by interactive shells
  only, and `bash -c 'type rm'` shows what an agent actually gets.

## 11. Caps on money and messages

Put the limits in the tool, where no prompt can talk past them:

```python
MAX_AMOUNT_MINOR = 100_00                 # 100.00 in minor units; one constant, one unit
ALLOWED_RECIPIENTS = frozenset(load_allowlist())

def send_payment(recipient: str, amount_minor: int, currency: str, *, confirmed_by: str | None = None):
    if recipient not in ALLOWED_RECIPIENTS:
        raise PermissionError(f"WARNING: {recipient} is not on the allowlist; this SENDS money to an unknown party. Refusing.")
    if amount_minor > MAX_AMOUNT_MINOR:
        raise PermissionError(
            f"WARNING: amount is {amount_minor / 100:.2f} {currency} (cap {MAX_AMOUNT_MINOR / 100:.2f}); "
            "this CHARGES a live account. Refusing.")
    if confirmed_by is None:
        raise PermissionError("WARNING: no human confirmation; this MOVES real money. Refusing.")
    ...
```

- Name the unit in the parameter (`amount_minor`, `amount_cents`), never a
  bare `amount`: a factor-of-100 mistake is the common failure.
- The confirmation must come from outside the agent's own turn — a signed
  approval, an interactive prompt, a second system — not a boolean the agent
  can set.
- Messaging tools take the same shape: recipient allowlist, a per-run count
  cap, and a dry-run default that prints the message instead of sending it.

Manual: switch the key to test mode or a restricted key; narrow the
connector's permissions.
