"""This machine's own memory server: started on demand at session start,
one graph for every chat; the gate asks it and falls back to the disk; the
mod's memory_distill call is answered here and promoted by the server."""

import json
import os
import signal
import socket
import time

import pytest

from claude_memory_graph import hookrun, localserver
from claude_memory_graph.gate import runtime
from claude_memory_graph.store import MemoryStore

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
def machine(tmp_path, monkeypatch):
    """A machine with a graph on disk and no server running yet."""
    from claude_memory_graph.hookcore import state
    store = MemoryStore.open_or_create(tmp_path / "store")
    store.create_resource("Project", {"name": "quartz"})
    _, d = store.create_resource("Decision", {"name": "Use pyoxigraph over rdflib",
                                              "rationale": "rdflib too slow"})
    quartz = next(iter(store.query(
        'SELECT ?p WHERE { GRAPH ?g { ?p a mem:Project ; mem:name "quartz" } }')))["p"]
    store.create_link(d, quartz, "affects", {})
    store.save()
    ctx = tmp_path / "context"
    ctx.mkdir()
    monkeypatch.setenv("MEMORY_GRAPH_PATH", str(tmp_path / "store"))
    monkeypatch.setenv(state.STATE_HOME_ENV, str(tmp_path / "state"))
    monkeypatch.setenv("CLAUDE_CONTEXT_DIR", str(ctx))
    monkeypatch.setenv("MEMORY_GRAPH_AUTO_DISTILL", "0")     # the tests distill by hand
    for name in ("MEMORY_GRAPH_SERVER", "MEMORY_GRAPH_TOKEN", runtime.SERVER_LOOKUPS_ENV):
        monkeypatch.setenv(name, "")                         # hookrun sets them; restored after
    monkeypatch.setattr(runtime, "_config", dict(runtime._DEFAULTS))
    url = f"http://127.0.0.1:{_free_port()}"
    yield type("Machine", (), {"url": url, "tmp": tmp_path, "ctx": ctx})
    pid = localserver._ours().get("pid")
    if pid:
        try:
            os.kill(int(pid), signal.SIGTERM)
        except OSError:
            pass


def _prompt(url: str, prompt: str, state=None) -> dict:
    return hookrun.run({"event": "UserPromptSubmit", "enabled": ["memory-recall"],
                        "remote": {"url": url, "token": ""}, "state": state or {},
                        "payload": {"prompt": prompt, "cwd": "/w/quartz", "session_id": "s"},
                        "core": {"project": "quartz", "session_id": "s"}})


def test_is_local():
    assert localserver.is_local("http://127.0.0.1:8848")
    assert localserver.is_local("http://localhost:9/mcp")
    assert not localserver.is_local("https://memory.example.com")


def test_session_start_starts_one_server_that_later_chats_reuse(machine):
    assert localserver.running_version(machine.url) is None
    first = hookrun.run({"event": "SessionStart", "enabled": [], "payload": {"cwd": "/w/quartz"},
                         "remote": {"url": machine.url, "token": ""}})
    assert first["core"]["server"] == "started", first
    pid = localserver._ours()["pid"]
    again = hookrun.run({"event": "SessionStart", "enabled": [], "payload": {"cwd": "/w/quartz"},
                         "remote": {"url": machine.url, "token": ""}})
    assert again["core"]["server"] == "running"
    assert localserver._ours()["pid"] == pid                 # the same process


def test_a_server_from_an_older_version_is_replaced(machine, monkeypatch):
    assert localserver.ensure_running(machine.url) == "started"
    old = localserver._ours()["pid"]
    monkeypatch.setattr(localserver, "_version", lambda: "99.0.0")   # the plugin was updated
    assert localserver.ensure_running(machine.url).startswith("restarted for v99.0.0")
    assert localserver._ours()["pid"] != old


def test_someone_elses_server_is_left_alone(machine, monkeypatch):
    assert localserver.ensure_running(machine.url) == "started"
    localserver._pidfile().unlink()                          # e.g. systemd's, not ours
    monkeypatch.setattr(localserver, "_version", lambda: "99.0.0")
    assert localserver.ensure_running(machine.url) == "running"


def test_the_gate_asks_the_server_and_falls_back_to_the_disk(machine):
    q = "Back on it. Which decisions affect quartz? Then deploy."
    down = _prompt(machine.url, q)                           # nothing listening yet
    assert "Memory answers" in down["output"]                # read from disk instead
    assert any("read the graph from disk" in e for e in down["errors"])
    localserver.ensure_running(machine.url)
    up = _prompt(machine.url, q)
    assert up["errors"] == [] and "Memory answers" in up["output"]
    log = (machine.tmp / "state" / "injections.jsonl").read_text()
    assert log.count('"kind": "answer"') == 2                # both logged on this machine


def test_distill_reads_this_machines_logs_and_the_server_promotes(machine):
    localserver.ensure_running(machine.url)
    log = machine.ctx / "quartz__2026-07-06_14-00.md"
    log.write_text(LOG)
    then = time.time() - 5 * 86400                          # not a live log
    os.utime(log, (then, then))
    reply = hookrun.run({"event": "Distill", "payload": {"project": "quartz"},
                         "remote": {"url": machine.url, "token": ""}})
    assert reply["errors"] == [], reply
    assert "files: 1" in reply["output"]
    found = _prompt(machine.url, "why did we use varnish for tiles?")
    assert "Use varnish for tiles" in found["output"]
    assert not (machine.ctx / "quartz__2026-07-06_14-00.md").exists()   # archived here
    assert json.loads(json.dumps(reply))                     # plain JSON for the mod


def test_mcp_answers_at_its_address_without_a_token(machine):
    """What Claude Code connects to: <server>/mcp, with an empty bearer when no
    token is set — and /mcp/mcp for an address saved with its suffix."""
    import urllib.request
    localserver.ensure_running(machine.url)
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}).encode()
    for path in ("/mcp", "/mcp/mcp"):
        req = urllib.request.Request(machine.url + path, data=body, headers={
            "Authorization": "Bearer ", "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            assert resp.status == 200
            assert "memory_distill" in resp.read().decode()
