# Remote access: one memory everywhere, and handovers

Memory normally lives on the machine Claude Code runs on. This page covers
the two ways to take it beyond that machine:

- **Host your memory on a server.** Every Claude Code machine you log in to,
  claude.ai, and the phone and desktop apps all read from and write to the
  same memory. Your laptop no longer holds it.
- **Hand over one project.** A colleague can query a scoped, read-only copy
  while you're away.

## Host your memory on a server

```
                       ┌──────────────── your server ────────────────┐
 Claude Code machines ─┤ HTTPS (Caddy) → claude-memory-graph serve    │
   (plugin, token)     │                  owns the one store          │
 claude.ai / phone  ───┤                  /mcp  /api/*  /login        │
   (connector, OAuth)  └──────────────────────────────────────────────┘
```

### What each client gets

| Client | How it connects | What it gets |
|---|---|---|
| **Claude Code** on any machine with the plugin | the plugin's `server` and `server_token` settings | everything: the tools; ambient recall, from a local copy of the graph that refreshes at most once a minute; the context log and Stop-block capture, with the log distilled into the server |
| **claude.ai, the phone app, the desktop app** | a custom connector, signed in with your server password | the tools, reads and writes. These apps have no hooks, so nothing is injected automatically: the model calls the memory tools when the conversation needs them |
| any other MCP client | `https://<host>/mcp` with `Authorization: Bearer <token>` | the tools |

Context logs never leave the machine that wrote them, except as the upload
distill makes to the server. The server owns the only store, so writes from
different machines can't overwrite each other.

### 1. Get a server

You need something that stays on and that the internet can reach over
HTTPS. claude.ai connectors call your server from Anthropic's side, so a
LAN address or a VPN won't do. Any one of these works:

| Option | Notes |
|---|---|
| A small VPS (Hetzner, DigitalOcean, Lightsail…) plus a domain name | the setup below as written; a few pounds a month |
| A machine at home or work that stays on, behind Cloudflare Tunnel or Tailscale Funnel | no open ports; the tunnel provides HTTPS, so skip Caddy and run only the `memory` service |
| A container platform with a persistent volume (Fly.io, Railway…) | build from the `Dockerfile` and mount a volume at `/data` |

The memory is small: a few MB of RAM per thousand memories and almost no
CPU. The smallest instance is plenty.

### 2. Run it

On the server, with Docker and a DNS record pointing your domain at it:

```sh
git clone https://github.com/StuCM/claude-memory-graph && cd claude-memory-graph/deploy
cp .env.example .env              # set DOMAIN, MEMORY_GRAPH_PUBLIC_URL, a token, a password
openssl rand -hex 32              # a good MEMORY_GRAPH_TOKEN
docker compose up -d
curl https://memory.example.com/healthz    # → ok
```

Caddy obtains and renews the TLS certificate by itself. The store,
sign-ins and logs live in `deploy/data/`, so back that folder up.

**Bring your existing memory** before the first start: copy your laptop's
`~/.claude/memory-graph/store/graph.nq` to `deploy/data/store/graph.nq`.
Without it the server starts empty. Its auto-distill fills it as each
machine's context logs arrive, but only from logs not yet distilled.

Without Docker, it's one command; put any TLS proxy in front:

```sh
claude-memory-graph serve --host 0.0.0.0 --port 8848 --token "$TOKEN" \
    --public-url https://memory.example.com --password "$PASSWORD"
```

### 3. Point each Claude Code machine at it

Install the plugin with the server settings:

```sh
claude plugin marketplace add StuCM/claude-memory-graph
claude plugin install memory-graph@claude-memory-graph --scope user \
    --config server=https://memory.example.com --config server_token=<token>
```

On a machine that already has the plugin, set **Memory server** and
**Memory server token** in `/config` (the token is kept in secure storage,
not `settings.json`). Then start a new session. To check:

- run `MEMORY_GRAPH_SERVER=https://memory.example.com MEMORY_GRAPH_TOKEN=<token>
  claude-memory-graph doctor`, which should report "reachable, token
  accepted";
- or look at the pane's State tab, where `memory` should name the server.

With the server set, the plugin's MCP server becomes a proxy to the remote
one. The ambient gate reads a replica of the graph kept in
`~/.claude/memory-graph/state/replica/`. Distill, whether it runs
automatically at session start, through `/memory-graph:distill`, or through
`memory_distill`, uploads this machine's undistilled logs, lets the server
promote them, and then archives or trims the local files the same way a
local distill would.

If the server is unreachable, nothing breaks. Recall keeps injecting from
the last replica, and tool calls say the server is unreachable. Nothing is
written locally, because a second store is how memories get lost.

### 4. Connect claude.ai and the phone

1. In claude.ai: **Settings → Connectors → Add custom connector**. Give it
   a name ("Memory") and the URL `https://memory.example.com/mcp`.
2. **Connect**. Your server's sign-in page opens, naming the app that's
   asking. Type `MEMORY_GRAPH_PASSWORD` and press **Allow**.
3. Connectors you add on claude.ai are available in the phone and desktop
   apps signed in to the same account. Enable it in a chat's tools menu.

Ask *"what do you remember about quartz?"* or *"remember that we chose
Varnish for tiles"*. The model uses the memory tools.

Sign-ins last until unused for 180 days. Five wrong passwords lock the
page for five minutes. Tokens are stored only as hashes in
`data/state/oauth.json`. To sign every app out, stop the server and
delete that file. To lock out Claude Code machines, change
`MEMORY_GRAPH_TOKEN`.

### Security in one paragraph

This is your memory, so treat the server like your email: HTTPS only (the
server warns if `--public-url` isn't https), a long random token, and a
password you don't use anywhere else. Every route except `/healthz` needs
the token or a signed-in app's token. Binding beyond localhost refuses to
start without a token. Uploaded context files are processed in a scratch
directory and are never stored as files on the server; only what distill
promotes is kept. The connectors you add can read and write everything, so
add only clients you trust.

## Handover: let a colleague query one project

Never point a colleague at your live memory. It holds every project, your
preferences, and whatever your sessions captured. The server can't filter
it per request safely: SPARQL reaches every graph, and one shared concept
like "arches" links into every project that mentions it. Instead, export the
project into its own store and serve that copy, read-only.

**1. Preview what would be shared**

```sh
claude-memory-graph share quartz --dry-run
```

This lists every node that would go, grouped by type. The boundary:

- the Project, everything linked to it, and one hop further out from those
  memories (a decision's technology, a pattern's task);
- the walk never goes *through* a concept, or another project, person or
  company. Those bridge into unrelated work, so they are included as
  endpoints only, and other projects, people and companies found at the
  second hop are left out;
- Preference concepts are never shared, and people keep only name and role;
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

or, with the container: `docker run -e MEMORY_GRAPH_READ_ONLY=1 -e
MEMORY_GRAPH_TOKEN=<secret> -v ~/handover-quartz:/data/store …`.

`--read-only` offers four tools: `memory_search`, `memory_recall`,
`memory_reflect` and `memory_query`. It refuses everything else, including
any write tool added in future, because it works from an allow-list. It
never auto-distills or saves, and it doesn't accept distill uploads.

**4. Your colleague connects**

```sh
claude mcp add --transport http stuart-memory https://<host>/mcp \
    --header "Authorization: Bearer <token>"
```

Their Claude can then ask things like *"search Stuart's memory for the tile
cache problem"*. To revoke access, stop the server or change the token. To
refresh what they see, export again. Serve it from somewhere that stays up,
not your laptop: a work VM is simplest, and the hosting options above all
apply.
