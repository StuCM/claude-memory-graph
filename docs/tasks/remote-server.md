# Task: remote server — one memory across clients and machines

Status: **v1, v1.5 and v2 done**: `serve` with bearer auth; single-owner OAuth for
claude.ai and the phone; the plugin's server mode (proxy, replica, remote distill). The
user guide is [docs/REMOTE.md](../REMOTE.md). ·
Owner: Stuart · Created: 2026-07-09 · Size: M

## As built (v1)

`claude-memory-graph serve [--host H] [--port 8848] [--token T]` runs the same MCP
server over streamable HTTP (stateless, JSON responses — any number of clients share
the endpoint). One long-running process **owns the store**, which is strictly safer
than today's one-stdio-server-per-session model: no last-writer-wins between
concurrent sessions. Auto-distill runs at server start as usual; provenance
(`capturedBy`) still stamps per client.

Security: loopback by default; binding beyond localhost **refuses to start without a
token** (`--token` / `MEMORY_GRAPH_TOKEN`); constant-time bearer check on every
request. LAN or reverse-proxy-with-TLS territory — not a public service.

Connect a client:
```sh
claude mcp add --transport http memory-graph http://host:8848/mcp \
    --header "Authorization: Bearer <token>"
```

## The honest v1 limitation — tools travel, hooks don't

The MCP tools (recall, search, store, link, distill, query, reflect) work from any
client. The **local hook machinery does not**: ambient injection, session-log recall,
the Stop block, and the dig counter all run on the client machine and read the store
file / context dir directly. A remote client therefore gets *pull* memory (the model
calls tools) but not *push* memory (memories arriving unasked).

Same-machine multi-client (Claude Code + Claude Desktop + an IDE) needs no server at
all — point them at the same `MEMORY_GRAPH_PATH`; hooks work wherever the plugin is
installed.

## What each client gets today

To be precise about "tools travel": the FULL tool surface travels — reads AND writes
(store/link/distill/forget as much as recall/search/query). "Hooks don't" means only
the automatic behaviours (ambient injection, Stop-block capture), which are Claude Code
hook features and never existed on other surfaces anyway.

| Client | Shared memory today? | Notes |
|---|---|---|
| Claude Code, any machine | **yes** — `claude mcp add --transport http … --header "Authorization: Bearer …"` | tools remote; hooks still run locally against the local store unless v2 |
| Claude Desktop app, same machine | **yes, no server needed** — stdio server in its MCP config against the same `MEMORY_GRAPH_PATH` | full tools; no hooks (the app has none) |
| claude.ai / phone (custom connector) | **needs v1.5** | connectors dial from Anthropic's side: public HTTPS required (no LAN/VPN), and the connector UI supports OAuth or no-auth — **no static-header option**, so the bearer token doesn't fit |

## Phasing

- **v1.5 — hosted for claude.ai (the phone case): DONE, as route (b).** The MCP SDK's
  auth scaffolding made native OAuth small for a single owner: `auth.py` (register,
  authorize → the server's own /login page → code → token; hashed, persisted, rotating).
  Original plan: public HTTPS + OAuth 2.1 with
  dynamic client registration. Two routes: (a) an OAuth-terminating proxy in front
  (Cloudflare Access, an MCP OAuth gateway) — zero code change here, the sane first
  move; (b) native OAuth via the MCP SDK's auth scaffolding — a substantial,
  security-sensitive build (client registry, token issuance, persistence). Do (a)
  first; promote to (b) only if the proxy chafes. Never run the no-auth option in
  public: this is your memory.
- **v2 — remote gate: DONE, as a replica.** Rather than a `/corpus` endpoint, the hook
  runner keeps a local copy of graph.nq (`/api/graph.nq`, ETag, ≤1 check a minute), so
  the gate code is unchanged. Distill uploads logs to `/api/distill`. Original plan: teach the gate extensions to fetch their corpus from the
  server (a `/corpus` endpoint or an MCP resource) with a short-TTL local cache, so
  ambient injection works on machines that only have the plugin + a server URL.
  The context dir stays local (capture is inherently per-session).
- **v3 — multi-user:** per-person stores, visibility tiers, the policy-gated `expand`
  — that's [SHARING.md](../future/SHARING.md)/[FEDERATION.md](../future/FEDERATION.md), not this task.

## Test

Exercised end to end: streamable HTTP client lists 11 tools, recall round-trips,
wrong bearer → 401, non-loopback bind without token refuses to start (SystemExit).
