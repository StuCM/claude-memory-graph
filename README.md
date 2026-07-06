# claude-memory-graph

An [Arches](https://www.archesproject.org/)-inspired RDF knowledge-graph MCP server giving Claude Code persistent, structured long-term memory. Facts are stored as typed resources (Person, Project, Decision, Pattern, …) in per-instance named graphs, connected by cross-links and shared concept nodes, so recall can traverse multi-hop chains ("what decisions affect the projects Stuart works on?") instead of grepping flat notes.

- **Storage:** in-memory [pyoxigraph](https://pypi.org/project/pyoxigraph/) triple store, persisted as NQuads after every mutation (atomic write). Default location `~/.claude/memory-graph/store/graph.nq` — human-readable, greppable, diffable.
- **Self-extending ontology:** the LLM must reuse the built-in relations; if none fits it can add a new one (with a description and provenance timestamp) that persists in the schema graph.
- **Token-lean:** tool outputs are terse text designed for LLM consumption — no IRIs, no timestamps, no pretty-printed JSON.

## Install (Claude Code plugin — recommended)

The repo is its own plugin marketplace. One plugin sets up everything: the MCP server (run via `uvx` from the bundled source — requires [uv](https://docs.astral.sh/uv/)), the conversation context-file protocol (injected each session, dirs auto-created), the `/memory-graph:distill` and `/memory-graph:ingest` skills, and [hook-kit](hook-kit/) — a standalone hook-extension framework (own plugin, also usable without memory-graph) whose installable extensions add session-start memory auto-priming (`memory-recall`) and mechanical context-log nudges (`context-counter`): enable them with `/hook-kit:install` or `claude-hooks enable <name>`.

```sh
claude plugin marketplace add <git-url-or-local-path>
claude plugin install memory-graph@claude-memory-graph --scope user
```

Optional: set `MEMORY_GRAPH_PATH` to change the data directory (defaults to `~/.claude/memory-graph/store`).

### Manual install (server only)

```sh
uv tool install git+<repo-url>   # or from a checkout: uv tool install .
claude mcp add --scope user memory-graph -- claude-memory-graph
```

This registers just the MCP server — no context protocol or distill skill.

## The workflow

1. **During every session**, Claude keeps a running context file in `~/.claude/context/` (decisions, problems solved, preferences — a handoff log any LLM can pick up).
2. **`/memory-graph:distill`** batch-extracts the durable knowledge from those files into the graph — with hindsight, deduped, favouring the final understanding over mid-session churn — then archives them to `~/.claude/context/archive/` (never deleted).
3. **Recall** happens naturally: Claude calls `memory_recall`/`memory_query` when past context is relevant, traversing links between projects, decisions, gotchas, and people.

## MCP tools

| Tool | Purpose |
|------|---------|
| `memory_store_resource` | Create/update a typed resource (Person, Project, Company, Task, Technology, Decision, Pattern). Upserts by model+name; any camelCase properties accepted. |
| `memory_store_concept` | Create a shared concept node (Skill, Concept, Constraint, Preference). |
| `memory_link` / `memory_unlink` | Cross-graph relationships. Unknown relations error with the valid list; pass `new_relation_description` to extend the ontology when nothing fits. |
| `memory_recall` | A resource, its properties, and linked resources — depth 1 or 2 (multi-hop via shared nodes). |
| `memory_forget` | Soft-delete (invalidated, kept for provenance, hidden from retrieval). |
| `memory_query` | Raw SPARQL (prefixes `rdf`, `rdfs`, `xsd`, `mem` pre-loaded). |
| `memory_reflect` | Graph overview: counts, available relations, recent additions. |

## Terminal use (read-only)

```sh
claude-memory-graph recall Person Stuart --depth 2
claude-memory-graph reflect
claude-memory-graph query 'SELECT ?name WHERE { GRAPH ?g { ?n rdf:type mem:Project ; mem:name ?name } }'
```

Writes are deliberately MCP-only: a running server holds the graph in memory and saves after each mutation, so terminal writes would be overwritten by the next in-session save.

## Design notes

Each resource instance lives in its own named graph (`…/graph/resource/<uuid>`); cross-links live in a dedicated links graph; shared concepts in a concepts graph; the ontology (including LLM-added relations) in a schema graph. See `claude_memory_graph/base.ttl` for the base ontology.

Multiple Claude Code sessions each spawn their own server process over the same NQuads file — last writer wins per mutation. This is fine for a personal memory store; if it ever outgrows that, the upgrade path is pyoxigraph's RocksDB-backed store behind a single shared daemon.
