"""The server's chat: sign-in, the tool loop against the real store, and the
limits. Claude is replaced by a scripted client — these test our side of the
wire (what we send, what we run, what the browser gets), not the model."""

import json
from types import SimpleNamespace as NS

import pytest
from starlette.testclient import TestClient

from claude_memory_graph import chat as chat_mod
from claude_memory_graph.chat import ChatService
from claude_memory_graph.http_server import build_app, chat_identity
from claude_memory_graph.share import share
from claude_memory_graph.store import MemoryStore

PASSWORD = "handover pw"


class Stream:
    def __init__(self, reply):
        self.reply = reply

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def __aiter__(self):
        async def events():
            for block in self.reply.content:
                if block.type == "text":
                    yield NS(type="text", text=block.text)
        return events()

    async def get_final_message(self):
        return self.reply


class ScriptedClaude:
    """Answers each request with the next scripted reply; records requests."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.requests = []
        self.beta = NS(messages=NS(stream=self.stream))

    def stream(self, **kwargs):
        self.requests.append(json.loads(json.dumps(kwargs, default=lambda o: vars(o))))
        return Stream(self.replies.pop(0))


def text(t):
    return NS(type="text", text=t)


def tool(name, args, id="tu_1"):
    return NS(type="tool_use", id=id, name=name, input=args)


def reply(*blocks, stop="end_turn"):
    return NS(content=list(blocks), stop_reason=stop)


@pytest.fixture
def store(tmp_path):
    s = MemoryStore.open_or_create(tmp_path / "store")
    s.create_resource("Project", {"name": "quartz"})
    s.create_resource("Decision", {"name": "Use varnish for tiles",
                                   "rationale": "tile server too slow"})
    s.save()
    return s


@pytest.fixture(autouse=True)
def api_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")


def app_with(store, tmp_path, claude, **kw):
    service = ChatService(store, client=claude, **kw)
    app = build_app(store, "x", token="tok", password=PASSWORD,
                    auth_path=tmp_path / "oauth.json", chat=service)
    return TestClient(app, base_url="https://memory.test"), service


def signed_in(client):
    r = client.post("/chat/login", data={"password": PASSWORD}, follow_redirects=False)
    assert r.status_code == 303
    return client


def ask(client, question, chat="c1"):
    r = client.post("/chat/send", json={"chat": chat, "text": question})
    assert r.status_code == 200, r.text
    return [json.loads(line[6:]) for line in r.text.split("\n\n") if line.startswith("data: ")]


def test_home_asks_for_the_password_first(store, tmp_path):
    client, _ = app_with(store, tmp_path, ScriptedClaude())
    assert '"view": "login"' in client.get("/").text
    assert client.post("/chat/send", json={"chat": "c", "text": "hi"}).status_code == 401
    r = client.post("/chat/login", data={"password": "nope"}, follow_redirects=False)
    assert r.status_code == 401
    signed_in(client)
    assert '"view": "chat"' in client.get("/").text


def test_cookie_is_httponly_and_secure_over_https(store, tmp_path):
    client, _ = app_with(store, tmp_path, ScriptedClaude())
    r = client.post("/chat/login", data={"password": PASSWORD}, follow_redirects=False)
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "secure" in cookie and "samesite=lax" in cookie


def test_answer_runs_memory_tools_against_the_store(store, tmp_path):
    claude = ScriptedClaude(
        reply(text("Let me look."), tool("memory_search", {"text": "tile cache"}), stop="tool_use"),
        reply(text("You chose **Varnish** because the tile server was too slow.")))
    client, _ = app_with(store, tmp_path, claude)
    events = ask(signed_in(client), "why varnish?")
    kinds = [e["type"] for e in events]
    assert kinds[-1] == "done" and "tool" in kinds
    assert any("searched for “tile cache”" == e.get("text") for e in events)
    answer = "".join(e["text"] for e in events if e["type"] == "text")
    assert "Varnish" in answer
    # the tool really ran: its result went back to Claude
    result = claude.requests[1]["messages"][-1]["content"][0]
    assert result["type"] == "tool_result" and "varnish" in result["content"].lower()


def test_request_shape(store, tmp_path):
    claude = ScriptedClaude(reply(text("hi")))
    client, _ = app_with(store, tmp_path, claude)
    ask(signed_in(client), "hello")
    req = claude.requests[0]
    assert req["model"] == chat_mod.MODEL
    assert [t["name"] for t in req["tools"]] == sorted(
        ["memory_query", "memory_recall", "memory_reflect", "memory_search"])
    assert req["cache_control"] == {"type": "ephemeral"}
    assert req["fallbacks"] == "default"


def test_the_chat_cannot_write(store, tmp_path):
    claude = ScriptedClaude(
        reply(tool("memory_store_resource", {"model": "Decision",
                                             "properties": {"name": "Sneaky"}}), stop="tool_use"),
        reply(text("I can only read.")))
    client, _ = app_with(store, tmp_path, claude)
    ask(signed_in(client), "store something")
    result = claude.requests[1]["messages"][-1]["content"][0]
    assert result["is_error"] and "read-only" in result["content"]
    assert store.find_resource("Decision", "Sneaky") is None


def test_conversation_continues_with_full_history(store, tmp_path):
    claude = ScriptedClaude(reply(text("First.")), reply(text("Second.")))
    client, service = app_with(store, tmp_path, claude)
    signed_in(client)
    ask(client, "one")
    ask(client, "two")
    roles = [m["role"] for m in claude.requests[1]["messages"]]
    assert roles == ["user", "assistant", "user"]
    assert service.chats["c1"]["turns"] == 2


def test_daily_limit(store, tmp_path):
    claude = ScriptedClaude(reply(text("ok")))
    client, _ = app_with(store, tmp_path, claude, daily_limit=1)
    signed_in(client)
    ask(client, "one")
    events = ask(client, "two")
    assert events[-1]["type"] == "error" and "limit" in events[-1]["text"]


def test_not_configured_without_an_api_key(store, tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    client, _ = app_with(store, tmp_path, ScriptedClaude())
    signed_in(client)
    assert '"configured": false' in client.get("/").text
    assert client.post("/chat/send", json={"chat": "c", "text": "hi"}).status_code == 503


def test_a_share_names_its_project(store, tmp_path):
    exported = MemoryStore.open_or_create(share(store, "quartz", tmp_path / "handover").out)
    title, scope = chat_identity(exported)
    assert "quartz" in title and "quartz" in scope
    assert chat_identity(store) == ("Memory", "")


# ------------------------------------------- the real SDK, against a fake API

def _sse(events):
    return "".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in events)


def _message(blocks, stop):
    """A streamed Messages API response in wire format."""
    out = [{"type": "message_start", "message": {
        "id": "msg_1", "type": "message", "role": "assistant", "model": "claude-opus-5-5",
        "content": [], "stop_reason": None, "stop_sequence": None,
        "usage": {"input_tokens": 10, "output_tokens": 1}}}]
    for i, block in enumerate(blocks):
        if block["type"] == "text":
            out += [{"type": "content_block_start", "index": i,
                     "content_block": {"type": "text", "text": ""}},
                    {"type": "content_block_delta", "index": i,
                     "delta": {"type": "text_delta", "text": block["text"]}}]
        else:
            out += [{"type": "content_block_start", "index": i, "content_block": {
                        "type": "tool_use", "id": block["id"], "name": block["name"], "input": {}}},
                    {"type": "content_block_delta", "index": i, "delta": {
                        "type": "input_json_delta", "partial_json": json.dumps(block["input"])}}]
        out.append({"type": "content_block_stop", "index": i})
    out += [{"type": "message_delta", "delta": {"stop_reason": stop, "stop_sequence": None},
             "usage": {"output_tokens": 5}},
            {"type": "message_stop"}]
    return _sse(out)


def test_real_sdk_round_trip(store, tmp_path, monkeypatch):
    import socket
    import threading
    import time

    import anthropic
    import uvicorn
    from starlette.applications import Starlette
    from starlette.responses import Response
    from starlette.routing import Route

    bodies = []
    scripted = [
        _message([{"type": "tool_use", "id": "toolu_1", "name": "memory_search",
                   "input": {"text": "varnish"}}], "tool_use"),
        _message([{"type": "text", "text": "Varnish, for tile speed."}], "end_turn"),
    ]

    async def messages(request):
        bodies.append(dict(await request.json(), _headers=dict(request.headers)))
        return Response(scripted.pop(0), media_type="text/event-stream")

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(Starlette(routes=[
        Route("/v1/messages", messages, methods=["POST"])]),
        host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    time.sleep(1)
    try:
        sdk = anthropic.AsyncAnthropic(api_key="test", base_url=f"http://127.0.0.1:{port}",
                                       max_retries=0)
        client, _ = app_with(store, tmp_path, sdk)
        events = ask(signed_in(client), "why varnish?")
    finally:
        server.should_exit = True

    assert [e["type"] for e in events] == ["tool", "text", "done"], events
    first, second = bodies
    assert "server-side-fallback-2026-07-01" in first["_headers"].get("anthropic-beta", "")
    assert first["fallbacks"] == "default" and first["output_config"] == {"effort": "medium"}
    assert all(t["eager_input_streaming"] for t in first["tools"])
    # turn 2 carries the assistant's tool_use and our tool_result, in order
    assert [m["role"] for m in second["messages"]] == ["user", "assistant", "user"]
    assert second["messages"][1]["content"][0]["type"] == "tool_use"
    assert "varnish" in second["messages"][2]["content"][0]["content"].lower()
