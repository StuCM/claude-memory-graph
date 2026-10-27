# A federated memory network — design exploration

Status: **exploration, not yet implemented.** Companion to [SHARING.md](SHARING.md), which covers
file-based sharing between local stores; this document explores the larger vision that sharing is
a stepping stone toward.

The vision: **host each person's memory DB** so it persists across models and clients, then
**connect the DBs into a network** using the same RDF principles the store is already built on —
a link can point *into* another person's DB, recall can traverse across the boundary, and a
policy layer on each DB controls what is traversable from outside. At scale that yields a network
of learned experience: decisions, gotchas, and patterns accumulated by many people, walkable as
one graph, while every node of the network remains sovereign over its own data.

## Why RDF makes the network cheap at the data layer

This is the part of the vision that costs almost nothing, and it's worth being precise about why:

- **IRIs are already global names.** A cross-link's `linkTarget` is a NamedNode; nothing in the
  data model cares whether that IRI resolves inside my store or yours. A cross-DB edge is just an
  edge whose far end happens to live elsewhere — no new link type, no foreign-key machinery.
- **Named graphs are already the containment unit.** "Your DB" vs "my DB" is the same partition
  discipline the store applies today between resource graphs; federation coarsens it one level.
- **Recall is already hop-structured.** `MemoryStore.recall()` is breadth-first with one query
  per hop over a frontier. In a network, a hop whose frontier node lives in a foreign DB becomes
  a *remote* call answering the same question — "this node's visible properties and visible
  edges" — instead of a local one. The traversal algorithm doesn't change shape; the transport
  under one hop does.

This is essentially the [Solid](https://solidproject.org/) thesis (personal RDF pods,
dereferenceable IRIs, access control at the pod boundary) applied to agent memory, and Solid,
SPARQL 1.1 federation (`SERVICE`), and Linked Data Fragments are the prior art to raid — both for
mechanisms and for the failure modes they hit (see "Hard problems" below).

## Architecture

```
 Claude / other LLM / CLI            Claude / other LLM / CLI
        │  remote MCP (HTTP + auth)         │
        ▼                                   ▼
 ┌──────────────────┐  gatekeeper  ┌──────────────────┐
 │  stuart's DB     │◄────────────►│  alice's DB      │
 │  (hosted store)  │   traversal  │  (hosted store)  │
 │  policy graph ───┼── filters ──►│  policy graph    │
 └──────────────────┘   every hop  └──────────────────┘
          ▲ full access                    ▲ full access
        owner                            owner
```

Four pieces, buildable in order:

### 1. Hosting: the store becomes a service

The MCP server moves from a per-session stdio process over `graph.nq` to a **remote MCP server**
(streamable HTTP + auth) in front of a persistent store. Two things fall out immediately, before
any federation:

- **Across models** — MCP is model-agnostic; any client (Claude, another vendor's agent, the CLI)
  connects to the same memory. "Persistent memory across models" is just remote MCP + auth.
- **The concurrency ceiling lifts** — one resident process per person means pyoxigraph's
  RocksDB store (single exclusive lock) is finally usable, ending last-writer-wins between
  sessions. The NQuads dump demotes to a backup/export format — which SHARING.md bundles
  already need it to be.

Multi-tenancy is per-tenant datasets (or per-tenant graph-IRI prefixes in one store); either way
the owner's own tools see exactly today's four-graph layout.

### 2. Identity: IRIs become addresses on the network

Current IRIs (`https://memory.claude.local/ontology#resource/<uuid>`) are placeholders — nothing
identifies an owner and nothing resolves. For a network, mint owner-scoped, dereferenceable IRIs:

```
https://mem.<host>/<owner>/resource/<uuid>     resource node + its named graph
https://mem.<host>/<owner>/concept/<uuid>
https://mem.<host>/<owner>/links               that owner's links graph
```

The IRI *is* the routing information: given a foreign node IRI, the traversal layer knows which
gatekeeper to ask. Owners are principals (people or agents) with an auth identity; groups
("project quartz team") are how policy avoids per-person ACL sprawl. Existing stores migrate by
rewriting the base prefix — UUIDs stay stable.

### 3. The gatekeeper: what is traversable from outside

The critical design decision: **outsiders never get raw SPARQL.** Arbitrary queries against
someone's memory are an enumeration, inference, and denial-of-service surface (this is where
naive SPARQL federation falls down in practice). Instead each DB exposes one narrow, policy-aware
operation — deliberately the same shape as the existing `_neighbours()` query:

```
expand(nodes: [IRI], principal: P) →
    for each node the principal may see:
        visible properties, visible outbound/incoming edges
        (each edge's far node at least stub-visible to P)
```

One hop per request, filtered at the boundary, priced and rate-limited per principal. Federated
recall is then the local BFS with a mixed frontier: local IRIs go to the local store, foreign
IRIs are batched per home DB and sent to that DB's `expand`. Depth limits already exist in recall;
they become the network's cost ceiling too.

**Policy model** — the SHARING.md manifest generalised into a policy graph (RDF, in its own named
graph, owner-writable only):

- **Visibility tiers per resource:** `private` (default) → `stub` (model + name only — "a
  decision exists here") → `visible` (properties, minus per-property redactions) — granted to
  principals or groups. Policy entries reference nodes by IRI; defaults can be rule-shaped
  ("everything linked to Project X with `visibility: project` hint → visible to group
  quartz-team"), but rules *propose*, the policy graph is the authority — same principle as the
  manifest, for the same reason: reachability must never imply exposure.
- **Edges are bi-gated:** an edge is traversable by P only if the *link itself* is visible to P
  and its far node is at least stub-visible to P. Links are already reified nodes, so link-level
  policy costs nothing new.
- **Evaluated live, every hop.** Unlike exported bundles, revocation is immediate: change the
  policy graph and the next `expand` reflects it. (Caches — see below — need TTLs bounded by how
  stale revocation may be.)

### 4. The connective tissue: shared concepts

Within one store, concept nodes are what make multi-hop recall useful. Across the network they
are what make it a *network*: two strangers' DBs mostly won't link to each other's resources
directly, but both will touch `Skill "rust"`, `Technology "pyoxigraph"`, `Constraint "GDPR"`. If
every DB mints its own private concept IRIs, the graph is connected in name only and cross-DB
traversal finds nothing.

Options, weakest to strongest:

1. **Label matching at query time** — no shared identity; the federated layer treats
   equal (type, label) as the same concept. Cheap, sloppy (synonyms, casing, languages).
2. **`owl:sameAs` links** between concept nodes, added opportunistically. Precise but requires
   curation nobody will do.
3. **A shared concept registry** — a well-known, append-only vocabulary service minting canonical
   concept IRIs (`https://mem.<host>/concepts/technology/pyoxigraph`); personal stores link to
   canonical IRIs directly (new concepts get registered on first use, like relations get added to
   the schema graph today). This mirrors how Arches uses shared thesauri, and it's the option
   that makes "a huge network of learned experience" actually traversable — concept nodes become
   the network's exchanges.

Recommendation: 3 for concepts, with 1 as the fallback when the registry is unreachable. Note the
privacy interaction: *linking* to a public concept is itself information ("stuart has memories
touching X"), so concept-incident edges obey the same edge policy as everything else — the
registry knows what concepts exist, never who links to them.

## Hard problems (the honest list)

- **Prompt injection becomes a network attack.** Remote memories are untrusted text that flows
  into other people's agent contexts. In a big network, someone *will* plant "ignore previous
  instructions"-shaped content in a widely-traversable node. Mitigations: recall output renders
  remote content clearly attributed and data-shaped (the token-lean format helps — no room for
  prose payloads to masquerade as protocol); clients treat shared-memory content as data by
  policy; possibly signed provenance so a poisoned node is traceable. This needs to be a design
  input from day one, not a patch.
- **Inference and enumeration.** Stub visibility leaks metadata; batched `expand` calls let a
  motivated principal map the shape of someone's graph. Rate limits and per-principal audit logs
  on the gatekeeper are table stakes; owners should be able to see who traversed what.
- **Availability vs the bundle model.** Live references mean an offline/slow peer is a missing
  subgraph at recall time. Per-hop caching with TTLs trades revocation latency for resilience.
  The pragmatic stance: bundles (SHARING.md) are the *offline replication* format of the network,
  not a competing design — a DB can serve a cached bundle of a peer's shared subgraph when the
  peer is unreachable, marked stale.
- **Trust in asserted experience.** The network transports *claims*. Attribution (who), recency
  (`updatedAt` already exists), and soft-delete propagation (invalidation is visible at the
  source immediately) are the first-order signals; reputation/endorsement layers are speculative
  and can wait.
- **Ontology drift at network scale.** Per-owner schema graphs with LLM-added relations will
  diverge. Same answer as SHARING.md: foreign relations are display-only overlays; promotion into
  your own ontology is explicit. A network-level relation registry could follow the concept
  registry pattern if drift becomes painful.

## Staging

Each phase is independently useful and none is thrown away:

| Phase | Deliverable | What it proves |
|---|---|---|
| 1 | Share bundles (SHARING.md) | The boundary/manifest model; attribution in recall |
| 2 | Hosted single-tenant store: remote MCP + RocksDB + auth | Cross-model persistence; ends last-writer-wins; NQuads becomes export/backup |
| 3 | Owner-scoped IRIs + policy graph + gatekeeper `expand`; federated recall between two consenting DBs | Live traversal with revocation; the policy model under real use |
| 4 | Concept registry; multi-tenant hosting; caching/stale-bundle fallback | Density — the "huge network" property |

The through-line: the SHARING.md manifest *is* the phase-3 policy graph in embryo, the boundary
computation *is* the gatekeeper filter evaluated at export time instead of query time, and
recall's one-query-per-hop structure *is* the federation protocol. Phase 1 isn't a detour from
the network — it's the same design with git as the transport.
