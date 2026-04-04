# op CLI examples (from op help)

## Sign in

- `op signin`
- `op signin --account <shorthand|signin-address|account-id|user-id>`

## Read

- `op read op://agentic_ai/db/password`
- `op read "op://agentic_ai/db/one-time password?attribute=otp"`
- `op read "op://agentic_ai/ssh key/private key?ssh-format=openssh"`
- `op read --out-file ./key.pem op://agentic_ai/server/ssh/key.pem`

## Run

- `export DB_PASSWORD="op://agentic_ai/db/password"`
- `op run --no-masking -- printenv DB_PASSWORD`
- `op run --env-file="./.env" -- printenv DB_PASSWORD`

## Inject

- `echo "db_password: {{ op://agentic_ai/db/password }}" | op inject`
- `op inject -i config.yml.tpl -o config.yml`

## Whoami / accounts

- `op whoami`
- `op account list`

## Create / store

- `op item create --category=api-credential --title="Service Name" --vault="agentic_ai" 'password=secret123'`
- `op item create --category=login --title="Service Name" --vault="agentic_ai" 'username=user' 'password=pass'`
