# Agent Teams — Full Reference

```
source: https://code.claude.com/docs/en/agent-teams
captured: 2026-07-03
```

`captured` is the last-revised date of this snapshot, not a confirmation that
the live docs still match.

## Enabling

Agent teams are experimental and disabled by default. Set
`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` in the `env` section of `settings.json`
(or the shell environment). Without it, no team is set up at session start, no
team directories are written, and Claude does not spawn or propose teammates.

## Spawning (no setup step)

As of v2.1.178, `TeamCreate` and `TeamDelete` no longer exist. There is no
explicit team-creation step: every session with the env flag set has one
implicit team, and spawning a teammate is just spawning an agent with a name
via the Agent tool (`Agent(name: "teammate-name")`). The first spawn forms the
team, with the current session as lead. The `team_name` input on the Agent
tool is accepted but ignored — the team name is always session-derived (see
Storage below).

Before v2.1.178, you had to ask Claude to create and name a team first, and
Claude used the `TeamCreate`/`TeamDelete` tools to set it up and tear it down.
That flow is gone; describe the task and desired teammates in natural language
and Claude spawns them directly.

## Architecture

| Component     | Role                                                                |
| :------------ | :------------------------------------------------------------------ |
| **Team lead** | The session that spawns teammates and coordinates work (fixed for the team's lifetime) |
| **Teammates** | Separate Claude Code instances, each with its own context window, working on assigned tasks |
| **Task list** | Shared work items that teammates claim and complete                |
| **Mailbox**   | Messaging system for direct inter-agent communication               |

Claude decides whether to propose teammates for a task, or you can ask for
them explicitly — either way, Claude won't spawn teammates without your
approval.

## Storage

Teams and tasks are stored locally under a session-derived name:
`session-` followed by the first eight characters of the session ID.

- Team config: `~/.claude/teams/{team-name}/config.json` (holds runtime state
  such as session IDs and pane IDs — auto-managed, don't hand-edit or
  pre-author; it's overwritten on the next state update)
- Task list: `~/.claude/tasks/{team-name}/`

The team config directory is generated automatically at session startup and
removed when the session ends — there's no separate cleanup step. The task
list directory persists locally (never uploaded) so resumed sessions keep
their tasks, subject to the same `cleanupPeriodDays` setting used for session
transcripts.

The team config's `members` array lists each teammate's name, agent ID, and
agent type; teammates can read it to discover each other. There is no
project-level equivalent — a file like `.claude/teams/teams.json` in a
project is not recognized as config.

## Display Modes

- **In-process** (default as of v2.1.179): all teammates run in the main
  terminal's agent panel. Use up/down arrows to select a teammate, Enter to
  view its transcript and message it directly, Escape to interrupt its
  current turn, `x` to stop it, Ctrl+T to toggle the task list. Works in any
  terminal, no extra setup.
- **Split panes**: each teammate gets its own pane. Requires tmux, or iTerm2
  with the `it2` CLI (enable iTerm2's Python API under Settings → General →
  Magic).

Configure in `~/.claude/settings.json`:
```json
{ "teammateMode": "in-process" }
```
Per-session override: `claude --teammate-mode in-process`

Valid values: `"in-process"` (default), `"auto"` (split panes when already
inside tmux, or iTerm2 with `it2` installed; otherwise in-process), `"tmux"`
(split panes, auto-detects tmux vs iTerm2), and `"iterm2"` (v2.1.186+, forces
iTerm2 native split panes, requires `it2`).

Before v2.1.179 the default was `"auto"`, so sessions upgraded across that
boundary keep split panes unless `teammateMode` is set explicitly.

As of v2.1.199, an idle teammate's row stays visible while any teammate or
subagent is still working; once everyone is idle, idle rows hide after 30
seconds and reappear on the teammate's next turn (the teammate keeps running
while hidden — message it by name to bring the row back). More than three
idle teammates collapse into one `N idle agents` row; select and press Enter
to expand.

## Communication

- **message**: send to one specific teammate by name (send one message per
  recipient to reach everyone — there's no built-in broadcast-all primitive)
- Messages are delivered automatically. The lead does not need to poll.
- Idle notifications: a teammate that finishes and stops automatically
  notifies the lead. As of v2.1.198, a teammate whose turn ends on an API
  error notifies the lead that it failed and includes the error text.
- When one agent messages another via SendMessage, the recipient is told the
  message came from another Claude session, not from the user. A teammate
  cannot approve a permission prompt or supply consent on the user's behalf,
  and a denied teammate cannot relay the action through another teammate to
  bypass the check — in auto mode, a relayed "approval" from another agent is
  treated as untrusted input, not user confirmation.

## Task Management

Three states: pending, in progress, completed. Tasks can depend on other
tasks — a pending task with unresolved dependencies cannot be claimed until
those dependencies complete; the system unblocks dependents automatically.
Task claiming uses file locking to prevent race conditions when multiple
teammates try to claim the same task.

Assignment modes:
- **Lead assigns**: direct a specific task to a specific teammate
- **Self-claim**: after finishing a task, a teammate picks up the next
  unassigned, unblocked task automatically

## Plan Approval

Require teammates to plan before implementing:

```
Spawn an architect teammate to refactor the auth module.
Require plan approval before they make any changes.
```

The teammate works in read-only plan mode until the lead approves. The lead
reviews and approves or rejects with feedback; on rejection the teammate
stays in plan mode, revises, and resubmits. Once approved it exits plan mode
and implements. The lead makes approval decisions autonomously — influence
its judgment via prompt criteria: "Only approve plans that include test
coverage" or "reject plans that modify the database schema."

## Models and Effort

Teammates do not inherit the lead's `/model` selection by default. Set
**Default teammate model** in `/config` (choose "Default (leader's model)" to
have teammates follow the lead's current model), or specify a model per spawn
in the prompt ("Use Sonnet for each teammate"). A teammate's model and fast
mode are fixed at spawn — `/model`/`/fast` while viewing a teammate change
the lead's settings instead (as of v2.1.199 this shows a notice; earlier
versions changed the lead silently). Teammates do inherit the lead's
[effort level](https://code.claude.com/docs/en/model-config#adjust-effort-level),
and `/effort` continues to apply to a viewed teammate's later turns. As of
v2.1.186, split-pane teammates also inherit the lead's effort at spawn
(earlier versions did not pass it through).

## Subagent Definitions as Teammates

Reference existing subagent types when spawning:

```
Spawn a teammate using the security-reviewer agent type to audit the auth module.
```

The teammate inherits the definition's `tools` allowlist and `model`. The
definition body is appended to the teammate's system prompt as additional
instructions rather than replacing it. Team coordination tools (SendMessage,
task management) remain available regardless of `tools` restrictions.

Note: `skills` and `mcpServers` frontmatter from subagent definitions are NOT
applied to teammates. Teammates load these from project/user settings, same
as a regular session.

## Quality Gates with Hooks

- `TeammateIdle`: runs when a teammate is about to go idle. Exit code 2 sends feedback and keeps the teammate working.
- `TaskCreated`: runs when a task is being created. Exit code 2 blocks creation with feedback.
- `TaskCompleted`: runs when a task is marked complete. Exit code 2 blocks completion with feedback.

Note: the `team_name` field in these hook payloads carries the session-derived
team name and is deprecated.

## Permissions

Teammates inherit the lead's permission settings at spawn time. If the lead
uses `--dangerously-skip-permissions`, all teammates do too. Individual modes
can be changed after spawning but not at spawn time. Teammate permission
prompts bubble up to the lead session — approve them there.

Pre-approve common tool operations in permission settings before spawning to
reduce prompt interruptions during parallel work.

## Context

Each teammate loads the same project context as a regular session (CLAUDE.md,
MCP servers, skills) plus the spawn prompt. The lead's conversation history
does NOT carry over — spawn prompts must include all task-specific context.
The lead assigns every teammate's name at spawn time; any teammate can
message any other by that name, so give the lead explicit names to reference
in later prompts.

## Shutdown and Cleanup

1. Shut down specific teammates by name: "Ask the researcher to shut down" —
   the lead sends a shutdown request and the teammate can approve (exiting
   gracefully) or reject with an explanation.
2. There is no separate team-cleanup step or command: the team config
   directory is removed automatically when the session ends. The task list
   directory persists locally so a resumed session keeps its tasks.

## Limitations

- **No session resumption for in-process teammates**: `/resume` and
  `/rewind` do not restore them. After resuming, the lead may try to message
  teammates that no longer exist — tell it to spawn replacements.
- Task status can lag — teammates sometimes fail to mark tasks complete,
  which blocks dependents; check manually or nudge the teammate.
- Shutdown can be slow (teammates finish their current request/tool call
  first).
- **One team per session**: exactly one implicit team per session, scoped to
  that session. No additional named teams and no sharing a team across
  sessions.
- **No nested teams**: teammates cannot spawn their own teammates; only the
  lead manages the team.
- **No background subagents from in-process teammates**: an in-process
  teammate's own subagents run in the foreground. Requesting a background one
  (`run_in_background` or a subagent definition with `background: true`)
  errors, because a teammate's background work can't outlive the lead's
  process.
- Lead is fixed for the team's lifetime — no promoting a teammate to lead.
- Permissions set at spawn (changeable after, not during).
- Split panes require tmux or iTerm2 (not VS Code terminal, Windows Terminal,
  or Ghostty). The default in-process mode works everywhere.

## Refreshing this file

Re-read https://code.claude.com/docs/en/agent-teams, update `captured` to the
refresh date, and revise only what changed. Ship the change as a plugin version
bump so installations pick it up.
