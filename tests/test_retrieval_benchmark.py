"""Retrieval benchmark: does the gate surface the right memory, and stay
quiet when nothing fits?

A fixed graph of realistic memories and a table of prompts, each with the
memory it should surface (or None: the gate must stay silent). It measures
the live decision path — corpus, scoring, proximity, cluster rule, thresholds
— exactly as a session runs it. The floors below are set at what the gate
achieves today: a change that makes retrieval worse fails here, before it
reaches anyone's sessions. Raise the floors when an improvement lands.

Grow the table from real evidence: `claude-memory-graph misses` names
prompts the gate missed; add them here with the memory they wanted.
"""

import pytest

from claude_memory_graph.gate import runtime
from claude_memory_graph.gate.recall import RecallExtension
from claude_memory_graph.hookcore import HookContext
from claude_memory_graph.store import MemoryStore

MEMORIES = [
    ("Project", "quartz", {"description": "arches heritage platform deployment for a council client"}),
    ("Project", "claude-memory-graph", {"description": "RDF knowledge graph long-term memory for Claude Code"}),
    ("Decision", "Use pyoxigraph over rdflib", {
        "rationale": "native quad store with named graphs; rdflib was slow on large SPARQL joins",
        "aliases": "graph database choice, triple store"}),
    ("Decision", "Save after every mutating tool call", {
        "rationale": "MCP stdio servers die without a shutdown hook, so save-on-exit lost the session",
        "aliases": "persist often, atomic dump"}),
    ("Pattern", "SPARQL FILTER on VALUES must be top level", {
        "description": "a FILTER inside the GRAPH group cannot see a VALUES-bound variable; rows vanish silently",
        "aliases": "filter scope bug, empty sparql results"}),
    ("Pattern", "Arches graph restore duplicates post_save", {
        "description": "restoring an Arches resource graph fires post_save twice and recreates tile rows",
        "aliases": "double signal, duplicated tiles"}),
    ("Pattern", "Tile cache poisoning after reindex", {
        "description": "reindexing Elasticsearch leaves stale map tiles; flush the varnish layer afterwards",
        "aliases": "stale tiles, map shows deleted features"}),
    ("Decision", "Celery workers restart on memory cap", {
        "rationale": "max-memory-per-child at 512MB stopped the slow leak in the export task",
        "aliases": "worker restart loop, celery memory leak"}),
    ("Pattern", "Docker compose healthcheck before migrations", {
        "description": "migrations raced postgres startup; depends_on with service_healthy fixed it",
        "aliases": "migration race, database not ready"}),
    ("Decision", "Stop block for context capture", {
        "rationale": "nudges injected with the prompt were ignored; a Stop block cannot be deprioritised",
        "aliases": "capture reminder, context log nag"}),
    ("Technology", "Elasticsearch", {"description": "search index behind the arches map and keyword search"}),
    ("Technology", "pyoxigraph", {"description": "Rust RDF store with Python bindings and SPARQL 1.1"}),
    ("Person", "Stuart Marshall", {"role": "developer at Flax & Teal"}),
]

# (prompt, project the session runs in, memory that should surface or None)
CASES = [
    ("why did we pick pyoxigraph instead of rdflib?", "claude-memory-graph", "Use pyoxigraph over rdflib"),
    ("which triple store does the graph database use", "claude-memory-graph", "Use pyoxigraph over rdflib"),
    ("the sparql query returns empty results when I add a filter", "claude-memory-graph",
     "SPARQL FILTER on VALUES must be top level"),
    ("why do we persist so often, every mutating tool call?", "claude-memory-graph",
     "Save after every mutating tool call"),
    ("restoring the arches graph creates duplicated tiles", "quartz", "Arches graph restore duplicates post_save"),
    ("the map shows deleted features after we reindex", "quartz", "Tile cache poisoning after reindex"),
    ("celery worker keeps restarting, is that the memory leak fix?", "quartz", "Celery workers restart on memory cap"),
    ("migrations fail because the database is not ready", "quartz", "Docker compose healthcheck before migrations"),
    ("why does the stop hook nag me about the context log", "claude-memory-graph", "Stop block for context capture"),
    # shares no words with the memory: matched by meaning (gate/semantic.py)
    ("map still draws things we removed", "quartz", "Tile cache poisoning after reindex"),
    # nothing in memory fits these: the gate must stay silent
    ("thanks, that looks good", "quartz", None),
    ("run the linter again please", "claude-memory-graph", None),
    ("write a haiku about autumn", "quartz", None),
    ("add a dark mode toggle to the settings page", "quartz", None),
    ("bump the version number and update the changelog", "claude-memory-graph", None),
    # techy, but nothing in memory is about them: the semantic channel must stay quiet too
    ("write unit tests for the csv parser", "quartz", None),
    ("the build is red, can you check CI", "claude-memory-graph", None),
    ("explain how python decorators work", "quartz", None),
    ("rename this variable to something clearer", "claude-memory-graph", None),
    ("the login page is slow to load", "quartz", None),
    ("add pagination to the search results", "quartz", None),
    ("fix the typo in the readme", "claude-memory-graph", None),
]

# Paraphrases sharing little vocabulary with the memory: the lexical gate's
# known blind spot (the README's "vocabulary miss"). Reported, not asserted —
# move a case into CASES once a change makes it pass.
KNOWN_GAPS = [
    ("why is the knowledge base saved to disk so eagerly", "claude-memory-graph",
     "Save after every mutating tool call"),
    ("the background job runner keeps bouncing", "quartz", "Celery workers restart on memory cap"),
]

# Without the embedding model (platforms with no wordllama wheel) the gate is
# word-only, and meaning-matched cases are gaps again rather than failures.
from claude_memory_graph.gate import semantic as _semantic  # noqa: E402

if not _semantic.available():
    _by_meaning = [c for c in CASES if c[0] == "map still draws things we removed"]
    CASES = [c for c in CASES if c not in _by_meaning]
    KNOWN_GAPS = KNOWN_GAPS + _by_meaning

# Floors: what the gate achieves today. Raise them when it improves.
MIN_HIT_RATE = 1.0         # share of answerable prompts whose memory surfaced
MAX_FALSE_INJECTIONS = 0   # silent-expected prompts that injected anything


@pytest.fixture
def graph(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_GRAPH_PATH", str(tmp_path / "store"))
    monkeypatch.setenv("CLAUDE_CONTEXT_DIR", str(tmp_path / "empty-context"))
    monkeypatch.setattr(runtime, "_config", dict(runtime._DEFAULTS))
    store = MemoryStore.open_or_create(tmp_path / "store")
    iris = {}
    for model, name, props in MEMORIES:
        _, iris[name] = store.create_resource(model, {"name": name, **props})
    for name in ("Use pyoxigraph over rdflib", "Save after every mutating tool call",
                 "SPARQL FILTER on VALUES must be top level", "Stop block for context capture"):
        store.create_link(iris[name], iris["claude-memory-graph"], "affects", {})
    for name in ("Arches graph restore duplicates post_save", "Tile cache poisoning after reindex",
                 "Celery workers restart on memory cap", "Docker compose healthcheck before migrations"):
        store.create_link(iris[name], iris["quartz"], "appliesTo", {})
    store.save()
    return store


def _inject(prompt: str, project: str) -> str:
    ctx = HookContext(event="UserPromptSubmit", payload={"prompt": prompt, "cwd": f"/w/{project}"},
                      core={"project": project, "session_id": "bench"}, state={})
    return RecallExtension().on_user_prompt_submit(ctx) or ""


def test_retrieval_benchmark(graph):
    hits, answerable, false_injections, report = 0, 0, 0, []
    for prompt, project, expected in CASES:
        out = _inject(prompt, project)
        if expected is None:
            if out:
                false_injections += 1
                report.append(f"FALSE INJECTION  {prompt!r}")
            continue
        answerable += 1
        if expected in out:
            hits += 1
        else:
            report.append(f"MISS  {prompt!r} wanted {expected!r}")
    closed = [p for p, project, want in KNOWN_GAPS if want in _inject(p, project)]
    report.append(f"known gaps closed: {len(closed)}/{len(KNOWN_GAPS)}"
                  + "".join(f"\n    now passes: {p!r}" for p in closed))
    rate = hits / answerable
    summary = f"hit rate {hits}/{answerable} = {rate:.0%}, false injections {false_injections}"
    print("\nretrieval benchmark: " + summary + "".join(f"\n  {r}" for r in report))
    assert rate >= MIN_HIT_RATE and false_injections <= MAX_FALSE_INJECTIONS, \
        summary + "\n" + "\n".join(report)
