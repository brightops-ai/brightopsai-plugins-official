# Docs

The `## Agent skills` block in the root `CLAUDE.md` configures **in-repo
coding agents** for this repository: the mattpocock-skills plugin's
issue-tracker, triage-label, and domain-docs conventions, with the long form
imported from the maintainer's private engineering-docs repo. It is **not**
documentation for people installing plugins from the marketplace, and there is
no `docs/agents/` directory any more.

`docs/adr/` holds architectural decision records. [0001-plugin-consolidation-scope.md](adr/0001-plugin-consolidation-scope.md) is the first.

Plugin users: start at the [root README](../README.md), then the README for
the plugin you installed (`plugins/<name>/README.md`).

## Seed-template leftovers

The `## Agent skills` block was appended by the maintainer's workspace repo
bundle, and the shared file it imports was forked from that bundle's seed
templates. References to `CONTEXT.md` and `bootstrap-repo.sh` come from there
and may be absent here. Their absence is expected; do not treat it as a
gap in the marketplace docs, and do not create those files just to match the
templates.
