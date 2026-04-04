# op CLI examples (from op help)

## Sign in

- `op signin`
- `op signin --account <shorthand|signin-address|account-id|user-id>`

## Read

- `op read op://<your-vault>/db/password`
- `op read "op://<your-vault>/db/one-time password?attribute=otp"`
- `op read "op://<your-vault>/ssh key/private key?ssh-format=openssh"`
- `op read --out-file ./key.pem op://<your-vault>/server/ssh/key.pem`

## Run

- `export DB_PASSWORD="op://<your-vault>/db/password"`
- `op run --no-masking -- printenv DB_PASSWORD`
- `op run --env-file="./.env" -- printenv DB_PASSWORD`

## Inject

- `echo "db_password: {{ op://<your-vault>/db/password }}" | op inject`
- `op inject -i config.yml.tpl -o config.yml`

## Whoami / accounts

- `op whoami`
- `op account list`

## Create / store

- `op item create --category=api-credential --title="Service Name" --vault="<your-vault>" 'password=secret123'`
- `op item create --category=login --title="Service Name" --vault="<your-vault>" 'username=user' 'password=pass'`
