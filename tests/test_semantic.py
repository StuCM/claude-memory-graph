"""The meaning channel (gate/semantic.py): what it adds, and that it can
only add — off, missing or broken, the gate is exactly the lexical gate."""

import json

import pytest

from test_retrieval_benchmark import _inject, graph  # noqa: F401  (fixture)

from claude_memory_graph.gate import runtime, semantic
from claude_memory_graph.hookcore import state_home

PARAPHRASE = ("map still draws things we removed", "quartz")

needs_model = pytest.mark.skipif(not semantic.available(),
                                 reason="no wordllama wheel on this platform")


def _last_decision() -> dict:
    lines = (state_home() / "injections.jsonl").read_text().splitlines()
    return [json.loads(l) for l in lines if '"kind"' not in l][-1]


@needs_model
def test_a_paraphrase_fires_by_meaning_and_says_so(graph):
    out = _inject(*PARAPHRASE)
    assert "Tile cache poisoning after reindex" in out
    entry = _last_decision()
    assert entry["via"] == "semantic" and entry["sem_top"] >= runtime._DEFAULTS["SEM_MIN"]


LONG = ("I've been looking at the release notes for next week and want to tidy up the "
        "changelog first. Also we need to sort out who is reviewing the onboarding docs, "
        "Sarah said she might have time on Thursday. Anyway, one thing that's bugging me is "
        "that the map still draws things we removed. Let me know if you need anything else "
        "from me before the standup.")


@needs_model
def test_a_paraphrase_inside_a_long_prompt_still_fires(graph):
    # averaged over six sentences the paraphrase drowns; scored per sentence it doesn't
    out = _inject(LONG, "quartz")
    assert "Tile cache poisoning after reindex" in out
    assert _last_decision()["via"] == "semantic"


def test_long_prompts_are_scored_per_sentence_too():
    vs = semantic.views(LONG)
    assert vs[0] == LONG and len(vs) > 1
    assert any("the map still draws things we removed" in v.lower() for v in vs[1:])
    assert semantic.views(PARAPHRASE[0]) == [PARAPHRASE[0]]        # short: one view


def test_a_word_match_stays_lexical(graph):
    _inject("restoring the arches graph creates duplicated tiles", "quartz")
    assert _last_decision()["via"] == "lexical"


@needs_model
def test_silences_record_the_semantic_scores_for_tuning(graph):
    assert _inject("write a haiku about autumn", "quartz") == ""
    entry = _last_decision()
    assert not entry["fired"] and "sem_top" in entry


def test_switched_off_it_is_the_lexical_gate(graph, monkeypatch):
    monkeypatch.setattr(runtime, "_config", {**runtime._DEFAULTS, "SEMANTIC": False})
    (state_home() / "gate-index.pickle").unlink(missing_ok=True)
    assert _inject(*PARAPHRASE) == ""


def test_without_the_model_it_fails_open(graph, monkeypatch):
    monkeypatch.setattr(semantic, "available", lambda: False)
    (state_home() / "gate-index.pickle").unlink(missing_ok=True)
    assert _inject(*PARAPHRASE) == ""
    assert "Arches graph restore" in _inject(
        "restoring the arches graph creates duplicated tiles", "quartz")


def test_a_broken_ranker_fails_open(graph, monkeypatch):
    def boom(*args):
        raise RuntimeError("bad vectors")
    monkeypatch.setattr(semantic, "rank", boom)
    assert _inject(*PARAPHRASE) == ""


def test_entities_are_never_matched_by_meaning(graph):
    # close in topic to the Elasticsearch node, but nothing to remember
    assert _inject("add pagination to the search results", "quartz") == ""


@needs_model
def test_word_ids_are_cached_for_the_next_process(graph, monkeypatch):
    from ceist import vectors
    monkeypatch.setattr(vectors, "_shared", {})       # a fresh process, this state home
    _inject(*PARAPHRASE)
    cache = next((state_home() / "embeddings").glob("word-ids.json"))
    words = json.loads(cache.read_text())
    assert "map" in words and "removed" in words
