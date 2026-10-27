"""Remote mode: this machine's memory lives on a server (docs/REMOTE.md).

Set MEMORY_GRAPH_SERVER (the plugin's `server` option) and
MEMORY_GRAPH_TOKEN (`server_token`) and three things change, nothing else:

- the local MCP server becomes a **proxy**: every tool call goes to the
  server, so reads and writes from every machine land in one store;
- the ambient gate reads a **replica** — the server's graph.nq, fetched
  with an ETag at session start and at most once a minute after, kept in
  the state home. A stale replica is still a fine replica: injection is a
  best-effort read, and the gate fails open if the server is unreachable;
- **distill** uploads this machine's context logs to the server
  (/api/distill), which promotes them into the one store, and applies the
  outcome (archive / split / keep) to the local files. The logs never
  leave this machine otherwise.

Only the standard library is used on the hook path (fetch_replica), so a
prompt never waits on importing an HTTP client.
"""

import gzip
import json
import logging
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

log = logging.getLogger(__name__)

SERVER_ENV = "MEMORY_GRAPH_SERVER"
TOKEN_ENV = "MEMORY_GRAPH_TOKEN"
REPLICA_MIN_INTERVAL = 60            # seconds between replica checks mid-session


def server_config() -> tuple[str, str] | None:
    """(base url, token) when remote mode is on. Accepts the URL with or
    without its /mcp suffix."""
    url = os.environ.get(SERVER_ENV, "").strip().rstrip("/")
    if not url:
        return None
    if url.endswith("/mcp"):
        url = url[:-4]
    return url, os.environ.get(TOKEN_ENV, "").strip()


def _request(path: str, *, data: bytes | None = None, headers: dict | None = None,
             timeout: float = 10.0):
    base, token = server_config()
    req = urllib.request.Request(base + path, data=data, headers={
        "Authorization": f"Bearer {token}", "User-Agent": "claude-memory-graph",
        **(headers or {})})
    return urllib.request.urlopen(req, timeout=timeout)


# ------------------------------------------------------------------ replica

def replica_dir() -> Path:
    from .hookcore.state import state_home
    return state_home() / "replica"


def fetch_replica(force: bool = False, timeout: float = 2.0) -> Path | None:
    """Bring the local replica up to date and return its folder (a store
    folder holding graph.nq), or None when there is no usable replica.
    Never raises: an unreachable server leaves the last replica in use."""
    if server_config() is None:
        return None
    folder = replica_dir()
    nq, meta_path = folder / "graph.nq", folder / "replica.json"
    try:
        meta = json.loads(meta_path.read_text())
    except (OSError, ValueError):
        meta = {}
    if not force and nq.exists() and time.time() - meta.get("checked", 0) < REPLICA_MIN_INTERVAL:
        return folder
    headers = {"Accept-Encoding": "gzip"}
    if nq.exists() and meta.get("etag"):
        headers["If-None-Match"] = meta["etag"]
    try:
        with _request("/api/graph.nq", headers=headers, timeout=timeout) as resp:
            body = resp.read()
            if resp.headers.get("Content-Encoding") == "gzip":
                body = gzip.decompress(body)
            folder.mkdir(parents=True, exist_ok=True)
            tmp = nq.with_suffix(".tmp")
            tmp.write_bytes(body)
            tmp.replace(nq)
            meta = {"etag": resp.headers.get("ETag", ""), "checked": time.time(),
                    "fetched": time.time()}
    except urllib.error.HTTPError as exc:
        if exc.code == 304:
            meta["checked"] = time.time()
        else:
            meta["error"] = f"HTTP {exc.code}"
            log.warning("replica fetch failed: HTTP %s", exc.code)
    except (OSError, ValueError) as exc:
        meta["error"] = str(exc)[:200]
        log.warning("replica fetch failed: %s", exc)
    else:
        meta.pop("error", None)
    try:
        folder.mkdir(parents=True, exist_ok=True)
        meta_path.write_text(json.dumps(meta))
    except OSError:
        pass
    return folder if nq.exists() else None


# ------------------------------------------------------------------ distill

def remote_distill(directory: Path | None = None, project: str | None = None,
                   dry_run: bool = False, keep: bool = False,
                   retire_after_days: float | None = None, timeout: float = 60.0) -> str:
    """The distill, with the graph half on the server. Returns the report."""
    from . import distill as distill_mod
    from .context_entries import undistilled_files

    directory = directory or distill_mod.context_dir()
    paths = list(undistilled_files(directory, project)) if directory.exists() else []
    if not paths:
        return "files: 0 · nothing to distill"
    now = time.time()
    payload = {"files": [{"name": p.name, "text": p.read_text(encoding="utf-8"),
                          "age_seconds": max(0.0, now - p.stat().st_mtime)} for p in paths],
               "project": project, "dry_run": dry_run, "keep": keep,
               "retire_after_days": retire_after_days}
    with _request("/api/distill", data=json.dumps(payload).encode(),
                  headers={"Content-Type": "application/json"}, timeout=timeout) as resp:
        result = json.loads(resp.read())

    if not dry_run:
        by_name = {p.name: p for p in paths}
        for name, outcome in result.get("files", {}).items():
            path = by_name.get(name)
            if path is None or not path.exists():
                continue
            if outcome.get("outcome") == "archived":
                distill_mod._mark_distilled(path)
                distill_mod._archive(path)
            elif outcome.get("outcome") == "split" and "text" in outcome:
                distill_mod._archive(path)
                path.write_text(outcome["text"], encoding="utf-8")
    return result.get("report", "")


def auto_distill_remote() -> None:
    """auto_distill's remote twin, run when the proxy starts. Fail open."""
    if os.environ.get("MEMORY_GRAPH_AUTO_DISTILL", "1").lower() in ("0", "false", "off"):
        return
    try:
        from .gate.runtime import config
        report = remote_distill(keep=True, retire_after_days=config()["DISTILL_AFTER_DAYS"],
                                timeout=15.0)
        log.info("remote auto-distill: %s", report.splitlines()[0] if report else "")
    except Exception as exc:  # noqa: BLE001 — never block a session starting
        log.warning("remote auto-distill skipped: %s", exc)


# ------------------------------------------------------------------ proxy

async def run_proxy(server_name: str, version: str, instructions: str) -> None:
    """Serve MCP over stdio, forwarding every tool to the remote server.

    memory_distill is the exception: the context logs it reads are on this
    machine, so it runs here and sends only the files to the server."""
    import contextlib

    import httpx2 as httpx
    from mcp import ClientSession, types
    from mcp.client.streamable_http import streamable_http_client
    from mcp.server import Server
    from mcp.server.stdio import stdio_server

    base, token = server_config()
    auto_distill_remote()

    @contextlib.asynccontextmanager
    async def remote():
        async with httpx.AsyncClient(headers={"Authorization": f"Bearer {token}"},
                                     timeout=httpx.Timeout(30.0, read=120.0)) as http:
            async with streamable_http_client(f"{base}/mcp", http_client=http) as streams:
                async with ClientSession(streams[0], streams[1]) as session:
                    await session.initialize()
                    yield session

    def unreachable(exc: BaseException) -> types.CallToolResult:
        return types.CallToolResult(is_error=True, content=[types.TextContent(
            type="text", text=f"memory server {base} unreachable ({type(exc).__name__}: "
                              f"{exc}). Nothing was read or written.")])

    async def on_list_tools(ctx, params) -> types.ListToolsResult:
        try:
            async with remote() as session:
                return await session.list_tools()
        except Exception as exc:  # noqa: BLE001
            log.warning("list_tools: server unreachable: %s", exc)
            return types.ListToolsResult(tools=[])

    async def on_call_tool(ctx, params) -> types.CallToolResult:
        args = params.arguments or {}
        if params.name == "memory_distill":
            import anyio
            try:
                report = await anyio.to_thread.run_sync(lambda: remote_distill(
                    project=args.get("project"), dry_run=bool(args.get("dry_run"))))
            except Exception as exc:  # noqa: BLE001
                return unreachable(exc)
            return types.CallToolResult(content=[types.TextContent(type="text", text=report)])
        try:
            async with remote() as session:
                return await session.call_tool(params.name, args)
        except Exception as exc:  # noqa: BLE001
            return unreachable(exc)

    server = Server(server_name, version=version,
                    instructions=instructions + f" (This memory lives on {base}.)",
                    on_list_tools=on_list_tools, on_call_tool=on_call_tool)
    log.info("memory-graph proxying to %s", base)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())
