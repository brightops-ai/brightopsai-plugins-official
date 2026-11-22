# op CLI command forms

Each section names the 1Password page its forms come from. Where a rule is
this repository's and not 1Password's, it says so. Sources:

- [Load secrets into the environment](https://www.1password.dev/cli/secrets-environment-variables)
- [Use secret references](https://www.1password.dev/cli/secret-references)
- [`op item` reference](https://www.1password.dev/cli/reference/management-commands/item)
- [`op run`](https://www.1password.dev/cli/reference/commands/run/),
  [`op read`](https://www.1password.dev/cli/reference/commands/read/),
  [`op inject`](https://www.1password.dev/cli/reference/commands/inject/)

Everything outside the last section keeps the secret value away from the
agent.

## Run (the default)

Source: Load secrets into the environment; Use secret references.

An env file of references, `KEY=VALUE` per line:

```
DB_USER="op://<your-vault>/db/user"
DB_PASSWORD="op://<your-vault>/db/password"
```

```bash
op run --env-file="./app.env" -- <command>
```

One reference set in the same command, or exported first:

```bash
DB_PASSWORD="op://<your-vault>/db/password" op run -- <command>
```

```bash
export DB_PASSWORD="op://<your-vault>/db/password"
op run -- <command>
```

The exported variable holds the reference, not the value. `<command>` reads
`DB_PASSWORD` from its own environment.

**Never as an argument.** Do not write `--password "$DB_PASSWORD"` or any
other form that expands the secret into a program's arguments. Process
arguments are visible to other processes on the machine; 1Password's item
reference gives that reason for keeping sensitive values out of command
arguments. A consumer that only takes its secret as an argument gets a
managed file instead ("Config files and key files").

**Standard input.** 1Password's subshell form exists because the shell
expands `$DB_PASSWORD` before `op run` substitutes it. Run the expansion in
an inner shell, and let a builtin do it, so the value is in no argument list:

```bash
# set +x first: the inner shell can inherit tracing (an exported SHELLOPTS,
# or a caller that ran it with -x), and a trace would print the expanded value.
DB_PASSWORD="op://<your-vault>/db/password" op run -- sh -c 'set +x; printf "%s" "$DB_PASSWORD" | <command-that-reads-stdin>'
```

`op run` resolves the reference before it starts the inner shell, so the
consumer does not start on a failed read.

**Masking.** "Secrets printed to stdout or stderr are concealed by default."
That is a convenience, not a boundary. The secret-references example prints
a referenced username in plaintext, the `op run` reference shows `printenv`
output that is not concealed, and an Environment secret set to "Show value by
default" in the app is not masked.

**Environments.** `op run --environment <environmentID> -- <command>`; see
`environments.md`.

## Check

Each check reads an exit status and discards all output. `op item get` shows
every field 1Password does not classify as sensitive (a credential saved in a
plain text field is printed), and `op run` masks only what it recognises.

- Item in the vault:
  ```bash
  if op item get "<item>" --vault "<your-vault>" >/dev/null 2>&1; then echo found; else echo "not found"; fi
  ```
  With a service account that can reach more than one vault, `--vault` is
  required.
- Reference resolves to a non-empty value. `test` is a shell builtin and
  prints nothing:
  ```bash
  if DB_PASSWORD="op://<your-vault>/db/password" op run -- sh -c 'test -n "$DB_PASSWORD"' >/dev/null 2>&1; then echo resolves; else echo "does not resolve"; fi
  ```
- Signed in: `op whoami`. Accounts: `op account list`. A failed check can
  mean "not signed in"; these tell the two apart and print no secret.

## Private directory for files

This repository's rule: any file that holds, or will hold, a secret lives in
a private directory outside every git work tree. 1Password's examples write
to the current directory; do not copy that. Define this function in the same
script or shell-tool command as the block that uses it:

```bash
# Prints the path of a new private directory, or fails without one.
op_private_dir() (
  umask 077
  d="$(mktemp -d /tmp/op-private.XXXXXX)" || exit 1
  [ -d "$d" ] || exit 1
  refuse() { echo "refusing: $1" >&2; rmdir "$d"; exit 1; }
  p="$(cd -P "$d" && pwd -P)" || refuse "cannot resolve $d"
  while :; do
    [ -e "$p/.git" ] && refuse "$p is a git work tree"
    [ "$p" = / ] && break
    p="$(dirname "$p")" && [ -n "$p" ] || refuse "cannot verify the parents of $d"
  done
  # git's own answer: true, false, or unknown when git is missing or fails.
  inside="$(git -C "$d" rev-parse --is-inside-work-tree 2>/dev/null)" || inside=unknown
  [ "$inside" = true ] && refuse "git reports $d inside a work tree"
  # A work tree declared through the environment has no .git to find, so only
  # git can rule it out. Without a clear "false", refuse.
  if [ -n "${GIT_WORK_TREE:-}${GIT_DIR:-}" ] && [ "$inside" != false ]; then
    refuse "GIT_WORK_TREE or GIT_DIR is set and git did not confirm $d is outside it"
  fi
  printf '%s\n' "$d"
)
```

- The parent is `/tmp`, not `$TMPDIR`, so a repository-local `TMPDIR` cannot
  move it into a work tree.
- The walk to `/` needs no `git`. It stops with an error unless every parent
  was checked, so a missing or failing tool cannot turn into "looks fine".
  `git`, when present, can only add a refusal.
- A work tree declared with `GIT_WORK_TREE` or `GIT_DIR` has no `.git` entry
  for the walk to find. When either is set, the function refuses unless
  `git` itself answers that the directory is outside the work tree.
- The directory is mode 700 and is removed again on every refusal.

## Store

Source: `op item` reference, "item create". "Command arguments get logged in
your command history, and can be visible to other processes on your machine.
If you're assigning sensitive values, use a JSON template instead."

**In the app.** The user creates the item and enters the value in the
1Password app. Nothing to run.

**Generated by 1Password.** For a Login or Password item, when a new random
value is acceptable. The default recipe is 32 characters:

```bash
op item create --category=password --title="<item>" --vault="<your-vault>" --generate-password
op item create --category=login --title="<item>" --vault="<your-vault>" --generate-password='letters,digits,symbols,32'
```

`--dry-run` previews the item without creating it. Never add `--reveal`.

**JSON template the user edits.**

1. Save the category template into a private directory (with
   `op_private_dir` defined as above). It holds no secret yet:
   ```bash
   TEMPLATE_DIR="$(op_private_dir)" || exit 1
   op item template get --out-file "$TEMPLATE_DIR/item.json" "API Credential" >/dev/null || {
     rmdir "$TEMPLATE_DIR"
     exit 1
   }
   printf '%s\n' "$TEMPLATE_DIR/item.json"
   ```
2. The user edits that file and puts the value in. From here on the agent
   does not open, print or copy it.
3. Create the item. Discard the CLI's output and read the exit status: the
   summary shows any field 1Password does not classify as sensitive, and the
   template may hold one:
   ```bash
   if op item create --vault="<your-vault>" --template="<template-file>" >/dev/null 2>&1; then echo created; else echo "not created"; fi
   ```
4. Delete the edited template and its directory, also when step 3 fails:
   ```bash
   rm -f "<template-file>" && rmdir "<template-dir>"
   ```

A template can also arrive on standard input, with `-` as the first argument
(`op item template get Login | op item create --vault "<your-vault>" -`).
Piping and `--template` cannot be combined.

`op item template list` lists the categories.

## Read (only when `op run` does not fit)

Source: Use secret references; [Load secrets into scripts](https://www.1password.dev/cli/secrets-scripts).

`op read` prints the value to stdout. For a consumer that reads standard
input, use the `op run` form under "Run". For a file, use the guarded block
below. What is left is a script that has to export the value into its own
environment. 1Password's form is `export VAR="$(op read ...)"`; prefer
`op run`, which scopes the value to one process. When the script must export,
this repository assigns first, because `export VAR="$(op read ...)"` succeeds
even when the read failed. Run with shell tracing off:

```bash
DB_PASSWORD="$(op read "op://<your-vault>/db/password")" || {
  unset DB_PASSWORD
  echo "op read failed; DB_PASSWORD not exported" >&2
  exit 1
}
export DB_PASSWORD
```

## Config files and key files

Source: Use secret references ("Use with configuration files"); `op inject`
and `op read` references.

A config template that uses secret references "can be safely checked into
Git". When the consumer can read environment variables, use `op run` with an
env file and render nothing.

When it needs a file, `op inject` renders the template and `op read
--out-file` writes a single secret such as a key. 1Password's rule: "Make
sure to delete the resolved file when you no longer need it." This
repository adds where the file may live. Render only with this block (with
`op_private_dir` defined as above); the subshell keeps `exit` and the cleanup
trap local:

```bash
(
  set +x
  SECRET_DIR="$(op_private_dir)" || exit 1
  [ -d "$SECRET_DIR" ] || exit 1
  trap 'rm -rf "$SECRET_DIR"' EXIT
  trap 'exit 1' INT TERM HUP
  umask 077
  op inject --in-file config.yml.tpl --out-file "$SECRET_DIR/config.yml" >/dev/null || exit 1
  <command> --config "$SECRET_DIR/config.yml"
)
```

- Nothing is written unless `op_private_dir` returned a verified directory.
- The trap is installed before the secret is written and also runs on a
  failed render or an interrupt.
- Both commands write owner-only by default (`--file-mode`, default 0600).

For a key file, replace the `op inject` line with
`op read --out-file "$SECRET_DIR/key.pem" "op://<your-vault>/server/ssh/key.pem" >/dev/null || exit 1`
and point the consumer at that file.

## For a human at a terminal only — never for an agent

Each command below prints a secret value to the terminal or takes one as
input. An agent must not run them, in a shell tool or in a tmux pane: the
value would enter the transcript. When the user asks to see or enter a value,
hand them the command to run in their own terminal.

- `op read "op://<your-vault>/db/password"`
- `op read "op://<your-vault>/db/one-time password?attribute=otp"`
- `op read "op://<your-vault>/ssh key/private key?ssh-format=openssh"`
- `op run --no-masking -- printenv DB_PASSWORD`, and `op run -- printenv
  DB_PASSWORD` (masked only when 1Password treats the value as concealed)
- `op item get "<item>"` with its output shown, with or without `--reveal`
  or `--format json`
- `echo "db_password: {{ op://<your-vault>/db/password }}" | op inject`
- `cat .env` on a mounted 1Password `.env` file (1Password's own
  verification step; it prints every value)
- `op item create ... 'password=<value>'` — an assignment statement carrying
  a value lands in shell history and the process list
- `op account add` — prompts for the Secret Key and account password
