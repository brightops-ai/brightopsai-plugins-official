# Agent Teams — Full Reference

Source: https://code.claude.com/docs/en/agent-teams

## Architecture

| Component     | Role                                                                |
| :------------ | :------------------------------------------------------------------ |
| **Team lead** | Main session that creates the team, spawns teammates, coordinates   |
| **Teammates** | Separate Claude Code instances working on assigned tasks            |
| **Task list** | Shared work items that teammates claim and complete                 |
| **Mailbox**   | Messaging system for inter-agent communication                     |

Local storage:
- Team config: `~/.claude/teams/{team-name}/config.json` (auto-managed — do not edit by hand)
- Task list: `~/.claude/tasks/{team-name}/`

## Display Modes

- **In-process** (default): all teammates in main terminal. Shift+Down to cycle. Works anywhere.
- **Split panes**: each teammate in its own pane. Requires tmux or iTerm2.

Configure in `~/.claude.json`:
```json
{ "teammateMode": "in-process" }
```
Per-session override: `claude --teammate-mode in-process`

Default `"auto"` uses split panes inside tmux, otherwise in-process.

## Communication

- **message**: send to one specific teammate by name
- **broadcast**: send to all teammates (use sparingly — costs scale with team size)

Messages are delivered automatically. The lead does not need to poll.

## Task Management

Three states: pending, in progress, completed. Tasks can depend on other tasks —
blocked tasks cannot be claimed until dependencies complete. File locking prevents
race conditions when multiple teammates try to claim the same task.

Assignment modes:
- **Lead assigns**: direct a specific task to a specific teammate
- **Self-claim**: teammates pick up the next unassigned, unblocked task automatically

## Plan Approval

Require teammates to plan before implementing:

```
Spawn an architect teammate to refactor the auth module.
Require plan approval before they make any changes.
```

The teammate works in read-only plan mode until the lead approves. On rejection,
the teammate revises and resubmits. Influence approval criteria in the prompt:
"Only approve plans that include test coverage."

## Subagent Definitions as Teammates

Reference existing subagent types when spawning:

```
Spawn a teammate using the security-reviewer agent type to audit the auth module.
```

The teammate inherits the definition's `tools` allowlist and `model`. The definition
body appends to the teammate's system prompt. Team coordination tools (SendMessage,
task management) remain available regardless of `tools` restrictions.

Note: `skills` and `mcpServers` frontmatter from subagent definitions are NOT applied
to teammates. Teammates load these from project/user settings.

## Quality Gates with Hooks

- `TeammateIdle`: runs when a teammate is about to go idle. Exit code 2 sends feedback and keeps the teammate working.
- `TaskCreated`: runs when a task is being created. Exit code 2 blocks creation with feedback.
- `TaskCompleted`: runs when a task is marked complete. Exit code 2 blocks completion with feedback.

## Permissions

Teammates inherit the lead's permission settings at spawn time. If the lead uses
`--dangerously-skip-permissions`, all teammates do too. Individual modes can be
changed after spawning but not at spawn time.

Pre-approve common tool operations in permission settings before spawning to
reduce prompt interruptions during parallel work.

## Context

Each teammate loads the same project context as a regular session (CLAUDE.md, MCP
servers, skills) plus the spawn prompt. The lead's conversation history does NOT
carry over — spawn prompts must include all task-specific context.

## Shutdown and Cleanup

1. Shut down specific teammates: "Ask the researcher to shut down"
2. Clean up the team via the lead: "Clean up the team"
3. The lead checks for active teammates before cleanup — shut them down first
4. Never let teammates run cleanup (their team context may not resolve correctly)

## Limitations

- No session resumption for in-process teammates (`/resume` and `/rewind` do not restore them)
- Task status can lag — teammates sometimes fail to mark tasks complete
- Shutdown can be slow (teammates finish current request first)
- One team per session — clean up before starting a new one
- No nested teams (teammates cannot spawn their own teams)
- Lead is fixed for the team's lifetime
- Permissions set at spawn (changeable after, not during)
- Split panes require tmux or iTerm2 (not VS Code terminal, Windows Terminal, or Ghostty)
