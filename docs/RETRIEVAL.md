# Retrieval instigation — when and how recall happens

Status: **exploration, not yet implemented.** Track B of [ROADMAP.md](ROADMAP.md).

## Current state, and why it's not enough

Retrieval today is entirely **instructed**: the SessionStart hook injects the "Recall First"
protocol ([hooks/context-protocol.md](../hooks/context-protocol.md)) and the server
`instructions` say to recall before re-deriving. The model then has to (a) remember the
instruction, (b) judge relevance, and (c) guess the **exact model + name** of a node, because
`memory_recall` and `find_resource` are exact-match only.

Observed failure modes of instruction-only retrieval:

- **Mid-session amnesia** — protocol prose injected at session start loses salience as context
  grows; recall happens at the start of a session or not at all.
- **The exact-name cliff** — the model must already know a node is called
  `Decision "use pyoxigraph"` to recall it; if it guesses "pyoxigraph choice", retrieval silently
  fails and the knowledge might as well not exist.
- **No presence signal** — the model has no cheap way to know the graph has *anything* relevant
  to the current topic, so it must choose between speculative recalls (token cost) and skipping
  (rederivation cost) blind.

## The trigger taxonomy — *when*

Moments where retrieval should fire, roughly ordered by how mechanisable they are:

| Trigger | Signal quality | Mechanism |
|---|---|---|
| Session start | High — project + user are known | Hook: run recall automatically, inject *results* |
| User names an entity (project, tech, person) | High — literal string match against node names | Prompt-time hint injection |
| Explicit user cue ("did we…", "last time…", "why did we…") | High | Instruction + tool description |
| Before an architectural decision / investigation | Medium — model judgement | Instruction + tool description |
| Before writing a memory | High — dedup check | Built into the write path (see CAPTURE.md) |
| Topic shift mid-session | Low — hard to detect cheaply | Deferred; falls out of prompt-time hints |

## Mechanisms — *how*, from passive to active

### 1. Auto-prime at session start (inject answers, not instructions)

The SessionStart hook already runs a script; the CLI already supports read-only
`recall`/`reflect`. So the hook can *call* `claude-memory-graph recall Project <cwd-basename>
--depth 2` (plus the user's Person node) and inject the actual results into session context —
the session starts already knowing past decisions and gotchas, no model discipline required.

- Deterministic, zero new infrastructure, and the token-lean output format keeps the cost to a
  few hundred tokens.
- Needs a relevance cap (top-N linked nodes, recency-weighted) so a hub project doesn't flood
  the context — a `--budget` flag on the CLI recall.
- If the project has no node yet, inject nothing (silence, not noise).

### 2. `memory_search` — the missing primitive

A fuzzy entry-point finder: `memory_search(text, model?)` → matching nodes by name/label *and*
property text, ranked, terse. Implementation now: SPARQL `CONTAINS`/`REGEX` over names and
property literals — fine at personal-store scale. Later: a side lexical index, then embeddings
(see below). This one tool fixes the exact-name cliff, gives the model a cheap presence check
("anything about X?" costs one call), and doubles as capture-side dedup (ROADMAP interlock).

### 3. Prompt-time retrieval hints

A `UserPromptSubmit` hook greps the prompt against the store's node names (the NQuads file is
plain text; a small script suffices — no server needed). On a hit it injects one line:

> memory-graph: nodes matching this prompt — Decision 'use pyoxigraph', Pattern 'oxigraph FILTER
> scope'. `memory_recall` if relevant.

This is a **hint injector, not an auto-recall**: a few tokens, fires only on matches, keeps the
relevance judgement with the model but replaces "remember the protocol" with a concrete,
present-tense pointer. This directly addresses mid-session amnesia — the reminder arrives at
exactly the moment it's actionable.

### 4. Semantic retrieval (embeddings) — later

Name/label matching misses paraphrase ("the DB locking problem" ≠ Pattern "RocksDB exclusive
lock"). Per-node embeddings (name + properties) with a local vector index would close that gap,
slotting in behind `memory_search` without changing its interface. Deferred until the graph is
big enough that lexical search demonstrably misses — embeddings add a model dependency and an
index-maintenance path that aren't worth it for a hundred nodes.

### Search finds doors, traversal explores rooms

Keep the division of labour explicit: `memory_search` locates *entry points*; `memory_recall`
traverses *from* them. The graph structure is the value (multi-hop chains through shared
concepts) — search exists to get you onto the graph, not to replace walking it.

## The multi-model constraint

The federation vision (FEDERATION.md) means retrieval instigation must not be Claude-Code-only.
Layer it:

- **Core, travels with MCP:** tool descriptions that carry the triggering guidance ("call at the
  start of substantive work; when the user references past decisions; before proposing
  architecture"), server `instructions`, and `memory_search` itself. Every MCP client gets these.
- **Adapter, per client:** SessionStart auto-prime and prompt-time hints are Claude Code hooks —
  the Claude Code *adapter* for the core triggers. Other clients would implement their own
  adapters (or live with core-only).

## Phasing

1. **Phase 1:** session-start auto-prime (hook calls CLI recall, injects results);
   `memory_search` tool + CLI subcommand; rewrite tool descriptions to carry trigger guidance.
2. **Phase 2:** prompt-time hint injector; recency/degree-weighted relevance cap on recall
   output.
3. **Phase 3:** embedding index behind `memory_search`, once lexical misses are observed in
   practice.
