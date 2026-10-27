"""Arches resource models as a vocabulary, and plans compiled to Rós Madair's IR."""

import json
import os
import shutil
import subprocess

import pytest

pytest.importorskip("alizarin")

import arches_fixture as fx  # noqa: E402

from ceist import HasValue, LinkTo, interpret, narrate  # noqa: E402
from ceist.arches import ArchesVocabulary  # noqa: E402
from ceist.arches_search import to_payload  # noqa: E402
from ceist.rosmadair import Unsupported, to_query  # noqa: E402


@pytest.fixture(scope="module")
def data(tmp_path_factory):
    root = tmp_path_factory.mktemp("data")
    meta = fx.write(root)
    return root, meta


@pytest.fixture(scope="module")
def vocab(data):
    return ArchesVocabulary.from_data_dir(data[0], relation_forms={"architect": ["designed by"]})


def test_vocabulary_reads_types_relations_values_and_names(vocab):
    words = vocab.type_words()
    assert words["buildings"] == "Building" and words["sites"] == "Site"
    rels = {r.name: r for r in vocab.relations()}
    assert rels["site"].domain == {"Building"} and rels["site"].range == {"Site"}
    assert "architect" in rels["architect"].forms
    phrases = {v.phrase: v for v in vocab.values()}
    assert {"listed", "protected", "grade ii", "candidate"} <= set(phrases)
    assert phrases["listed"].field == "heritage_status"
    assert phrases["protected"].value == phrases["listed"].value    # an alt label
    assert vocab.rank_entities({"leeds", "dock"})[0][1].name == "Leeds Dock"


def test_listed_buildings_on_a_site(vocab, data):
    m = interpret(vocab, "which listed buildings are on site Leeds Dock?")
    q = to_query(m.plan, vocab, 25)
    listed = data[1]["concepts"]["Listed"]
    assert q["model"] == fx.BUILDING and q["measures"] == ["select_ids"]
    assert {"has_link": {"path": "site", "target": data[1]["ids"]["dock"]}} in q["where"]["all"]
    assert {"concept": {"path": "heritage_status", "op": "descendant_or_self_of",
                        "value": listed}} in q["where"]["all"]


def test_count_and_multi_hop(vocab):
    m = interpret(vocab, "how many buildings designed by Ada Lovelace are on site Salts Mill?")
    q = to_query(m.plan, vocab)
    assert q["measures"] == ["count_records"] and "limit" not in q
    paths = {next(iter(p.values()))["path"] for p in q["where"]["all"]}
    assert paths == {"architect", "site"}


def test_backwards_link_is_refused_by_name(vocab):
    m = interpret(vocab, "which sites have buildings designed by Ada Lovelace?")
    assert m.plan.type == "Site" and m.plan.where[0].direction == "in"
    with pytest.raises(Unsupported, match="backwards"):
        to_query(m.plan, vocab)


def test_narration(vocab):
    m = interpret(vocab, "which protected buildings are on site Leeds Dock?")
    assert narrate(m.plan) == ("Find Buildings that site Site 'Leeds Dock' "
                               "and whose heritage status is Listed.")


# ── Alizarin: answered straight from the data_dir ──────────────────────────

CASES = [
    ("which listed buildings are on site Leeds Dock?",
     ["Clock Tower", "Grain Warehouse"], ["Boat Shed"]),           # Grade II is under Listed
    ("which buildings were designed by Ada Lovelace?", ["Clock Tower", "Boat Shed"],
     ["Grain Warehouse"]),
    ("how many candidate buildings are there?", ["1 Building records"], []),
    ("which buildings are on site Salts Mill?", ["Boat Shed"], ["Clock Tower"]),
]


@pytest.mark.parametrize("question, expect, absent", CASES + [
    # what Rós Madair can't walk, the data_dir can
    ("which sites have buildings designed by Isambard Brunel?", ["Leeds Dock"], ["Salts Mill"]),
    ("how many buildings designed by Ada Lovelace are on site Salts Mill?",
     ["1 Building records"], []),
])
def test_alizarin(vocab, question, expect, absent):
    from ceist.alizarin import ask
    out = ask(question, vocab)
    for e in expect:
        assert e in out, out
    for a in absent:
        assert a not in out, out


# ── Arches Search ──────────────────────────────────────────────────────────

GROUP_KEYS = {"graph_slug", "scope", "logic", "clauses", "groups", "aggregations",
              "relationship"}


def _valid(group):
    """The structure arches-search's PayloadValidator requires."""
    assert set(group) == GROUP_KEYS and group["logic"] == "AND"
    for c in group["clauses"]:
        assert {"type", "quantifier", "subject", "operator", "operands"} <= set(c)
        assert {"type", "graph_slug", "node_alias", "search_models"} <= set(c["subject"])
    if group["relationship"] is not None:
        assert {"path", "is_inverse", "traversal_quantifier"} <= set(group["relationship"])
    for g in group["groups"]:
        _valid(g)


def test_arches_search_link_and_concept(vocab, data):
    m = interpret(vocab, "which listed buildings are on site Leeds Dock?")
    with pytest.raises(Unsupported, match="concept"):
        to_payload(m.plan, vocab)                   # no concept facet by default
    p = to_payload(m.plan, vocab, concept_operator="REFERENCES_ANY")
    _valid(p)
    assert p["graph_slug"] == "building"
    by_alias = {c["subject"]["node_alias"]: c for c in p["clauses"]}
    assert by_alias["site"]["operands"][0]["value"] == [data[1]["ids"]["dock"]]
    c = data[1]["concepts"]
    assert by_alias["heritage_status"]["operands"][0]["value"] == [c["Listed"], c["Grade II"]]


def test_arches_search_walks_backwards(vocab, data):
    m = interpret(vocab, "which sites have buildings designed by Ada Lovelace?")
    p = to_payload(m.plan, vocab)
    _valid(p)
    assert p["graph_slug"] == "site" and not p["clauses"]
    child = p["groups"][0]
    assert child["graph_slug"] == "building"
    assert child["relationship"] == {
        "path": {"type": "NODE", "graph_slug": "building", "node_alias": "site"},
        "is_inverse": True, "traversal_quantifier": "ANY"}
    assert child["clauses"][0]["subject"]["node_alias"] == "architect"
    assert child["clauses"][0]["operands"][0]["value"] == [data[1]["ids"]["ada"]]


# ── end to end over a real Rós Madair snapshot (needs the Rust tools) ──────

def _tools():
    emit = os.environ.get("ROS_MADAIR_EMIT") or shutil.which("ros-madair-emit")
    try:
        import ros_madair  # noqa: F401
    except ImportError:
        return None
    return emit


@pytest.fixture(scope="module")
def snapshot(data, tmp_path_factory):
    emit = _tools()
    if not emit:
        pytest.skip("needs ros_madair bindings and ros-madair-emit (ROS_MADAIR_EMIT)")
    out = tmp_path_factory.mktemp("snapshot")
    subprocess.run([emit, str(data[0]), str(out)], check=True, capture_output=True)
    return out


@pytest.mark.parametrize("question, expect, absent", CASES)
def test_end_to_end(vocab, snapshot, question, expect, absent):
    from ceist.rosmadair import ask
    out = ask(question, vocab, str(snapshot))
    for e in expect:
        assert e in out, out
    for a in absent:
        assert a not in out, out


def test_end_to_end_explains(vocab, snapshot):
    from ceist.rosmadair import ask
    out = ask("which listed buildings are on site Leeds Dock?", vocab, str(snapshot), explain=True)
    assert "── query ──" in out and '"has_link"' in out and "Find Buildings" in out
    json.loads(out.split("── query ──\n  ")[1].splitlines()[0])
