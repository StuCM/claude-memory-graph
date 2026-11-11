"""Type words that combine: a value plural ("candidates") and a role noun ("keyholders") inside link
questions, a numbered record name not bound by its partial name, and a link read from its far end.

    the fixture, plus Person.keyholder_for → Building:  Ada keyholds Boat Shed (Candidate),
                                                       Isambard keyholds Clock Tower (Listed)
    and a Site 'Mill Yard v1.0', which no building is on
"""

import json

import arches_fixture as fx
import pytest
from test_vocab_rules import layers_dir

from ceist import interpret, narrate
from ceist import bundle as _bundle
from ceist import site
from ceist import vocab_rules as vr
from ceist.alizarin import Tiles, evaluate
from ceist.arches import ArchesVocabulary, read_resources
from ceist.plan import EntityRef, LinkTo, Plan
from ceist.questions import fill, score
from ceist.vocabulary import Entity

LINKS = [{"phrases": ["designed by", "designed"], "kind": "link", "node": "architect"}]
CANDIDATES = {"heritage_status": {"phrases": [], "nodes": {}, "combos": [
    {"phrases": ["candidates"], "set": {"heritage_status": "Candidate"}}]}}
ROLE = {"phrases": ["keyholders"], "kind": "link", "node": "keyholder_for", "role": True}


def _bundle_of(person_entries=()):
    return {"format": "ceist.vocab/2", "models": {
        "Building": {"nodes": {"architect": {"kind": "link"}}, "entries": LINKS, "groups": CANDIDATES},
        "Person": {"nodes": {"keyholder_for": {"kind": "link"}}, "entries": list(person_entries)}}}


@pytest.fixture(scope="module")
def data(tmp_path_factory):
    root = tmp_path_factory.mktemp("keyholders")
    info = fx.write(root)
    path = root / "graphs" / f"{fx.PERSON}.json"
    doc = json.loads(path.read_text())
    g = doc["graph"][0]
    keys = fx._node(fx.PERSON, "keyholder_for", "Keyholder for", "resource-instance",
                    {"graphs": [{"graphid": fx.BUILDING}]})
    g["nodes"].append(keys)
    g["nodegroups"].append({"nodegroupid": keys["nodeid"], "cardinality": "n", "parentnodegroup_id": None})
    g["edges"].append({"edgeid": fx._id("person/edge/keyholder_for"), "domainnode_id": g["root"]["nodeid"],
                       "rangenode_id": keys["nodeid"], "graph_id": fx.PERSON})
    path.write_text(json.dumps(doc))
    people = root / "resources" / "person" / "data.json"
    doc = json.loads(people.read_text())
    ids = info["ids"]
    for r in doc["business_data"]["resources"]:
        building = {ids["ada"]: "shed", ids["isambard"]: "tower"}[r["resourceinstance"]["resourceinstanceid"]]
        r["tiles"].append({"tileid": fx._id(f"tile/{building}/keys"), "nodegroup_id": keys["nodeid"],
                           "parenttile_id": None, "resourceinstance_id": r["resourceinstance"]["resourceinstanceid"],
                           "sortorder": 0, "provisionaledits": None,
                           "data": {keys["nodeid"]: [{"resourceId": ids[building], "ontologyProperty": "",
                                                      "inverseOntologyProperty": ""}]}})
    people.write_text(json.dumps(doc))
    sites = root / "resources" / "site" / "data.json"
    doc = json.loads(sites.read_text())
    yard = json.loads(json.dumps(doc["business_data"]["resources"][0]).replace(ids["dock"], fx._id("resource/yard"))
                      .replace("Leeds Dock", "Mill Yard v1.0"))
    doc["business_data"]["resources"].append(yard)
    sites.write_text(json.dumps(doc))
    return root, info


@pytest.fixture(scope="module")
def vocab(data):
    return ArchesVocabulary.from_data_dir(data[0], bundle=_bundle_of([ROLE]))


def _answer(vocab, q):
    m = interpret(vocab, q)
    assert not m.refused, m.refused
    return sorted(vocab.names[i] for i in evaluate(m.plan, Tiles(vocab))), narrate(m.plan)


def test_a_value_plural_is_the_subject_of_a_link_question(vocab):
    assert _answer(vocab, "which candidates were designed by persons?") == (
        ["Boat Shed"], "Find Buildings whose architect is any Person and whose heritage status is Candidate.")


def test_a_value_plural_is_the_far_end_of_a_link_question(vocab):
    assert _answer(vocab, "who designed the candidates?") == (
        ["Ada Lovelace"], "Find Persons that are the architect of any Building whose heritage status is Candidate.")


def test_a_role_noun_names_the_holder_of_its_link(vocab):
    assert _answer(vocab, "keyholders of the candidates") == (
        ["Ada Lovelace"], "Find Persons whose keyholder for is any Building whose heritage status is Candidate.")
    assert _answer(vocab, "who are the keyholders of Clock Tower?")[0] == ["Isambard Brunel"]


def test_without_its_role_entry_a_role_noun_refuses(data):
    v = ArchesVocabulary.from_data_dir(data[0], bundle=_bundle_of())
    assert interpret(v, "keyholders of the candidates").refused.startswith("couldn't place 'keyholders'")


def test_a_numbered_name_is_not_bound_by_its_partial_name(vocab):
    m = interpret(vocab, "which buildings are on site Mill Yard?")
    assert m.refused == ("couldn't place 'mill', 'yard' — answering without them would widen the question; "
                         "did you mean 'Mill Yard v1.0' for 'mill yard'?")
    m = interpret(vocab, "which buildings are on site Mill Yard v1.0?")
    assert narrate(m.plan) == "Find Buildings whose site is Site 'Mill Yard v1.0'."


def test_a_link_is_read_from_its_far_end_by_its_passive_or_its_noun():
    org = Entity("Organisation", "o", "Port Trust")
    assert narrate(Plan("Building", [LinkTo("occupies", EntityRef(org), "in", form="occupy", style="field")])) == \
        "Find Buildings occupied by Organisation 'Port Trust'."
    assert narrate(Plan("Building", [LinkTo("keyholder_for", EntityRef(org), "in", form="keyholders",
                                            style="field")])) == \
        "Find Buildings whose keyholder is Organisation 'Port Trust'."
    # the comparable form keeps the link's name
    assert narrate(Plan("Building", [LinkTo("occupies", EntityRef(org), "in", form="occupy", style="field")]),
                   canonical=True) == "Find Buildings that are the occupies of Organisation 'Port Trust'."


def test_setup_proposes_a_role_nouns_plural_and_checks_it_on_a_record(data, tmp_path):
    vocabularies = layers_dir(tmp_path)
    L = vr.Layers([data[0] / "graphs"], vocabularies / "base", tmp_path / "client",
                  reference=data[0] / "vocabularies", resources=read_resources(data[0] / "resources"))
    c, = [c for c in vr.candidates(vr.checklist(L)) if c["key"] == "role Person.keyholder_for"]
    assert c["phrases"] == ["keyholders"] and c["role"] == "keyholder"
    vr.apply([c], L.ontology_dir, L.base_dir, L.client_dir)
    v = L.vocab().with_bundle(_bundle.layered(L.graphs, L.base_dir, L.client_dir,
                                              ontology_dir=L.ontology_dir)[0])
    check, = site.role_checks(c, v)
    assert check["q"] == "list the keyholders of {Building}"
    assert score(check, interpret(v, fill(check["q"], v))) == "right"
