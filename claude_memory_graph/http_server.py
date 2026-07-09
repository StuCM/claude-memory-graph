"""Remote MCP server — the same memory over streamable HTTP.

One long-running process owns the store and serves every client (Claude
Code on other machines, Claude Desktop, any MCP client) — which is
strictly SAFER than today's one-stdio-server-per-session model: a single
process means no last-writer-wins between concurrent sessions.

Deliberate v1 scope (docs/tasks/remote-server.md): the MCP tools travel;
the LOCAL hook machinery (ambient injection, capture enforcement) does
not — hooks on a remote client would need local store access. Remote
clients get recall/search/store/link/distill/query on shared memory;
ambient injection stays a same-machine feature until the gate learns to
query a server.

Security: binds loopback by default. Binding beyond localhost REQUIRES a
bearer token (--token / MEMORY_GRAPH_TOKEN) — the server refuses to start
otherwise. This is a personal/team memory store, not a public service:
keep it on a LAN or behind a reverse proxy with TLS.

Connect a client:
    claude mcp add --transport http memory-graph http://host:8848/mcp \\
        --header "Authorization: Bearer <token>"
"""

import contextlib
import logging

from mcp.server import Server

from . import tools
from .store import MemoryStore

log = logging.getLogger(__name__)


def _unauthorized():
    from starlette.responses import PlainTextResponse
    return PlainTextResponse("unauthorized", status_code=401)


class _BearerAuth:
    """Minimal ASGI middleware: constant-time bearer check on every request."""

    def __init__(self, app, token: str):
        self.app = app
        self.token = token

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and self.token:
            import hmac
            headers = dict(scope.get("headers") or [])
            supplied = headers.get(b"authorization", b"")
            expected = f"Bearer {self.token}".encode()
            if not hmac.compare_digest(supplied, expected):
                await _unauthorized()(scope, receive, send)
                return
        await self.app(scope, receive, send)


def serve(store_path, instructions: str, host: str = "127.0.0.1",
          port: int = 8848, token: str = "") -> None:
    import uvicorn
    from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
    from starlette.applications import Starlette
    from starlette.routing import Mount

    loopback = host in ("127.0.0.1", "::1", "localhost")
    if not loopback and not token:
        raise SystemExit(
            "Refusing to bind beyond localhost without a token. Pass --token "
            "(or set MEMORY_GRAPH_TOKEN) — this is your memory; protect it.")

    store = MemoryStore.open_or_create(store_path)
    from . import distill as distill_mod
    distill_mod.auto_distill(store)

    server = Server("claude-memory-graph")
    server.instructions = instructions
    tools.register(server, store)

    # stateless + JSON responses: every client request is self-contained, so
    # any number of clients can share the endpoint with nothing to resume.
    manager = StreamableHTTPSessionManager(app=server, json_response=True,
                                           stateless=True)

    @contextlib.asynccontextmanager
    async def lifespan(app):
        async with manager.run():
            log.info("memory-graph serving at http://%s:%d/mcp (%s)",
                     host, port, "token required" if token else "loopback, no token")
            yield
        store.save()
        log.info("store saved; goodbye")

    app = Starlette(routes=[Mount("/mcp", app=manager.handle_request)],
                    lifespan=lifespan)
    uvicorn.run(_BearerAuth(app, token), host=host, port=port, log_level="warning")
