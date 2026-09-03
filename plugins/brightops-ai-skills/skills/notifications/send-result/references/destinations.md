# Destinations

Configuration lives at `config.json` in the per-plugin data directory, which is
`${CLAUDE_PLUGIN_DATA}` when set. Never inside the plugin directory: installed
plugins live in a version-keyed cache, so anything written there is orphaned by
the next version bump.

## `file` — the default

No configuration. Writes the summary and reports the path.

```json
{ "destination": "file" }
```

## `command`

Runs a command you configure, with the summary on its stdin.

```json
{
  "destination": "command",
  "command": "your-notify-command --to your-channel",
  "timeout_seconds": 60
}
```

The command is split with shell-style quoting, not run through a shell, so
pipelines and redirections do not work. Wrap those in a script and point at the
script.

A non-zero exit is reported as a failure with the command's stderr. It is never
swallowed.

## Why an unconfigured `command` is an error

Selecting `command` without configuring one fails loudly rather than writing a
file instead.

A delivery that silently went somewhere other than where it was asked to go is
worse than one that failed: the run reports success, the summary sits in a file
nobody opens, and the automation looks healthy while being useless. Failing is
recoverable; looking successful is not.

## Adding a destination

Add a branch in `lib/dream/delivery.py` and document it here. Two rules hold for
any new destination:

1. It is selected explicitly. Nothing is ever inferred from the environment.
2. Misconfiguration raises, and never degrades to a different destination.

A webhook destination is the obvious next one: a URL, a method, headers from
config. It is deliberately not implemented, because it needs a decision about
where the URL's credentials come from, and that decision belongs with whoever
needs it.

## Secrets

The summary may leave this machine. Do not put credentials in it. Digests
produced by this suite are redacted at extraction, but a summary you compose by
hand is your responsibility.
