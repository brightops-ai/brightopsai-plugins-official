# What the sync writes

`t3_op_env_sync.py` writes into `settings.json` under the T3 home's `userdata` directory. It holds an exclusive lock on `settings.json.lock` for the run, saves a `0600` backup of the original bytes beside the file (`settings.json.bak-TIME-PID`), and aborts without writing if the file changed while it ran. The lock file is empty and is kept after the run, because deleting it during a run would defeat the lock; it is safe to leave.

```json
{
  "secretProviders": {
    "onepassword": { "kind": "one_password", "label": "1Password", "config": { "account": "my.1password.com" } }
  },
  "providerInstances": {
    "PROVIDER": {
      "environment": [
        { "name": "NAME", "value": "", "sensitive": true,
          "secret": { "provider": "onepassword", "reference": "op://vault/item/field" } }
      ]
    }
  }
}
```

## Ownership

- Only the names in the references file are managed. Every other variable, including other 1Password references, is kept.
- A managed variable leaves only through `--remove=NAME` (it wins over a line of the same name in the references file) or `--remove-all` (every name in the references file).
- An existing `onepassword` secret provider is left as it is.
- A same-named variable that holds a literal value, or a reference through another secret provider, stops the run unless `--replace` is given.

## Types

`environment` absent means an empty list; a list is used; anything else (`null`, `0`, a string) is an error. `secret` is absent or an object; `null` is an error. Errors name the file and line, or the provider and index, and never echo a line's content.

## Validation

`t3_op_env_sync.py --list-references` applies the rules of a sync to the references file and prints `NAME<TAB>REFERENCE` per line without writing anything. `op_check.sh` reads the file only through it.
