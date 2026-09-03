---
name: send-result
description: Deliver a run summary to the configured destination.
disable-model-invocation: true
argument-hint: "[path to summary] [--destination file|command]"
allowed-tools:
  - Bash
  - Read
  - Write
---

# Send result

Deliver a summary to wherever the person actually looks. Useful to any
automation, not only the one it was written for.

## References

- `references/destinations.md` — configuring each destination, and adding another

## Why the destination is configuration

An automation that runs unattended is only useful if its output is seen. Where
that is — a file, a chat channel, an inbox — differs per person, so this skill
ships knowing how to write a file and how to hand a summary to a command, and
knows nothing about any particular platform.

## Workflow

### 1. Compose the summary

Short enough to read where it lands. Lead with what changed and what needs a
decision; link to the full document rather than inlining it.

### 2. Deliver

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/lib/dream/cli.py" deliver \
  --summary-file "<path>"
```

With no configuration this writes a file and reports the path.

To route elsewhere, set a destination in the plugin's `config.json` under the
per-plugin data directory:

```json
{
  "destination": "command",
  "command": "your-notify-command --to your-channel"
}
```

The summary arrives on the command's stdin.

### 3. Report where it went

Always state the destination and the path or command used. "Delivered" without
a destination is not a report.

## Guardrails

- **Never infer a destination.** Selecting `command` without configuring one is
  an error, and the skill must not quietly write a file instead. A delivery that
  went somewhere other than where it was asked to go looks successful and is
  never read.
- A failing delivery command is reported, never swallowed
- Configuration lives in the per-plugin data directory, never in the plugin directory
- Do not put secrets in the summary; it may leave this machine
