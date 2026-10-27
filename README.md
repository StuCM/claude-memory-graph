# claude-memory-graph

An [Arches](https://www.archesproject.org/)-inspired RDF knowledge-graph MCP server giving Claude Code persistent, structured long-term memory. Facts are stored as typed resources (Person, Project, Decision, Pattern, …) in per-instance named graphs, connected by cross-links and shared concept nodes, so recall can traverse multi-hop chains ("what decisions affect the projects Stuart works on?") instead of grepping flat notes.

- **Storage:** in-memory [pyoxigraph](https://pypi.org/project/pyoxigraph/) triple store, persisted as NQuads after every mutation (atomic write). Default location `~/.claude/memory-graph/store/graph.nq` — human-readable, greppable, diffable.
- **Self-extending ontology:** the LLM must reuse the built-in relations; if none fits it can add a new one (with a description and provenance timestamp) that persists in the schema graph.
- **Token-lean:** tool outputs are terse text designed for LLM consumption — no IRIs, no timestamps, no pretty-printed JSON.

## Install

Needs Claude Code **2.1.287 or later** (it loads plugin mods) and
[uv](https://docs.astral.sh/uv/) on your PATH.

```sh
claude plugin marketplace add StuCM/claude-memory-graph
claude plugin install memory-graph@claude-memory-graph --scope user
```

Start a new session. That's the whole install: the plugin brings the MCP server, the
`/memory-graph:distill` and `/memory-graph:ingest` skills, and a mod
([hooks/register.ts](hooks/register.ts)) that runs memory for every session:

- **session start** — injects the context-log protocol and a short, ranked summary of
  what memory knows about this project;
- **every prompt** — injects relevant memories when the gate is confident, silence
  otherwise;
- **end of each turn** — blocks once when the context log has fallen behind, or after a
  long investigation, so the knowledge gets written down;
- **compaction** — tells the summariser to keep what isn't in the log yet;
- writes to `~/.claude/context/` are pre-approved (real-path checked; `Bash` is never
  covered), so the capture loop doesn't become a permission prompt every few turns.

The first prompt of the first session takes a few seconds while uv builds the plugin's
environment. To check everything is live, run `claude-memory-graph doctor`, or open the
pane (`/graph-panel`) and look at its **State** tab.

**Upgrading from 0.13 or earlier:** the hooks used to be registered by hand in
`~/.claude/settings.json` and the separate `hook-kit` plugin. Both are retired: delete the
memory-graph entries (`dispatch.sh`, `session-start.sh`, `allow-context-writes.sh`) from
the `"hooks"` block of your settings and uninstall `hook-kit`
(`claude plugin uninstall hook-kit@claude-memory-graph`). `doctor` flags any leftovers.
Your logs move from `~/.claude/hook-kit` to `~/.claude/memory-graph/state` by themselves.

### The pane

`/graph-panel` opens a **Memory graph** pane beside the conversation:

- **Injected** — the full text of everything memory put in front of the model this
  session (the start-up summary, per-prompt memories, end-of-turn asks), then each gate
  decision with its scores, including the silent ones;
- **State** — project, prompt counts, uncaptured turns, digs this turn, context size,
  and the last error if the Python side failed;
- **Activity** — each memory-graph tool call with its input and output.

Memory-graph tool calls also draw as one dim line each in the transcript; their output
still reaches the model.

### Settings (`/config`)

| Setting | Values | |
|---|---|---|
| **Memory graph pane** | `auto` (default) · `manual` · `off` | `auto` opens the pane on the first graph tool call; `manual` only via `/graph-panel`; `off` drops the pane and shows graph tool calls in the transcript as normal. Memory runs either way. |
| **Periodic graph review** | off (default) · on | every few days, ends one turn asking for a graph tidy-up (over-long names, orphans, missing links) |

Thresholds live in `~/.claude/memory-graph/gate.json` — see the tuning table in
[docs/HANDBOOK.md](docs/HANDBOOK.md). Set `MEMORY_GRAPH_PATH` to move the store
(default `~/.claude/memory-graph/store`).

### Remote access and handovers

`claude-memory-graph serve` runs the memory over HTTP for other machines and clients,
and `claude-memory-graph share <project>` exports one project for a colleague to query
read-only while you're away. See **[docs/REMOTE.md](docs/REMOTE.md)**.

### MCP server only (no ambient memory)

```sh
uv tool install git+https://github.com/StuCM/claude-memory-graph
claude mcp add --scope user memory-graph -- claude-memory-graph
```

For clients other than Claude Code: the tools work, but nothing injects or captures
by itself.

## The workflow

1. **During every session**, Claude keeps a running context file in `~/.claude/context/` (decisions, problems solved, preferences, codebase orientation and dig findings — a handoff log any LLM can pick up; graph-worthy points are written as *structured entries* that distill promotes directly instead of re-deriving).
2. **Distill happens by itself**: every new session's server starts by mechanically promoting structured entries into the graph (no LLM, idempotent, refuses anything questionable to a residue report; `MEMORY_GRAPH_AUTO_DISTILL=0` to disable). A file that left no residue and has been untouched for `DISTILL_AFTER_DAYS` (default 2 — see `~/.claude/memory-graph/gate.json`) is finished, so that run also marks and archives it; mtime is what keeps a live session's own log out of reach. A file still active past that window is one the mechanical lane refused, and the Stop hook blocks once per session asking for a distill run. **`/memory-graph:distill`** is for the residue — narrative bullets, near-duplicates, ontology extensions — and archives clean files to `~/.claude/context/archive/` (never deleted). Also available on demand as the `memory_distill` MCP tool and the `claude-memory-graph distill` CLI.
3. **Recall** happens naturally: Claude calls `memory_recall`/`memory_query` when past context is relevant, traversing links between projects, decisions, gotchas, and people.

## MCP tools

| Tool | Purpose |
|------|---------|
| `memory_store_resource` | Create/update a typed resource (Person, Project, Company, Task, Technology, Decision, Pattern). Upserts by model+name; any camelCase properties accepted. |
| `memory_store_concept` | Create a shared concept node (Skill, Concept, Constraint, Preference). |
| `memory_link` / `memory_unlink` | Cross-graph relationships. Unknown relations error with the valid list; pass `new_relation_description` to extend the ontology when nothing fits. Links are bi-temporal: single-valued relations (employedBy, assignedTo) auto-close a conflicting earlier edge (`worldChange`) instead of keeping two current facts, and unlink *closes* by default (`worldChange`/`correction`) — `mode: remove` for hard delete. Recall shows only currently-valid edges; history stays queryable. |
| `memory_rename` | Rename a resource or concept **in place**, preserving every link. The only safe way to shorten an over-long name — `memory_store_resource` upserts by name, so storing a shorter one creates a second, linkless node and leaves the original behind. |
| `memory_recall` | A resource, its properties, and linked resources — depth 1 or 2 (multi-hop via shared nodes). |
| `memory_forget` | Soft-delete (invalidated, kept for provenance, hidden from retrieval). |
| `memory_query` | Raw SPARQL (prefixes `rdf`, `rdfs`, `xsd`, `mem` pre-loaded). |
| `memory_reflect` | Graph overview: counts, available relations, recent additions, mechanical link-gap candidates. |
| `memory_distill` | Mechanical promotion of structured context entries (no LLM): parse → fold → apply, refusing anything questionable to a residue report. In-session equivalent of the `distill` CLI. |

## Terminal use (read-only)

```sh
claude-memory-graph recall Person Stuart --depth 2
claude-memory-graph reflect
claude-memory-graph query 'SELECT ?name WHERE { GRAPH ?g { ?n rdf:type mem:Project ; mem:name ?name } }'
```

Writes are deliberately MCP-only: a running server holds the graph in memory and saves after each mutation, so terminal writes would be overwritten by the next in-session save.

## Running, debugging, tuning

**[docs/HANDBOOK.md](docs/HANDBOOK.md)** is the operator's guide: what each subsystem is
doing at runtime (with the code and log locations to dig into), the terminology with
examples, setup verification steps, the symptom→knob tuning table, how to prompt so
retrieval works with you, and the command cadence.

## Design notes

Each resource instance lives in its own named graph (`…/graph/resource/<uuid>`); cross-links live in a dedicated links graph; shared concepts in a concepts graph; the ontology (including LLM-added relations) in a schema graph. See `claude_memory_graph/base.ttl` for the base ontology.

Each Claude Code session runs its own stdio server; each reloads the file when another has saved since, and `serve` runs one shared process instead. The graph is persisted as NQuads after every write.
