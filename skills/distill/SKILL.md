---
name: distill
description: Distill conversation context files into the long-term memory graph. Use when the user says "distill", "distill context", "save this to memory", or when 3+ undistilled context files have accumulated.
---

# Distill Conversation Context into the Memory Graph

Review context files in `~/.claude/context/` and extract what matters into the memory-graph MCP server as granular, connected nodes.

## Steps

### 1. Gather
Read all `.md` files in `~/.claude/context/` with `distilled: false` in frontmatter. If none, tell the user there's nothing to distill and stop.

### 2. Analyse
Across the undistilled files, extract: decisions WITH rationale, hard-won gotchas, user preferences and corrections, constraints, and the people/projects/technologies involved. Favour the most recent understanding when a topic evolved during a session. Do NOT save routine task details, one-off trivia, or anything derivable from code/git history. Quality over quantity.

### 3. Store
Use the memory-graph MCP tools:

- `memory_store_resource` — models: Person, Project, Company, Task, Technology, Decision, Pattern. Every resource needs `name` — a short, specific, stable title (Decision: imperative phrase stating the choice, e.g. "Use pyoxigraph over rdflib"); other camelCase properties are free-form. Decisions require `rationale` (plus `outcome`, `date`); Patterns require `description` (plus `example`) — the server rejects creation without them. Add `sourceContext: <context filename>` so nodes are traceable to their session. Upserts by model+name — no need to check existence first, but only set properties you have real content for. If the server reports a similar existing node, prefer updating that node by its exact name; pass `force: true` only when it is genuinely a distinct thing.
- `memory_store_concept` — shared nodes: Skill, Concept, Constraint, Preference (needs `label`).
- `memory_link` — connect everything. Prefer the existing relations (an unknown relation errors with the full current list); pass `new_relation_description` only when nothing genuinely fits. Typical shape: Person worksOn Project; Project uses Technology; Decision affects Project; Pattern appliesTo Project; Project hasConstraint Constraint; Person hasPreference Preference.

Keep property values terse — one or two sentences. A node nobody links to is usually not worth storing.

### 4. Mark and archive
Set `distilled: true` in each processed file's frontmatter, then move it to `~/.claude/context/archive/` (never delete). Keep at most 5 active files.

### 5. Report
Terse summary: files processed, nodes created/updated by type, links created, files archived. Optionally run `memory_reflect` to show the resulting graph shape.
