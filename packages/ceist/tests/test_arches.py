"""Arches resource models as a vocabulary, and plans compiled to Rós Madair's IR."""

import json
import os
import shutil
import subprocess
from datetime import date

import arches_fixture as fx
import pytest

from ceist import DateRange, Detail, HasValue, LinkTo, Not, OnTile, Plan, interpret, narrate
from ceist.plan import EntityRef
from ceist.arches import ArchesVocabulary
from ceist.arches_search import compile_checked, read_back as as_read_back, to_payload  # noqa: E501
from ceist.readback import check
from ceist.rosmadair import Unsupported, compile_plan, read_back, to_query


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


def test_backwards_link_compiles_to_on_backlink(vocab, data):
    m = interpret(vocab, "which sites have buildings designed by Ada Lovelace?")
    assert m.plan.type == "Site" and m.plan.where[0].direction == "in"
    q = to_query(m.plan, vocab)
    assert q["where"] == {"on_backlink": {"path": "site", "model": fx.BUILDING, "where": {
        "has_link": {"path": "architect", "target": data[1]["ids"]["ada"]}}}}
    assert check(m.plan, read_back(compile_plan(m.plan, vocab), vocab)).ok


def test_backwards_link_from_one_record_is_refused_by_name(vocab, data):
    tower = EntityRef(vocab.entity(data[1]["ids"]["tower"]))
    with pytest.raises(Unsupported, match="backwards"):
        to_query(Plan("Site", [LinkTo("site", tower, "in", style="field")]), vocab)


def _classed(root, site_class="E53_Place"):
    """The fixture with CIDOC-CRM classes, and an architect link that names no target model."""
    fx.write(root)
    crm = "http://www.cidoc-crm.org/cidoc-crm/"
    roots = {fx.SITE: site_class, fx.PERSON: "E21_Person", fx.BUILDING: "E22_Human-Made_Object"}
    for gid, cls in roots.items():
        p = root / "graphs" / f"{gid}.json"
        doc = json.loads(p.read_text())
        for n in doc["graph"][0]["nodes"]:
            if n["istopnode"] and cls:
                n["ontologyclass"] = crm + cls
            if n["alias"] == "architect":
                n["config"], n["ontologyclass"] = {"graphs": []}, crm + "E39_Actor"
        p.write_text(json.dumps(doc))
    return ArchesVocabulary.from_data_dir(root)


def test_a_link_naming_no_model_fits_by_its_cidoc_crm_class(tmp_path):
    vocab = _classed(tmp_path / "classed")
    m = interpret(vocab, "which buildings have the architect Leeds Dock?")
    assert m.plan is None and "'architect' (architect) can't join Building and Site" in m.refused
    m = interpret(vocab, "which buildings have the architect Ada Lovelace?")
    assert narrate(m.plan) == "Find Buildings whose architect is Person 'Ada Lovelace'."
    # a model with no class fits as before
    unclassed = _classed(tmp_path / "unclassed", site_class=None)
    m = interpret(unclassed, "which buildings have the architect Leeds Dock?")
    assert narrate(m.plan) == "Find Buildings whose architect is Site 'Leeds Dock'."


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


# "or": either value of one field, or a link to either record
CASES_OR = [
    ("which grade ii or candidate buildings are there?",
     ["Grain Warehouse", "Boat Shed"], ["Clock Tower"]),
    ("how many buildings are designed by Ada Lovelace or Isambard Brunel?",
     ["3 Building records"], []),
]


@pytest.mark.parametrize("question, expect, absent", CASES + CASES_DATES_NOT + CASES_OR + [
    ("which sites have no buildings designed by Isambard Brunel?", ["Salts Mill"],
     ["Leeds Dock"]),
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


def test_a_named_records_own_fields_read_from_its_tiles(vocab, data):
    from ceist.alizarin import RecordTiles, ask
    from ceist.rosmadair import compile_detail, detail_lines, read_back_detail, read_detail
    assert ask("what is the heritage status of Clock Tower?", vocab) == (
        "Building 'Clock Tower': heritage status Listed")
    tower = vocab.entity(data[1]["ids"]["tower"])
    d = Detail(tower, [("site", "site"), ("construction_date", "construction date")])
    q = compile_detail(d, vocab)
    assert check(d, read_back_detail(q, vocab)).ok
    tiles = RecordTiles(vocab)
    assert read_detail(tiles, q, vocab) == [("site", ["Leeds Dock"]),
                                            ("construction date", ["1845-06-01"])]
    tiles.by_id[tower.id] = [t for t in tiles.by_id[tower.id]
                             if q["nodes"][0] not in t["data"]]
    assert detail_lines(d, read_detail(tiles, q, vocab)) == [
        "Building 'Clock Tower': no site recorded; construction date 1845-06-01"]


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


@pytest.mark.parametrize("question, expect, absent", CASES + CASES_DATES_NOT + CASES_OR)
def test_end_to_end(vocab, snapshot, question, expect, absent):
    from ceist.rosmadair import ask
    out = ask(question, vocab, str(snapshot))
    assert "Site '" not in out and "Person '" not in out, out    # only the asked-for type
    for e in expect:
        assert e in out, out
    for a in absent:
        assert a not in out, out


@pytest.mark.parametrize("question, expect, absent", [
    ("which sites have buildings designed by Isambard Brunel?", ["Leeds Dock"], ["Salts Mill"]),
    ("which sites have no buildings designed by Isambard Brunel?", ["Salts Mill"],
     ["Leeds Dock"]),
])
def test_end_to_end_reverse_link(vocab, snapshot, question, expect, absent):
    from ceist.rosmadair import ask
    out = ask(question, vocab, str(snapshot))
    assert "Building '" not in out, out
    for e in expect:
        assert e in out, out
    for a in absent:
        assert a not in out, out


def test_end_to_end_chain_through_another_model(vocab, data, snapshot):
    """Buildings on a site where Isambard designed a building: a hop into Site
    and back, so the compiler needs the Site graph passed as `linked`."""
    from ceist.rosmadair import linked_models
    ids = data[1]["ids"]
    isambard = EntityRef(vocab.entity(ids["isambard"]))
    by_isambard = Plan("Building", [LinkTo("architect", isambard, style="field")])
    on_that_site = Plan("Site", [LinkTo("site", by_isambard, "in", style="field")])
    plan = Plan("Building", [LinkTo("site", on_that_site, style="field")])
    q = to_query(plan, vocab)
    assert linked_models(q) == [fx.SITE]
    assert _resolve(snapshot, vocab, q) == {ids["tower"], ids["warehouse"]}
    import ros_madair
    graph, site = (ros_madair.Graph(json.dumps(vocab.model(t).doc)) for t in ("Building", "Site"))
    counted = dict(q, measures=["count_records"])
    assert ros_madair.Reader(str(snapshot)).count(json.dumps(counted), graph, linked=[site]) == 2


def test_end_to_end_explains(vocab, snapshot):
    from ceist.rosmadair import ask
    out = ask("which listed buildings are on site Leeds Dock?", vocab, str(snapshot), explain=True)
    assert "── query ──" in out and '"has_link"' in out and "Find Buildings" in out
    json.loads(out.split("── query ──\n  ")[1].splitlines()[0])
    assert "── query says ──" in out and "✓ matches" in out


def test_end_to_end_reads_a_named_records_own_links(vocab, snapshot):
    # the Clock Tower holds the link to Leeds Dock, so a backlink alone finds nothing
    from ceist.rosmadair import ask
    out = ask("which sites is the Clock Tower at?", vocab, str(snapshot))
    assert "Site 'Leeds Dock'" in out and "Salts Mill" not in out, out


def test_end_to_end_a_named_records_own_field(vocab, snapshot):
    from ceist.rosmadair import ask
    out = ask("what heritage status is Clock Tower?", vocab, str(snapshot), explain=True)
    assert "Show the heritage status of Building 'Clock Tower'." in out and "✓ matches" in out
    assert out.endswith("Building 'Clock Tower': heritage status Listed"), out


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
    """A bundle's link and date phrasings ground exactly; a qualified entry
    whose value isn't in its node's collection is counted, not guessed."""
    bundle = {"format": "ceist.vocab/1", "models": {"Building": {
        "nodes": {"construction_date": {"kind": "date"}, "architect": {"kind": "link"},
                  "actor": {"kind": "link"}},
        "entries": [
            {"phrases": ["put up", "erected"], "kind": "date", "node": "construction_date"},
            {"phrases": ["drawn up by"], "kind": "link", "node": "architect"},
            {"phrases": ["painted by"], "kind": "link", "node": "actor",
             "qualifier": {"node": "actor_role", "value": "Painter"}}]}}}
    v = ArchesVocabulary.from_data_dir(data[0], bundle=bundle)
    m = interpret(v, "which buildings were put up before 1900?")
    assert isinstance(m.plan.where[0], DateRange) and m.plan.where[0].field == "construction_date"
    m = interpret(v, "which buildings were drawn up by Ada Lovelace?")
    assert m.plan.where[0].relation == "architect"
    v.relations()
    assert v.skipped_qualified == 1                      # no "Painter" in the roles thesaurus


# ── qualified links: a link and a value on the SAME entry (tile) ────────────

ROLE_BUNDLE = {"format": "ceist.vocab/1", "models": {"Building": {
    "nodes": {"actor": {"kind": "link", "targets": ["Person"]}},
    "entries": [
        {"phrases": ["designed by"], "kind": "link", "node": "actor",
         "qualifier": {"node": "actor_role", "value": "Architect"}},
        {"phrases": ["built by"], "kind": "link", "node": "actor",
         "qualifier": {"node": "actor_role", "value": "Builder"}},
        {"phrases": ["associated with"], "kind": "link", "node": "actor"}]}}}


@pytest.fixture(scope="module")
def roles(data):
    return ArchesVocabulary.from_data_dir(data[0], bundle=ROLE_BUNDLE)


def test_qualified_link_is_planned(roles, data):
    m = interpret(roles, "which buildings were designed by Ada Lovelace?")
    (c,) = m.plan.where
    assert c.group == "associated_actor"
    link, role = c.conditions
    assert link.relation == "actor" and link.target.entity.id == data[1]["ids"]["ada"]
    assert link.qualifier is None
    assert role == HasValue("actor_role", data[1]["concepts"]["Architect"], "Architect")
    assert narrate(m.plan) == ("Find Buildings with one associated actor entry (whose actor "
                               "is Person 'Ada Lovelace' and whose actor role is Architect).")


@pytest.mark.parametrize("question, expect, absent", [
    # Ada is the Grain Warehouse's BUILDER; its architect is Isambard — same entry or nothing
    ("which buildings were designed by Ada Lovelace?", ["Clock Tower"], ["Grain Warehouse"]),
    ("which buildings were built by Ada Lovelace?", ["Grain Warehouse"], ["Clock Tower"]),
    ("which buildings were designed by Isambard Brunel?", ["Grain Warehouse"], ["Clock Tower"]),
    ("which buildings are associated with Ada Lovelace?", ["Clock Tower", "Grain Warehouse"], []),
])
def test_qualified_link_on_the_same_entry(roles, question, expect, absent):
    from ceist.alizarin import ask
    out = ask(question, roles)
    for e in expect:
        assert e in out, out
    for a in absent:
        assert a not in out, out


def test_qualified_link_to_rosmadair_on_tile(roles, data):
    m = interpret(roles, "which buildings were designed by Ada Lovelace?")
    q = to_query(m.plan, roles)
    assert q["where"] == {"on_tile": [
        {"has_link": {"path": "actor", "target": data[1]["ids"]["ada"]}},
        {"concept": {"path": "actor_role", "op": "descendant_or_self_of",
                     "value": data[1]["concepts"]["Architect"]}}]}
    assert check(m.plan, read_back(compile_plan(m.plan, roles), roles)).ok
    wrong = compile_plan(m.plan, roles)
    wrong.query["where"] = {"all": wrong.query["where"]["on_tile"]}   # separate facts: broader
    assert not check(m.plan, read_back(wrong, roles)).ok


def test_qualified_link_on_a_real_snapshot(roles, snapshot):
    from ceist.rosmadair import ask
    out = ask("which buildings were designed by Ada Lovelace?", roles, str(snapshot))
    assert "Clock Tower" in out and "Grain Warehouse" not in out, out


def test_qualified_link_to_arches_search_tile_scope(roles, data):
    m = interpret(roles, "which buildings were designed by Ada Lovelace?")
    payload, verdict = compile_checked(m.plan, roles, concept_operator="REFERENCES_ANY")
    assert verdict.ok and payload["scope"] == "TILE"
    assert [c["subject"]["node_alias"] for c in payload["clauses"]] == ["actor", "actor_role"]
    # alongside another condition: a RESOURCE search with a nested TILE group
    both = interpret(roles, "which listed buildings were designed by Ada Lovelace?")
    payload, verdict = compile_checked(both.plan, roles, concept_operator="REFERENCES_ANY")
    _valid(payload)
    assert verdict.ok and payload["scope"] == "RESOURCE"
    assert [c["subject"]["node_alias"] for c in payload["clauses"]] == ["heritage_status"]
    (tile,) = payload["groups"]
    assert tile["scope"] == "TILE" and tile["relationship"] is None
    assert [c["subject"]["node_alias"] for c in tile["clauses"]] == ["actor", "actor_role"]
    # read-back notices if the nested group loses its tile scope
    tile["scope"] = "RESOURCE"
    from ceist.arches_search import read_back as as_rb
    assert not check(both.plan, as_rb(payload, roles, "REFERENCES_ANY")).ok


# ── OnTile: conditions that hold on one tile ─────────────────────────────

def _entry(vocab, data, who, role):
    person = vocab.entity(data[1]["ids"][who])
    return OnTile("associated_actor", [LinkTo("actor", EntityRef(person), style="field"),
                                       HasValue("actor_role", data[1]["concepts"][role], role)])


def _resolve(snapshot, vocab, query, type_name="Building"):
    """The records of the type a query selects (a vacuous filter selects every record)."""
    import ros_madair
    from ceist.rosmadair import linked_models
    graph = ros_madair.Graph(json.dumps(vocab.model(type_name).doc))
    linked = [ros_madair.Graph(json.dumps(vocab.model(vocab.by_graph[m].name).doc))
              for m in linked_models(query)]
    ids = ros_madair.Reader(str(snapshot)).resolve(json.dumps(query), graph, linked=linked)
    return set(ids) & vocab.ids_of(type_name)


def test_on_tile_compiles_on_every_backend_and_reads_back(roles, data):
    from ceist.alizarin import Tiles, evaluate
    ids = data[1]["ids"]
    plan = Plan("Building", [_entry(roles, data, "ada", "Builder")])
    assert evaluate(plan, Tiles(roles)) == {ids["warehouse"]}
    compiled = compile_plan(plan, roles)
    assert compiled.query["where"] == {"on_tile": [
        {"has_link": {"path": "actor", "target": ids["ada"]}},
        {"concept": {"path": "actor_role", "op": "descendant_or_self_of",
                     "value": data[1]["concepts"]["Builder"]}}]}
    assert read_back(compiled, roles) == plan
    assert check(plan, read_back(compiled, roles)).ok
    payload, verdict = compile_checked(plan, roles, concept_operator="REFERENCES_ANY")
    assert verdict.ok and payload["scope"] == "TILE"
    assert as_read_back(payload, roles, "REFERENCES_ANY") == plan
    # a different value on the entry reads back as a different question
    other = Plan("Building", [_entry(roles, data, "ada", "Architect")])
    assert not check(other, read_back(compiled, roles)).ok


def test_values_on_different_tiles_do_not_match(roles, data, snapshot):
    """The Grain Warehouse has Ada (Builder) on one tile and an Architect on
    another: one entry with both is not there."""
    from ceist.alizarin import Tiles, evaluate
    ids = data[1]["ids"]
    plan = Plan("Building", [_entry(roles, data, "ada", "Architect")])
    assert evaluate(plan, Tiles(roles)) == {ids["tower"]}
    assert _resolve(snapshot, roles, to_query(plan, roles)) == {ids["tower"]}
    # the same two conditions anywhere on the record match the warehouse too
    loose = Plan("Building", plan.where[0].conditions)
    assert evaluate(loose, Tiles(roles)) == {ids["tower"], ids["warehouse"]}
    assert _resolve(snapshot, roles, to_query(loose, roles)) == {ids["tower"], ids["warehouse"]}


@pytest.mark.parametrize("question", [
    "which buildings were designed by Ada Lovelace?",
    "which buildings were built by Ada Lovelace?",
    "which buildings were designed by Isambard Brunel?",
    "which listed buildings were designed by Ada Lovelace?",
    "which buildings were not designed by Ada Lovelace?",
    "which sites have buildings designed by Ada Lovelace?",
])
def test_qualified_links_answer_the_same_through_on_tile(roles, data, snapshot, question):
    """The compatibility form (LinkTo.qualifier) and the OnTile the planner
    now emits select the same records, on Alizarin and on a snapshot."""
    from dataclasses import replace

    from ceist.alizarin import Tiles, evaluate

    def shim(plan):
        where = []
        for c in plan.where:
            negated = isinstance(c, Not)
            inner = c.condition if negated else c
            if isinstance(inner, OnTile):
                link, qual = inner.conditions
                inner = replace(link, qualifier=qual)
            elif isinstance(inner, LinkTo) and isinstance(inner.target, Plan):
                inner = replace(inner, target=shim(inner.target))
            where.append(Not(inner) if negated else inner)
        return replace(plan, where=where)

    plan = interpret(roles, question).plan
    old = shim(plan)
    assert old != plan
    tiles = Tiles(roles)
    assert evaluate(old, tiles) == evaluate(plan, tiles) != set()

    def run(p):
        compiled = compile_plan(p, roles)
        ids = _resolve(snapshot, roles, compiled.query, p.type)
        for m in compiled.minus:
            ids -= _resolve(snapshot, roles, m, p.type)
        return ids

    assert run(old) == run(plan) == evaluate(plan, tiles)


def test_or_joins_values_of_one_field_or_records_of_one_link(vocab, data):
    ids, concepts = data[1]["ids"], data[1]["concepts"]
    m = interpret(vocab, "which grade ii or candidate buildings are there?")
    assert narrate(m.plan) == "Find Buildings whose heritage status is Grade II or Candidate."
    assert to_query(m.plan, vocab)["where"] == {"any": [
        {"concept": {"path": "heritage_status", "op": "descendant_or_self_of",
                     "value": concepts[label]}} for label in ("Grade II", "Candidate")]}
    m = interpret(vocab, "how many buildings are designed by Ada Lovelace or Isambard Brunel?")
    assert narrate(m.plan) == ("Count Buildings whose architect is Person 'Ada Lovelace' "
                               "or Person 'Isambard Brunel'.")
    compiled = compile_plan(m.plan, vocab)
    assert compiled.query["where"] == {"any": [
        {"has_link": {"path": "architect", "target": ids[p]}} for p in ("ada", "isambard")]}
    assert check(m.plan, read_back(compiled, vocab)).ok
    with pytest.raises(Unsupported, match="'or'"):
        to_payload(m.plan, vocab)


def test_or_refuses_across_fields_and_under_not(vocab):
    m = interpret(vocab, "which listed or builder buildings are there?")
    assert m.plan is None
    assert "'or' joins 'listed' and 'builder', which aren't values of one field" in m.refused
    m = interpret(vocab, "which buildings are not on site Leeds Dock or Salts Mill?")
    assert m.plan is None and "'not' with 'or'" in m.refused


def test_group_by_counts_per_linked_record(vocab, data, monkeypatch):
    import ceist.rosmadair as rm
    ids = data[1]["ids"]
    m = interpret(vocab, "list buildings by site")
    assert narrate(m.plan) == "Count Buildings, by site."
    compiled = compile_plan(m.plan, vocab)
    assert set(compiled.values) == {ids["dock"], ids["mill"]}
    assert check(m.plan, read_back(compiled, vocab)).ok
    m = interpret(vocab, "which architect has the most candidate buildings?")
    assert narrate(m.plan) == ("Count Buildings whose heritage status is Candidate, "
                               "by architect: the one with the most.")
    with pytest.raises(Unsupported, match="counting by"):
        to_payload(m.plan, vocab)
    monkeypatch.setattr(rm, "GROUP_CAP", 1)
    with pytest.raises(Unsupported, match="over the 1 a count per record runs"):
        compile_plan(m.plan, vocab)


@pytest.mark.parametrize("question, expect, absent", [
    ("list buildings by site", ["- Leeds Dock: 2 Building records",
                                "- Salts Mill: 1 Building records"], []),
    ("which architect has the most buildings?", ["- Ada Lovelace: 2 Building records"],
     ["Isambard"]),
    ("which architect has the fewest listed buildings?", ["- Ada Lovelace: 1 Building records",
                                                          "- Isambard Brunel: 1 Building records"],
     []),
])
def test_end_to_end_group_by(vocab, snapshot, question, expect, absent):
    from ceist.rosmadair import ask
    out = ask(question, vocab, str(snapshot))
    for e in expect:
        assert e in out, out
    for a in absent:
        assert a not in out, out


# ── near and within N km of a named record ─────────────────────────────────

@pytest.fixture(scope="module")
def places(tmp_path_factory):
    root = tmp_path_factory.mktemp("places")
    meta = fx.write(root, places=True)
    return root, ArchesVocabulary.from_data_dir(root), meta


@pytest.mark.parametrize("question, said, expect, absent", [
    ("which buildings are near Clock Tower?", "within 5 km of Building 'Clock Tower'",
     ["Grain Warehouse"], ["Boat Shed", "Clock Tower"]),
    ("which buildings are within 10 km of Clock Tower?", "within 10 km of Building 'Clock Tower'",
     ["Grain Warehouse", "Boat Shed"], ["Clock Tower"]),
    ("which buildings are within 1 mile of Clock Tower?", "within 1 mile of Building 'Clock Tower'",
     ["Grain Warehouse"], ["Boat Shed"]),
    # inside the site's polygon is 0 km from it
    ("which buildings are near Salts Mill?", "within 5 km of Site 'Salts Mill'",
     ["Boat Shed"], ["Grain Warehouse", "Clock Tower"]),
])
def test_near_a_named_record(places, question, said, expect, absent):
    from ceist.alizarin import ask
    _root, vocab, _meta = places
    meaning = interpret(vocab, question)
    assert said in narrate(meaning.plan), meaning.refused
    out = ask(question, vocab)
    for e in expect:
        assert f"'{e}'" in out, out
    for a in absent:
        assert f"'{a}'" not in out, out


@pytest.mark.parametrize("question, refused", [
    ("which buildings are near Leeds Dock?", "'Leeds Dock' has no location to measure from"),
    ("which persons are near Clock Tower?", "Person records have no location"),
    ("which buildings are not near Clock Tower?", "'not near' isn't supported yet"),
])
def test_near_refuses(places, question, refused):
    meaning = interpret(places[1], question)
    assert meaning.plan is None and meaning.refused == refused, meaning.refused


def test_near_compiles_to_a_bbox_and_reads_back(places):
    _root, vocab, _meta = places
    plan = interpret(vocab, "which buildings are within 2 km of Clock Tower?").plan
    compiled = compile_plan(plan, vocab)
    box = compiled.query["where"]["bbox"]
    assert box["path"] == "location" and box["min_lat"] < 53.8 - 0.017 < 53.8 + 0.017 < box["max_lat"]
    assert compiled.near == [{"record": plan.where[0].entity.id, "km": 2.0, "path": "location"}]
    assert check(plan, read_back(compiled, vocab)).ok
    compiled.query["where"]["bbox"]["max_lat"] += 1          # a wider box than the distance
    assert not check(plan, read_back(compiled, vocab)).ok


def test_end_to_end_near(places, tmp_path_factory):
    emit = _tools()
    if not emit:
        pytest.skip("needs ros_madair bindings and ros-madair-emit (ROS_MADAIR_EMIT)")
    from ceist.rosmadair import ask
    root, vocab, _meta = places
    out = tmp_path_factory.mktemp("places-snapshot")
    subprocess.run([emit, str(root), str(out)], check=True, capture_output=True)
    said = ask("which buildings are near Clock Tower?", vocab, str(out))
    assert said == "- Building 'Grain Warehouse'", said
    counted = ask("how many buildings are within 10 km of Clock Tower?", vocab, str(out))
    assert counted == "2 Building records", counted


def test_near_with_a_group_by_refuses(places):
    _root, vocab, _meta = places
    plan = interpret(vocab, "list buildings near Clock Tower by site").plan
    assert narrate(plan) == "Count Buildings within 5 km of Building 'Clock Tower', by site."
    with pytest.raises(Unsupported, match="by site within a distance"):
        compile_plan(plan, vocab)
