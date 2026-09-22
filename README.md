# claude-memory-graph

An [Arches](https://www.archesproject.org/)-inspired RDF knowledge-graph MCP server giving Claude Code persistent, structured long-term memory. Facts are stored as typed resources (Person, Project, Decision, Pattern, …) in per-instance named graphs, connected by cross-links and shared concept nodes, so recall can traverse multi-hop chains ("what decisions affect the projects Stuart works on?") instead of grepping flat notes.

- **Storage:** in-memory [pyoxigraph](https://pypi.org/project/pyoxigraph/) triple store, persisted as NQuads after every mutation (atomic write). Default location `~/.claude/memory-graph/store/graph.nq` — human-readable, greppable, diffable.
- **Self-extending ontology:** the LLM must reuse the built-in relations; if none fits it can add a new one (with a description and provenance timestamp) that persists in the schema graph.
- **Token-lean:** tool outputs are terse text designed for LLM consumption — no IRIs, no timestamps, no pretty-printed JSON.

## Install

Two pieces, installed separately:

| Piece | Gives you | Installed via |
|---|---|---|
| **Plugins** | the MCP server, `/memory-graph:distill`, `/memory-graph:ingest`, `/hook-kit:install` | `claude plugin install` |
| **Hooks** | session-start priming, ambient recall injection, context-log enforcement | `~/.claude/settings.json` |

The hooks are deliberately **not** shipped in a plugin `hooks.json`. Plugin-scope hooks
never fire in bridge sessions — which is what the Claude desktop app runs — so a
plugin-only install silently loses every hook, and you get no ambient recall and no
capture enforcement while everything still *looks* installed. Registering them in
`settings.json` works on both surfaces. See [docs/HANDBOOK.md](docs/HANDBOOK.md) for
how to verify they are live.

### 1. Plugins — MCP server and skills

```sh
claude plugin marketplace add <git-url-or-local-path>
claude plugin install memory-graph@claude-memory-graph --scope user
claude plugin install hook-kit@claude-memory-graph --scope user
```

`memory-graph` brings the MCP server (run via `uvx` from the bundled source — requires
[uv](https://docs.astral.sh/uv/)) and the distill/ingest skills. [hook-kit](hook-kit/) is
the standalone hook-extension framework the hooks below run on; installing it adds
`/hook-kit:install` for enabling and disabling individual extensions. Both extensions
(`memory-recall` for priming and per-prompt injection, `context-counter` for context-log
enforcement — see [docs/ORCHESTRATION.md](docs/ORCHESTRATION.md)) are on by default, so
there is nothing to enable for a standard setup.

Optional: set `MEMORY_GRAPH_PATH` to change the data directory (defaults to
`~/.claude/memory-graph/store`).

### 2. Hooks — priming, recall injection, context capture

The hooks run out of a checkout, so clone the repo somewhere permanent — the plugin
cache directory is versioned and not a stable path. Then merge this into
`~/.claude/settings.json`, replacing `/path/to/claude-memory-graph` with your clone:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "\"/path/to/claude-memory-graph/hooks/session-start.sh\""
          },
          {
            "type": "command",
            "command": "\"/path/to/claude-memory-graph/hooks/dispatch.sh\" SessionStart"
          }
        ]
      }
    ],
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "\"/path/to/claude-memory-graph/hooks/dispatch.sh\" UserPromptSubmit"
          }
        ]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "Write|Edit|MultiEdit",
        "hooks": [
          {
            "type": "command",
            "command": "\"/path/to/claude-memory-graph/hooks/allow-context-writes.sh\""
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "mcp__.*memory_.*",
        "hooks": [
          {
            "type": "command",
            "command": "\"/path/to/claude-memory-graph/hooks/dispatch.sh\" PostToolUse"
          }
        ]
      },
      {
        "matcher": "Grep|Glob|Read|Bash",
        "hooks": [
          {
            "type": "command",
            "command": "\"/path/to/claude-memory-graph/hooks/dispatch.sh\" PostToolUse"
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "\"/path/to/claude-memory-graph/hooks/dispatch.sh\" Stop"
          }
        ]
      }
    ],
    "PreCompact": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "\"/path/to/claude-memory-graph/hooks/dispatch.sh\" PreCompact"
          }
        ]
      }
    ],
    "SessionEnd": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "\"/path/to/claude-memory-graph/hooks/dispatch.sh\" SessionEnd"
          }
        ]
      }
    ]
  }
}
```

`PreToolUse` is what makes the capture loop usable in manual approval mode: writes whose
target resolves inside `~/.claude/context/` are pre-approved, so the Stop block asking for
a context entry doesn't turn into a permission prompt every few turns. Nothing else is
touched — the check is on the resolved real path, and `Bash` is deliberately not covered.
Drop this block if you would rather approve each write.

Settings are re-read live, so the hooks take effect on your next prompt — no restart
needed. To confirm they are actually firing:

```sh
claude-memory-graph pulse          # sessions seen, prompts gated, injections
```

A session that shows `SessionStart` but no `UserPromptSubmit` means the hooks are
registered in a plugin rather than in `settings.json`.

### Shared server (across clients and machines)

```sh
claude-memory-graph serve --host 0.0.0.0 --port 8848 --token <secret>   # on the host
claude mcp add --transport http memory-graph http://host:8848/mcp \
    --header "Authorization: Bearer <secret>"                            # on each client
```

One process owns the store (no last-writer-wins between sessions). Non-localhost binds
require the token. v1 scope: the MCP tools travel; ambient injection/capture hooks stay
per-machine — see [docs/tasks/remote-server.md](docs/tasks/remote-server.md).

### Manual install (server only)

```sh
uv tool install git+<repo-url>   # or from a checkout: uv tool install .
claude mcp add --scope user memory-graph -- claude-memory-graph
```

This registers just the MCP server — no context protocol or distill skill.

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

Multiple Claude Code sessions each spawn their own server process over the same NQuads file — last writer wins per mutation. This is fine for a personal memory store; if it ever outgrows that, the upgrade path is pyoxigraph's RocksDB-backed store behind a single shared daemon.
