"""Arches resource models as a vocabulary, and plans compiled to Rós Madair's IR."""

import json
import os
import shutil
import subprocess
from datetime import date

import pytest

pytest.importorskip("alizarin")

import arches_fixture as fx  # noqa: E402

from ceist import DateRange, HasValue, LinkTo, Not, interpret, narrate  # noqa: E402
from ceist.arches import ArchesVocabulary  # noqa: E402
from ceist.arches_search import compile_checked, read_back as as_read_back, to_payload  # noqa: E402,E501
from ceist.readback import check  # noqa: E402
from ceist.rosmadair import Unsupported, compile_plan, read_back, to_query  # noqa: E402


@pytest.fixture(scope="module")
def data(tmp_path_factory):
    root = tmp_path_factory.mktemp("data")
    meta = fx.write(root)
    return root, meta


@pytest.fixture(scope="module")
def vocab(data):
    return ArchesVocabulary.from_data_dir(
        data[0], relation_forms={"architect": ["designed by"]},
        date_forms={"construction_date": ["built", "constructed"]})


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
    assert narrate(m.plan) == ("Find Buildings whose site is Site 'Leeds Dock' "
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


# dates and negation — Clock Tower 1845 Listed (Ada), Grain Warehouse 1872 Grade II
# (Isambard), Boat Shed 1903 Candidate (Ada, Salts Mill)
CASES_DATES_NOT = [
    ("which buildings were built before 1900?",
     ["Clock Tower", "Grain Warehouse"], ["Boat Shed"]),
    ("which buildings are not listed?", ["Boat Shed"], ["Clock Tower", "Grain Warehouse"]),
    ("which buildings were not designed by Ada Lovelace?",
     ["Grain Warehouse"], ["Clock Tower", "Boat Shed", "Leeds Dock", "Ada Lovelace"]),
    ("how many buildings are there?", ["3 Building records"], []),
    ("how many buildings built in the 1870s are on site Leeds Dock?", ["1 Building records"], []),
    ("which listed buildings were not built in the 1840s?",
     ["Grain Warehouse"], ["Clock Tower", "Boat Shed"]),
]


@pytest.mark.parametrize("question, expect, absent", CASES + CASES_DATES_NOT + [
    ("which sites have no buildings designed by Isambard Brunel?", ["Salts Mill"],
     ["Leeds Dock"]),
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


# ── Rós Madair: dates, negation, read-back ───────────────────────────────

def test_rosmadair_dates_and_not(vocab):
    m = interpret(vocab, "which listed buildings were not built in the 1840s?")
    q = to_query(m.plan, vocab)
    (concept, neg) = q["where"]["all"]
    assert concept["concept"]["path"] == "heritage_status"
    def day(*ymd):                     # proleptic Gregorian days since 1970, as quantize_date
        return (date(*ymd) - date(1970, 1, 1)).days
    assert neg == {"not": {"range": {"path": "construction_date",
                                     "lo": day(1840, 1, 1), "hi": day(1849, 12, 31)}}}
    m = interpret(vocab, "which buildings were built before 1900?")
    r = to_query(m.plan, vocab)["where"]["range"]
    assert r["hi"] == day(1899, 12, 31) and r["lo"] <= -10 ** 9   # open below


def test_rosmadair_negated_link_subtracts(vocab, data):
    m = interpret(vocab, "which buildings were not designed by Ada Lovelace?")
    with pytest.raises(Unsupported, match="compile_plan"):
        to_query(m.plan, vocab)
    c = compile_plan(m.plan, vocab)
    assert "where" not in c.query                                 # every Building …
    assert c.minus == [{"model": fx.BUILDING, "measures": ["select_ids"],
                        "where": {"has_link": {"path": "architect",
                                               "target": data[1]["ids"]["ada"]}}}]


@pytest.mark.parametrize("question", [q for q, _e, _a in CASES + CASES_DATES_NOT])
def test_rosmadair_reads_back(vocab, question):
    m = interpret(vocab, question)
    assert check(m.plan, read_back(compile_plan(m.plan, vocab), vocab)).ok


def test_rosmadair_readback_catches_a_wrong_query(vocab, data):
    m = interpret(vocab, "which listed buildings are on site Leeds Dock?")
    c = compile_plan(m.plan, vocab)
    for part in c.query["where"]["all"]:
        if "has_link" in part:
            part["has_link"]["target"] = data[1]["ids"]["mill"]  # a compiler bug
    verdict = check(m.plan, read_back(c, vocab))
    assert not verdict.ok and "Salts Mill" in verdict.said


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


def test_arches_search_dates_and_not(vocab, data):
    m = interpret(vocab, "which listed buildings were not built in the 1840s?")
    p = to_payload(m.plan, vocab, concept_operator="REFERENCES_ANY")
    _valid(p)
    date = next(c for c in p["clauses"] if c["subject"]["node_alias"] == "construction_date")
    assert date["operator"] == "BETWEEN" and date["quantifier"] == "NONE"
    assert [o["value"] for o in date["operands"]] == ["1840-01-01", "1849-12-31"]
    m = interpret(vocab, "which buildings were built before 1900?")
    (c,) = to_payload(m.plan, vocab)["clauses"]
    assert c["operator"] == "LESS_THAN_OR_EQUALS" and c["operands"][0]["value"] == "1899-12-31"


def test_arches_search_negated_hop(vocab):
    m = interpret(vocab, "which sites have no buildings designed by Isambard Brunel?")
    p = to_payload(m.plan, vocab)
    _valid(p)
    child = p["groups"][0]
    assert child["relationship"]["traversal_quantifier"] == "NONE"
    assert child["clauses"][0]["quantifier"] == "ANY"            # the architect isn't negated


@pytest.mark.parametrize("question", [q for q, _e, _a in CASES + CASES_DATES_NOT] + [
    "which sites have no buildings designed by Isambard Brunel?",
    "which sites have buildings designed by Ada Lovelace?"])
def test_arches_search_reads_back(vocab, question):
    m = interpret(vocab, question)
    payload, verdict = compile_checked(m.plan, vocab, concept_operator="REFERENCES_ANY")
    assert verdict.ok


def test_arches_search_readback_catches_a_wrong_payload(vocab):
    m = interpret(vocab, "which buildings are not listed?")
    p = to_payload(m.plan, vocab, concept_operator="REFERENCES_ANY")
    p["clauses"][0]["quantifier"] = "ANY"                       # the negation lost
    said = as_read_back(p, vocab, "REFERENCES_ANY")
    assert not check(m.plan, said).ok
    p["clauses"][0]["quantifier"] = "NONE"
    p["clauses"][0]["operands"][0]["value"] = p["clauses"][0]["operands"][0]["value"][:1]
    said = as_read_back(p, vocab, "REFERENCES_ANY")              # Grade II dropped
    assert not check(m.plan, said).ok


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


@pytest.mark.parametrize("question, expect, absent", CASES + CASES_DATES_NOT)
def test_end_to_end(vocab, snapshot, question, expect, absent):
    from ceist.rosmadair import ask
    out = ask(question, vocab, str(snapshot))
    assert "Site '" not in out and "Person '" not in out, out    # only the asked-for type
    for e in expect:
        assert e in out, out
    for a in absent:
        assert a not in out, out


def test_end_to_end_explains(vocab, snapshot):
    from ceist.rosmadair import ask
    out = ask("which listed buildings are on site Leeds Dock?", vocab, str(snapshot), explain=True)
    assert "── query ──" in out and '"has_link"' in out and "Find Buildings" in out
    json.loads(out.split("── query ──\n  ")[1].splitlines()[0])
    assert "── query says ──" in out and "✓ matches" in out


def test_end_to_end_refuses_a_query_that_reads_back_wrong(vocab, snapshot, monkeypatch):
    import ceist.rosmadair as rm
    real = rm._expr

    def buggy(plan, v):                         # a compiler that loses negations
        out = real(plan, v)
        return out["not"] if isinstance(out, dict) and "not" in out else out
    monkeypatch.setattr(rm, "_expr", buggy)
    out = rm.ask("which buildings are not listed?", vocab, str(snapshot), explain=True)
    assert "✗ differs" in out and "(not run" in out and "Clock Tower" not in out.split("(not run")[1]


def test_vocabulary_bundle_phrasings(data):
    """A bundle's link and date phrasings ground exactly; qualified ones are skipped."""
    bundle = {"format": "ceist.vocab/1", "models": {"Building": {
        "nodes": {"construction_date": {"kind": "date"}, "architect": {"kind": "link"},
                  "site": {"kind": "link"}},
        "entries": [
            {"phrases": ["put up", "erected"], "kind": "date", "node": "construction_date"},
            {"phrases": ["drawn up by"], "kind": "link", "node": "architect"},
            {"phrases": ["sited by"], "kind": "link", "node": "site",
             "qualifier": {"node": "heritage_status", "value": "Listed"}}]}}}
    v = ArchesVocabulary.from_data_dir(data[0], bundle=bundle)
    assert v.skipped_qualified == 1
    m = interpret(v, "which buildings were put up before 1900?")
    assert isinstance(m.plan.where[0], DateRange) and m.plan.where[0].field == "construction_date"
    m = interpret(v, "which buildings were drawn up by Ada Lovelace?")
    assert m.plan.where[0].relation == "architect"
