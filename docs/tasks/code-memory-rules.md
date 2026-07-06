# Task: code memory rules — what code knowledge earns a node

Status: **rules drafted (this doc) · protocol/docs wiring done · drift flagging depends on
[[code-anchors]]** · Owner: Stuart · Created: 2026-07-06 · Size: S

## Why

[CODE-GRAPH.md](../CODE-GRAPH.md) drew a binary line: *intent* (why the code is the way it
is) goes in the graph; *structure* (where is X defined, who calls Y) never does. Live use
showed a middle band the binary misses: a cold session on a known project still burns its
first minutes re-discovering the **map** — where state lives, what format the store uses,
how the pieces wire together. That knowledge is not symbol-level structure (one grep does
not answer it, and it does not churn every commit), and it is not intent either. It should
be memory.

## The three lanes

| Lane | Example | Store |
|---|---|---|
| **Intent** — why | "full dump + atomic rename because MCP stdio servers die ungracefully" | graph (Decision / Pattern) — existing rule |
| **Orientation** — how/where things are stored, located, wired | "hook-kit session state: `~/.claude/hook-kit/sessions/<id>.json`, atomic tmp+rename; `core` is framework-owned, extensions get namespaced dicts" | graph (Pattern, rules below) — **this task** |
| **Structure** — symbol-level facts | "`run_dispatch` is defined in dispatch.py and has 14 call sites" | never — derivable, voluminous, stale per commit; the derived code graph's job |

## The keep test (orientation lane)

All three must hold — the capture rubric specialised for code:

1. **Convention over instance.** It describes a rule or place a *category* of things
   follows — where hooks live, how state is keyed, what format the store persists — not
   one symbol's location. ("Extensions are discovered via `claude_hook_kit` entry points"
   passes; "`ContextCounterExtension` is in nudge.py" fails.)
2. **Multi-file to re-derive.** Reconstructing it means reading several files or running
   the system. If a single grep answers it, it is structure — keep it out.
3. **Restructure-horizon churn.** It survives ordinary commits and breaks only on
   deliberate reorganisation — and it carries an anchor so [[code-anchors]] can flag the
   drift when that happens.

Documentation guard: if the repo already documents it well (README, ARCHITECTURE), do not
duplicate the prose — store the pointer (`anchorPath` at the doc) plus only what the doc
does *not* say: the gotcha, the reason, the thing learned the hard way.

## Modelling — reuse Pattern, don't mint a model

Retrieval is model-agnostic and the ontology stays small: orientation memories are
**Patterns** with a discriminating property, not a new resource type. Revisit only if
volume or query needs prove otherwise.

- `name` — the phenomenon: `"hook-kit state layout"`, `"memory store persistence format"`
- `description` — one or two sentences a stranger could act on (required, as for any Pattern)
- `kind: layout | storage | wiring` — filterable later, free-form for now
- `anchorPath` (dir, file, or doc; repo-relative) + `anchorCommit` when distill writes it —
  the staleness hook
- `aliases` + concept links (`Concept "state"`, `"storage"`, `"hooks"` …) per the standard
  enrichment rules; `appliesTo Project` link always

**Volume guard:** a handful per project — one node per *subsystem*, never per file.
Upsert-by-name means a restructure updates the node; use `supersedes` only when the old
layout itself stays worth knowing.

## Capture path (already wired)

- **Structured context entries** carry the lane naturally:

  ```markdown
  - [15:10] Pattern: hook-kit state layout
    description: per-session JSON under ~/.claude/hook-kit/sessions/<id>.json; core is framework-owned, extensions namespaced; writes atomic tmp+rename
    kind: storage
    anchorPath: hook-kit/claude_hook_kit/state.py
    appliesTo: Project/claude-memory-graph
    concepts: state, storage
  ```

- **Recall already pays out:** session-start prime recalls the Project at depth 2, so
  orientation Patterns linked `appliesTo Project` surface exactly when a cold session
  needs the map — before it starts re-deriving it with greps.

## Remaining work

- [[code-anchors]] — the drift flag that keeps this lane honest (`(code changed since)`
  on recall when the anchored path has commits past `anchorCommit`).
- After a few sessions, check volume: if orientation Patterns exceed ~a dozen per project,
  tighten test 1 (subsystem granularity) before anything else.
