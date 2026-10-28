"""Hosted memory: one server, reached by Claude Code machines (static token,
proxy, replica, remote distill) and by the Claude apps (OAuth). Everything
here runs a real server on a real port — the point is the wire."""

import asyncio
import base64
import hashlib
import os
import secrets
import socket
import sys
import threading
import time
from urllib.parse import parse_qs, urlparse

import httpx2 as httpx
import pytest
import uvicorn

from claude_memory_graph import remote
from claude_memory_graph.auth import MAX_FAILURES, OwnerAuth
from claude_memory_graph.http_server import build_app
from claude_memory_graph.store import MemoryStore

TOKEN = "static-" + "x" * 24
PASSWORD = "correct horse battery"

LOG = """---
created: 2026-07-06T14:00
distilled: false
summary: "s"
---

## Key Points

- [14:32] Decision: Use varnish for tiles
  rationale: tile server too slow
  affects: Project/quartz
"""


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def server(tmp_path):
    store = MemoryStore.open_or_create(tmp_path / "server-store")
    store.create_resource("Project", {"name": "quartz"})
    store.save()
    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    app = build_app(store, "test memory", token=TOKEN, public_url=base,
                    password=PASSWORD, auth_path=tmp_path / "oauth.json")
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()
    for _ in range(100):
        try:
            if httpx.get(base + "/healthz").status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.05)
    yield type("Server", (), {"base": base, "store": store, "app": app, "tmp": tmp_path})
    srv.should_exit = True
    thread.join(5)


@pytest.fixture
def remote_env(server, monkeypatch, tmp_path):
    monkeypatch.setenv(remote.SERVER_ENV, server.base + "/mcp")
    monkeypatch.setenv(remote.TOKEN_ENV, TOKEN)
    ctx = tmp_path / "ctx"
    ctx.mkdir()
    monkeypatch.setenv("CLAUDE_CONTEXT_DIR", str(ctx))
    return ctx


def _bearer(token=TOKEN):
    return {"Authorization": f"Bearer {token}"}


# ------------------------------------------------------------------ access

def test_everything_but_health_needs_a_credential(server):
    assert httpx.get(server.base + "/healthz").status_code == 200
    for path in ("/api/graph.nq", "/mcp/"):
        r = httpx.get(server.base + path)
        assert r.status_code == 401
        assert "resource_metadata" in r.headers["www-authenticate"]
    assert httpx.post(server.base + "/api/distill", json={"files": []},
                      headers=_bearer("wrong")).status_code == 401


def test_graph_download_with_etag(server):
    r = httpx.get(server.base + "/api/graph.nq", headers=_bearer())
    assert r.status_code == 200 and b"quartz" in r.content
    again = httpx.get(server.base + "/api/graph.nq",
                      headers={**_bearer(), "If-None-Match": r.headers["etag"]})
    assert again.status_code == 304


# ------------------------------------------------------------------- OAuth

def _pkce():
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
    return verifier, challenge.rstrip(b"=").decode()


def _connect_app(server, password=PASSWORD):
    """What claude.ai does: discover, register, authorize, (owner logs in),
    exchange the code. Returns (client, token response, login response)."""
    meta = httpx.get(server.base + "/.well-known/oauth-authorization-server").json()
    resource = httpx.get(server.base + "/.well-known/oauth-protected-resource/mcp").json()
    assert resource["authorization_servers"][0].rstrip("/") == server.base
    redirect = "https://claude.ai/api/mcp/auth_callback"
    client = httpx.post(meta["registration_endpoint"], json={
        "client_name": "Claude", "redirect_uris": [redirect],
        "grant_types": ["authorization_code", "refresh_token"],
        "token_endpoint_auth_method": "none"}).json()
    verifier, challenge = _pkce()
    r = httpx.get(meta["authorization_endpoint"], params={
        "response_type": "code", "client_id": client["client_id"], "redirect_uri": redirect,
        "code_challenge": challenge, "code_challenge_method": "S256", "state": "st8"})
    assert r.status_code == 302
    login_url = r.headers["location"]
    assert login_url.startswith(server.base + "/login?request=")
    page = httpx.get(login_url)
    assert page.status_code == 200 and "Claude" in page.text
    request_id = parse_qs(urlparse(login_url).query)["request"][0]
    login = httpx.post(server.base + "/login", data={"request": request_id, "password": password})
    if login.status_code != 302:
        return client, None, login
    back = urlparse(login.headers["location"])
    assert f"{back.scheme}://{back.netloc}{back.path}" == redirect
    query = parse_qs(back.query)
    assert query["state"] == ["st8"]
    tokens = httpx.post(meta["token_endpoint"], data={
        "grant_type": "authorization_code", "code": query["code"][0],
        "redirect_uri": redirect, "client_id": client["client_id"],
        "code_verifier": verifier}).json()
    return client, tokens, login


def test_app_connects_through_owner_login(server):
    client, tokens, _ = _connect_app(server)
    assert tokens["token_type"].lower() == "bearer"
    r = httpx.get(server.base + "/api/graph.nq", headers=_bearer(tokens["access_token"]))
    assert r.status_code == 200

    refreshed = httpx.post(server.base + "/token", data={
        "grant_type": "refresh_token", "refresh_token": tokens["refresh_token"],
        "client_id": client["client_id"]}).json()
    assert httpx.get(server.base + "/api/graph.nq",
                     headers=_bearer(refreshed["access_token"])).status_code == 200
    # rotation: the old access token died with its refresh token
    assert httpx.get(server.base + "/api/graph.nq",
                     headers=_bearer(tokens["access_token"])).status_code == 401


def test_wrong_password_gets_no_code_and_locks_out(server):
    _, tokens, login = _connect_app(server, password="guess")
    assert tokens is None and login.status_code == 401
    for _ in range(MAX_FAILURES):
        _connect_app(server, password="guess")
    _, tokens, login = _connect_app(server)            # even the right one, now
    assert tokens is None and login.status_code == 429


def test_tokens_survive_restart_and_are_stored_hashed(server):
    _, tokens, _ = _connect_app(server)
    raw = (server.tmp / "oauth.json").read_text()
    assert tokens["access_token"] not in raw and tokens["refresh_token"] not in raw
    reborn = OwnerAuth(server.tmp / "oauth.json", TOKEN, PASSWORD, server.base)
    assert asyncio.run(reborn.load_access_token(tokens["access_token"])) is not None


# --------------------------------------------- Claude Code machines (remote mode)

def test_replica_fetch_then_not_modified_then_offline(server, remote_env, monkeypatch):
    folder = remote.fetch_replica(force=True)
    assert b"quartz" in (folder / "graph.nq").read_bytes()
    assert remote.fetch_replica(force=True) == folder          # 304: kept
    monkeypatch.setenv(remote.SERVER_ENV, "http://127.0.0.1:9")  # nothing listens
    assert remote.fetch_replica(force=True) == folder          # stale beats nothing


def test_remote_distill_promotes_on_server_and_archives_locally(server, remote_env):
    log = remote_env / "quartz__2026-07-06_14-00.md"
    log.write_text(LOG)
    then = time.time() - 5 * 86400
    os.utime(log, (then, then))
    report = remote.remote_distill()
    assert "nodes: 1" in report
    assert server.store.find_resource("Decision", "Use varnish for tiles") is not None
    assert not log.exists()
    archived = remote_env / "archive" / log.name
    assert "distilled: true" in archived.read_text()


def test_remote_distill_keeps_a_live_log(server, remote_env):
    log = remote_env / "quartz__2026-07-06_14-00.md"
    log.write_text(LOG)                                   # just written: a live session
    remote.remote_distill(keep=True, retire_after_days=2)
    assert log.exists() and log.read_text() == LOG
    assert server.store.find_resource("Decision", "Use varnish for tiles") is not None


def test_distill_rejects_path_tricks(server):
    r = httpx.post(server.base + "/api/distill", headers=_bearer(),
                   json={"files": [{"name": "../escape.md", "text": "x"}]})
    assert r.status_code == 400


def test_hook_runner_reads_the_replica(server, remote_env, monkeypatch):
    from claude_memory_graph import hookrun
    monkeypatch.delenv("MEMORY_GRAPH_PATH", raising=False)
    reply = hookrun.run({"event": "SessionStart", "payload": {"cwd": "/w/quartz"},
                         "enabled": [], "remote": {"url": server.base, "token": TOKEN,
                                                   "lookups": "replica"}})
    assert reply["errors"] == []
    assert os.environ["MEMORY_GRAPH_PATH"] == str(remote.replica_dir())
    assert (remote.replica_dir() / "graph.nq").exists()


def _server_lookups(server, monkeypatch, tmp_path):
    """A client in server-lookup mode: its own state home, no local graph."""
    from claude_memory_graph.gate import runtime
    from claude_memory_graph.hookcore import state
    monkeypatch.setenv(state.STATE_HOME_ENV, str(tmp_path / "client-state"))
    monkeypatch.setenv("MEMORY_GRAPH_PATH", str(tmp_path / "no-local-graph"))
    monkeypatch.setenv(runtime.SERVER_LOOKUPS_ENV, "")   # hookrun sets it; restored after
    monkeypatch.setattr(runtime, "_config", dict(runtime._DEFAULTS))
    return {"url": server.base, "token": TOKEN}


def test_server_lookups_answer_without_a_local_graph(server, remote_env, monkeypatch, tmp_path):
    from claude_memory_graph import hookrun
    store = server.store
    _, decision = store.create_resource("Decision", {"name": "Use varnish for tiles",
                                                     "rationale": "tile server too slow"})
    quartz = next(iter(store.query(
        'SELECT ?p WHERE { GRAPH ?g { ?p a mem:Project ; mem:name "quartz" } }')))["p"]
    store.create_link(decision, quartz, "affects", {})
    store.save()
    remote_cfg = _server_lookups(server, monkeypatch, tmp_path)
    request = {"event": "UserPromptSubmit", "enabled": ["memory-recall"], "remote": remote_cfg,
               "payload": {"prompt": "Back on it. Which decisions affect quartz? Then deploy.",
                           "cwd": "/w/quartz", "session_id": "s1"},
               "core": {"project": "quartz", "session_id": "s1"}}
    reply = hookrun.run(request)
    assert reply["errors"] == []
    assert "Memory answers" in reply["output"] and "Use varnish for tiles" in reply["output"]
    assert not (tmp_path / "no-local-graph").exists()           # nothing opened locally
    assert not remote.replica_dir().exists()                    # nothing downloaded
    # the server's log lines landed in the CLIENT's log
    log = (tmp_path / "client-state" / "injections.jsonl").read_text()
    assert '"kind": "answer"' in log
    # session state came back: the same question isn't answered twice
    again = hookrun.run({**request, "state": reply["state"]})
    assert "Memory answers" not in again["output"]
    # the client's settings travel with the call, and don't stick on the server
    from claude_memory_graph.gate import runtime
    off = hookrun.run({**request, "gate": {"ANSWER_QUESTIONS": False}})
    assert "Memory answers" not in off["output"]
    # (client and server share this test process: undo the client's own override)
    monkeypatch.setattr(runtime, "_config", dict(runtime._DEFAULTS))
    assert "Memory answers" in hookrun.run(request)["output"]


def test_server_lookups_fail_open(server, remote_env, monkeypatch, tmp_path):
    from claude_memory_graph import hookrun
    remote_cfg = {**_server_lookups(server, monkeypatch, tmp_path), "url": "http://127.0.0.1:9"}
    reply = hookrun.run({"event": "UserPromptSubmit", "enabled": ["memory-recall"],
                         "remote": remote_cfg, "payload": {"prompt": "which decisions affect quartz?"},
                         "core": {"project": "quartz", "session_id": "s"}})
    assert reply["output"] == "" and reply["errors"]


def test_server_runs_only_graph_reading_hooks(server):
    r = httpx.post(server.base + "/api/hook", headers=_bearer(),
                   json={"extension": "context-counter", "event": "Stop"})
    assert r.status_code == 403
    assert httpx.post(server.base + "/api/hook", json={}).status_code == 401


def test_review_reads_gaps_from_the_server(server, remote_env, monkeypatch, tmp_path):
    from claude_memory_graph.gate import review
    _server_lookups(server, monkeypatch, tmp_path)
    monkeypatch.setenv("MEMORY_GRAPH_LOOKUPS", "server")
    gaps = review._gaps()
    assert ("Project", "quartz") in [tuple(o) for o in gaps.orphans]


def test_proxy_reads_and_writes_the_server(server, remote_env):
    """The plugin's stdio MCP server, in remote mode, end to end."""
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    async def scenario():
        params = StdioServerParameters(command=sys.executable,
                                       args=["-m", "claude_memory_graph"], env=dict(os.environ))
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                names = {t.name for t in (await session.list_tools()).tools}
                assert {"memory_store_resource", "memory_recall"} <= names
                stored = await session.call_tool("memory_store_resource", {
                    "model": "Decision",
                    "properties": {"name": "Cache tiles at the edge",
                                   "rationale": "phone-tested"}})
                assert not stored.is_error, stored.content[0].text
                recalled = await session.call_tool("memory_recall", {
                    "model": "Project", "name": "quartz"})
                assert not recalled.is_error

    asyncio.run(asyncio.wait_for(scenario(), 60))
    assert server.store.find_resource("Decision", "Cache tiles at the edge") is not None


def test_doctor_checks_the_server(server, remote_env):
    from claude_memory_graph.gate.doctor import report
    text = report()
    assert "reachable, token accepted" in text and "graph is EMPTY" not in text


def test_doctor_names_a_wrong_token(server, remote_env, monkeypatch):
    from claude_memory_graph.gate.doctor import report
    monkeypatch.setenv(remote.TOKEN_ENV, "wrong")
    assert "HTTP 401" in report()


def test_server_rebuilds_the_gate_after_a_write(server, tmp_path, monkeypatch):
    from claude_memory_graph.hookcore import state
    from claude_memory_graph.http_server import warm_gate
    monkeypatch.setenv(state.STATE_HOME_ENV, str(tmp_path / "server-state"))
    warm_gate(server.store)
    assert warm_gate(server.store) is False            # nothing changed: nothing to do
    server.store.create_resource("Decision", {"name": "Warm the gate after writes"})
    server.store.save()
    assert warm_gate(server.store) is True             # rebuilt before any prompt asks
