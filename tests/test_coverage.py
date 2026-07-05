import json

import pytest

from claude_memory_graph.gate import coverage
from claude_memory_graph.store import MemoryStore
from claude_memory_graph.tools import store_resource


@pytest.fixture
def store(tmp_path):
    s = MemoryStore.open_or_create(tmp_path)
    store_resource.handle_resource(s, "Decision", {
        "name": "Use pyoxigraph over rdflib",
        "rationale": "native quad store",
        "aliases": "storage choice, db pick",
    })
    store_resource.handle_resource(s, "Project", {"name": "quartz"})
    return s


def cats(store, prompt):
    return coverage.analyse(store, [prompt])["prompts"][0]["categories"]


# ---------------- question shape ----------------

def test_question_shapes():
    assert coverage.question_shaped("what decisions affect quartz?")
    assert coverage.question_shaped("did we pick pyoxigraph")
    assert coverage.question_shaped("why the full dump on save")
    assert not coverage.question_shaped("refactor the dispatcher to batch saves")


# ---------------- word categorization ----------------

def test_model_nouns_ground(store):
    c = cats(store, "which decisions and patterns matter here")
    assert c["decisions"] == "model" and c["patterns"] == "model"

def test_relation_verb_forms_ground(store):
    c = cats(store, "who works on quartz")
    assert c["works"] == "relation"
    assert c["quartz"] == "entity"

def test_alias_tokens_ground(store):
    c = cats(store, "remind me about the storage choice")
    assert c["storage"] == "alias" and c["choice"] == "alias"

def test_modifiers_and_leftovers(store):
    c = cats(store, "recent kubernetes decisions")
    assert c["recent"] == "modifier"
    assert c["kubernetes"] == "leftover"
    assert c["decisions"] == "model"

def test_wh_word_grounds(store):
    assert cats(store, "why did we pick pyoxigraph")["why"] == "wh"


# ---------------- report ----------------

def test_report_counts_and_leftover_work_order(store):
    out = coverage.report(store, [
        "what decisions affect quartz?",        # fully grounded question
        "deploy the kubernetes ingress today",   # statement, leftovers
        "who works on quartz",
    ])
    assert "question-shaped: 2" in out
    assert "kubernetes(1)" in out and "deploy(1)" in out
    assert "planner-ready questions" in out
    assert "what decisions affect quartz?" in out
    assert "affect(1)" not in out  # bare verb form is in the lexicon now

def test_report_handles_no_prompts(store):
    assert "No analysable prompts" in coverage.report(store, ["thanks", "  "])


# ---------------- prompt sources ----------------

def test_transcript_extraction(tmp_path):
    t = tmp_path / "session.jsonl"
    lines = [
        {"type": "user", "message": {"role": "user", "content": "why pyoxigraph?"}},
        {"type": "user", "message": {"role": "user", "content": [
            {"type": "text", "text": "block style prompt"},
            {"type": "tool_result", "content": "ignored"}]}},
        {"type": "assistant", "message": {"content": "not a prompt"}},
        {"type": "user", "isMeta": True, "message": {"content": "meta skipped"}},
        {"type": "user", "message": {"content": "<command-name>/distill</command-name>"}},
        {"type": "user", "message": {"content": "/memory-graph:distill"}},
    ]
    t.write_text("\n".join(json.dumps(x) for x in lines) + "\nnot json\n")
    prompts = coverage.prompts_from_transcripts([tmp_path])
    assert prompts == ["why pyoxigraph?", "block style prompt"]


def test_prompts_file(tmp_path):
    f = tmp_path / "p.txt"
    f.write_text("one prompt\n\n  another prompt \n")
    assert coverage.prompts_from_file(f) == ["one prompt", "  another prompt "]
