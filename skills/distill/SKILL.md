---
name: distill
description: Distill conversation context files into the long-term memory graph. Use when the user says "distill", "distill context", "save this to memory", or when 3+ undistilled context files have accumulated.
---

# Distill Conversation Context into the Memory Graph

Review context files in `~/.claude/context/` and extract what matters into the memory-graph MCP server as granular, connected nodes.

## Steps

### 1. Gather
First call the **`memory_distill` tool** — the mechanical lane promotes all structured entries with zero LLM work and returns a RESIDUE list (narrative bullets, refused promotions, unknown relations). Your job is only what it left behind. (Do NOT try `claude-memory-graph distill` in Bash — the CLI is not on PATH in plugin installs; the tool is the same code running inside the live server, which is also safer.) Then read the remaining `.md` files in `~/.claude/context/` with `distilled: false` in frontmatter. If the mechanical lane archived everything and there is no residue, report its summary and stop.

### 2. Analyse
Context entries come in two shapes, and they cost you very differently — do not re-derive what is already structured:

- **Structured entries** (a bullet with indented `key: value` lines) are pre-shaped graph nodes: the head line is `Type: name`, property lines map straight to `memory_store_resource` properties, `relation: Model/name` lines to `memory_link` calls, `concepts:` to concept links. Your job here is *folding and hindsight only*: merge repeated `Type: name` bullets (latest values win), honour `supersedes:` lines, and drop entries the session itself later invalidated. Do NOT re-summarise or rename them.
- **Narrative entries** (single bullet lines) need the full extraction: decisions WITH rationale, hard-won gotchas, user preferences and corrections, constraints, and the people/projects/technologies involved. Favour the most recent understanding when a topic evolved during a session.

Either way: do NOT save routine task details, one-off trivia, or anything derivable from code/git history. Quality over quantity.

### 3. Store
Work **per entry**: store the node, then immediately its concepts and links, before moving to the next entry — not resources, concepts, and links as three separate graph-wide phases. Use the memory-graph MCP tools:

- `memory_store_resource` — models: Person, Project, Company, Task, Technology, Decision, Pattern. Every resource needs `name` — a short, specific, stable title (Decision: imperative phrase stating the choice, e.g. "Use pyoxigraph over rdflib"); other camelCase properties are free-form. Decisions require `rationale` (plus `outcome`, `date`); Patterns require `description` (plus `example`) — the server rejects creation without them. Add `sourceContext: <context filename>` so nodes are traceable to their session. Upserts by model+name — no need to check existence first, but only set properties you have real content for. If the server reports a similar existing node, prefer updating that node by its exact name; pass `force: true` only when it is genuinely a distinct thing.
- `memory_store_concept` — shared nodes: Skill, Concept, Constraint, Preference (needs `label`, lowercase singular).
- `memory_link` — connect everything. Prefer the existing relations (an unknown relation errors with the full current list); only when nothing genuinely fits, pass `new_relation_description` plus `new_relation_verb_forms` (the phrasings a future question would use — required; they make the relation groundable by retrieval). Typical shape: Person worksOn Project; Project uses Technology; Decision affects Project; Pattern appliesTo Project; Decision manifestsIn Pattern (the anchored layout/trace where the choice lives in code — put file paths in that Pattern's `anchorPath`, not in the Decision's properties); Project hasConstraint Constraint; Person hasPreference Preference.

Write for retrieval — future recall is lexical and link-walking, so the associations must be in the data:
- **`aliases` property on every substantial node**: the 2–3 phrasings a future prompt would plausibly use (Pattern "RocksDB exclusive lock" → `aliases: "db locking, database lock"`). This is what lets a dumb matcher bridge paraphrase.
- **Link every node to at least one concept** — concepts are the associative index; a node with no concept link is invisible to associative recall.
- **Property values use the words future-you would search with**, not session-local shorthand.

Keep property values terse — one or two sentences. A node nobody links to is usually not worth storing.

### 4. Mark and archive
Set `distilled: true` in each processed file's frontmatter, then move it to `~/.claude/context/archive/` (never delete). Keep at most 5 active files.

### 5. Report
Terse summary: files processed, nodes created/updated by type, links created, files archived. Optionally run `memory_reflect` to show the resulting graph shape.
