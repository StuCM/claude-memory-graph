"""Handover sharing: a project's neighbourhood as its own store, and a
read-only server over it. The boundary is the point — what must NOT leak."""

import asyncio

import pytest

from claude_memory_graph import tools
from claude_memory_graph.share import share
from claude_memory_graph.store import MemoryStore


@pytest.fixture
def store(tmp_path):
    s = MemoryStore.open_or_create(tmp_path / "live")
    ids = {}

    def node(model, name, **props):
        _, ids[name] = s.create_resource(model, {"name": name, **props})

    node("Project", "quartz", description="arches deployment")
    node("Project", "charcoal", description="another client's project")
    node("Decision", "Use varnish for tiles", rationale="tile server too slow",
         sourceContext="quartz__2026-10-01.md", capturedBy="claude-code")
    node("Pattern", "Arches restore duplicates post_save", description="restore fires twice")
    node("Technology", "Varnish", description="HTTP cache")
    node("Decision", "Charcoal uses Django 5", rationale="charcoal only")
    node("Person", "Stuart Marshall", role="developer", email="stuart@example.com")
    node("Decision", "Old tile approach", rationale="superseded")
    s.forget_resource(ids["Old tile approach"], ids["Old tile approach"].value.rsplit("/", 1)[-1], "gone")
    arches = s.store_concept("Concept", "arches", {})
    pref = s.store_concept("Preference", "prefers tabs", {})

    s.create_link(ids["Use varnish for tiles"], ids["quartz"], "affects", {})
    s.create_link(ids["Arches restore duplicates post_save"], ids["quartz"], "appliesTo", {})
    s.create_link(ids["Old tile approach"], ids["quartz"], "affects", {})
    s.create_link(ids["Use varnish for tiles"], ids["Varnish"], "relatesTo", {})
    s.create_link(ids["Stuart Marshall"], ids["quartz"], "worksOn", {})
    s.create_link(ids["Stuart Marshall"], pref, "hasPreference", {})
    # the cross-project bridges a naive traversal would walk through
    s.create_link(ids["Arches restore duplicates post_save"], arches, "hasConcept", {})
    s.create_link(ids["Charcoal uses Django 5"], arches, "hasConcept", {})
    s.create_link(ids["Charcoal uses Django 5"], ids["charcoal"], "affects", {})
    s.create_link(ids["Use varnish for tiles"], ids["charcoal"], "relatesTo", {})
    s.save()
    return s


def names(result):
    return {n for group in result.nodes.values() for n in group}


def test_project_neighbourhood_is_shared(store):
    shared = names(share(store, "quartz"))
    assert {"quartz", "Use varnish for tiles", "Arches restore duplicates post_save",
            "Varnish", "Stuart Marshall", "arches"} <= shared


def test_nothing_leaks_through_hubs_or_other_projects(store):
    shared = names(share(store, "quartz"))
    assert "Charcoal uses Django 5" not in shared   # only reachable through the arches concept
    assert "charcoal" not in shared                 # another project, second hop
    assert "prefers tabs" not in shared             # personal preference
    assert "Old tile approach" not in shared        # forgotten


def test_export_strips_provenance_and_personal_details(store, tmp_path):
    result = share(store, "quartz", tmp_path / "handover")
    text = (tmp_path / "handover" / "graph.nq").read_text()
    assert "quartz__2026-10-01.md" not in text and "claude-code" not in text
    assert "stuart@example.com" not in text and "developer" in text
    copy = MemoryStore.open_or_create(tmp_path / "handover")
    assert copy.find_resource("Decision", "Use varnish for tiles") is not None
    assert copy.find_resource("Decision", "Charcoal uses Django 5") is None
    assert result.links == 5


def test_export_refuses_to_overwrite(store, tmp_path):
    share(store, "quartz", tmp_path / "handover")
    with pytest.raises(FileExistsError):
        share(store, "quartz", tmp_path / "handover")


def test_unknown_project_errors(store):
    with pytest.raises(ValueError, match="no Project named"):
        share(store, "nope")


# ------------------------------------------------------- read-only server

def _call(handlers, name, arguments):
    class Params:
        pass
    p = Params()
    p.name, p.arguments = name, arguments
    return asyncio.run(handlers["on_call_tool"](None, p))


def test_read_only_server_lists_and_serves_only_reads(store):
    h = tools.handlers(store, read_only=True)
    listed = {t.name for t in asyncio.run(h["on_list_tools"](None, None)).tools}
    assert listed == tools.READ_TOOLS
    found = _call(h, "memory_search", {"text": "varnish tiles"})
    assert not found.is_error and "varnish" in found.content[0].text.lower()
    refused = _call(h, "memory_store_resource", {"model": "Decision", "properties": {"name": "x"}})
    assert refused.is_error and "read-only" in refused.content[0].text
    assert store.find_resource("Decision", "x") is None


def test_full_server_still_lists_writes(store):
    listed = {t.name for t in asyncio.run(tools.handlers(store)["on_list_tools"](None, None)).tools}
    assert "memory_store_resource" in listed
