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

## The lanes

| Lane | Example | Store |
|---|---|---|
| **Intent** — why | "full dump + atomic rename because MCP stdio servers die ungracefully" | graph (Decision / Pattern) — existing rule |
| **Orientation** — how/where things are stored, located, wired | "hook-kit session state: `~/.claude/hook-kit/sessions/<id>.json`, atomic tmp+rename; `core` is framework-owned, extensions get namespaced dicts" | graph (Pattern, rules below) — **this task** |
| **Investigation findings** — the answer a long dig paid for | "the state write path: hooks.json → dispatch.sh → `run_dispatch` → `StateStore.save`" | graph (Pattern `kind: trace`, rules below) — **this task** |
| **Bulk structure** — every symbol-level fact | "`run_dispatch` is defined in dispatch.py and has 14 call sites" | never *authored* — mechanically enumerable, voluminous, stale per commit; the derived code graph's job ([CODE-GRAPH.md](../CODE-GRAPH.md) phase 2) |

The noise objection to storing structure was always about the **bulk** lane, and it is a
volume argument, not a content one: thousands of auto-extracted symbols sharing tokens like
`get`/`handle`/`state` would flatten the analyzer's term distinctiveness and blur every
match. A curated structure thread has the opposite profile — a few dozen nodes whose tokens
(file paths, symbol names) are the most distinctive in the corpus. What separates the lanes
is *who writes it*: a node is authored because a session **paid** for it (cost-gated), never
because a tool could enumerate it.

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

## The keep test (investigation-findings lane)

Test 1 above deliberately excludes instance-level facts — this lane is the exception, and
**re-derivation cost is the gate**: when answering a where/how question took a real
investigation (many greps/reads across files, running the system — not a lookup), the
*answer* earns a Pattern even though it is instance-level. What made it expensive once
makes it expensive every time; that cost is exactly what memory exists to amortise.

- `kind: trace` · name states the phenomenon ("hook-kit state write path"), description
  carries the finding — the path/flow/location, one or two sentences with the file paths
  and symbols in them (those tokens are the retrieval surface).
- **Aliases are the question**: the phrasings the *next* dig would start from ("where does
  session state get written", "who persists core state"). The finding is only useful if the
  future question can find it — this lane lives or dies on its aliases.
- **Anchors are mandatory** (`anchorPath`, `anchorCommit`): traces stale faster than
  conventions, so the [[code-anchors]] drift flag is what keeps this lane trustworthy.
  Until it lands, recall of a trace should be read as "true as of `anchorCommit`".
- One grep answers it → still out. The lane is cost-gated, not topic-gated.

## Linking learnings to the layout — `manifestsIn`

Intent and structure are separate lanes, but the edge between them is where the graph
beats prose: a Decision links to the layout/trace Patterns where the choice lives in code,
via **`Decision manifestsIn Pattern`** (ontology 0.5.0; verb forms "implemented in",
"lives in", "located at" …). The Pattern's `anchorPath` carries the exact files, so recall
traverses from a *why* to its *where* — per project:

```
Decision "Use Pinia stores"
  ├─ manifestsIn → Pattern "charcoal store layout"   (anchorPath: src/stores/project.ts, appliesTo → Project charcoal)
  ├─ manifestsIn → Pattern "raspberry store layout"  (anchorPath: src/store/,             appliesTo → Project raspberry)
  └─ affects → Project charcoal, Project raspberry
```

"Why Pinia?" grounds the Decision and walks depth 2 to both layouts and their files;
"where do stores live in raspberry?" grounds the layout Pattern directly and walks *back*
to the rationale. One decision, N projects, each with its own anchored layout node — and
when one project restructures, only that Pattern updates (or is superseded); the Decision
and the other project's layout are untouched. The drift flag ([[code-anchors]]) marks each
edge-of-truth independently.

Rule for distill: when a decision's implementation has a known location, put the paths in
an anchored layout/trace Pattern and link `manifestsIn` — do **not** stuff file paths into
the Decision's properties, where they can't be shared across decisions, anchored, or
drift-flagged.

## The structure thread off the Project

Both authored code lanes hang off the Project node (`appliesTo Project`,
discriminated by `kind`), forming what is in effect an independent structure thread:
session-start prime recalls the Project at depth 2, so the map and the paid-for traces
arrive *before* a cold session starts re-deriving them with greps. The **complete**
structure thread — every symbol, always fresh — is the derived code graph
([CODE-GRAPH.md](../CODE-GRAPH.md) phase 2): a separate named graph per repo, regenerated
on commit, disposable, never authored. The findings lane is the bridge until that exists —
and stays valuable after, because it records *which* paths mattered enough to investigate,
which no extractor can know.

## Modelling — reuse Pattern, don't mint a model

Retrieval is model-agnostic and the ontology stays small: orientation memories are
**Patterns** with a discriminating property, not a new resource type. Revisit only if
volume or query needs prove otherwise.

- `name` — the phenomenon: `"hook-kit state layout"`, `"memory store persistence format"`
- `description` — one or two sentences a stranger could act on (required, as for any Pattern)
- `kind: layout | storage | wiring | trace` — filterable later, free-form for now
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

- ~~Dig counter~~ — **done** ([[dig-counter]]): the trace lane no longer depends on the
  model noticing "that was an expensive dig" — PostToolUse counts file-inspection calls
  per turn, and a turn past `DIG_THRESHOLD` gets a Stop block asking for the trace entry.
- ~~[[code-anchors]]~~ — **done**: recall now appends `(code changed since <commit>)`
  when the anchored path has commits past `anchorCommit` (git-only, fail open).
- After a few sessions, check volume: if orientation Patterns exceed ~a dozen per project,
  tighten test 1 (subsystem granularity); if traces accumulate faster than they get
  recalled, raise the cost gate before anything else. The lane earns its keep when the
  injection log shows traces firing ahead of would-be grep sessions.
