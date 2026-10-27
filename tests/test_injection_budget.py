"""Injection size, clustering, and latency: the prime is a bounded table of
contents, topic clusters inject instead of silencing, the per-prompt index
is cached on the store file, and drift checks batch their git calls."""

import subprocess

import pytest

import claude_hook_kit.state as kit_state
from claude_hook_kit import HookContext
from claude_memory_graph.gate import recall as gate_recall
from claude_memory_graph.gate import runtime
from claude_memory_graph.gate.preview import preview
from claude_memory_graph.gate.recall import RecallExtension, decide
from claude_memory_graph.store import MemoryStore
from claude_memory_graph.tools import recall as recall_tool


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv(kit_state.HOOK_KIT_HOME_ENV, str(tmp_path / "kit"))
    monkeypatch.setenv("CLAUDE_CONTEXT_DIR", str(tmp_path / "empty-context"))
    monkeypatch.setattr(runtime, "_config", dict(runtime._DEFAULTS))


@pytest.fixture
def store(tmp_path, monkeypatch):
    path = tmp_path / "store"
    monkeypatch.setenv("MEMORY_GRAPH_PATH", str(path))
    return MemoryStore.open_or_create(path)


def ctx(prompt="", event="UserPromptSubmit", project="quartz", state=None):
    return HookContext(event=event, payload={"prompt": prompt, "cwd": f"/w/{project}"},
                       core={"project": project, "session_id": "s"},
                       state=state if state is not None else {})


def _cluster(store, n=5):
    _, proj = store.create_resource("Project", {"name": "quartz"})
    for i in range(n):
        _, iri = store.create_resource("Pattern", {
            "name": f"arches graph restore gotcha {i}",
            "description": "arches graph restore recreates rows and fires post_save twice",
            "aliases": "restore duplicates, double post_save",
            "status": "active",
        })
        store.create_link(iri, proj, "appliesTo", {})
    store.save()


# ================= 1. topic clusters inject instead of silencing =================

def test_strong_tied_cluster_injects_head_and_points_at_the_rest(store):
    _cluster(store)
    out = RecallExtension().on_user_prompt_submit(
        ctx("why does the arches graph restore fire post_save twice"))
    assert out is not None
    assert out.count("next: memory_recall(") == 2           # TOP_N heads
    assert "+3 similar — memory_search(" in out


def test_weak_tie_stays_silent():
    cfg = dict(runtime._DEFAULTS)
    weak = [(4.0, {"name": "a"}), (4.0, {"name": "b"}), (4.0, {"name": "c"})]
    group, _rest, _similar = decide(weak, cfg)
    assert group == []  # generic match, below CLUSTER_FACTOR x ABS_MIN


def test_standout_group_unaffected():
    cfg = dict(runtime._DEFAULTS)
    group, rest, similar = decide([(20.0, {"name": "a"}), (2.0, {"name": "b"})], cfg)
    assert [d["name"] for _, d in group] == ["a"] and similar == 0


def test_preview_agrees_with_the_live_gate(store):
    _cluster(store)
    out = preview("why does the arches graph restore fire post_save twice", "quartz")
    assert "topic cluster" in out and "SILENT" not in out.split("SESSION-LOG")[0]


# ================= 3. injected text is the memory, not its matching data =================

def test_desc_hides_aliases_and_status_but_aliases_still_match(store):
    store.create_resource("Pattern", {
        "name": "Tile cache poisoning after reindex",
        "description": "flush the varnish layer after every reindex",
        "aliases": "stale tiles, map shows deleted features",
        "status": "active",
    })
    store.save()
    out = RecallExtension().on_user_prompt_submit(
        ctx("the map shows deleted features again, stale tiles", project=""))
    assert out is not None and "flush the varnish layer" in out   # matched via aliases
    bullet = next(l for l in out.splitlines() if l.startswith("- Tile"))
    assert "stale tiles" not in bullet and "active" not in bullet


# ================= 2. the prime is a ranked, bounded table of contents =================

def _hub(store, n):
    _, proj = store.create_resource("Project", {
        "name": "quartz", "description": "arches deployment"})
    _, tech = store.create_resource("Technology", {"name": "elastic", "description": "search"})
    store.create_link(proj, tech, "uses", {})
    for i in range(n):
        _, d = store.create_resource("Decision", {
            "name": f"decision {i}",
            "rationale": "because the old approach broke under load " * 4,
            "aliases": "secret alias text", "status": "active",
            "sourceContext": "quartz__x.md", "capturedBy": "cc"})
        store.create_link(d, proj, "affects", {})
    store.save()


def test_prime_ranks_decisions_before_reference_nodes(store):
    _hub(store, 3)
    out = recall_tool.prime(store, "Project", "quartz", 20, 3000)
    lines = out.splitlines()
    assert lines[0].startswith("Project 'quartz' — arches deployment")
    assert lines[-1].startswith("- Technology 'elastic'")  # reference node last


def test_prime_respects_char_budget_and_says_what_it_left_out(store):
    _hub(store, 40)
    out = recall_tool.prime(store, "Project", "quartz", 20, 1500)
    assert len(out) <= 1500 + 200  # budget + the trailing "+N more" pointer
    assert "+" in out.splitlines()[-1] and "more — memory_search(" in out


def test_prime_hides_matching_and_provenance_data(store):
    _hub(store, 2)
    out = recall_tool.prime(store, "Project", "quartz", 20, 3000)
    for noise in ("secret alias text", "active", "quartz__x.md", "capturedBy"):
        assert noise not in out


def test_session_start_uses_the_budgeted_prime(store):
    _hub(store, 40)
    out = RecallExtension().on_session_start(ctx(event="SessionStart"))
    assert out is not None and len(out) < runtime._DEFAULTS["PRIME_MAX_CHARS"] + 400
    assert "secret alias text" not in out


# ================= 4. the per-prompt index is cached on the store file =================

def test_index_cached_until_the_store_changes(store, monkeypatch):
    _cluster(store, 2)
    opened = []

    def opener():
        opened.append(1)
        return MemoryStore.open_or_create(runtime.store_dir())

    gate_recall.gate_index("quartz", opener)
    assert opened, "first call must build"
    opened.clear()
    docs, _idf, near, _links = gate_recall.gate_index("quartz", opener)
    assert not opened, "unchanged store must be served from the cache"
    assert len(docs) == 3 and near

    store.create_resource("Pattern", {"name": "fresh node", "description": "new"})
    store.save()
    docs, _idf, _near, _links = gate_recall.gate_index("quartz", opener)
    assert opened and any(d["name"] == "fresh node" for d in docs)


def test_corrupt_cache_fails_open(store):
    _cluster(store, 2)
    (kit_state.state_home() / "gate-index.pickle").parent.mkdir(parents=True, exist_ok=True)
    (kit_state.state_home() / "gate-index.pickle").write_bytes(b"not a pickle")
    out = RecallExtension().on_user_prompt_submit(
        ctx("why does the arches graph restore fire post_save twice"))
    assert out is not None


# ================= 5. drift checks batch their git calls =================

def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True, check=True)


def test_drift_flags_one_git_log_per_commit(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    (repo / "pkg").mkdir(parents=True)
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    for f in ("a.py", "b.py", "pkg/c.py"):
        (repo / f).write_text("v1\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "v1")
    base = _git(repo, "rev-parse", "HEAD").stdout.strip()
    (repo / "a.py").write_text("v2\n")
    (repo / "pkg/c.py").write_text("v2\n")
    _git(repo, "commit", "-qam", "v2")
    monkeypatch.chdir(repo)

    calls = []
    real_run = subprocess.run

    def counting_run(cmd, *a, **kw):
        calls.append(cmd[1])
        return real_run(cmd, *a, **kw)

    monkeypatch.setattr(recall_tool.subprocess, "run", counting_run)
    props = [{"anchorPath": p, "anchorCommit": base} for p in ("a.py", "b.py", "pkg/")]
    flags = recall_tool._drift_flags(props)
    assert calls == ["rev-parse", "log"]                       # not 2 per anchor
    assert ("a.py", base) in flags and ("pkg/", base) in flags  # dir anchor too
    assert ("b.py", base) not in flags
