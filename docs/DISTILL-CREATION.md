# Distill creation — writing the graph so retrieval can be dumb

Status: **rules consolidated here; hard subset implemented in
[capture_rules.py](../claude_memory_graph/capture_rules.py).** One of the two creation
subsystems — see [CONTEXT-CREATION.md](CONTEXT-CREATION.md) for the split and the other half.

## The principle that makes creation the most important subsystem

Retrieval in this system is deterministic and cheap **because every association it needs was
precomputed at write time**. The analyzer doesn't reason that a brand preference is relevant to
"where can I get some coffee" — it finds the preference because the node that stores it carries
the token "coffee" (name, alias, or property text) or sits one edge from `Concept "coffee"`.
Association *is* the graph. The retrieval function is only allowed to be dumb because
distillation is smart — intelligence is spent once, by the LLM already in session, and persisted.

Every rule below serves that principle. This is the full ruleset, consolidated.

## 1. The rubric — what earns a node (soft)

All three must hold: **durable** (useful beyond this session) · **not derivable** (the why, not
the what — code and git already store the what) · **reachable** (you can say what it links to).
Standing test: *would a future session, starting cold, act differently for knowing this?*
Under-promotion is recoverable (context archives are never deleted); over-promotion pollutes
every future recall.

## 2. Names are identity (soft conventions, hard lint)

Upsert-by-model+name makes the name the node's identity and the analyzer's strongest matching
signal, so it must contain the distinctive tokens:

- **Decision** — imperative phrase stating the choice: `"Use pyoxigraph over rdflib"`
- **Pattern** — the phenomenon: `"SPARQL FILTER on VALUES var must be top-level"`
- **Project/Technology/Person/Company** — canonical short name, matching what the user says
  (projects: the repo/directory basename — the session-start anchor)
- **Concepts** — lowercase singular labels
- Stable over clever: update properties on an existing name rather than minting a better title.

*Hard-enforced:* whitespace normalisation, 120-char cap, placeholder-name rejection
("notes", "misc", …).

## 3. Required shape per model (hard at creation)

Decision → `rationale` · Pattern → `description`. Recommended beyond that: Decision `outcome`,
`date`, `status`; Pattern `example`, `appliesWhen`; Task `status`, `context`. Values are one or
two sentences a stranger could act on — written in the vocabulary future-you would use, not
session-local shorthand (property text is a retrieval matching surface).

## 4. Retrieval-serving enrichment (soft — the rules that make dumb retrieval smart)

- **Aliases** — every node gets an `aliases` property: the two or three phrasings a future
  prompt would plausibly use (`Pattern "RocksDB exclusive lock"` → aliases *"db locking",
  "database lock", "rocksdb lock"*). This closes the paraphrase gap so read-time matching can
  stay lexical. Scope note: per-node aliases are worth it *here* because our instances are
  descriptive phrases (where paraphrase bites), volume is a few nodes per session, and the LLM
  is already present. They are **not** the scale strategy — for bulk ingest or pre-existing
  corpora (CIDOC/Arches), the retrieval index is built mechanically from existing text and
  aliasing shifts to the vocabulary layer, where SKOS `altLabel`s and ontology labels usually
  already exist (see RETRIEVAL.md, "Aliases vs the index"). Aliases live in the graph because
  they are knowledge (shareable, inspectable); indexes are derived and disposable — the index
  indexes the aliases, they never compete.
- **Concept hubs** — link every node to at least one concept. Concepts are the associative
  index: any entry point reaching `Concept "coffee"` fans out to every coffee memory, even ones
  sharing no tokens. A node linked to no concept is invisible to associative recall.
- **Link everything** — minimum one edge (usually to the Project); the rubric's reachability
  test made operational. Typical shape: Person worksOn Project; Project uses Technology;
  Decision affects Project; Pattern appliesTo Project.
- **Verb forms on new relations** — when extending the ontology, supply the natural-language
  verb forms alongside the description (`worksOn` → *"works on", "working on"*), so the query
  planner ([QUERY-PLANNING.md](QUERY-PLANNING.md)) can ground them with zero code changes.
- **Code anchors** — a memory *about code* carries `anchorPath` (repo-relative),
  `anchorSymbol`, and `anchorCommit`, enabling staleness flagging when the code drifts and,
  later, joins to the derived code graph ([CODE-GRAPH.md](CODE-GRAPH.md)). Symbol-level
  structural facts (where X is defined, who calls Y) stay out of the graph — derivable by one
  grep, so they fail the rubric. *Orientation* knowledge — how and where things are stored,
  located, and wired, at convention level — passes it and is stored as Patterns under the
  three-lane rules in [tasks/code-memory-rules](tasks/code-memory-rules.md).

## 5. Dedup (hard guard, soft preference)

*Hard:* creating a node with a name similar to an existing one errors with the candidates;
`force: true` only after reviewing them. Concept identity is case/whitespace-insensitive.
*Soft:* prefer updating the existing node — an issue report describing a gotcha a session
already stored should append to that node (adding its source), not twin it. Multiple sources on
one node = corroboration.

## 6. Provenance (hard, server-side)

`capturedBy` stamped from the MCP client identity; `sourceContext` (context filename) passed by
distill; `sourceDocument`/`sourceKind` passed by ingest — the latter doubling as the re-ingest
ledger. This is also the attribution/trust substrate for sharing and federation.

## 7. Supersession — memories that replace memories

A reversed decision: write the new Decision, link `new supersedes old`, set
`status: superseded` on the old; `memory_forget` only if actively misleading. Recall then shows
the chain — what we decided *and what we used to think*. Applies at distill time (a context file
records a reversal) and at reflect time (contradictory decisions found).

## 8. Temporal validity — facts carry two clocks (adopted from Zep/Graphiti)

Bi-temporal modelling (temporal databases, SQL:2011) separates **valid time** (when a fact was
true in the world) from **transaction time** (when we believed it). Our reified CrossLinks are
already the structure this needs — an edge is a node that can carry properties — so adoption is
four additions per link:

- `linkValidFrom` / `linkValidUntil` — the world clock (`validFrom` defaults to recording time;
  backdate when the source says "since 2019")
- `linkInvalidatedAt` — when belief was revised
- `invalidationKind` — **`worldChange`** (was true, stopped being true: a job change) vs
  **`correction`** (was never true: mis-captured). The distinction our current `invalidated`
  flag conflates — and they answer historical queries differently: a superseded fact *should*
  appear in "what was true last spring?"; a corrected one should not.

**The contradiction-closure rule (write path):** when a new link contradicts an existing one —
same source, same effectively-single-valued relation, different target (`worksAt A` vs
`worksAt B`) — **close the old edge** (`linkValidUntil = now`, `worldChange`) instead of
deleting it or leaving both equally current. Nothing is ever deleted; facts get bounded. This is
the duplicate guard's sibling: the guard stops identity twins, closure stops *temporal* twins.

**Retrieval defaults to "true now":** recall and the ambient injector filter to open edges, so a
stale `worksAt` is never injected as confidently as a live one. Point-in-time questions are the
query planner's job (temporal modifiers, QUERY-PLANNING.md). Bounds travel with share bundles,
so consumers of shared knowledge see whether it is still operative.

**Deliberate limit:** links get the full treatment (relationships are where "no longer true"
happens); scalar properties keep current-value semantics — full bi-temporal property versioning
is compliance-database machinery, not personal memory. Decisions, where history *is* the point,
already have the `supersedes` chain.

## Two promotion paths, one ruleset

- **[/memory-graph:distill](../skills/distill/SKILL.md)** — from session context files, with
  hindsight; archives its sources. Structured context entries arrive pre-shaped (the
  protocol now captures graph shape at write time), so distill *folds and stores* rather
  than re-derives — and the fully mechanical, no-LLM lane is
  [tasks/structured-context-entries](tasks/structured-context-entries.md) phase 2.
- **[/memory-graph:ingest](../skills/ingest/SKILL.md)** — from documents we don't own (issue
  repos, ADRs, postmortems); never modifies its sources, tracks state via `sourceDocument`.

Same rubric, same enrichment rules, same hard enforcement underneath — only the source lifecycle
differs. Direct writes (bypassing both) are reserved for zero-churn facts: explicit user
corrections and stated preferences, at the moment they happen.
