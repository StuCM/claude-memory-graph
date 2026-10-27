"""Remote MCP server — the same memory over streamable HTTP.

One long-running process owns the store and serves every client, which is
strictly SAFER than one stdio server per session: a single process means no
last-writer-wins between concurrent sessions. Hosted somewhere always-on it
is the one memory every machine and app shares (docs/REMOTE.md):

- **Claude Code machines** (terminal, IDE, or the desktop app's Code tab)
  point the plugin at it (`server` + `server_token`
  in /config). Their local MCP server becomes a proxy to this one, and the
  ambient gate reads a replica of the graph it downloads from
  `/api/graph.nq`. Their context logs stay local and reach the graph
  through `/api/distill`.
- **A browser** — the home page is a chat (chat.py): sign in with the
  password and ask questions; Claude answers from the memory, read-only.
  On a handover share, that is all a colleague needs.
- **Chats in claude.ai and the phone and desktop apps** add it as a custom
  connector (tools only: chats have no hooks, so nothing is injected).
  Connectors can only do OAuth, so with `--public-url` set the server is
  also a single-owner OAuth authorization server (auth.py): a connector is
  let in only after the owner types the password on the server's /login
  page.

Every route but /healthz needs a credential: the static bearer token, or
an OAuth access token. Binding beyond localhost refuses to start without a
token. Serve it over HTTPS (a reverse proxy such as Caddy, or a tunnel) —
the token must never travel in clear text.

Connect a Claude Code machine without the plugin:
    claude mcp add --transport http memory-graph https://host/mcp \\
        --header "Authorization: Bearer <token>"
"""

import contextlib
import gzip
import hashlib
import json
import logging
import os
import tempfile
import time
from pathlib import Path

from mcp.server import Server

from . import tools
from .store import MemoryStore

log = logging.getLogger(__name__)

MAX_UPLOAD = 20 * 1024 * 1024        # /api/distill body limit


# ------------------------------------------------------------- the API

def graph_bytes(store: MemoryStore) -> bytes:
    """The store as NQuads — what a client's ambient gate reads. Dumped from
    memory, so it is current even between saves (and on a read-only share)."""
    import io
    import pyoxigraph as ox
    out = io.BytesIO()
    store._store.dump(out, ox.RdfFormat.N_QUADS)
    return out.getvalue()


def distill_upload(store: MemoryStore, payload: dict) -> dict:
    """Run the mechanical distill over context files a client uploaded.

    The files are written to a scratch directory with their ages restored,
    the ordinary distill runs over them against THIS store, and each file's
    outcome goes back so the client can do the same to its own copy:
    `archived` (mark distilled, move to archive/), `split` (archive the
    original, keep only `text`, the residue) or `kept` (leave it)."""
    from . import distill as distill_mod

    files = payload.get("files") or []
    if not isinstance(files, list):
        raise ValueError("files must be a list")
    with tempfile.TemporaryDirectory(prefix="mg-distill-") as tmp:
        directory = Path(tmp)
        names = []
        for item in files:
            name = str(item.get("name", ""))
            if (not name.endswith(".md") or "/" in name or "\\" in name
                    or name.startswith(".")):
                raise ValueError(f"bad context file name: {name!r}")
            path = directory / name
            path.write_text(str(item.get("text", "")), encoding="utf-8")
            mtime = time.time() - max(0.0, float(item.get("age_seconds", 0)))
            os.utime(path, (mtime, mtime))
            names.append(name)

        report = distill_mod.distill(
            store, directory=directory, project=payload.get("project") or None,
            dry_run=bool(payload.get("dry_run")), keep=bool(payload.get("keep")),
            retire_after_days=payload.get("retire_after_days"))

        outcomes = {}
        split = {name for name, _ in report.split}
        for name in names:
            if name in split:
                outcomes[name] = {"outcome": "split",
                                  "text": (directory / name).read_text(encoding="utf-8")}
            elif not (directory / name).exists():
                outcomes[name] = {"outcome": "archived"}
            else:
                outcomes[name] = {"outcome": "kept"}
    return {"report": report.render(), "files": outcomes,
            "stored": len(report.stored), "linked": report.linked,
            "residue": len(report.residue)}


def api_routes(store: MemoryStore, read_only: bool):
    from starlette.requests import Request
    from starlette.responses import JSONResponse, Response
    from starlette.routing import Route

    async def graph(request: Request):
        body = graph_bytes(store)
        etag = '"' + hashlib.sha256(body).hexdigest()[:32] + '"'
        if request.headers.get("if-none-match") == etag:
            return Response(status_code=304, headers={"ETag": etag})
        headers = {"ETag": etag, "Cache-Control": "no-cache"}
        if "gzip" in request.headers.get("accept-encoding", ""):
            body = gzip.compress(body, 6)
            headers["Content-Encoding"] = "gzip"
        return Response(body, media_type="application/n-quads", headers=headers)

    async def distill(request: Request):
        if read_only:
            return JSONResponse({"error": "read-only server"}, status_code=403)
        raw = await request.body()
        if len(raw) > MAX_UPLOAD:
            return JSONResponse({"error": "upload too large"}, status_code=413)
        try:
            result = distill_upload(store, json.loads(raw))
        except (ValueError, TypeError, AttributeError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        log.info("remote distill: %d node(s), %d link(s), %d residue",
                 result["stored"], result["linked"], result["residue"])
        return JSONResponse(result)

    return [("/api/graph.nq", graph, ["GET"]), ("/api/distill", distill, ["POST"])]


# ------------------------------------------------------------- auth

class _RequireAuth:
    """Rejects requests without a valid credential. `scope["user"]` is set
    by Starlette's AuthenticationMiddleware from the bearer header."""

    def __init__(self, app, metadata_url: str | None):
        self.app = app
        self.metadata_url = metadata_url

    async def __call__(self, scope, receive, send):
        from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
        if scope["type"] == "http" and not isinstance(scope.get("user"), AuthenticatedUser):
            from starlette.responses import PlainTextResponse
            challenge = 'Bearer error="invalid_token"'
            if self.metadata_url:
                challenge += f', resource_metadata="{self.metadata_url}"'
            await PlainTextResponse("unauthorized", status_code=401,
                                    headers={"WWW-Authenticate": challenge})(scope, receive, send)
            return
        await self.app(scope, receive, send)


def chat_identity(store: MemoryStore) -> tuple[str, str]:
    """(page title, scope sentence for the system prompt). A handover export
    carries share.json naming its project; anything else is the whole memory."""
    title = os.environ.get("MEMORY_GRAPH_CHAT_TITLE", "")
    try:
        meta = json.loads((Path(store._data_path).parent / "share.json").read_text())
        project = str(meta["project"])
    except (OSError, ValueError, KeyError, TypeError):
        return title or "Memory", ""
    return (title or f"{project} — handover memory",
            f"This copy holds only what relates to the project “{project}”, shared "
            f"for a handover on {meta.get('created', 'an unknown date')}. The reader is "
            "a colleague picking the work up; answer for them.")


def build_app(store: MemoryStore, instructions: str, token: str = "",
              read_only: bool = False, public_url: str = "", password: str = "",
              auth_path: Path | None = None, chat=True):
    """The ASGI app, separate from serve() so tests can drive it in-process."""
    from mcp.server.auth.middleware.bearer_auth import BearerAuthBackend
    from mcp.server.auth.routes import (build_resource_metadata_url, create_auth_routes,
                                        create_protected_resource_routes)
    from mcp.server.auth.settings import ClientRegistrationOptions, RevocationOptions
    from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
    from pydantic import AnyHttpUrl
    from starlette.applications import Starlette
    from starlette.middleware import Middleware
    from starlette.middleware.authentication import AuthenticationMiddleware
    from starlette.responses import PlainTextResponse
    from starlette.routing import Mount, Route

    from .auth import SCOPE, OwnerAuth, login_routes

    server = Server("claude-memory-graph", instructions=instructions,
                    **tools.handlers(store, read_only=read_only))
    # stateless + JSON responses: every client request is self-contained, so
    # any number of clients can share the endpoint with nothing to resume.
    manager = StreamableHTTPSessionManager(app=server, json_response=True, stateless=True)

    public_url = public_url.rstrip("/")
    auth = OwnerAuth(auth_path or Path(tempfile.mkdtemp()) / "oauth.json",
                     token, password, public_url or "http://localhost")
    protect = bool(token or public_url)
    metadata = (str(build_resource_metadata_url(AnyHttpUrl(public_url + "/mcp")))
                if public_url else None)

    def guarded(app):
        return _RequireAuth(app, metadata) if protect else app

    def endpoint(handler):
        # a Starlette Route given a plain ASGI app needs request→response wrapping
        from starlette.routing import request_response
        return guarded(request_response(handler))

    routes = [Route("/healthz", lambda request: PlainTextResponse("ok"))]
    if public_url:
        routes += create_auth_routes(
            auth, AnyHttpUrl(public_url),
            client_registration_options=ClientRegistrationOptions(
                enabled=True, valid_scopes=[SCOPE], default_scopes=[SCOPE]),
            revocation_options=RevocationOptions(enabled=True))
        routes += create_protected_resource_routes(
            AnyHttpUrl(public_url + "/mcp"), [AnyHttpUrl(public_url)],
            scopes_supported=[SCOPE], resource_name="Memory graph")
        routes += login_routes(auth)
    routes += [Route(path, endpoint(handler), methods=methods)
               for path, handler, methods in api_routes(store, read_only)]
    if chat:
        from .chat import ChatService, chat_routes
        title, scope = chat_identity(store)
        routes += chat_routes(chat if isinstance(chat, ChatService)
                              else ChatService(store, title=title, scope=scope), auth)
    routes.append(Mount("/mcp", app=guarded(manager.handle_request)))

    @contextlib.asynccontextmanager
    async def lifespan(app):
        async with manager.run():
            yield
        if not read_only:
            store.save()
        log.info("store saved; goodbye")

    app = Starlette(routes=routes, lifespan=lifespan,
                    middleware=[Middleware(AuthenticationMiddleware,
                                           backend=BearerAuthBackend(auth))])
    app.state.auth = auth
    return app


def serve(store_path, instructions: str, host: str = "127.0.0.1",
          port: int = 8848, token: str = "", read_only: bool = False,
          public_url: str = "", password: str = "", chat: bool = True) -> None:
    import uvicorn

    loopback = host in ("127.0.0.1", "::1", "localhost")
    if not loopback and not token:
        raise SystemExit(
            "Refusing to bind beyond localhost without a token. Pass --token "
            "(or set MEMORY_GRAPH_TOKEN) — this is your memory; protect it.")
    if public_url and not token:
        raise SystemExit("--public-url needs --token: the OAuth login checks "
                         "--password, or the token when no password is set.")
    if public_url and not public_url.startswith("https://"):
        log.warning("--public-url is not https: claude.ai connectors need HTTPS, "
                    "and credentials would travel in clear text")

    store = MemoryStore.open_or_create(store_path)
    if not read_only:
        from . import distill as distill_mod
        distill_mod.auto_distill(store)

    from .hookcore.state import state_home
    app = build_app(store, instructions, token=token, read_only=read_only,
                    public_url=public_url, password=password,
                    auth_path=state_home() / "oauth.json", chat=chat)
    log.warning("memory-graph serving %s at http://%s:%d/mcp (%s%s%s)",
                store_path, host, port,
                "token required" if token else "loopback, no token",
                f"; connectors sign in at {public_url}" if public_url else "",
                ", read-only" if read_only else "")
    # behind a TLS proxy the scheme and host come from its forwarded headers
    uvicorn.run(app, host=host, port=port, log_level="warning",
                proxy_headers=True, forwarded_allow_ips="*")
