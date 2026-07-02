# Sharing memories with a team — design exploration

Status: **exploration, not yet implemented.** See [FEDERATION.md](FEDERATION.md) for the larger
vision this feeds into: hosted per-person DBs connected into a live, policy-gated memory network.

The problem: knowledge linked to a project — decisions, gotchas, patterns — is useful to other
people on that project, but each person's memory graph is *theirs*. It also contains things they
would never share: preferences, notes about people, half-formed judgements, other clients' work.
So the design constraints are:

1. **A person's store stays contained.** Nothing leaves it without an explicit act.
2. **Private by default, opt-in per node.** Sharing a project must not mean sharing everything
   linked to it — links are exactly how private context attaches to shared work.
3. **Consumers see provenance.** Recall should say *whose* memory a fact came from, and shared
   knowledge must never silently merge into (or overwrite) the reader's own nodes.
4. **No mandatory infrastructure.** The current model — a per-session stdio process over a local
   file — should keep working. Anything requiring an always-on daemon is a later phase, not the
   entry point.

## What the current architecture already gives us

The Arches-style partitioning turns out to be most of the battle:

- **Per-resource named graphs** (`…/graph/resource/<uuid>`) are a natural *unit of sharing*: a
  resource's graph is self-contained (type, properties, timestamps), so "share this Decision"
  is literally "copy this named graph".
- **Reified cross-links** live in one links graph and name both endpoints, so an exporter can
  filter links by whether *both* ends are in the shared set — the mechanism that stops private
  context leaking through edges.
- **NQuads/Turtle persistence** means a share bundle is a human-readable, diffable, git-friendly
  text file. That makes review-before-publish (the real privacy control) nearly free.
- **Soft delete** (`mem:invalidated`) travels with the data: if a shared decision is later
  invalidated and re-exported, every consumer's existing filters hide it automatically.

Two things the current model does **not** give us:

- **Identity.** IRIs are UUIDs under a single namespace; nothing says who authored a node.
  Sharing needs an author identity (git `user.email` or a `MEMORY_GRAPH_AUTHOR` env var) stamped
  on export.
- **Merge safety.** `memory_store_resource` upserts by model + name. If Alice's
  `Decision "use pyoxigraph"` were imported *into* Bob's graphs, it would collide with — or be
  clobbered by — Bob's own node of the same name. Imported knowledge must therefore live in its
  own read-only graphs, never merged.

## The sharing boundary problem

This is the core of the user need: *"memories linked to a project… but may not want to share
everything that is linked."* Whatever the transport, every option below needs the same boundary
computation:

1. Start from an **explicit share set** — a list of (model, name) pairs the owner has approved.
   Never a graph traversal on its own: "everything within 2 hops of Project X" is precisely the
   leak we're trying to prevent.
2. Include the **resource graph** of each node in the set, minus any per-property redactions
   (e.g. share a Decision's `rationale` but not its `context`).
3. Include a **cross-link only if both endpoints are in the share set** (or the endpoint is an
   included concept). Links to unshared nodes are dropped by default; an opt-in "stub" mode could
   emit just `model + name` of the far end so consumers know *something* exists without its content.
4. Include **concept nodes** (Skill/Constraint/…) referenced by included links. Concepts are
   labels more than content, so they're usually safe — but they stay excludable.
5. Tooling can *propose* an expansion ("Decision X links to Pattern Y and Constraint Z — include
   them?"), but a human approves the final set. The manifest, not the graph, is the authority.

A **share manifest** (a checked-in list of shared model+name pairs, plus property excludes) beats
tagging nodes with a `visibility` property as the primary mechanism: it's one auditable place that
answers "what am I currently sharing?", it doesn't pollute node data, and removing a line is
revocation. A `visibility: project` property set at capture time can still exist — as a *hint* the
share tool surfaces when proposing additions to the manifest.

## Options

### Option A — Git-versioned share bundles (export / import)

Each person exports an approved subset as a Turtle/NQuads bundle into the project repo, e.g.
`.claude/memory-shared/<author>.ttl`. Teammates' servers load any bundles they find (or are
pointed at) into **read-only per-author named graphs** — `…/graph/shared/<author>/resource/<uuid>`
plus a per-author links graph — at startup.

- **Publish** = `memory_share` computes the boundary from the manifest, writes the bundle,
  stamps `mem:sharedBy` / `mem:sharedAt`. The bundle lands in a normal git commit/PR, so a human
  (or a review skill) eyeballs exactly what leaves the private store. Review-before-publish is
  the strongest leak control any of these designs can offer, and here it's free.
- **Consume** = recall's `_neighbours` query already spans graphs generically; extending its
  graph filter to include shared graphs, plus an attribution suffix in output
  (`- decidedFor → Decision 'use pyoxigraph' (shared by alice)`), covers reading. Imported graphs
  are never written to; the reader's own node with the same name coexists, disambiguated by
  attribution.
- **Revoke / update** = re-export replaces the file; deleting a manifest line and re-exporting
  removes the knowledge for everyone at their next load. Invalidations propagate as soft deletes.
- **Conflicts** = none, by construction: no merging. Two people sharing a Decision with the same
  name yields two attributed nodes — which is honest, since they may genuinely disagree.

*Pros:* zero infrastructure; private by default; versioned history of what was shared and when;
works offline; per-project scoping falls out of "the bundle lives in the project repo".
*Cons:* pull-based, so staleness between publishes; publishing is a deliberate step (mitigable by
having `/memory-graph:distill` end with "these new nodes touch Project X, which has a share
manifest — add any?").

### Option B — Project-scoped shared store with write-time audience

A second `graph.nq` per project (in the repo or a synced directory). `memory_store_resource` /
`memory_link` take an `audience: private | project` argument; project-audience writes go to the
shared store; recall federates over both.

*Pros:* sharing happens at capture time, no separate publish step; always current.
*Cons:* pushes a privacy decision onto every write (LLM-mediated, so misclassification leaks —
and there's no review step before the data is visible to others); retroactive sharing still needs
an export path, so Option A's machinery is required anyway; the current last-writer-wins
persistence becomes last-writer-wins *across people*, which is much less acceptable than within
one person's sessions.

### Option C — Per-person read endpoint, federated recall

Each person runs a small daemon exposing a **read-only** SPARQL endpoint restricted to graphs
listed in their manifest. Teammates' recall issues SPARQL `SERVICE` federation calls to peers.

*Pros:* always live; nothing is copied, so revocation is instantaneous; the personal store is
maximally contained (data never leaves except per-query).
*Cons:* always-on process per person, discovery, network, authentication — a different product
shape from "a file next to your dotfiles". Recall latency becomes network-bound. Sensible only if
staleness in Option A proves painful.

### Option D — Central team store

One shared daemon (pyoxigraph's RocksDB store, or any SPARQL server) holding a team graph with
per-author named graphs; people push approved bundles to it instead of into a repo. This is
Option A with a server as the transport instead of git — the boundary/manifest machinery is
identical. Worth considering when a team outgrows "the shared knowledge lives in one repo"
(cross-project sharing, non-git consumers), not before.

## Cross-cutting decisions (apply to every option)

- **Identity:** stamp `mem:sharedBy <author>` and `mem:sharedAt` on every exported quad's
  resource, with author derived from git config or `MEMORY_GRAPH_AUTHOR`. Keep original UUIDs —
  they're already globally unique — and carry authorship in the graph IRI
  (`…/graph/shared/<author>/…`) so provenance survives even quad-level manipulation.
- **Read-only imports:** shared graphs are excluded from every mutation path (store, link,
  forget). Correcting someone else's shared fact = writing your own node and, if worth it,
  telling them.
- **Schema:** LLM-added relations referenced by a bundle ride along in the bundle (with their
  `rdfs:comment`/`definedAt`), but land in a per-author schema overlay used only for *display* of
  shared data — they don't become valid relation names for the reader's own writes unless the
  reader adopts them explicitly. Keeps one person's ontology drift from silently becoming
  everyone's.
- **Redaction:** manifest supports property-level excludes per node. Because bundles are Turtle,
  the final check is always a human reading a diff.
- **Trust:** imported bundles are data from a teammate, not instructions — recall output should
  render shared property values the same way as local ones (terse, attributed), and nothing in a
  bundle can trigger writes.

## Recommendation

**Phase 1 — Option A**, because it adds sharing without changing the trust or infrastructure
model: manifest + boundary export (`memory_share` tool and/or a `/memory-graph:share` skill that
proposes the share set for a project), bundles in the project repo, read-only per-author shared
graphs loaded via a `MEMORY_GRAPH_SHARED_PATHS` setting, attribution in recall output.

**Phase 2 —** reduce publish friction: `visibility` hints at capture time that distill/share
surface as manifest suggestions; a diff-style preview in the share tool ("since your last export:
2 new decisions touch this project").

**Phase 3 (only if needed) —** a live transport (Option D, then C) once bundle staleness or
repo-scoping actually hurts. The manifest and boundary logic carry over unchanged, which is the
main reason to build them first.
