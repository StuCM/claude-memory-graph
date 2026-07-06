# Glossary

Every term of art in this project, one or two sentences each, grouped by subsystem.
Start here; [SYSTEM.md](SYSTEM.md) shows how the pieces connect.

## The store (implemented)

- **Resource** — a typed entity (Person, Project, Company, Task, Technology, Decision,
  Pattern). Identified by **model + name**; lives in its own named graph.
- **Model** — a resource's type. The list is fixed so lookups stay unambiguous.
- **Concept** — a lightweight shared node (Skill, Concept, Constraint, Preference) identified
  by `label`. Many resources link to one concept, making it a traversal bridge.
- **Concept hub** — a concept in its role as associative index: any entry point reaching
  `Concept "coffee"` fans out to every memory linked to it, even ones sharing no words.
- **CrossLink** — a relationship, *reified*: each link is its own node carrying source, target,
  relation, timestamps, and free metadata. Costs a node per edge; buys provenance, link-level
  policy, and (later) temporal validity for free.
- **Named graph** — RDF's partitioning unit. One per resource instance, plus dedicated graphs
  for concepts, links, and the schema. The containment mechanism everything else builds on.
- **Schema graph / ontology** — the machine-readable definition of models and relations,
  including LLM-added relations. Self-describing: doubles as the retrieval lexicon.
- **Soft delete / invalidated** — `memory_forget` marks a resource invalidated (hidden from
  retrieval, kept for audit). Being refined into the two-clock model below.
- **Upsert** — `memory_store_resource` updates an existing model+name match instead of
  creating. Makes the **name the node's identity**.

## Creation (2a: context, 2b: distill)

- **Context file** — the per-session markdown **write-ahead log** in `~/.claude/context/`:
  timestamped notes of decisions, problems, preferences. Optimises for *completeness* (losing
  a fact is the failure); churn and wrongness are fine.
- **Distill** — the promotion step (`/memory-graph:distill`): reads context files *with
  hindsight*, extracts what survived, writes graph nodes, archives the files. Optimises for
  *quality* (a junk node is the failure).
- **Ingest** — distillation for documents we don't own (issue repos, ADRs): same rules, but
  sources are never modified; ingestion state lives in the graph via `sourceDocument`.
- **The rubric** — the three-part test a fact must pass to earn a node: **durable** (useful
  beyond this session), **not derivable** (from code/git/docs), **reachable** (you can say what
  it links to).
- **Hard rules** — the checkable subset of capture policy the server enforces in code
  (`capture_rules.py`): required properties, name lint, duplicate guard, provenance stamping.
- **Soft rules** — capture judgement the LLM follows from protocols and tool descriptions
  (the rubric, naming conventions, enrichment).
- **Duplicate guard** — creating a node whose name is *similar* to an existing one errors with
  the candidates; `force: true` overrides after review.
- **Aliases** — an `aliases` property listing the phrasings a future prompt would plausibly
  use. Content, not index: it adds vocabulary the data lacks, closing the paraphrase gap so
  read-time matching can stay lexical.
- **Provenance** — who/where a memory came from: `capturedBy` (writing client, stamped
  server-side), `sourceContext` (context file), `sourceDocument`/`sourceKind` (ingested doc),
  code anchors (below).
- **Supersedes** — the relation linking a new Decision to the one it replaces, preserving the
  chain of what we decided and used to think.
- **Two-clock (bi-temporal) model** — every link carries **valid time** (when the fact was true
  in the world: `linkValidFrom`/`linkValidUntil`) and **belief time** (when we recorded/revised
  it: `linkCreatedAt`/`linkInvalidatedAt`).
- **worldChange vs correction** — the two kinds of invalidation: a fact that *stopped being
  true* (job change) vs one that *never was* (mis-captured). They answer historical queries
  differently.
- **Contradiction closure** — the write rule: a new link contradicting a single-valued relation
  *closes* the old edge (bounds its valid time) instead of deleting or duplicating it.

## Retrieval (1)

- **Ambient retrieval** — the target design: memories arrive in the context window *unasked*;
  the model never has to remember to look.
- **Analyzer** — the deterministic, **no-LLM** process run on every prompt: extract candidate
  terms → match against the graph's vocabulary → score → inject memories or stay silent.
- **Grounding** — mapping a word in the prompt to something the graph knows: an entity name,
  alias, model noun, relation verb-form, or modifier.
- **Lexicon** — the vocabulary grounding matches against. Read from the graph itself (names,
  labels, aliases, verb forms), not shipped with the code.
- **Entry point** — a matched node where retrieval enters the graph; traversal from entry
  points supplies the actual context ("search finds doors, traversal explores rooms").
- **Threshold / fail toward silence** — below a confidence score the analyzer injects
  *nothing*. Misses cost only the status quo; false injections poison trust — so tune for
  precision.
- **Session memo** — per-session record of already-injected nodes, preventing re-injection
  every prompt.
- **Injection log** — the analyzer's decision record (fired/silent, scores, nodes); the tuning
  dataset.
- **Miss detector** — an explicit `memory_recall` right after analyzer silence = a logged false
  negative, for free.
- **Nominate / dispose** — the division of intelligence: the analyzer *nominates* candidate
  memories cheaply; the main model (already reading the injection) *disposes* — makes the final
  relevance judgement. No second LLM is ever added just to decide whether to look.
- **Index (vs content)** — derived, rebuildable matching structures (lexical index, FTS,
  embedding/ANN) built mechanically from whatever text exists, stored *outside* the graph.
  Indexes everything, including aliases; never authored.
- **Query planner** — for question-shaped prompts: ground the words, then *compose* SPARQL from
  building blocks (nouns → type constraints/anchors, verbs → relations, adjectives → filters,
  wh-words → projections, tense → valid-time filters) instead of selecting a canned query.
- **Path template** — what a lexicon entry maps a phrase to: a graph pattern, possibly
  multi-triple (our reified links; CIDOC's event paths), not a single predicate.
- **Grounding coverage** — the fraction of a question's content words that grounded; the
  planner's confidence gate and the metric that decides whether v0's grammar is big enough.

## Orchestration (3)

- **Orchestration** — the reliability layer: hook adapters + session state + prompt counting,
  so both loops fire mechanically instead of depending on model discipline.
- **Instruction decay** — the failure orchestration exists to fix: protocol prose injected at
  session start loses salience as context grows.
- **Session state** — a small per-session JSON file: prompt count, context-log freshness,
  session memo, injection log.
- **Nudge** — a mechanical, present-tense reminder injected when counted activity outruns the
  context log (vs hoping session-start prose is still salient).
- **Flush points** — PreCompact and SessionEnd hooks: last chances to write the context log
  before in-context knowledge is summarised away or lost.
- **Auto-prime** — SessionStart hook recalls the current Project (cwd basename) + Person and
  injects the *results*, so sessions start already primed.

## Sharing & federation (horizon)

- **Share manifest** — the explicit, auditable list of what a person shares (model+name pairs +
  property redactions). The authority — never a graph traversal; **reachability must not imply
  exposure**.
- **Share bundle** — a Turtle/NQuads export of the manifest's closure, git-versioned in the
  project repo; consumed as **read-only per-author named graphs**, never merged.
- **Boundary computation** — what goes in a bundle: selected resource graphs, links only when
  *both* endpoints are shared, referenced concepts.
- **Gatekeeper / `expand`** — the one operation a hosted DB exposes to outsiders (never raw
  SPARQL): given nodes and a principal, return what that principal may see, one hop at a time.
- **Visibility tiers** — `private` (default) → `stub` (model+name only) → `visible`
  (properties minus redactions), granted per principal/group in a policy graph.
- **Concept registry** — the horizon's connective tissue: canonical shared concept IRIs so
  strangers' stores link through common concepts.

## Code knowledge (horizon)

- **Semantic overlay** — the *why* of code (decisions, gotchas, constraints) — belongs in
  memory; small and durable.
- **Derived code graph** — code *structure* (symbols, calls, imports) generated by
  tree-sitter/SCIP into a separate named graph, regenerated per commit, never hand-written.
- **Code anchor** — `anchorPath`/`anchorSymbol`/`anchorCommit` on a memory node about code:
  enables drift flagging ("code changed since") now, cross-graph joins later.

## Recurring principles

- **Spend intelligence at write time** — the LLM already in session enriches once (aliases,
  concept links, verb forms); read time stays deterministic, fast, private.
- **Authored vs derived** — knowledge lives in the graph and travels (aliases, anchors);
  matching structures are derived, disposable, rebuilt (indexes, code graph).
- **Index everything; alias the vocabulary; alias instances only where they're phrases,
  low-volume, and an LLM is present.**
- **Fail toward silence / fail open** — retrieval says nothing rather than something wrong; a
  broken memory layer must never degrade the session.
- **Association is precomputed** — retrieval is only allowed to be dumb because creation wrote
  the associations down.
