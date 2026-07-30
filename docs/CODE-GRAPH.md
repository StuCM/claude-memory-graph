# Code knowledge — the semantic overlay and the derived code graph

Status: **horizon exploration, not yet implemented.** A fourth application of the system's core
pattern: authored knowledge lives in the graph; everything derivable is generated into
rebuildable structures outside it.

## The dividing line is the capture rubric

"Can memory map and understand a codebase?" splits on the rubric's *not derivable* test:

- **Structure** (where is `save()` defined, who calls it, imports) is derivable — the code is
  the authoritative store and grep/LSP answer from it, always fresh. Structure must **never**
  be written into the memory graph: it goes stale every commit, its volume (thousands of
  symbols) would destroy the analyzer's term-distinctiveness, and an LLM is the wrong author
  for it.
- **The semantic overlay** — *why* the code is the way it is — is not derivable and is exactly
  what the graph already holds: Decisions with rationale ("full dump + atomic rename because
  MCP stdio servers die ungracefully"), Patterns/gotchas ("FILTER on a VALUES var must be
  top-level"), architectural constraints ("all mutations persist via the dispatcher's
  `_MUTATING` hook"). Small (dozens of nodes per project), durable across refactors, and the
  knowledge that leaves when a person does.

The scope discipline stays: **memory answers *why*; code tools answer *where*.**

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

## Buy, don't build: codebase-memory-mcp

[codebase-memory-mcp](https://github.com/DeusData/codebase-memory-mcp) (36k+ stars, mature) is
this document's "derived code graph" built to a standard we would never reach ourselves:
tree-sitter across 158 languages plus an embedded LSP-lite type-resolution layer, a
SQLite-backed structural graph (File/Function/Class nodes; CALLS/IMPORTS/DATA_FLOWS edges),
incremental git-watch re-indexing, Cypher-like queries, embedded local embeddings, and a
committable team snapshot — all as an MCP server any client can use.

By its own positioning it stores **"only code structure, not design rationale"** — it is the
substrate half of this document with none of the semantic overlay. Which is exactly the
division we designed: structure derived mechanically, the *why* in memory. So the extractor we
planned to write (old phase 2) is cancelled in favour of adoption. Its team-snapshot feature is
also a neat confirmation of our authored-vs-derived split: derived data is trivially shareable
precisely because it contains no personal knowledge; authored memory is why the manifest/policy
machinery exists.

## Phasing (revised)

1. **Anchors + drift flag** (unchanged) — anchor properties written by distill when a memory is
   about code; recall appends `(code changed since)` when the anchor is stale. Git-only, cheap.
2. **Coexistence join (zero code)** — run codebase-memory-mcp alongside memory-graph as sibling
   MCP servers. The model bridges in-context: their tools answer *who calls `save()`*, ours
   answer *what gotchas apply to it* — the join happens in the model's head, guided by matching
   anchor paths/symbols. Evaluate in real use before building anything.
3. **Mechanical join (only if 2 proves insufficient)** — resolve our anchors against their
   graph (symbol existence/validation), or mirror relevant slices into an RDF named graph so
   the query planner can compose cross-graph queries natively.
