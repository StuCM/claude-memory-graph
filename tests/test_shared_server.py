"""The shared server's hook routes, and the hooks using them."""

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from claude_hook_kit import HookContext
from claude_memory_graph.gate import recall
from claude_memory_graph.gate.recall import RecallExtension
from claude_memory_graph.http_server import _hook_routes
from claude_memory_graph.store import MemoryStore

PROMPT = "why did we choose pyoxigraph over rdflib for the quad store?"
ENTRY = """---
created: 2026-10-23T22:00
distilled: false
summary: "s"
---

## Key Points

- [22:00] Decision: Use flurbonium for caching
  rationale: flurbonium beats the rest
  affects: Project/quartzproj
  concepts: caching
"""


@pytest.fixture
def store(tmp_path, monkeypatch):
    d = tmp_path / "store"
    monkeypatch.setenv("MEMORY_GRAPH_PATH", str(d))
    monkeypatch.setenv("CLAUDE_CONTEXT_DIR", str(tmp_path / "context"))
    s = MemoryStore.open_or_create(d)
    _, proj = s.create_resource("Project", {"name": "quartzproj"})
    _, dec = s.create_resource("Decision", {
        "name": "Use pyoxigraph over rdflib",
        "rationale": "native quad store beats rdflib for named graphs"})
    s.create_link(proj, dec, "decided", {})
    s.save()
    return s


@pytest.fixture
def client(store):
    return TestClient(Starlette(routes=_hook_routes(store)))


def run(prompt):
    ctx = HookContext(event="UserPromptSubmit", payload={"prompt": prompt},
                      core={"project": "quartzproj", "session_id": "s"}, state={})
    return RecallExtension().on_user_prompt_submit(ctx)


def test_hook_uses_the_server_and_matches_local(store, client, monkeypatch):
    local = run(PROMPT)
    assert local and "pyoxigraph" in local
    asked = []

    def post(path, payload, timeout=5.0):
        asked.append(path)
        return client.post(path, json=payload).json()
    monkeypatch.setattr(recall, "post", post)

    served = recall.rank

    def server_only(prompt, project, store=None):
        assert store is not None, "hook ranked locally"
        return served(prompt, project, store)
    monkeypatch.setattr(recall, "rank", server_only)
    assert run(PROMPT) == local and asked == ["/hook/recall"]


def test_prime_route(client):
    sections = client.post("/hook/prime", json={"project": "quartzproj"}).json()["sections"]
    assert len(sections) == 1 and "quartzproj" in sections[0]


def test_query_route(client):
    text = client.post("/query", json={
        "sparql": "SELECT ?n WHERE { GRAPH ?g { ?s mem:name ?n } } ORDER BY ?n"}).json()["text"]
    assert "Use pyoxigraph over rdflib" in text


def test_distill_route_promotes_new_entries(store, client, tmp_path):
    (tmp_path / "context").mkdir()
    (tmp_path / "context" / "quartzproj__2026-10-23_22-00.md").write_text(ENTRY)
    client.post("/hook/distill", json={})  # TestClient runs the background task
    assert store.find_resource("Decision", "Use flurbonium for caching") is not None
