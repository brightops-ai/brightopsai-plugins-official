# op CLI examples (from op help)

Every example outside the last section keeps the secret value off the
terminal: it goes to a consumer, a file outside the work tree, or a masked
subprocess.

## Sign in

- `eval "$(op signin)"`
- `eval "$(op signin --account <shorthand|signin-address|account-id|user-id>)"`

## Read

- `op read op://<your-vault>/db/password | <command-that-reads-stdin>`
- `DB_PASSWORD="$(op read op://<your-vault>/db/password)" <command>`

When a tool accepts a key only as a file, write it outside any git work tree
and delete it after use. `mktemp -d` gives a private directory; `--out-file`
writes the file readable by the owner only:

```bash
KEY_DIR="$(mktemp -d)"
op read --out-file "$KEY_DIR/key.pem" op://<your-vault>/server/ssh/key.pem
<command> --key "$KEY_DIR/key.pem"
rm -rf "$KEY_DIR"
```

## Run

`./.env` and the exported variable hold `op://` references, not values.
`op run` resolves them for the subprocess only and masks them in its output.

- `export DB_PASSWORD="op://<your-vault>/db/password"`
- `op run -- <command>`
- `op run --env-file="./.env" -- <command>`

## Inject

- `op inject -i config.yml.tpl -o config.yml`

## Whoami / accounts

- `op whoami`
- `op account list`

## Create / store

- `op item create --category=api-credential --title="Service Name" --vault="<your-vault>" 'password=secret123' >/dev/null`
- `op item create --category=login --title="Service Name" --vault="<your-vault>" 'username=user' 'password=pass' >/dev/null`

## For a human at a terminal only — never for an agent

Each command below prints a secret value to the terminal. An agent must not
run them, in a shell tool or in a tmux pane: the value would enter the
transcript. When the user asks to see a value, hand them the command to run
in their own terminal.

- `op read op://<your-vault>/db/password`
- `op read "op://<your-vault>/db/one-time password?attribute=otp"`
- `op read "op://<your-vault>/ssh key/private key?ssh-format=openssh"`
- `op run --no-masking -- printenv DB_PASSWORD`
- `echo "db_password: {{ op://<your-vault>/db/password }}" | op inject`
