# Code knowledge — the semantic overlay and the derived code graph

Status: **horizon exploration, not yet implemented.** A fourth application of the system's core
pattern: authored knowledge lives in the graph; everything derivable is generated into
rebuildable structures outside it.

## The dividing line is the capture rubric

"Can memory map and understand a codebase?" splits on the rubric's *not derivable* test:

- **Structure** (where is `save()` defined, who calls it, imports) is derivable — the code is
  the authoritative store and grep/LSP answer from it, always fresh. Bulk structure must
  **never** be authored into the memory graph: it goes stale every commit, its volume
  (thousands of symbols) would destroy the analyzer's term-distinctiveness, and an LLM is the
  wrong author for it. Note the objection is to *mechanical enumeration*, not to structural
  content: the one authored exception is cost-gated — the **finding** of a genuine
  investigation (a path trace that took many greps to establish) earns a Pattern
  (`kind: trace`, anchors mandatory, the question as aliases) under
  [tasks/code-memory-rules](tasks/code-memory-rules.md).
- **The semantic overlay** — *why* the code is the way it is — is not derivable and is exactly
  what the graph already holds: Decisions with rationale ("full dump + atomic rename because
  MCP stdio servers die ungracefully"), Patterns/gotchas ("FILTER on a VALUES var must be
  top-level"), architectural constraints ("all mutations persist via the dispatcher's
  `_MUTATING` hook"). Small (dozens of nodes per project), durable across refactors, and the
  knowledge that leaves when a person does.
- **Orientation** — the middle band live use surfaced: how and where things are stored,
  located, and wired ("session state lives under `~/.claude/hook-kit/sessions/`, atomic
  tmp+rename"). Convention-level, multi-file to re-derive, churns only on deliberate
  restructuring — so it passes the rubric and belongs in the graph, under the keep test and
  volume guard in [tasks/code-memory-rules](tasks/code-memory-rules.md).

The scope discipline stays, refined: **memory answers *why* and holds the *map*; code tools
answer symbol-level *where*.**

## The structural half, done right: a derived code graph

Same move as the retrieval index (see "Aliases vs the index", RETRIEVAL.md): derive it, don't
author it. Tree-sitter/LSP extraction over the repo emits RDF — symbols, definitions, imports,
call edges — into a **separate named graph** (`…/graph/code/<repo>`), regenerated on commit,
disposable, never hand-written. Stale-proof by construction. Prior art treats code as a
queryable database already (Sourcegraph SCIP, GitHub stack graphs, Meta's Glean, CodeQL); none
of them join it to a memory layer.

## The join: code anchors

Memory nodes about code carry anchor properties:

- `anchorPath` — repo-relative file path
- `anchorSymbol` — function/class name where applicable
- `anchorCommit` — the commit hash when the memory was written

Anchors buy two things, in order of arrival:

1. **Drift detection (near-term, no code graph needed):** if the anchored file has changed
   since `anchorCommit`, recall flags the memory *possibly stale* — a mechanical freshness
   check for the semantic overlay, using only git.
2. **Cross-graph queries (once the derived graph exists):** anchors and the code graph share
   symbol IRIs, so the query planner can join them —
   *"what gotchas apply to code that calls `save()`?"* = structural hop (callers, derived
   graph) ⋈ semantic hop (Patterns anchored to those files, memory). Two-graph multi-hop
   questions no similarity-based system can represent; the CIDOC/Arches shape again — a large
   mechanically-derived substrate under a small curated semantic layer.

## Phasing

1. **Anchors + drift flag** — anchor properties written by distill when a memory is about code
   (protocol already says "reference file paths"; this makes it structured); recall appends
   `(code changed since)` when the anchor is stale. Cheap, immediately useful.
2. **Derived code graph v0** — extractor (tree-sitter or SCIP import) → NQuads for one repo;
   rebuilt by a git hook; queryable via `memory_query`.
3. **Planner integration** — code-graph vocabulary (symbol names) joins the grounding lexicon;
   cross-graph path templates.
