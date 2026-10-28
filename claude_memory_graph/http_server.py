"""Remote MCP server — the same memory over streamable HTTP.

One long-running process owns the store and serves every client, which is
strictly SAFER than one stdio server per session: a single process means no
last-writer-wins between concurrent sessions. Hosted somewhere always-on it
is the one memory every machine and app shares (docs/REMOTE.md):

- **Claude Code machines** (terminal, IDE, or the desktop app's Code tab)
  point the plugin at it (`server` + `server_token`
  in /config). Their local MCP server becomes a proxy to this one, and the
  ambient gate's graph reads run here (`/api/hook`, `/api/gaps`), so the
  machine holds no copy of the graph; or, with lookups set to "local copy",
  the gate reads a replica it downloads from `/api/graph.nq`. Their context
  logs stay local and reach the graph through `/api/distill`.
- **A browser**: the home page (chat.py) shows how to connect from your own
  Claude, and links to Settings. With ANTHROPIC_API_KEY set it is a chat
  instead, billed to that key.
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
import threading
import time
from pathlib import Path

import anyio
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

    async def hook(request: Request):
        try:
            payload = json.loads(await request.body())
            if not isinstance(payload, dict):
                raise ValueError("expected an object")
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        try:
            reply = await anyio.to_thread.run_sync(run_client_hook, store, payload)
        except PermissionError as exc:
            return JSONResponse({"error": str(exc)}, status_code=403)
        return JSONResponse(reply)

    async def gaps(request: Request):
        from dataclasses import asdict
        from .gaps import analyse
        def report():
            with _gate_lock:
                return asdict(analyse(store, limit=5))
        return JSONResponse(await anyio.to_thread.run_sync(report))

    async def ping(request: Request):
        # behind the credential check, so a 200 also means the token is good;
        # "lookups" tells a client this server can run its gate (/api/hook)
        return JSONResponse({"ok": True, "lookups": True})

    return [("/api/graph.nq", graph, ["GET"]), ("/api/distill", distill, ["POST"]),
            ("/api/hook", hook, ["POST"]), ("/api/gaps", gaps, ["GET"]),
            ("/api/ping", ping, ["GET"])]


_gate_lock = threading.Lock()


WARM_EVERY = 2.0   # seconds between checks for a changed graph


def warm_gate(store: MemoryStore) -> bool:
    """Rebuild the gate's indexes if the graph changed since they were built;
    True if it rebuilt. Rebuilding costs seconds on a big graph (3.6s at
    10,000 memories), so the server does it right after a write rather than
    leaving it to the next prompt, which would wait on it or time out."""
    from . import planner
    from .gate import recall, runtime
    with _gate_lock:
        runtime.use_live_store(store)
        try:
            key = recall._index_key()
            if key is None or recall._memo.get("key") == key:
                return False
            recall.gate_index("", lambda: store)
            planner.entity_index(store)
            return True
        finally:
            runtime.use_live_store(None)


def _keep_gate_warm(store: MemoryStore, stop: threading.Event) -> None:
    while not stop.wait(WARM_EVERY):
        try:
            warm_gate(store)
        except Exception:  # noqa: BLE001 - a failed warm-up just means a cold prompt
            log.exception("gate warm-up failed")


def run_client_hook(store: MemoryStore, request: dict) -> dict:
    """Run one of a client's graph-reading gate hooks here, on the live
    store, so the client needs no copy of the graph (hookrun.SERVER_EVENTS).
    The client's settings apply to this call only; its log lines are
    returned rather than written, and the client writes them. One call at a
    time: the gate's config and index memo are process-wide."""
    from .gate import runtime
    from .hookcore.state import capture_jsonl
    from .hookrun import SERVER_EVENTS, run_extension
    name, event = request.get("extension"), request.get("event")
    if (name, event) not in SERVER_EVENTS:
        raise PermissionError(f"not a server-side hook: {name} {event}")
    state = dict(request.get("state") or {})
    global_state = dict(request.get("global") or {})
    with _gate_lock, capture_jsonl() as logs, runtime.overridden(request.get("gate") or {}):
        runtime.use_live_store(store)
        try:
            output = run_extension(name, event, dict(request.get("payload") or {}),
                                   dict(request.get("core") or {}), state, global_state)
        finally:
            runtime.use_live_store(None)
    return {"output": output, "state": state, "global": global_state, "logs": logs}


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
                              else ChatService(store, title=title, scope=scope), auth,
                              public_url=public_url, read_only=read_only)
    routes.append(Mount("/mcp", app=guarded(manager.handle_request)))

    @contextlib.asynccontextmanager
    async def lifespan(app):
        stop = threading.Event()
        threading.Thread(target=_keep_gate_warm, args=(store, stop), daemon=True,
                         name="gate-warm").start()
        async with manager.run():
            yield
        stop.set()
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
