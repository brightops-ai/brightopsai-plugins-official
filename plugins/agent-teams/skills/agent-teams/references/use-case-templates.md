# Agent Teams — Use Case Templates

Ready-to-use prompt templates for common team patterns. Each includes the spawn
instruction with full context — copy, customize the placeholders, and use directly.

## 1. Parallel Code Review

Best when: reviewing a PR from multiple independent angles simultaneously.

```
Create an agent team to review PR #<number>. Spawn three reviewers:

- "security-reviewer" with the prompt: "Review PR #<number> for security
  vulnerabilities. Focus on auth bypasses, injection risks, and data exposure.
  Rate each finding by severity. Report findings to the lead."

- "perf-reviewer" with the prompt: "Review PR #<number> for performance
  impact. Check for N+1 queries, unnecessary allocations, missing indexes,
  and hot-path regressions. Report findings to the lead."

- "test-reviewer" with the prompt: "Review PR #<number> for test coverage.
  Identify untested code paths, missing edge cases, and brittle assertions.
  Report findings to the lead."

Synthesize all findings into a single review summary when they finish.
```

Why it works: a single reviewer gravitates toward one issue type. Splitting
criteria means each domain gets thorough, unbiased attention.

## 2. Competing Debug Hypotheses

Best when: root cause is unclear and anchoring bias is a risk.

```
Users report <symptom>. Create an agent team to investigate. Spawn 4-5
teammates, each with a different hypothesis:

- "hypothesis-network" with the prompt: "Investigate whether <symptom> is
  caused by network issues. Check connection handling, timeouts, and retry
  logic in <relevant paths>. Try to disprove the other teammates' theories.
  Share evidence with the team."

- "hypothesis-state" with the prompt: "Investigate whether <symptom> is
  caused by state management bugs. Check <relevant paths> for race conditions,
  stale caches, or incorrect state transitions. Challenge other theories."

[... additional hypotheses ...]

Have them debate like a scientific review — each teammate's job is to disprove
the others. Update <findings doc> with whatever consensus emerges.
```

Why it works: multiple investigators actively disproving each other avoids
anchoring on the first plausible explanation.

## 3. New Feature — Parallel Modules

Best when: building independent pieces that don't touch the same files.

```
Create an agent team to build <feature>. Spawn teammates:

- "data-dev" with the prompt: "Own the data layer at <path>. Create models,
  migrations, and queries for <feature>. Use <ORM> and follow existing
  patterns in <example file>. Coordinate the schema with api-dev before
  implementing."

- "api-dev" with the prompt: "Own the API layer at <path>. Build endpoints
  for <feature> with <auth middleware>. Use <validation library> for input.
  Agree on request/response schema with data-dev and frontend-dev before
  implementing."

- "frontend-dev" with the prompt: "Own the frontend at <path>. Build
  components and hooks for <feature>. Use <framework/library>. Coordinate
  on API contract with api-dev before implementing."

- "test-dev" with the prompt: "Own tests at <path>. Write unit and
  integration tests for <feature> across all layers. Wait for data-dev,
  api-dev, and frontend-dev to complete before writing tests."

Have test-dev's tasks depend on the other teammates' tasks.
```

## 4. Cross-Layer Coordination

Best when: a single change spans frontend, backend, and infrastructure.

```
Add <feature> that touches the React frontend, Express API, and Postgres
schema. Create a team with one teammate per layer:

- "schema-dev" with the prompt: "Own the database layer. Add the migration
  and update Prisma schema for <feature>. Coordinate with api-dev on the
  data contract."

- "api-dev" with the prompt: "Own src/api/. Add routes and controllers for
  <feature>. Wait for schema-dev's migration before implementing queries.
  Share the API contract with frontend-dev."

- "frontend-dev" with the prompt: "Own src/components/. Build the UI for
  <feature>. Wait for api-dev to share the API contract. Use existing
  design system components."

Have them coordinate on contracts before implementing.
```

## 5. Research and Exploration

Best when: evaluating options or gathering information from multiple angles.
Good starter pattern — read-only, low risk.

```
I'm designing <system>. Create an agent team to explore from different angles:

- "ux-researcher" with the prompt: "Research the UX implications of <system>.
  Explore user workflows, identify friction points, and suggest interaction
  patterns. Challenge architecture decisions that hurt usability."

- "architect" with the prompt: "Design the technical architecture for
  <system>. Consider scalability, maintainability, and integration with
  existing systems at <paths>. Justify trade-offs."

- "skeptic" with the prompt: "Play devil's advocate for <system>. Challenge
  assumptions from ux-researcher and architect. Identify risks, edge cases,
  and failure modes. Propose alternatives where the design is weak."
```

## 6. Large Refactor — File-Partitioned

Best when: applying the same pattern across many files.

```
Create a team with 4 teammates to refactor <description>. Use Sonnet for
each teammate. Partition files so each teammate owns a distinct set:

- "refactor-1" with the prompt: "Refactor <pattern> in these files:
  <file list 1>. Follow the approach in <example file>. Do not touch
  files outside your list."

[... refactor-2, refactor-3, refactor-4 with their file lists ...]

No overlaps — each teammate owns only their listed files.
```
