# Remote access: one memory everywhere, and handovers

Memory normally lives on the machine Claude Code runs on. This page covers
the two ways to take it beyond that machine:

- **Host your memory on a server.** Every Claude Code machine you log in to,
  claude.ai, and the phone and desktop apps all read from and write to the
  same memory. Your laptop no longer holds it.
- **Hand over one project.** A colleague adds a scoped, read-only copy to
  their own Claude and asks it questions while you're away.

Either way, the server's home page shows how to connect: the connector
address and the steps for claude.ai, the apps and Claude Code. Everyone
uses their own Claude plan, and the server needs no API key and costs
nothing per question. A browser chat that runs on the server is available
as an [opt-in extra](#optional-a-chat-on-the-server-billed-to-an-api-key),
billed to an API key.

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
| **Claude Code** on any machine with the plugin, including the desktop app's Code tab | the plugin's `server` and `server_token` settings | everything: the tools; ambient recall and question answers, run on the server so the machine holds no copy of the graph (or, with **Memory lookups** set to `local copy`, read from a local copy that refreshes at most once a minute); the context log and Stop-block capture, with the log distilled into the server |
| **ordinary chats** in claude.ai, the phone app and the desktop app (not its Code tab) | a custom connector, signed in with your server password | the tools, reads and writes. Chats have no hooks, so nothing is injected automatically: the model calls the memory tools when the conversation needs them |
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

With the server set, Claude Code connects to the remote server's `/mcp`
directly, and the ambient gate's graph reads run on the server too. That covers
recall, the session-start prime, question answers and the review's health
report. For each prompt the plugin sends the prompt to `/api/hook`, and the
server answers from its live store and sends back only the text to add, so
nothing of the graph is downloaded. That suits phones and small devices, and
it stays fast as the graph grows: the server keeps its indexes in memory and
rebuilds them in the background after each write. At 10,000 memories a
warm prompt takes about 140 ms on the server, plus the round trip. A prompt
waits at most 4 seconds; after that the gate stays silent for that prompt.

Set **Memory lookups** to `local copy` to download the graph instead, into
`~/.claude/memory-graph/state/replica/` (refreshed at most once a minute),
and look it up on the machine. It costs more per prompt as the graph grows,
but recall keeps working briefly offline. A server older than this setting
has no `/api/hook`: update it, or use `local copy` (`doctor` says which).

Distill, whether it runs
automatically at session start, through `/memory-graph:distill`, or through
`memory_distill`, uploads this machine's undistilled logs, lets the server
promote them, and then archives or trims the local files the same way a
local distill would. The plugin answers the `memory_distill` tool call
itself on this machine, because the logs are here and not on the server.

To go back to memory on this machine, set **Memory server** back to
`http://127.0.0.1:8848` (its default). That is the same arrangement with
the server on this machine: one graph for every chat, started on demand.

If the server is unreachable, nothing breaks. With server lookups, recall
stays silent until it is back; with a local copy, recall keeps injecting
from the last copy. Tool calls say the server is unreachable. Nothing is
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
`data/state/oauth.json`. To sign apps out or change the password, use
[Settings](#settings-sign-out-change-the-password-replace-the-token).

### Optional: a chat on the server, billed to an API key

For people with no Claude account, the server can host its own chat.
Without an API key, `https://memory.example.com/` is the connect page
described above; with one, it becomes a chat (and the connect page moves
to `/connect`). A Pro or Max plan can't pay for this chat: Anthropic only
lets those plans be used through its own apps, so a chat your server runs
must use an API key.

Sign in with the password and ask what
you'd ask Claude ("what did we decide about tile caching, and why?"). The
answer streams in, with a note of each lookup it made ("searched for…",
"recalled Decision…"). Behind it, Claude runs on your server with five
read-only tools: search, plain-English questions, recall, SPARQL query and an
overview. It is told
to answer from the memory and to say when the memory doesn't hold the
answer, not to fill the gap from general knowledge.

- **It's turned on by setting `ANTHROPIC_API_KEY`** in `.env`. Every answer
  is billed to that key. `MEMORY_GRAPH_CHAT_DAILY_LIMIT`
  (default 300 messages a day, across everyone) caps what a shared link can
  spend. The model is `claude-opus-5-5` at medium effort; set
  `MEMORY_GRAPH_CHAT_MODEL` and `MEMORY_GRAPH_CHAT_EFFORT` to change them.
- **It can't change anything.** Writing still happens from Claude Code, and
  from the apps through the connector.
- Conversations are kept in the server's memory only, and a restart clears
  them. Sign-ins last a week. Wrong passwords count towards the same
  lockout as the connector sign-in.
- `serve --no-chat` turns the browser pages off (connect page, chat and
  settings).

### Settings: sign out, change the password, replace the token

**Settings**, linked from the top of the home page, has three controls. It
asks you to sign in with the password first:

- **Sign everything out.** Every browser, and every app connected through
  claude.ai or the phone, has to sign in again. Claude Code machines use
  the token, so they stay connected.
- **Change the password** used by the chat and when connecting apps. This
  also signs everything out.
- **Replace the token**, for when it may have leaked. The new token is shown
  once, and the old one stops working straight away. Put the new one into
  each Claude Code machine's plugin settings (*Memory server token*).

Each control needs the **server token** typed in as well as a signed-in
browser. A colleague who has only the chat password, as on a handover
share, can ask questions but can't lock you out. If you set no separate
password, the token doubles as the password, so replacing the token
retires the old one as a password too.

Changes made here are saved (hashed) in `data/state/oauth.json` and take
precedence over `MEMORY_GRAPH_PASSWORD` and `MEMORY_GRAPH_TOKEN` in
`.env`. If you're locked out, stop the server and delete that file. It
goes back to the `.env` values, and every app signs in again.

### Security in one paragraph

This is your memory, so treat the server like your email: HTTPS only (the
server warns if `--public-url` isn't https), a long random token, and a
password you don't use anywhere else. Every route needs the token, a signed-in
app's token, or a signed-in browser, except `/healthz` and the sign-in pages. Binding beyond localhost refuses to
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
    --host 0.0.0.0 --port 8848 --token "$(openssl rand -hex 24)" \
    --password "<something to give your colleague>"
```

plus `--public-url https://<its address>` so their Claude can sign in, and
HTTPS in front. The simplest way is the `deploy/` compose setup on its own
domain, with `MEMORY_GRAPH_READ_ONLY=1` added to `.env` and the share's
`graph.nq` in `data/store/`.

`--read-only` offers five tools: `memory_search`, `memory_ask` (plain-English
questions), `memory_recall`, `memory_reflect` and `memory_query`. It refuses everything else, including
any write tool added in future, because it works from an allow-list. It
never auto-distills or saves, and it doesn't accept distill uploads.

**4. Send your colleague the link and the password**

`https://<host>/` is titled "quartz — handover memory". It shows them the
connector address and the steps: add it as a custom connector in
claude.ai (or `claude mcp add --transport http …` and `/mcp` in Claude
Code), sign in with the password, and ask *"what's the state of the tile
cache work?"* or *"what should I watch out for when deploying quartz?"*.
It runs on their own Claude plan, and you pay nothing per question. They
need a Claude account whose plan allows custom connectors.

To revoke access,
stop the server or change the password and token. To refresh what they see,
export again. Serve it from somewhere that stays up,
not your laptop: a work VM is simplest, and the hosting options above all
apply.
