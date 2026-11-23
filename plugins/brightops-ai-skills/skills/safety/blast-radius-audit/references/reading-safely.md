# Reading safely

Read this before verifying leads in either part. It says which files hold
values and must not be opened, and how to get what the audit needs from them
without a value reaching the context.

Source code, scripts, CI workflows, Terraform and rule files are safe to open
with a file-read tool. Three kinds of file are not, because their purpose is to
hold values:

- In the repo: `.env*`, `*.env`, `.envrc`, `*.tfvars`, `*.tfstate`, and
  tracked agent config such as `.mcp.json` and `.claude/settings.json`.
- On the machine: anything under `~/.aws`, `~/.kube`, `~/.config/gcloud`,
  `~/.ssh`, and `~/.netrc`, `~/.pgpass`, `~/.npmrc`, `~/.git-credentials`.
- On the machine: agent config that embeds tokens, such as `~/.claude.json`
  and user-level MCP config files.

For those, rely on the collector's output. When a detail is missing, ask the
collector for key names. It prints names and line numbers, never values, and
it understands quoted values that span several lines (a PEM key in a `.env`),
which `cut` and `grep` do not:

```bash
python3 <skill-dir>/scripts/collect.py --keys .env.test     # 3: DATABASE_URL
python3 <skill-dir>/scripts/collect.py --keys .mcp.json     # mcpServers.x.env.API_KEY (str)
```

It accepts dotenv, JSON and TOML files and refuses everything else (a shell
script such as `.envrc`, a PEM file, a link) rather than guess. For a refused
file, report that it exists and was not examined.

Do not pipe such a file through `cat`, `head`, `grep`, `cut` or a JSON
pretty-printer, and do not open it with a file-read tool. That includes
tracked project config such as `.mcp.json` and `.claude/settings.json`: an
argument list, a URL or a hook command can hold a literal credential, and no
check short of reading the value can rule that out. Work from the collector's
leads and the key listing. Where judging a hook or server needs its full
command line, report what the collector shows (the program it runs, how many
arguments) and put the rest to the user as a question.

A script *file* that a hook or MCP server runs is code: read it.

A `token-shaped-string` lead is a line that may hold a real value. Judge it
without displaying that line: from the path (a fixtures directory), the file's
header or docstring, and `git log --oneline -- <path>`. Read around the lead's
line number, not at it.

The same rule covers the environment. Do not run `env`, `printenv` or `set`
to see what the machine part reported: the collector's `env:NAME` leads are
the names, and the values are not the audit's business.
