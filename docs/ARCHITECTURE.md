# Architecture

claude-memory-graph is an MCP server giving Claude Code persistent, structured long-term memory backed by an RDF quad store. This document explains how it's put together and why.

```
Claude Code session
   │  (stdio JSON-RPC, spawned per session)
   ▼
MCP server            claude_memory_graph/__main__.py
   │  tool dispatch   claude_memory_graph/tools/
   ▼
MemoryStore           claude_memory_graph/store.py
   │  in-memory pyoxigraph quad store
   ▼
graph.nq              ~/.claude/memory-graph/store/ (NQuads, saved after every mutation)
```

## Data model: Arches-inspired hybrid graph

The design borrows from the [Arches](https://www.archesproject.org/) heritage platform: instead of one flat pile of triples, each *resource instance* gets its own named graph, and shared *concept nodes* act as traversal bridges between them.

Four kinds of named graph partition the store:

| Graph IRI | Contents |
|---|---|
| `…/graph/resource/<uuid>` | One per resource instance: its `rdf:type`, scalar properties, timestamps |
| `…/graph/concepts` | All shared concept nodes (Skill, Concept, Constraint, Preference) |
| `…/graph/links` | Cross-graph relationships, reified as CrossLink nodes |
| `…/graph/schema` | The ontology — base classes/relations plus any LLM-added relations |

Namespace: `mem:` = `https://memory.claude.local/ontology#`. All IRI construction lives in [namespaces.py](../claude_memory_graph/namespaces.py).

### Resources

Typed entities: Person, Project, Company, Task, Technology, Decision, Pattern (the list lives in [ontology.py](../claude_memory_graph/ontology.py)). A resource is identified by **model + name** at the API level — tools never expose IRIs. Properties are free-form: any camelCase key is accepted and stored as a `mem:<key>` literal (keys are validated against `^[A-Za-z][A-Za-z0-9_]*$` because they become IRI local names; invalid keys error rather than being silently dropped). `memory_store_resource` upserts: if a resource with the same model+name exists, its properties are updated in place.

### Concepts

Lightweight shared nodes (Skill, Concept, Constraint, Preference) identified by `label`. Because many resources can link to the same concept node, they are what makes multi-hop recall useful — "which projects share this constraint?" is a two-hop traversal through one node.

### Cross-links

Relationships are *reified*: each link is a `mem:CrossLink` node in the links graph carrying `linkSource`, `linkTarget`, `linkRelation`, `linkCreatedAt`, plus any free-form metadata. Reification costs a node per edge but lets links carry provenance and metadata, and keeps resource graphs self-contained.

### Soft delete

`memory_forget` marks a resource `mem:invalidated true` with a timestamp and reason. Nothing is removed — but `find_resource`, `recall`, and `reflect` all filter invalidated resources out, so forgotten knowledge is invisible while remaining auditable.

## Module map

| File | Responsibility |
|---|---|
| [`__main__.py`](../claude_memory_graph/__main__.py) | Entry point. No args → MCP server over stdio; `recall`/`reflect`/`query` subcommands → read-only CLI |
| [`store.py`](../claude_memory_graph/store.py) | `MemoryStore`: persistence, CRUD, ontology extension, recall traversal |
| [`ontology.py`](../claude_memory_graph/ontology.py) | The fixed model/concept type lists and the name-property rule |
| [`namespaces.py`](../claude_memory_graph/namespaces.py) | IRI constants, SPARQL prefixes, node constructors |
| [`base.ttl`](../claude_memory_graph/base.ttl) | Base ontology (classes, properties, 16 core relations). Inside the package so wheels ship it |
| [`tools/__init__.py`](../claude_memory_graph/tools/__init__.py) | MCP tool schemas, dispatcher, save-after-mutation hook |
| [`tools/*.py`](../claude_memory_graph/tools/) | One handler module per tool concern (store, link, recall, forget, query, reflect) |

## Persistence: save on every mutation

**The constraint that shapes everything:** MCP stdio servers never shut down gracefully. Clients kill the process or close the pipe; code after `server.run()` never executes. Save-on-exit therefore loses everything (this was a real bug — the store reset every session).

So the dispatcher in [tools/__init__.py](../claude_memory_graph/tools/__init__.py) saves after every successful mutating tool call (`_MUTATING` set). `MemoryStore.save()` dumps the entire store as NQuads to a temp file and atomically renames it over `graph.nq` — a kill mid-write can't corrupt the file.

**Why not pyoxigraph's built-in RocksDB persistence?** RocksDB takes an exclusive per-process lock, and each Claude Code session spawns its own server process over the same data — a second session's server would fail to start. The whole-file NQuads dump makes concurrent sessions *workable* instead: each server holds its own in-memory copy and the last writer wins per mutation. That's the accepted ceiling for a personal memory store; the upgrade path (if the graph outgrows a few MB or lost updates start to matter) is the RocksDB store behind a single shared daemon.

This is also why the CLI subcommands are **read-only**: a terminal write would be overwritten by the next save from any live session's in-memory copy.

## Recall: breadth-first, one query per hop

`MemoryStore.recall()` walks the graph breadth-first. Each hop is **one SPARQL query** (`_neighbours()`), regardless of how many nodes are on the frontier: a `VALUES` clause carries the frontier IRIs, the links graph provides edges in both directions, and the same query joins each neighbour's full property set — covering resource graphs *and* the concepts graph, so concept-mediated hops work. Results are deduped across hops (a node reachable by two paths appears once), invalidated resources are filtered, and second-hop entries are labelled `via <name>`.

A SPARQL subtlety in `_neighbours` worth knowing: a `FILTER` referencing an outer `VALUES` variable must sit at the **top level** of the WHERE clause, not inside the `GRAPH` group. SPARQL evaluates groups bottom-up, so inside the group the variable is unbound and the filter silently drops every row.

## Ontology: fixed core, LLM-extendable relations

The schema graph is the single source of truth for relations. Relations are marked `a rdf:Property, mem:RelationType` in [base.ttl](../claude_memory_graph/base.ttl); `valid_relations()` queries the marker.

The extension flow is deliberately high-friction so the LLM reuses before inventing:

1. `memory_link` with an unknown relation **errors**, listing every current relation with its description and instructing the model to prefer an existing one.
2. Only if nothing genuinely fits, the model retries with `new_relation_description`, and `add_relation()` writes the new relation into the schema graph — with an `rdfs:comment` and a `mem:definedAt` timestamp, so LLM additions are auditable (base relations have no `definedAt`).

Because LLM-added relations live in the schema graph, they persist like everything else and are immediately valid in future sessions. `_ensure_base_ontology()` keys on the `RelationType` marker rather than "schema graph non-empty", so stores created before an ontology change get the updated base.ttl re-loaded (RDF loading is set-semantics — re-loading is safe), without touching LLM additions.

Resource models are intentionally *not* extendable — the fixed list in ontology.py keeps recall lookups (model + name) unambiguous.

## Token-lean outputs

Every tool output is consumed by an LLM, so tokens are the real cost. The rules:

- No IRIs in outputs — everything is addressed by model + name.
- No `createdAt`/`updatedAt` noise in recall.
- Terse text, not pretty-printed JSON: `- worksOn → Project 'quartz' — status: active`.
- SPARQL results shorten IRIs to prefixed names (`mem:Person`) and emit raw literal values, compact JSON.
- Mutation confirmations are one line.

## Interfaces

**MCP tools** (definitions in [tools/__init__.py](../claude_memory_graph/tools/__init__.py)): `memory_store_resource`, `memory_store_concept`, `memory_link`, `memory_unlink`, `memory_recall`, `memory_forget`, `memory_query`, `memory_reflect`. The server `instructions` tell the model to recall before re-deriving knowledge.

**CLI** (read-only): `claude-memory-graph recall Person Stuart --depth 2`, `reflect`, `query '<sparql>'`.

**Claude Code plugin**: the repo is its own marketplace ([.claude-plugin/](../.claude-plugin/)). The plugin bundles:
- the MCP server, launched as `uvx --from ${CLAUDE_PLUGIN_ROOT} claude-memory-graph` — the plugin's bundled source is the package, so users need only `uv`;
- a SessionStart hook ([hooks/](../hooks/)) that creates `~/.claude/context/` dirs and injects the recall-first + context-writing protocol into every session;
- skills [`/memory-graph:distill`](../skills/distill/SKILL.md) (context files → graph nodes), [`/memory-graph:ingest`](../skills/ingest/SKILL.md) (arbitrary markdown documents — issue reports, ADRs, notes — → graph nodes, source files never modified), and [`/memory-graph:reflect`](../skills/reflect/SKILL.md) (find missing links, orphans, stale nodes).

Note the plugin's MCP config is `mcp-servers.json`, *not* `.mcp.json` — the latter at a repo root is also read as project-scope MCP config, which would double-register the server for anyone working in this repo.

## The memory workflow

1. **Capture** — during every session, Claude appends decisions/problems/preferences to a context file in `~/.claude/context/` (cheap write-ahead log, narrative handoff state).
2. **Distill** — `/memory-graph:distill` batch-extracts durable knowledge into the graph with hindsight (deduped, final understanding rather than mid-session churn), then archives the context files. Zero-churn facts (explicit user corrections/preferences) may be written straight to the graph.
3. **Recall** — future sessions query the graph before re-deriving: `memory_recall` on the current project or person surfaces decisions, gotchas, constraints, and preferences in one call.
