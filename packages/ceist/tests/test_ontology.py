"""The CIDOC-CRM ontology layer: phrases by CRM path beneath the base, and "who" by class."""

import json

import arches_fixture as fx
import pytest

from ceist import interpret, narrate
from ceist.arches import ArchesVocabulary, graph_doc
from ceist.bundle import layered
from ceist.readback import check
from ceist.rosmadair import compile_plan, read_back

CRM = "http://www.cidoc-crm.org/cidoc-crm/"
ONTOLOGY = {"format": "ceist.ontology/1", "entries": [
    {"path": "P108i E12 P14", "kind": "link", "phrases": ["built by", "made by"]},
    {"path": "P108i E12 P4", "kind": "date", "phrases": ["built"]}]}


def _tag(node: dict, cls: str, prop: str | None = None) -> None:
    node["ontologyclass"] = CRM + cls
    if prop:
        node["parentproperty"] = CRM + prop


@pytest.fixture(scope="module")
def data(tmp_path_factory):
    """The fixture with CRM classes: Building's associated actor is its production (P108i E12),
    the actor on it P14 E39, with a time-span and date under it; architect is a bare P14 off
    the root. Person is renamed Maker, an E21 Person; Site is an E53 Place."""
    root = tmp_path_factory.mktemp("ontology")
    info = fx.write(root)
    for path in (root / "graphs").glob("*.json"):
        doc = json.loads(path.read_text())
        g = doc["graph"][0]
        nodes = {n["alias"]: n for n in g["nodes"]}
        if g["graphid"] == fx.PERSON:
            g["name"] = "Maker"
            _tag(nodes["person"], "E21_Person")
        elif g["graphid"] == fx.SITE:
            _tag(nodes["site"], "E53_Place")
        else:
            _tag(nodes["building"], "E22_Human-Made_Object")
            _tag(nodes["associated_actor"], "E12_Production", "P108i_was_produced_by")
            _tag(nodes["actor"], "E39_Actor", "P14_carried_out_by")
            _tag(nodes["architect"], "E39_Actor", "P14_carried_out_by")
            span = dict(fx._node(fx.BUILDING, "production_time", "Production time", "semantic"),
                        nodegroup_id=nodes["associated_actor"]["nodeid"])
            made = dict(fx._node(fx.BUILDING, "production_date", "Production date", "date",
                                 {"dateFormat": "YYYY-MM-DD"}),
                        nodegroup_id=nodes["associated_actor"]["nodeid"])
            _tag(span, "E52_Time-Span", "P4_has_time-span")
            _tag(made, "E61_Time_Primitive", "P82a_begin_of_the_begin")
            g["nodes"] += [span, made]
            g["edges"] += [{"edgeid": fx._id(f"edge/{b['alias']}"), "domainnode_id": a["nodeid"],
                            "rangenode_id": b["nodeid"], "graph_id": fx.BUILDING}
                           for a, b in ((nodes["associated_actor"], span), (span, made))]
        path.write_text(json.dumps(doc))
    return root, info


def layers(tmp_path, base_entries=(), ontology=ONTOLOGY):
    (tmp_path / "ontology" / "cidoc-crm").mkdir(parents=True)
    (tmp_path / "ontology" / "cidoc-crm" / "phrases.json").write_text(json.dumps(ontology))
    base = tmp_path / "base" / fx.BUILDING
    base.mkdir(parents=True)
    (base / "architect.json").write_text(json.dumps({"model": "Building", "nodegroup": "architect",
                                                     "entries": list(base_entries)}))
    return tmp_path / "base"


def vocab(data, tmp_path, base_entries=(), ontology=ONTOLOGY):
    graphs = [graph_doc(p) for p in sorted((data[0] / "graphs").glob("*.json"))]
    bundle, report = layered(graphs, layers(tmp_path, base_entries, ontology))
    return ArchesVocabulary.from_data_dir(data[0], bundle=bundle), bundle, report


def test_an_ontology_phrase_reaches_a_node_only_through_its_crm_path(data, tmp_path):
    v, bundle, report = vocab(data, tmp_path)
    assert report == []
    # architect is P14 too, but not under P108i E12: it gets nothing
    assert [(e["node"], e["phrases"]) for e in bundle["models"]["Building"]["entries"]] == [
        ("actor", ["built by", "made by"]), ("production_date", ["built"]), ("actor", ["who built"])]
    m = interpret(v, "which buildings were made by Ada Lovelace?")
    assert narrate(m.plan) == "Find Buildings whose actor is Maker 'Ada Lovelace'."
    compiled = compile_plan(m.plan, v)
    assert check(m.plan, read_back(compiled, v)).ok


def test_a_graph_layer_phrase_overrides_the_ontology(data, tmp_path):
    v, bundle, _ = vocab(data, tmp_path, [{"phrases": ["made by"], "kind": "link", "node": "architect"}])
    entries = [(e["node"], e["phrases"]) for e in bundle["models"]["Building"]["entries"]]
    assert ("architect", ["made by"]) in entries and ("actor", ["built by"]) in entries
    m = interpret(v, "which buildings were made by Ada Lovelace?")
    assert m.plan.where[0].relation == "architect"


def test_who_means_the_e39_model_whatever_it_is_named(data):
    v = ArchesVocabulary.from_data_dir(data[0])
    assert v.implied_types() == {"who": "Maker"}


def test_who_built_follows_the_production_path_and_reads_back(data, tmp_path):
    from ceist.alizarin import Tiles, evaluate
    v, bundle, _ = vocab(data, tmp_path)
    assert {"kind": "link", "node": "actor", "phrases": ["who built"]} in bundle["models"]["Building"]["entries"]
    m = interpret(v, "who built the Clock Tower?")
    assert narrate(m.plan) == "Find Makers that are the actor of Building 'Clock Tower'."
    assert evaluate(m.plan, Tiles(v)) == {data[1]["ids"]["ada"]}


def test_when_was_it_made_is_the_production_date_or_names_made(data, tmp_path):
    made = dict(ONTOLOGY, entries=[{"path": "P108i E12 P4", "kind": "date", "phrases": ["made"]}])
    v, _, _ = vocab(data, tmp_path / "made", ontology=made)
    m = interpret(v, "when was the Clock Tower made?")
    assert m.direct is None and narrate(m.detail) == "Show the production date of Building 'Clock Tower'."
    v, _, _ = vocab(data, tmp_path / "plain")
    m = interpret(v, "when was the Clock Tower made?")
    assert m.direct is None and m.detail is None
    assert m.refused.startswith("couldn't place 'made'"), m.refused


def test_a_dropped_verb_beside_a_record_with_fields_is_named(data, tmp_path):
    v, _, _ = vocab(data, tmp_path)
    m = interpret(v, "what does the Clock Tower need?")
    assert m.direct is None and m.detail is None
    assert m.refused.startswith("couldn't place 'need'"), m.refused


def test_templated_questions_come_from_the_crm_paths_each_with_a_target(data, tmp_path):
    from ceist.questions import templated
    v, _, _ = vocab(data, tmp_path)
    items = templated(v, ONTOLOGY)
    assert items == templated(v, ONTOLOGY)
    assert all(("target" in o) != ("reason" in o) for o in items)
    by_q = {o["q"]: o for o in items}
    assert by_q["which buildings were built by {Maker}?"]["target"] == {
        "model": "Building", "count": False, "conditions": [{"node": "actor", "link": "Maker"}]}
    assert by_q["who built {Building}?"]["target"] == {
        "model": "Maker", "count": False, "conditions": [{"node": "actor", "link": "Building"}]}
    assert by_q["when was {Building} built?"]["target"]["detail"] == ["production_date"]
    assert by_q["why was {Building} built?"]["reason"] == "why"
    # architect is P14 too, but off no production: nothing asks about it
    assert not [o for o in items if "architect" in json.dumps(o)]


def test_a_template_question_with_no_one_actor_expects_a_refusal(data, tmp_path):
    from ceist.questions import templated
    v, _, _ = vocab(data, tmp_path)
    for n in v.models["Building"].doc["nodes"]:
        if n["alias"] == "actor":
            n["parentproperty"] = CRM + "P11_had_participant"
    by_q = {o["q"]: o for o in templated(v, ONTOLOGY)}
    assert by_q["who built {Building}?"]["reason"].startswith("no one actor")
    assert by_q["when was {Building} built?"]["target"]["detail"] == ["production_date"]
    assert "which buildings were built by {Maker}?" not in by_q


def test_template_questions_score_through_interpret(data, tmp_path):
    from ceist.questions import fill, score, templated
    v, _, _ = vocab(data, tmp_path)
    got = {o["q"]: score(o, interpret(v, fill(o["q"], v))) for o in templated(v, ONTOLOGY)}
    assert got["which buildings were made by {Maker}?"] == "right"
    assert got["who built {Building}?"] == "right"
    assert sum(1 for s in got.values() if s == "right") >= 4
