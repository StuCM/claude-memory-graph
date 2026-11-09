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
            _tag(nodes["heritage_status"], "E55_Type", "P2_has_type")
            _tag(nodes["site"], "E53_Place", "P53_has_former_or_current_location")
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
    assert {"kind": "link", "node": "actor", "phrases": ["who built"], "layer": "ontology"} in (
        bundle["models"]["Building"]["entries"])
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


# ── what made the ontology layer miss (026's bench)

def _plain(tmp_path, edit=None):
    """The fixture, uncrm'd, with `edit(graphs by name)` applied to its graph files."""
    fx.write(tmp_path)
    if edit is not None:
        docs = {p: json.loads(p.read_text()) for p in (tmp_path / "graphs").glob("*.json")}
        edit({d["graph"][0]["name"]: d["graph"][0] for d in docs.values()})
        for p, d in docs.items():
            p.write_text(json.dumps(d))
    return tmp_path


def test_have_x_as_a_noun_links_the_subject_to_x(data):
    v = ArchesVocabulary.from_data_dir(data[0])
    m = interpret(v, "which buildings have Ada Lovelace as architect?")
    assert narrate(m.plan) == "Find Buildings whose architect is Maker 'Ada Lovelace'."


def test_a_bundle_phrase_stays_on_the_model_that_owns_it(tmp_path):
    def person_has_a_site(g):
        g["Person"]["nodes"].append(fx._node(fx.PERSON, "site", "Site", "resource-instance",
                                             {"graphs": [{"graphid": fx.SITE}]}))
    root = _plain(tmp_path, person_has_a_site)
    bundle = {"format": "ceist.vocab/1", "models": {"Building": {
        "nodes": {"site": {"kind": "link"}},
        "entries": [{"phrases": ["stands on"], "kind": "link", "node": "site"}]}}}
    v = ArchesVocabulary.from_data_dir(root, bundle=bundle)
    m = interpret(v, "which buildings stands on Leeds Dock?")
    assert narrate(m.plan) == "Find Buildings whose site is Site 'Leeds Dock'."
    m = interpret(v, "which persons stands on Leeds Dock?")
    assert m.plan is None and m.refused == "out of grammar ('stands on' (site) can't join Person and Site)"


def test_type_words_and_names_keep_their_diacritics(tmp_path):
    from ceist import terms
    assert terms("Táin Bó Cúailnge, mātaurangas") == ["táin", "cúailnge", "mātaurangas"]

    def rename(g):
        g["Site"]["name"] = "Mātauranga"
    v = ArchesVocabulary.from_data_dir(_plain(tmp_path, rename))
    m = interpret(v, "how many mātaurangas are there?")
    assert narrate(m.plan) == "Count Mātaurangas."


def _graph(*nodes):
    """A graph from (alias, class, property into it, parent alias, datatype); the first is the root."""
    out = {"nodes": [], "edges": []}
    for alias, cls, prop, up, datatype in nodes:
        out["nodes"].append({"nodeid": alias, "alias": alias, "datatype": datatype,
                             "ontologyclass": CRM + cls, "parentproperty": CRM + prop if prop else None})
        if up:
            out["edges"].append({"domainnode_id": up, "rangenode_id": alias})
    return out


def test_membership_is_only_the_records_own():
    from ceist.crm import ontology_entries
    members = {"entries": [{"path": "^ P107", "kind": "link", "phrases": ["members"]}]}
    group = _graph(("group", "E74", None, None, "semantic"),
                   ("associated_actors", "E39", "P107", "group", "resource-instance-list"))
    assert ontology_entries(group, members) == [
        {"kind": "link", "node": "associated_actors", "phrases": ["members"]}]
    # a vessel's crew: the members of a group inside its voyage
    vessel = _graph(("vessel", "E24", None, None, "semantic"),
                    ("voyage", "E9", "P16i", "vessel", "semantic"),
                    ("crew", "E74", "P17", "voyage", "semantic"),
                    ("crew_member", "E21", "P107", "crew", "resource-instance"))
    assert ontology_entries(vessel, members) == []


def test_what_is_its_date_takes_the_one_date_a_form_names(data, tmp_path):
    named = dict(ONTOLOGY, entries=[{"path": "P108i E12 P4", "kind": "date", "phrases": ["build date"]}])
    v, _, _ = vocab(data, tmp_path, ontology=named)
    m = interpret(v, "what is the build date of the Clock Tower?")
    assert narrate(m.detail) == "Show the production date of Building 'Clock Tower'."
    m = interpret(v, "what is the date of the Clock Tower?")
    assert m.detail is None and "did you mean" in m.refused, m.refused


def test_a_phrase_no_relation_it_names_can_take_refuses(data):
    bundle = {"format": "ceist.vocab/1", "models": {"Building": {
        "nodes": {"site": {"kind": "link"}, "architect": {"kind": "link"}},
        "entries": [{"phrases": ["part of"], "kind": "link", "node": "site"},
                    {"phrases": ["part of"], "kind": "link", "node": "architect"}]}}}
    v = ArchesVocabulary.from_data_dir(data[0], bundle=bundle)
    m = interpret(v, "which makers are part of Leeds Dock?")
    assert m.plan is None and m.refused == "out of grammar ('part of' can't join Maker and Site)"
    # the memory graph's free text still sets it aside and links loosely, saying so
    v.free_text = True
    m = interpret(v, "which makers are part of Leeds Dock?")
    assert narrate(m.plan) == "Find Makers linked to or from Site 'Leeds Dock'."


# ── fields by CRM path: "what kind of", "made of", "where" (task 025)

FIELDS = {"format": "ceist.ontology/1", "entries": [
    {"path": "P2", "kind": "property", "phrases": ["kind"]},
    {"path": "^ P45", "kind": "property", "phrases": ["made of", "material"]}]}


def _consists_of(data, tmp_path):
    """The fixture with heritage status as what a Building is made of (P45 E57)."""
    import shutil
    root = tmp_path / "p45"
    shutil.copytree(data[0], root)
    for path in (root / "graphs").glob("*.json"):
        doc = json.loads(path.read_text())
        for n in doc["graph"][0]["nodes"]:
            if n["alias"] == "heritage_status":
                _tag(n, "E57_Material", "P45_consists_of")
        path.write_text(json.dumps(doc))
    return (root, data[1])


def test_a_field_phrase_holds_the_value_after_it_to_that_field(data, tmp_path):
    v, bundle, _ = vocab(_consists_of(data, tmp_path), tmp_path, ontology=FIELDS)
    assert {"kind": "property", "node": "heritage_status", "phrases": ["made of", "material"],
            "layer": "ontology"} in bundle["models"]["Building"]["entries"]
    m = interpret(v, "which buildings are made of candidate?")
    assert narrate(m.plan) == "Find Buildings whose heritage status is Candidate."
    assert check(m.plan, read_back(compile_plan(m.plan, v), v)).ok
    # a value of another field: the phrase can't hold it, so it places nothing
    m = interpret(v, "which buildings are made of architect?")
    assert m.plan is None and m.refused.startswith("couldn't place 'made'"), m.refused


def test_what_kind_of_x_is_y_is_its_type(data, tmp_path):
    v, _, _ = vocab(data, tmp_path, ontology=FIELDS)
    for q in ("what kind of building is the Clock Tower?", "what kind is the Clock Tower?"):
        m = interpret(v, q)
        assert narrate(m.detail) == "Show the heritage status of Building 'Clock Tower'.", (q, m.refused)
    from ceist.questions import templated
    by_q = {o["q"]: o for o in templated(v, FIELDS)}
    assert by_q["what is the kind of {Building}?"]["target"]["detail"] == ["heritage_status"]


def test_what_is_x_made_of_is_its_material_or_names_made(data, tmp_path):
    v, _, _ = vocab(_consists_of(data, tmp_path), tmp_path / "p45", ontology=FIELDS)
    m = interpret(v, "what is the Clock Tower made of?")
    assert narrate(m.detail) == "Show the heritage status of Building 'Clock Tower'."
    v, _, _ = vocab(data, tmp_path / "p2", ontology=FIELDS)       # heritage status is P2: no P45
    m = interpret(v, "what is the Clock Tower made of?")
    assert m.detail is None and m.refused.startswith("couldn't place 'made'"), m.refused


def test_where_is_x_gives_its_links_to_a_place_or_refuses(data, tmp_path):
    from ceist.rosmadair import compile_detail, read_back_detail
    v, _, _ = vocab(data, tmp_path)
    m = interpret(v, "where is the Clock Tower?")
    assert m.direct is None and narrate(m.detail) == "Show the site of Building 'Clock Tower'."
    assert check(m.detail, read_back_detail(compile_detail(m.detail, v), v)).ok
    m = interpret(v, "where is Ada Lovelace?")
    assert m.detail is None and m.direct is None
    assert m.refused == "'where': a Maker has no link to a place to answer it from"


def test_a_plain_field_takes_only_a_field_path_and_an_end_date_only_its_own():
    from ceist.crm import ontology_entries
    g = _graph(("thing", "E22", None, None, "semantic"),
               ("making", "E12", "P108i", "thing", "semantic"),
               ("making_type", "E55", "P2", "making", "concept"),
               ("making_note", "E55", "P2", "making", "string"),
               ("span", "E52", "P4", "making", "semantic"),
               ("began", "E61", "P82a", "span", "date"),
               ("ended", "E61", "P82b", "span", "date"))
    onto = {"entries": [{"path": "P108i E12 P2", "kind": "property", "phrases": ["production type"]},
                        {"path": "P108i E12 P2", "kind": "field", "phrases": ["production note"]},
                        {"path": "P108i E12 P4", "kind": "date", "phrases": ["made"]},
                        {"path": "E12 P4 E52 P82b", "kind": "date", "phrases": ["finished"]}]}
    assert ontology_entries(g, onto) == [
        {"kind": "property", "node": "making_type", "phrases": ["production type"]},
        {"kind": "property", "node": "making_note", "phrases": ["production note"]},
        {"kind": "date", "node": "began", "end_node": "ended", "phrases": ["made"]},
        {"kind": "date", "node": "ended", "phrases": ["finished"]}]
