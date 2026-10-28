"""The gate answers a question buried in a prompt — when, and only when, the
planner understands all of it."""

from test_retrieval_benchmark import _inject, graph  # noqa: F401  (fixture)

from claude_memory_graph import planner
from claude_memory_graph.gate import runtime

LONG = ("Morning. I'm picking up the memory work again after the break and want the release "
        "out by Friday. Before I touch anything, which decisions affect claude-memory-graph? "
        "I remember we changed how saving works but not the details. Then let's draft the notes.")


def test_question_candidates_trim_the_lead_in():
    assert planner.question_candidates(LONG) == ["which decisions affect claude-memory-graph?"]
    assert planner.question_candidates("Fix the failing test please.") == []
    two = "Which patterns apply to quartz? And who works on it? What about the third?"
    assert len(planner.question_candidates(two, max_questions=2)) == 2


def test_a_buried_question_is_answered_as_memory(graph):
    out = _inject(LONG, "claude-memory-graph")
    assert out.startswith("Memory answers")
    answer = out.split("\n\n")[0]
    assert "searched: Find Decisions that affect Project 'claude-memory-graph'." in answer
    for name in ("Use pyoxigraph over rdflib", "Save after every mutating tool call",
                 "Stop block for context capture"):
        assert name in answer
    assert "SPARQL FILTER on VALUES" not in answer          # a Pattern, not a Decision


def test_answered_once_per_session(graph):
    from claude_memory_graph.gate.recall import RecallExtension
    from claude_memory_graph.hookcore import HookContext
    state: dict = {}

    def ask():
        ctx = HookContext(event="UserPromptSubmit",
                          payload={"prompt": "which patterns apply to quartz?", "cwd": "/w/quartz"},
                          core={"project": "quartz", "session_id": "s"}, state=state)
        return RecallExtension().on_user_prompt_submit(ctx) or ""
    assert "Memory answers" in ask()
    assert "Memory answers" not in ask()


def test_half_understood_questions_stay_pointers(graph):
    # "nag" grounds nothing: the planner doesn't fully understand it, so no answer
    out = _inject("which patterns nag the quartz deploy team?", "quartz")
    assert "Memory answers" not in out


def test_switched_off(graph, monkeypatch):
    monkeypatch.setattr(runtime, "_config", {**runtime._DEFAULTS, "ANSWER_QUESTIONS": False})
    assert "Memory answers" not in _inject(LONG, "claude-memory-graph")


def test_entity_index_is_reused_until_the_store_file_changes(graph, tmp_path, monkeypatch):
    from claude_memory_graph.hookcore import state
    monkeypatch.setenv(state.STATE_HOME_ENV, str(tmp_path / "state"))
    built = []
    real = planner._entity_docs
    monkeypatch.setattr(planner, "_entity_docs", lambda s: built.append(1) or real(s))
    planner.entity_index(graph)
    planner.entity_index(graph)
    assert len(built) == 1                                   # second read came from disk
    graph.create_resource("Decision", {"name": "Cache the planner index"})
    graph.save()
    docs, _ = planner.entity_index(graph)
    assert len(built) == 2                                   # the file changed: rebuilt
    assert "Cache the planner index" in {d["name"] for d in docs}
