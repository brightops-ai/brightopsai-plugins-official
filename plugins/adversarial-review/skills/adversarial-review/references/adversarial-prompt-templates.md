# Adversarial Prompt Templates

Templates for requesting structured adversarial reviews from Grok via browser automation.

**Audience note:** This file has two audiences. The selection logic, assembly instructions, and fallback rules (outside code blocks) are for the prompt assembler. The template content (inside code blocks) is what Grok sees — it must not reference the assembler, automation tooling, or internal implementation details.

## Template Selection Logic

**Primary method — LLM classifier (recommended):** Before composing the prompt, read the document and reason about which variant fits best. Consider the document's primary purpose, not just keywords:

- Is it describing how components interact? → **Architecture**
- Is it a step-by-step plan with milestones? → **Implementation**
- Is it focused on threats, auth, or data protection? → **Security**
- Is it about user experience, mobile, accessibility, or visual design? → **UX/Product**
- Does it not fit any of the above? → **Standard**

If the document spans multiple categories (e.g., an implementation plan with heavy UX components), select a primary variant and append the secondary variant's dimensions as items 8-14 in the review instructions. Note both variants in the selection reasoning (e.g., "Selecting Implementation as primary + UX/Product as secondary — document is a phased build plan but Phase 4 is entirely UX/accessibility work").

**Manual override:** If the user specifies a variant (e.g., "review this with the security lens"), use that variant regardless of auto-detection.

**Classifier prompt template** — use this to make variant selection deterministic:

```
Read this document and classify it for adversarial review. Pick the single best primary variant. If the document clearly spans two categories, also pick a secondary variant.

Variants: Standard, Architecture, Implementation, Security, UX/Product

Example: {"primary": "Implementation", "secondary": "UX/Product", "reasoning": "Phased build plan with numbered steps, but Phase 4 covers mobile and accessibility"}

Respond with ONLY this JSON (no other text):
{"primary": "variant_name", "secondary": "variant_name_or_null", "reasoning": "one sentence explaining why"}
```

**Parsing the classifier response:**

1. Extract the first `{...}` block from the response using regex (models sometimes prepend text or wrap in markdown)
2. Parse with `JSON.parse` — if it fails, try stripping markdown code fences and re-parsing
3. Validate that `primary` is one of the 5 known variants
4. If parsing fails after retries, fall back to keyword hinting and log a warning
5. Never block the review pipeline on a classifier failure — always degrade gracefully to Standard

**Fallback — keyword hinting:** If the classifier fails or returns ambiguous results, use keyword density as a tie-breaker:

| Variant | Hint keywords |
|---------|--------------|
| **Architecture** | "component", "service", "data flow", "system design", "API boundary", "microservice", "schema" |
| **Implementation** | "step 1", "implementation", "milestone", "dependency", "build sequence", "deploy", "phase" |
| **Security** | "auth", "encryption", "threat", "vulnerability", "token", "permission", "RBAC" |
| **UX/Product** | "mobile", "responsive", "accessibility", "viewport", "UX", "usability", "WCAG", "user flow" |
| **Standard** | Default when no strong signal for the above |

## Standard Adversarial Review

```
## Context

**Project:** {project_name}
**Document type:** {doc_type — plan, design doc, RFC, checklist, etc.}
**Additional context:** {any constraints or goals the user mentioned}

## Document Under Review

Review the attached document ({filename}) from the project sources.

If you cannot access the full current content of {filename} in this conversation, immediately reply "FILE ACCESS FAILURE: I cannot read the project source file. Please provide the document content inline." and stop. Do not guess or hallucinate content.

<DOCUMENT_CONTENT_FALLBACK>
{Fallback: if Grok cannot access the project source file, paste the document content inline here. Size limits:
- Documents under 4,000 tokens (~16,000 characters): paste in full.
- Documents over 4,000 tokens: summarize each major section in 2-3 sentences, preserving all headings, and append "[TRUNCATED — full section available on request]" after each summary. Preserve code blocks, tables, and configuration snippets verbatim (do not summarize these — they are the most review-critical content). Ask the user for confirmation before submitting a truncated version.
Remove the file reference sentence above when using this fallback.}
</DOCUMENT_CONTENT_FALLBACK>

## Review Instructions

You are in ruthless adversarial mode. In every finding and dimension review, produce ONLY problems, risks, and gaps. No praise, no positives, no balancing statements in any finding. Counter your default helpfulness bias — be harsher than usual. If you find yourself writing "however, the plan does well at..." stop and delete it.

The only exception is the final overall assessment, which must include a numeric readiness score. Frame it purely as a risk summary — what must be fixed and how severe the blockers are. Example: "Three Critical blockers (no migration path, missing geocoding, no test plan) make this plan unshippable. Fix these before any implementation begins. Readiness: 25/100."

Assume this plan will be implemented exactly as written — what will go wrong?

Review the document across these dimensions:

1. **Logical gaps and unstated assumptions** — What is taken for granted that shouldn't be?
2. **Missing edge cases and failure modes** — What happens when things go wrong?
3. **Scalability and performance concerns** — Will this hold up under load or growth?
4. **Security and data integrity risks** — Where could data leak, be corrupted, or be accessed improperly?
5. **Simpler alternatives overlooked** — Is there a less complex way to achieve the same goal?
6. **Dependency and sequencing issues** — Are steps in the right order? Are there hidden dependencies?
7. **Production breakage risks** — What will cause incidents when this ships?

For each finding, provide:
- A **number** (sequential)
- A **severity tag**: Critical (will cause failure), Major (significant risk), Minor (should fix), or Nit (nice to have)
- A **rationale** explaining the concern (2-3 sentences)
- A **concrete suggestion** for how to address it
- A **self-improvement note** — one sentence on how this finding itself could be made sharper, more specific, or more actionable. This is your chance to critique your own review. If the finding is already as good as it can be, say why.

First, output a JSON array of findings for machine parsing. Then repeat in markdown for readability. Deviate from this format and the review is useless.

JSON schema (output this first):
```json
[{"id": 1, "severity": "Critical|Major|Minor|Nit", "title": "...", "rationale": "...", "suggestion": "...", "self_improvement": "..."}]
```

Then format each finding in markdown as:

### [N]. [Severity] — [Title]
**Rationale:** ...
**Suggestion:** ...
**Self-improvement:** ...

Here are examples of the quality and format expected (these are illustrative — adapt severity and domain to the actual document):

### 1. Critical — No rollback path for data schema change
**Rationale:** The plan introduces a new storage format but never addresses how to revert if the migration fails mid-way. Users who hit an error will be left with partially-migrated data that neither the old nor new code can read. This is a data-loss scenario with no recovery path documented.
**Suggestion:** Add an explicit rollback step: back up existing data before migration, validate the new format before deleting the backup, and document the manual recovery procedure.
**Self-improvement:** This finding would be stronger if it named the specific migration step that's most likely to fail and estimated the blast radius (number of affected users/records).

### 2. Minor — Success metrics are unmeasurable as stated
**Rationale:** The plan claims a performance target but specifies no tooling, benchmark dataset, or CI integration to measure it. Without automated verification, the metric will never be tested and will silently regress after initial development.
**Suggestion:** Define the measurement tool, test dataset size, and where in CI the check runs. Make the metric a gate, not an aspiration.
**Self-improvement:** This finding is already specific and actionable — it names the exact gap (no tooling) and the exact fix (CI gate with dataset).

End with a brief overall assessment (2-3 sentences). State what must be fixed before implementation can begin and rate readiness as a score out of 100. This is a risk summary, not a compliment — frame it in terms of remaining blockers and their severity.
```

## Architecture Variant

Replace the review dimensions with:

```
1. **Component boundary clarity** — Are responsibilities well-defined? Any overlapping concerns?
2. **Data flow completeness** — Can you trace every piece of data from source to destination?
3. **Interface contracts** — Are APIs, events, and shared types well-specified?
4. **Coupling and cohesion** — Are components appropriately decoupled? Any hidden tight coupling?
5. **Extensibility and evolution** — How painful will the next feature or migration be?
6. **Failure isolation** — Does a failure in one component cascade to others?
7. **Observability gaps** — Can you debug this system in production with the planned instrumentation?
```

## Implementation Plan Variant

Replace the review dimensions with:

```
1. **Step completeness** — Are any steps missing? Could you hand this to an engineer and have them execute it without questions?
2. **Sequencing correctness** — Are steps in the right order? Any hidden dependencies that would block progress?
3. **Estimation accuracy** — Are any steps significantly underscoped or overscoped?
4. **Rollback strategy** — If step N fails, can you undo it without data loss?
5. **Testing gaps** — What would you need to verify at each step that isn't called out?
6. **Environment assumptions** — What tooling, access, or infrastructure is assumed but not stated?
7. **Parallelization opportunities** — Which steps could run concurrently to reduce wall-clock time?
```

## UX/Product Variant

Replace the review dimensions with:

```
1. **User mental model alignment** — Does the design match how users actually think about this task? Any confusing navigation or terminology?
2. **Mobile and responsive gaps** — Will this work on small screens? Any touch targets too small, horizontal scrolling, or hidden functionality?
3. **Visual hierarchy and information density** — Can users find what matters quickly? Is anything buried or overwhelming?
4. **Accessibility compliance** — Are there WCAG violations? Missing ARIA labels, poor contrast, keyboard traps, or screen reader dead ends?
5. **Performance perception** — Will users feel the app is fast? Any loading states missing, skeleton screens needed, or janky transitions?
6. **Success metrics realism** — Are the stated metrics measurable? Can they actually be achieved with the proposed approach?
7. **Edge case UX** — What happens with 0 results, 10,000 results, network errors, or stale data? Are empty states and error states designed?
```

## Security Variant

Replace the review dimensions with:

```
1. **Authentication and authorization gaps** — Where could an unauthorized actor gain access?
2. **Data exposure risks** — What sensitive data could leak through logs, errors, APIs, or storage?
3. **Input validation** — Where is untrusted input processed without validation or sanitization?
4. **Cryptographic concerns** — Are algorithms, key management, and protocols appropriate?
5. **Privilege escalation paths** — Can a low-privilege actor reach high-privilege operations?
6. **Supply chain risks** — Are dependencies trusted? Could a compromised package affect this system?
7. **Compliance and audit** — Does this meet relevant compliance requirements (SOC2, GDPR, etc.)?
```

## Variant Example Findings

Each variant should include at least one example finding in the assembled prompt to anchor output quality. When assembling a non-Standard variant, append the relevant example below after the dimension list (in the same position as the Standard template's examples).

### Architecture example:

```
### 1. Major — Service boundary between auth and user-profile is undefined
**Rationale:** The diagram shows auth and user-profile as separate services but every API call from user-profile hits the auth database directly. This bypasses the auth service's validation logic and creates hidden tight coupling that will break when either service is deployed independently.
**Suggestion:** Define an explicit auth API contract (token validation endpoint) that user-profile calls instead of direct DB access. Document the contract in the interface contracts section.
**Self-improvement:** This finding would be stronger with a sequence diagram showing the current vs. proposed call path.
```

### Implementation example:

```
### 1. Major — Step 3 depends on Step 6's output but is sequenced before it
**Rationale:** The migration script (Step 3) requires the new API server to be running for data validation, but the API server isn't deployed until Step 6. An engineer following the plan in order will hit a blocker at Step 3 with no documented workaround.
**Suggestion:** Either reorder Steps 3 and 6, or add a "local validation mode" to the migration script that doesn't require the full API server.
**Self-improvement:** Finding is specific about the dependency chain; it could also flag whether any other steps have similar hidden ordering issues.
```

### UX/Product example:

```
### 1. Major — Empty state for zero search results is undesigned
**Rationale:** The plan covers grid, table, and map views for listings but never mentions what the user sees when a search returns zero results. A blank screen with no guidance will cause confusion and support tickets. This is especially likely for niche product searches.
**Suggestion:** Design an empty state with: a clear "No results found" message, the search term echoed back, and 2-3 suggested actions (broaden search, adjust filters, try different keywords).
**Self-improvement:** This finding is actionable but could be strengthened by naming which specific views (grid? map? both?) need the empty state treatment.
```

### Security example:

```
### 1. Critical — API tokens stored in localStorage are accessible to any XSS payload
**Rationale:** The auth section stores session tokens in localStorage for persistence across page reloads. Any cross-site scripting vulnerability in the app (or any third-party script) can read localStorage and exfiltrate the token silently. This is a well-known attack vector that bypasses CSRF protections entirely.
**Suggestion:** Move token storage to httpOnly cookies with SameSite=Strict. If localStorage is required for offline support, encrypt the token with a key derived from a server-set httpOnly cookie.
**Self-improvement:** This finding is already highly specific and actionable — it names the exact attack vector and provides a concrete alternative.
```

## Prompt Assembly

When composing the final prompt:

1. Start with the Context block — fill in project name, doc type, and any user-provided context
2. Reference the uploaded filename by name in the Document block (e.g., "Review the attached document (my-plan.md)"). Prefer referencing project source files over pasting inline — it keeps the prompt concise. However, if Grok fails to read the file (returns "FILE ACCESS FAILURE" or hallucinates content), fall back to pasting the document inline using the `DOCUMENT_CONTENT_FALLBACK` block, respecting the token-size limits documented there.
3. Append the appropriate Review Instructions variant
4. If the user specified additional focus areas, append them as a numbered addition to the review dimensions

**Important:** Over time, a project may accumulate multiple source files from prior reviews. Always reference the specific filename being reviewed so Grok doesn't confuse it with older versions or unrelated documents.

**Token budget:** Estimate the assembled prompt size before submitting. Use ~4 characters per token as a rough guide:

| Component | Typical size |
|-----------|-------------|
| Context block | ~200 tokens |
| Document reference (file mode) | ~50 tokens |
| Document inline (fallback mode) | varies — see DOCUMENT_CONTENT_FALLBACK limits |
| Review instructions + dimensions | ~400 tokens |
| JSON schema + format rules | ~150 tokens |
| Example findings (1 per variant) | ~200 tokens each |
| Anti-bias + assessment rules | ~150 tokens |

**Target:** Keep the assembled prompt under 8,000 tokens total. If a primary + secondary variant with inline document fallback exceeds this:
1. Drop the secondary variant's example finding (keep its dimensions)
2. If still over, drop the primary variant's example finding
3. If still over, summarize the inline document per the DOCUMENT_CONTENT_FALLBACK truncation rules

## Maintenance

- These templates should be reviewed and updated quarterly based on actual document types encountered
- Track which variant is selected most often — if Standard dominates, the detection logic or variant coverage may need expansion
- When adding new variants, update the Template Selection Logic table and the Prompt Assembly instructions
- Deprecated dimensions should be removed, not commented out
- Audit assembled prompt token sizes quarterly — if the template file grows beyond 20KB, consider splitting variant examples into a separate reference file
