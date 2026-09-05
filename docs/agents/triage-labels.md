_See [docs/README.md](../README.md) for what this file is._

# Triage Labels

The skills speak in terms of five canonical triage roles. This file maps those roles to the actual label strings used in this repo's issue tracker.

| Label in mattpocock/skills | Label in our tracker | Meaning                                  |
| -------------------------- | -------------------- | ---------------------------------------- |
| `needs-triage`             | `needs-triage`       | Maintainer needs to evaluate this issue  |
| `needs-info`               | `needs-info`         | Waiting on reporter for more information |
| `ready-for-agent`          | `ready-for-agent`    | Fully specified, ready for an AFK agent  |
| `ready-for-human`          | `ready-for-human`    | Requires human implementation            |
| `wontfix`                  | `wontfix`            | Will not be actioned                     |

When a skill mentions a role (e.g. "apply the AFK-ready triage label"), use the corresponding label string from this table.

Edit the right-hand column to match whatever vocabulary you actually use — but if
you do, re-run `bootstrap-repo.sh` for this repo with the label set changed at
the bundle, or the audit will keep reporting this file as drifted.

## Creating the labels

`gh issue edit --add-label` fails on a label that does not exist rather than
creating it, so the labels have to exist before `/triage` can apply them.
`bootstrap-repo.sh --apply` creates all five idempotently. To do it by hand:

```bash
gh label create needs-triage    --description "Maintainer needs to evaluate this issue"
gh label create needs-info      --description "Waiting on reporter for more information"
gh label create ready-for-agent --description "Fully specified, ready for an AFK agent"
gh label create ready-for-human --description "Requires human implementation"
gh label create wontfix         --description "Will not be actioned"
```

`wontfix` ships with every new GitHub repo, so that one usually already exists —
its stock description differs slightly but the string is what `/triage` matches
on, so it needs no fixing.
