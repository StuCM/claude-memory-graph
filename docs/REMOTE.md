# Remote access: handovers, and memory from anywhere

The memory server can run over HTTP (`claude-memory-graph serve`), so a Claude
on another machine — yours, or a colleague's — can query it with the MCP tools.
This page covers the two uses: letting someone **query one project while you're
away**, and reaching **your own memory from anywhere**.

## Handover: let a colleague query one project

Never point a colleague at your live store. It holds every project, your
preferences, and whatever your sessions captured; the server can't filter it
per request safely (SPARQL reaches every graph, and one shared concept like
"arches" links into every project that mentions it). Instead, export the
project into its own store and serve that copy, read-only.

**1. Preview what would be shared**

```sh
claude-memory-graph share quartz --dry-run
```

It lists every node that would go, by type. The boundary:

- the Project, everything linked to it, and one hop further out from those
  memories (a decision's technology, a pattern's task);
- never walked *through* a concept, or another project, person or company —
  those bridge into unrelated work, so they're included as endpoints only,
  and other projects/people/companies found at the second hop are left out;
- Preference concepts are never shared; people keep only name and role;
- provenance (which session file or document a memory came from) is stripped;
- forgotten memories and closed links are left out.

`--depth 1` shares only what is linked directly to the project.

**2. Export it**

```sh
claude-memory-graph share quartz --out ~/handover-quartz
MEMORY_GRAPH_PATH=~/handover-quartz claude-memory-graph reflect   # read it back
```

**3. Serve it, read-only**

```sh
claude-memory-graph serve --store ~/handover-quartz --read-only \
    --host 0.0.0.0 --port 8848 --token "$(openssl rand -hex 24)"
```

`--read-only` offers four tools — `memory_search`, `memory_recall`,
`memory_reflect`, `memory_query` — and refuses everything else, including any
write tool added in future (it's an allow-list). It never auto-distills and
never saves. A non-localhost bind refuses to start without `--token`.

**4. Your colleague connects**

```sh
claude mcp add --transport http stuart-memory https://<host>/mcp \
    --header "Authorization: Bearer <token>"
```

Their Claude can then ask things like *"search Stuart's memory for the tile
cache problem"* or *"recall the decisions affecting quartz"*. Revoke access by
stopping the server or changing the token; refresh it by exporting again.

### Where to run it while you're away

The share is one file (`graph.nq`), so it can be served from anywhere that
stays up — not your laptop. In order of least effort:

| Option | How | Notes |
|---|---|---|
| A work server or VM on the office network | copy the folder over, run step 3 | simplest; reachable only on that network |
| The container | `docker run -p 8848:8848 -e MEMORY_GRAPH_TOKEN=<secret> -v ~/handover-quartz:/data` + an image built from this repo's `Dockerfile` | read-only by default |
| Over the internet | the container behind a TLS reverse proxy (Caddy, a cloud load balancer) or a tunnel (Tailscale, cloudflared) | **never** expose plain HTTP: the token would travel in clear text |

## Your own memory from anywhere

`serve` on your own store (no `--store`, no `--read-only`) gives full read-write
access to the MCP tools from any machine or client — see
[docs/tasks/remote-server.md](tasks/remote-server.md) for the client matrix.
One process owns the store, so there is no last-writer-wins between sessions.

**The current gap.** Only the MCP *tools* travel. The ambient layer — the
session-start prime, the per-prompt injection, the capture cadence — runs in
the plugin's mod on the machine Claude Code runs on, and reads the store and
context files from that machine's disk. A laptop pointed at a remote server
gets tools but no ambient memory.

**The design to close it** (not built yet): the mod already sends each
event to a stateless Python call (`claude_memory_graph.hookrun`) with the
session state in the request. That makes the split easy:

- add a `POST /hook` endpoint to `serve` that runs the **graph** half of that
  call (recall, prime, review) against the server's store, behind the same
  bearer token;
- give the plugin a `server` option (URL + token). When set, the mod sends the
  graph events there and keeps the **file** half (the capture cadence, which
  reads the local context log) local;
- context files stay on each machine and reach the server as they always have:
  through distill, which writes via the MCP tools.

Result: one store, ambient memory on every machine that has the plugin, tools
from every MCP client (including the phone path in the client matrix).
