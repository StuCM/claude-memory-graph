"""memory_amend_relation + planner telemetry: the ontology self-correction
loop. Verb forms are curable at runtime, every ask leaves a log line, and
the `asks` report joins the log into curation signals."""

import json

import pytest
from claude_hook_kit import state_home

from claude_memory_graph import planner
from claude_memory_graph.store import MemoryStore
from claude_memory_graph.tools import link, store_resource


@pytest.fixture
def store(tmp_path):
    s = MemoryStore.open_or_create(tmp_path)
    store_resource.handle_resource(s, "Person", {"name": "Stuart Marshall"})
    store_resource.handle_resource(s, "Project", {"name": "quartz", "status": "active"})
    link.handle_link(s, "Person", "Stuart Marshall", "Project", "quartz", "worksOn", {})
    return s


# ── amend_relation ─────────────────────────────────────────────────────

def test_added_form_grounds_immediately(store):
    link.handle_amend_relation(store, "worksOn", add_verb_forms=["collaborates on"])
    out = planner.handle(store, "Who collaborates on quartz?")
    assert "Stuart Marshall" in out


def test_remove_from_base_relation_refused(store):
    with pytest.raises(ValueError, match="base.ttl"):
        store.amend_relation("worksOn", [], ["works on"])
    # and the form still grounds
    assert "works on" in store.relation_lexicon()["worksOn"]["verbForms"]


def test_remove_from_llm_added_relation(store):
    store.add_relation("mentors", "Person mentors Person", ["mentors", "guides"])
    out = link.handle_amend_relation(store, "mentors", remove_verb_forms=["guides"])
    assert "removed: 'guides'" in out
    assert "guides" not in store.relation_lexicon()["mentors"]["verbForms"]
    assert "mentors" in store.relation_lexicon()["mentors"]["verbForms"]


def test_remove_missing_form_reported_not_silent(store):
    store.add_relation("mentors", "Person mentors Person", ["mentors"])
    out = link.handle_amend_relation(store, "mentors", remove_verb_forms=["coaches"])
    assert "not present" in out


def test_unknown_relation_and_empty_amend_error(store):
    with pytest.raises(ValueError, match="Unknown relation"):
        store.amend_relation("frobnicates", ["frobs"], [])
    with pytest.raises(ValueError, match="Nothing to amend"):
        store.amend_relation("worksOn", [], [])


# ── telemetry ──────────────────────────────────────────────────────────

def _entries():
    path = state_home() / "ask-decisions.jsonl"
    return [json.loads(l) for l in path.read_text().splitlines()]


def test_every_ask_logs_one_entry(store):
    planner.handle(store, "Who works on quartz?")
    planner.handle(store, "Refactor the dispatcher")
    planner.handle(store, "What colour is the bikeshed?")
    outcomes = [e["outcome"] for e in _entries()]
    assert outcomes == ["answered", "statement", "low-coverage"]


def test_log_carries_grounding_details(store):
    planner.handle(store, "Who works on quartz?")
    e = _entries()[0]
    assert e["relations"] == [{"rel": "worksOn", "form": "works on"}]
    assert e["anchor"] == "quartz"
    assert e["coverage"] == 1.0


def test_asks_report_flags_dry_verb_form(store):
    # "picked" → madeBy fires but never produces rows → misgrounding suspect
    planner.handle(store, "What decisions were picked for quartz?")
    report = planner.asks_report()
    assert "'picked' → madeBy" in report
    # "works on" answered fine → must NOT be a suspect
    planner.handle(store, "Who works on quartz?")
    assert "works on" not in planner.asks_report()


def test_asks_report_flags_vocabulary_gap(store):
    planner.handle(store, "What colour is the bikeshed?")
    report = planner.asks_report()
    assert "bikeshed" in report or "colour" in report
