# Capture refinement — what gets written, in what shape

Status: **partially implemented; superseded as the entry point.** Creation has since been split
into two independent subsystems with opposite objectives — completeness vs. quality:
[CONTEXT-CREATION.md](CONTEXT-CREATION.md) (the session write-ahead log) and
[DISTILL-CREATION.md](DISTILL-CREATION.md) (the consolidated write-for-retrieval ruleset,
including the retrieval-serving enrichment rules — aliases, concept hubs, verb forms). Start
there; this document remains for the original analysis and the enforcement-layer detail.

## Current state, and what's undefined

Capture today has a *pipeline* but not a *policy*. The pipeline: context files during the session
([hooks/context-protocol.md](../hooks/context-protocol.md)), batch extraction with hindsight via
[/memory-graph:distill](../skills/distill/SKILL.md), direct writes for zero-churn facts. What it
lacks:

- **A rubric** for what deserves a node ("significant" and "quality over quantity" are vibes,
  not tests).
- **Naming discipline.** Upsert-by-model+name is the only dedup mechanism, so names *are* the
  identity scheme — yet nothing defines what a good name is. `Decision "use pyoxigraph"` and
  `Decision "pyoxigraph choice"` silently become two nodes and split all future links between
  them.
- **Property shape per model.** "Decisions: add rationale, outcome, date" lives as a hint in one
  skill file; nothing else enforces or even suggests consistency, so recall output varies
  node by node.
- **Write-time dedup.** Nothing checks for near-duplicates before creating a node.
- **Provenance.** Nodes don't record which session, context file, or model produced them —
  cheap to capture now, impossible to reconstruct later, and required by the sharing/federation
  tracks (attribution and trust are provenance).
- **A supersession story.** When a decision is reversed, the protocol offers only
  `memory_forget`; the *replacement* relationship is unmodelled.

## The capture rubric — what deserves a node

A candidate memory earns a node only if **all three** hold:

1. **Durable** — still true and useful after this session ends. (Mid-task state belongs in the
   context file, which already exists for exactly that.)
2. **Not derivable** — can't be cheaply recovered from code, git history, or docs. The *why*
   of a decision qualifies; the *what* usually doesn't (it's in the diff).
3. **Reachable** — you can say who/what it links to. A node nobody links to won't be found by
   traversal; if no link comes to mind, it's trivia, not memory.

And the standing test for the writer: *would a future session, starting cold, act differently for
knowing this?* If not, skip. Under-capture is recoverable (the context file archive is never
deleted); over-capture pollutes every future recall.

## Naming conventions — names are identity

- **Decision**: imperative verb phrase stating the choice — `"Use pyoxigraph over rdflib"`, not
  `"storage decision"`. The name alone should say what was decided.
- **Pattern**: the phenomenon, not the story — `"SPARQL FILTER on VALUES var must be top-level"`.
- **Project / Technology / Person / Company**: canonical short name, matching what the user says
  and (for projects) the repo/directory basename — that's the key session-start recall uses.
- **Concepts**: lowercase singular labels (`"rust"`, `"GDPR"`), since concepts are the shared
  spine that cross-store linking (FEDERATION.md) will hang off.
- Stable over clever: renaming a node orphans every mental reference to it; prefer updating
  properties on an existing name to minting a better-titled duplicate.

These conventions belong where the writer sees them: in the tool description of
`memory_store_resource` and the distill skill — not only in docs.

## Property shape per model

Keep properties free-form (that flexibility is a feature) but publish a **recommended shape** —
surfaced in tool descriptions, checked nowhere:

| Model | Recommended properties |
|---|---|
| Decision | `rationale` (the why — mandatory in spirit), `outcome`, `date`, `status` (active/superseded) |
| Pattern | `description`, `example`, `appliesWhen` |
| Task | `status`, `context` |
| Project | `status`, `description` |
| Technology | `role` (how it's used here) |
| Person / Company | `role`, `relationship` |

One or two sentences per value — recall output is token-priced. Values should be sentences a
stranger (or another model) can act on, not fragments only this session understands.

## Write paths — a decision matrix

| Situation | Path |
|---|---|
| Explicit user correction or stated preference | **Direct write** at the moment it happens (zero churn risk) |
| Decision reached and confirmed in-session | Context file; **distill** promotes it with hindsight |
| Insight still evolving mid-session | Context file only — distill sees the final form |
| Routine action, derivable fact, one-off trivia | **Neither** — fails the rubric |

Distill stays the default promotion path deliberately: hindsight is the cheapest quality gate we
have. The end-of-session view knows which mid-session "decisions" survived; a write-as-you-go
graph would capture the churn.

## Ingesting existing documents — capture beyond sessions

Sessions are not the only source of durable knowledge: issue-report repos, ADRs, postmortems,
and notes hold exactly the decisions/gotchas/constraints the graph exists for. The extraction
discipline is source-agnostic — the rubric, naming conventions, and property shapes above apply
unchanged — but documents differ from context files in two ways that change the mechanics
(implemented as [/memory-graph:ingest](../skills/ingest/SKILL.md)):

- **We don't own their lifecycle.** Context files get frontmatter flipped and are archived;
  foreign documents must never be modified. Ingestion state therefore lives in the graph: every
  ingested node carries `sourceDocument` (repo + relative path), which doubles as the re-ingest
  ledger — "has this file been processed?" is a SPARQL query, not a sidecar file.
- **They overlap with session capture.** An issue report often describes a gotcha a past session
  already stored, so document ingestion leans harder on pre-write dedup: check the graph first,
  update the existing node (appending the new `sourceDocument`) rather than minting a twin. A
  node accumulating several sources is corroboration — exactly the trust signal federation wants.

Document-type mapping for the common case (an issues repo): recurring problem + root cause →
Pattern; unresolved issue future work must respect → Task; ADR-shaped reasoning → Decision;
hard limits → Constraint concepts. A fixed typo is not a memory; quality over quantity holds
even more for bulk sources, since one over-eager ingest of a large repo can pollute every future
recall.

## Write-time dedup

`memory_store_resource` should check for near-matches before creating (not upserting) a node:
same model, similar name — via the `memory_search` primitive (RETRIEVAL.md). On a near-hit,
return the candidates instead of creating:

> Similar existing node: Decision 'Use pyoxigraph over rdflib'. Update it (same name), or pass
> `force: true` to create a distinct node.

One round-trip of friction, applied exactly where duplicates are born. The reflect skill remains
the retroactive cleanup for what slips through.

## Provenance — cheap now, required later

Stamp on every node at write time (server-side, not model-supplied):

- `capturedAt` (exists as `createdAt`), `capturedBy` (model/client id),
  `sourceContext` (context filename, when the write comes from distill).

This is the attribution data SHARING.md bundles and FEDERATION.md trust signals are built on,
and it makes reflect-time staleness review ("which model wrote this, from what session?")
possible at all.

## Supersession — memories that replace memories

When a decision is reversed: write the new Decision, link
`new supersedes old` (new base relation), set `status: superseded` on the old node, and only
`memory_forget` the old one if it's actively misleading rather than historically true. Recall
then shows the chain — *what we decided, and what we used to think* — which is often the most
valuable memory of all. Distill and reflect both need to know this flow: distill when a context
file records a reversal, reflect when it finds contradictory decisions on the same subject.

## Enforcement layers

The rules above split into two layers with different guarantees:

- **Soft (LLM-followed):** the rubric, "would future-you act differently", property shapes,
  write-path choices — these live in the context protocol, the distill/ingest skills, and tool
  descriptions. They make capture *good* but decay with context and vary by client.
- **Hard (server-enforced, in [capture_rules.py](../claude_memory_graph/capture_rules.py)):**
  the checkable subset the write path refuses to violate, regardless of who is writing —
  required properties per model (Decision→`rationale`, Pattern→`description`, creation-only so
  legacy nodes still accept updates), name lint (normalization, length cap, placeholder-name
  rejection), the near-duplicate guard on create (similar names error with candidates unless
  `force`), case/whitespace-insensitive concept identity, and `capturedBy` provenance stamped
  server-side from the MCP client identity.

## Phasing

1. **Phase 1 — implemented:** hard rules above enforced in the write path; naming conventions +
   recommended shapes in tool descriptions and the distill skill; `sourceContext` provenance
   passed by distill; `supersedes` relation (already in base.ttl).
2. **Phase 2:** the duplicate guard's matcher unifies with `memory_search` (RETRIEVAL.md);
   distill becomes two-pass (extract candidates → search graph for near-matches → write/update).
3. **Ongoing:** reflect skill audits against the rubric (orphans, fragment-valued properties,
   contradictory decisions) — the retroactive half of capture quality.
