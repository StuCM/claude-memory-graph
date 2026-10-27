"""The 10-question comparison: graph vs Claude Code's built-in memory."""


from claude_memory_graph import compare
from claude_memory_graph.hookcore import state_home
from claude_memory_graph.store import MemoryStore

QUESTIONS = '''
[[question]]
text = "what did we decide about caching map tiles?"
project = "quartz"
expect = ["varnish"]

[[question]]
text = "which test runner does charcoal use?"
project = "charcoal"
expect = ["pytest"]
'''


def setup(tmp_path):
    store = MemoryStore.open_or_create(tmp_path / "store")
    _, quartz = store.create_resource("Project", {"name": "quartz"})
    _, d = store.create_resource("Decision", {
        "name": "Cache map tiles in varnish", "rationale": "tile server too slow",
        "aliases": "tile caching, slow map"})
    store.create_link(d, quartz, "affects", {})
    store.save()
    home = tmp_path / "home"
    mem = home / ".claude" / "projects" / "-work-charcoal" / "memory"
    mem.mkdir(parents=True)
    (mem / "MEMORY.md").write_text("- [testing](testing.md): charcoal uses pytest\n")
    (mem / "testing.md").write_text("Run the suite with pytest -q.\n")
    path = tmp_path / "q.toml"
    path.write_text(QUESTIONS)
    return store, home, path


def test_each_memory_is_checked(tmp_path, monkeypatch):
    store, home, path = setup(tmp_path)
    monkeypatch.setenv("MEMORY_GRAPH_PATH", str(tmp_path / "store"))
    rows = compare.run(compare.load(path), store, home)
    tiles, runner = rows
    assert tiles.results["graph_on_request"][0] == 1
    assert tiles.results["builtin_at_start"][0] == 0
    assert runner.results["builtin_at_start"][0] == 1
    assert runner.results["builtin_if_opened"][0] == 1
    assert runner.results["graph_on_request"][0] == 0
    text = compare.report(rows, "q.toml")
    assert "**Only the graph:** 1" in text and "only built-in:** 2" in text
    assert "claude.ai (fill in)" in text


def test_a_run_leaves_the_real_logs_alone(tmp_path, monkeypatch):
    store, home, path = setup(tmp_path)
    monkeypatch.setenv("MEMORY_GRAPH_PATH", str(tmp_path / "store"))
    log = state_home() / "injections.jsonl"
    before = log.read_text() if log.exists() else ""
    compare.main(path, tmp_path / "report.md")
    assert (log.read_text() if log.exists() else "") == before
    assert "Memory comparison" in (tmp_path / "report.md").read_text()


def test_bad_file_says_so(tmp_path):
    (tmp_path / "empty.toml").write_text("# nothing\n")
    try:
        compare.load(tmp_path / "empty.toml")
    except ValueError as exc:
        assert "no [[question]]" in str(exc)
    else:
        raise AssertionError("expected an error")
