---
name: agent-teams
description: >
  This skill should be used when the user asks to "create an agent team",
  "spawn teammates", "set up parallel agents", "coordinate multiple Claude
  sessions", "do a parallel code review", "debug with competing hypotheses",
  "build features across layers with separate agents", or any task that
  benefits from multiple Claude Code instances working together. Also trigger
  when the user mentions "agent team", "teammates", "multi-agent", "parallel
  agents", or describes work that could be split across independent workers
  who need to communicate — even if they don't explicitly say "agent team".
---

# Agent Teams Orchestration

Coordinate multiple Claude Code instances as a team with shared tasks,
inter-agent messaging, and centralized management.

## References

- `references/full-docs.md` — architecture, tools, config, permissions, and limitations
- `references/use-case-templates.md` — ready-to-use prompt templates with spawn examples

## Prerequisites

- Claude Code v2.1.178+ (spawns teammates directly via the Agent tool with a
  `name`; no separate team-creation step, and every session has one implicit
  team while the flag below is set)
- `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` in settings.json `env` section
- For split panes: tmux or iTerm2 with the `it2` CLI (optional — in-process
  is the default display mode and works anywhere)

## Decision: Agent Team vs Subagents vs Single Session

Evaluate the task before creating a team:

**Create an agent team when:**
- Work partitions into 3-5 independent parallel tracks
- Multiple perspectives add value (review, research, debugging)
- Teammates need to discuss, challenge, or coordinate with each other
- Each teammate owns different files with no overlap

**Use subagents instead when:**
- Workers only need to report results back — no inter-agent discussion
- Tasks are quick and focused
- The result matters, not the collaboration

**Use a single session when:**
- Tasks are sequential or heavily interdependent
- Work involves editing the same files
- The task is routine (teams have significant token overhead)

## Workflow

### 1. Analyze the Task

Identify:
1. Can this split into 3-5 independent tracks?
2. What files/directories does each track own?
3. Are there dependencies between tracks?
4. Will teammates need to discuss findings or just report back?

If the answer to #4 is "just report back," use subagents instead.

### 2. Design the Team

- **3-5 teammates** for most workflows (diminishing returns beyond that)
- **5-6 tasks per teammate** to keep everyone productive
- Name teammates descriptively (e.g., "security-reviewer", "frontend-dev")
- Partition file ownership — no two teammates editing the same file

### 3. Write Spawn Prompts

Teammates do NOT inherit the lead's conversation history. The spawn prompt
is their only context. Include:

- What to do and why
- Specific files/directories they own
- Technical context (frameworks, patterns, constraints)
- Who to coordinate with and what to report
- Whether plan approval is required

**Example:**
```
Spawn a teammate named "api-dev" with the prompt: "Own the Express API
layer at src/api/. Build the new /users endpoint with JWT auth middleware.
The app uses Prisma for DB access and Zod for validation. Coordinate with
frontend-dev on the request/response schema before implementing. Report
blockers to the lead."
```

### 4. Coordinate and Monitor

- Create tasks with explicit dependency chains when needed
- Require plan approval for risky changes: "Only approve plans that include test coverage"
- Let teammates self-claim independent tasks from the shared list
- If the lead starts implementing instead of delegating, tell it:
  "Wait for your teammates to complete their tasks before proceeding"

### 5. Shut Down

Shut down via the lead (never via teammates), one at a time by name:
"Ask [name] to shut down". There is no separate team-cleanup command — the
team's shared directories are removed automatically when the session ends,
and the task list persists locally for a resumed session.

## Guardrails

- Partition file ownership clearly — two teammates on the same file means overwrites
- Include full context in spawn prompts — history does not carry over
- Start with read-only tasks (review, research) before parallel implementation
- Pre-approve common tool permissions before spawning to reduce interruptions
- Token usage scales linearly with teammate count — size teams appropriately

See `references/full-docs.md` for architecture details, display modes, hooks,
permissions, and known limitations. See `references/use-case-templates.md` for
ready-to-use prompt templates.
