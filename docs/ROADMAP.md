# Roadmap — three workstreams

The project is one loop — **capture → store → retrieve** — that we eventually want to run across
a network of stores. That breaks into three workstreams, each with its own design doc:

| Track | Question | Doc |
|---|---|---|
| **A. The bigger vision** | Where do memories live and who can traverse them? | [SHARING.md](SHARING.md) → [FEDERATION.md](FEDERATION.md) |
| **B. Retrieval instigation** | *When and how* does recall actually happen? | [RETRIEVAL.md](RETRIEVAL.md), [QUERY-PLANNING.md](QUERY-PLANNING.md) |
| **C. Capture refinement** | What gets written, in what shape, with what quality gates? | [CAPTURE.md](CAPTURE.md) |

## How the tracks interlock

- **C gates B.** Retrieval is only as good as what's in the graph: sloppy names defeat lookup,
  near-duplicate nodes split the signal, unlinked nodes are unreachable by traversal. Capture
  discipline is a retrieval feature.
- **B and C share a primitive.** The fuzzy entry-point finder (`memory_search`, proposed in
  RETRIEVAL.md) is the same machinery capture needs for write-time dedup ("a similar Decision
  already exists — update it instead?"). Build it once, use it on both sides of the loop.
- **C feeds A.** Provenance captured at write time (source session, capturing model, timestamps)
  is exactly the attribution/trust data the federated network needs. Cheap to record now,
  impossible to reconstruct later.
- **B constrains A's shape.** Whatever triggers retrieval must survive the move to hosted,
  multi-model stores — so triggering logic belongs in server instructions and tool descriptions
  (which travel with MCP to any client), with Claude Code hooks as one adapter, not the mechanism.

## Sequencing

Validate the loop on one person's store before scaling it to a network — a federation of
low-quality, rarely-recalled memories is just distributed noise.

1. **Now:** B phase 1 + C phase 1 (small, immediately felt): session-start auto-priming,
   `memory_search`, capture rubric + naming conventions + provenance properties.
2. **Next:** A phase 1 (share bundles) — first contact with the boundary/manifest model, using
   the provenance C added.
3. **Then:** B phase 2 (prompt-time retrieval hints), C phase 2 (write-time dedup, supersedes
   flow), A phase 2 (hosted store, cross-model persistence).
4. **Later:** semantic retrieval (embeddings), federation gatekeeper — each justified by observed
   pain, not speculation.
