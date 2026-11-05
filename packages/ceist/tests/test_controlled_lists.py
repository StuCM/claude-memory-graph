"""Controlled lists (`reference` nodes) as the primary kind of controlled value,
read through Alizarin, and tiles read as Alizarin trees: a child tile counts
with its parent tile, never with a sibling.

    Monuments   status (controlled list)   phases (type list; child tile: actor)
    Old Mill    Grade II  (narrower: Listed)   Destruction ← Ada · Construction ← Brunel
    New Mill    Candidate                      Construction ← Ada
    Barn        Listed                         Destruction (no actor) · Construction ← Ada
"""

import json

import alizarin
import pytest
from arches_fixture import _id, _node

from ceist import HasValue, LinkTo, Plan, interpret, narrate
from ceist.alizarin import Tiles, ask, evaluate
from ceist.arches import ArchesVocabulary
from ceist.arches_search import compile_checked, to_payload
from ceist.plan import EntityRef
from ceist.rosmadair import to_query

MONUMENT, PERSON = "5e000000-0000-4000-8000-0000000000c1", "5e000000-0000-4000-8000-0000000000c2"
STATUS_LIST, PHASE_LIST = (str(_id(f"list/{n}")) for n in ("status", "phase"))


def _lists():
    status = alizarin.RustRdmCollection.from_nested_labels(
        "Heritage status", {"Listed": {"Grade II": None}, "Candidate": None}, id=STATUS_LIST)
    phase = alizarin.RustRdmCollection.from_nested_labels(
        "Phase type", {"Construction": None, "Destruction": None}, id=PHASE_LIST)
    return status, phase


def _items(coll) -> dict:
    """{label: (item id, label value id)} from a collection's simplified JSON."""
    out = {}

    def walk(c):
        lab = c["prefLabels"]["en"]
        out[lab["value"]] = (c["id"], lab["id"])
        for child in c.get("children") or []:
            walk(child)

    for c in json.loads(coll.to_simplified_json())["concepts"].values():
        walk(c)
    return out


def _ref(coll_id, item):
    """A reference value as Arches stores it in a tile."""
    item_id, value_id = item[1]
    return [{"uri": f"http://example.org/{item_id}", "list_id": coll_id,
             "labels": [{"id": value_id, "value": item[0], "language_id": "en",
                         "valuetype_id": "prefLabel", "list_item_id": item_id}]}]


def _graph(gid, name, nodes, nodegroups, edges):
    root = _node(gid, name.lower(), name, "semantic", root=True)
    return {"graph": [{
        "graphid": gid, "name": name, "root": root, "nodes": [root] + nodes,
        "nodegroups": nodegroups,
        "edges": [{"edgeid": _id(f"{gid}/edge/{b['alias']}"),
                   "domainnode_id": (a or root)["nodeid"], "rangenode_id": b["nodeid"],
                   "graph_id": gid} for a, b in edges]}]}


@pytest.fixture(scope="module")
def data(tmp_path_factory):
    root = tmp_path_factory.mktemp("cl")
    status, phase = _lists()
    S, P = _items(status), _items(phase)
    # the status list as SKOS XML, the phase list as collection JSON: both load
    (root / "vocabularies").mkdir()
    (root / "vocabularies" / "status.xml").write_text(status.to_skos_xml("http://example.org/"))
    (root / "vocabularies" / "phase.json").write_text(phase.to_simplified_json())

    def n(alias, name, datatype, config=None, group=None):
        node = _node(MONUMENT, alias, name, datatype, config)
        if group is not None:
            node["nodegroup_id"] = group
        return node

    mname = n("name", "Name", "string")
    mstatus = n("heritage_status", "Heritage status", "reference",
                {"controlledList": STATUS_LIST, "multiValue": False})
    phases = n("phases", "Phases", "semantic")
    ptype = n("phase_type", "Phase type", "reference",
              {"controlledList": PHASE_LIST, "multiValue": False}, group=phases["nodeid"])
    pactor = n("phase_actor", "Phase actor", "semantic")                 # a child nodegroup
    actor = n("actor", "Actor", "resource-instance", {"graphs": [{"graphid": PERSON}]},
              group=pactor["nodeid"])
    ng = [{"nodegroupid": mname["nodeid"], "cardinality": "1", "parentnodegroup_id": None},
          {"nodegroupid": mstatus["nodeid"], "cardinality": "1", "parentnodegroup_id": None},
          {"nodegroupid": phases["nodeid"], "cardinality": "n", "parentnodegroup_id": None},
          {"nodegroupid": pactor["nodeid"], "cardinality": "n",
           "parentnodegroup_id": phases["nodeid"]}]
    monument = _graph(MONUMENT, "Monument", [mname, mstatus, phases, ptype, pactor, actor], ng,
                      [(None, mname), (None, mstatus), (None, phases), (phases, ptype),
                       (phases, pactor), (pactor, actor)])
    pname = _node(PERSON, "name", "Name", "string")
    person = _graph(PERSON, "Person", [pname],
                    [{"nodegroupid": pname["nodeid"], "cardinality": "1",
                      "parentnodegroup_id": None}], [(None, pname)])
    (root / "graphs").mkdir()
    for gid, doc in ((MONUMENT, monument), (PERSON, person)):
        (root / "graphs" / f"{gid}.json").write_text(json.dumps(doc))

    ids = {}

    def resource(gid, key, name, tiles):
        rid = _id(f"resource/{key}")
        ids[key] = rid
        out = []
        for i, (group, data, parent) in enumerate(tiles):
            tid = _id(f"tile/{key}/{i}")
            out.append({"tileid": tid, "nodegroup_id": group, "resourceinstance_id": rid,
                        "parenttile_id": parent and _id(f"tile/{key}/{parent}"),
                        "sortorder": i, "provisionaledits": None, "data": data})
        return {"resourceinstance": {"resourceinstanceid": rid, "graph_id": gid, "name": name,
                                     "legacyid": None,
                                     "descriptors": {"en": {"name": name, "description": "",
                                                            "map_popup": ""}}},
                "tiles": out}

    def text(v):
        return {"en": {"value": v, "direction": "ltr"}}

    people = [resource(PERSON, k, v, [(pname["nodeid"], {pname["nodeid"]: text(v)}, None)])
              for k, v in (("ada", "Ada Lovelace"), ("brunel", "Isambard Brunel"))]

    def link(key):
        return [{"resourceId": ids[key], "ontologyProperty": "", "inverseOntologyProperty": ""}]

    def monument_res(key, name, status_label, phase_list):
        tiles = [(mname["nodeid"], {mname["nodeid"]: text(name)}, None),
                 (mstatus["nodeid"], {mstatus["nodeid"]: _ref(STATUS_LIST, (status_label,
                                                                            S[status_label]))},
                  None)]
        for kind, who in phase_list:
            k = len(tiles)
            tiles.append((phases["nodeid"],
                          {ptype["nodeid"]: _ref(PHASE_LIST, (kind, P[kind]))}, None))
            if who:
                tiles.append((pactor["nodeid"], {actor["nodeid"]: link(who)}, k))
        return resource(MONUMENT, key, name, tiles)

    monuments = [
        monument_res("old", "Old Mill", "Grade II", [("Destruction", "ada"),
                                                     ("Construction", "brunel")]),
        monument_res("new", "New Mill", "Candidate", [("Construction", "ada")]),
        # Ada is on the Construction phase; the Destruction phase has no actor
        monument_res("barn", "Barn", "Listed", [("Destruction", None), ("Construction", "ada")]),
    ]
    (root / "resources").mkdir()
    (root / "resources" / "data.json").write_text(
        json.dumps({"business_data": {"resources": people + monuments}}))
    return root, ids, S, P


@pytest.fixture(scope="module")
def vocab(data):
    return ArchesVocabulary.from_data_dir(data[0])


def test_controlled_list_items_are_values(vocab, data):
    _, _, S, P = data
    phrases = {(v.phrase, v.field): v.value for v in vocab.values()}
    assert phrases[("listed", "heritage_status")] == S["Listed"][0]
    assert phrases[("destruction", "phase_type")] == P["Destruction"][0]     # from the JSON list
    assert vocab.descendants(S["Listed"][0]) == [S["Grade II"][0]]
    assert vocab.is_reference("Monument", "heritage_status")


def test_a_list_value_and_its_narrower_items_answer(vocab):
    out = ask("which listed monuments are there?", vocab)
    assert "Old Mill" in out and "Barn" in out and "New Mill" not in out   # Grade II is Listed


def test_tile_values_count_with_their_parent_tile_not_a_sibling(vocab, data):
    _, ids, _, P = data
    ada = vocab.entity(ids["ada"])
    destroyed_by_ada = Plan("Monument", [LinkTo(
        "actor", EntityRef(ada), "out", style="field",
        qualifier=HasValue("phase_type", P["Destruction"][0], "Destruction"))])
    hits = evaluate(destroyed_by_ada, Tiles(vocab))
    # Old Mill: Ada's tile is a child of the Destruction phase. Barn: Ada is
    # under the Construction phase, a sibling of the Destruction one.
    assert hits == {ids["old"]}


def test_arches_search_takes_list_values_as_reference_items(vocab, data):
    _, _, S, _ = data
    plan = interpret(vocab, "which listed monuments are there?").plan
    payload, verdict = compile_checked(plan, vocab)          # no concept_operator needed
    (clause,) = payload["clauses"]
    assert clause["operator"] == "REFERENCES_ANY"
    (items,) = [o["value"] for o in clause["operands"]]
    labels = {lab["value"] for item in items for lab in item["labels"]}
    assert labels == {"Listed", "Grade II"} and verdict.ok
    assert {item["list_id"] for item in items} == {STATUS_LIST}


def test_ros_madair_takes_list_values_by_item_id(vocab, data):
    _, _, S, _ = data
    q = to_query(interpret(vocab, "which listed monuments are there?").plan, vocab, 25)
    assert q["where"] == {"concept": {"path": "heritage_status", "op": "descendant_or_self_of",
                                      "value": S["Listed"][0]}}


def test_legacy_concepts_still_need_their_operator_on_arches_search():
    import arches_fixture as fx
    import tempfile
    from pathlib import Path
    from ceist.rosmadair import Unsupported
    root = Path(tempfile.mkdtemp())
    fx.write(root)
    v = ArchesVocabulary.from_data_dir(root)
    plan = interpret(v, "which listed buildings are there?").plan
    with pytest.raises(Unsupported, match="concept_operator"):
        to_payload(plan, v)
    assert not v.is_reference("Building", "heritage_status")


def test_skipped_bundle_entries_say_why(data):
    bundle = {"format": "ceist.vocab/1", "models": {"Monument": {
        "nodes": {"phase_type": {"kind": "property"}, "actor": {"kind": "link"}},
        "entries": [
            {"phrases": ["burnt down"], "kind": "property", "node": "phase_type",
             "qualifier": {"node": "phase_type", "value": "Destruction"}},
            {"phrases": ["wrecked by"], "kind": "link", "node": "actor",
             "qualifier": {"node": "phase_type", "value": "Shipwreck"}},
            {"phrases": ["destroyed by"], "kind": "link", "node": "actor",
             "qualifier": {"node": "phase_type", "value": "Destruction"}}]}}}
    v = ArchesVocabulary.from_data_dir(data[0], bundle=bundle)
    rels = {r.name for r in v.relations()}
    assert "actor#Destruction" in rels
    assert v.skipped_qualified == 2
    assert any("qualified reference entries aren't supported yet" in s for s in v.skipped)
    assert any("'Shipwreck' isn't a value of phase_type" in s for s in v.skipped)


def test_a_record_without_a_name_is_noted(data, tmp_path):
    root, *_ = data
    import shutil
    copy = tmp_path / "copy"
    shutil.copytree(root, copy)
    res = json.loads((copy / "resources" / "data.json").read_text())
    for r in res["business_data"]["resources"]:
        if r["resourceinstance"]["graph_id"] == MONUMENT:
            r["resourceinstance"].pop("descriptors")
            r["resourceinstance"].pop("name")
    (copy / "resources" / "data.json").write_text(json.dumps(res))
    v = ArchesVocabulary.from_data_dir(copy)
    assert any("3 Monument record(s) have no name" in n for n in v.notes)


def test_narration_names_the_list_item(vocab):
    assert narrate(interpret(vocab, "which listed monuments are there?").plan) == \
        "Find Monuments whose heritage status is Listed."


def test_describe_lists_a_small_controlled_lists_labels(data, tmp_path):
    from ceist.arches_describe import describe
    root, *_ = data
    ref = tmp_path / "reference_data" / "controlled_lists"
    ref.mkdir(parents=True)
    for p in (root / "vocabularies").iterdir():
        (ref / p.name).write_text(p.read_text())
    models = describe(root / "graphs", tmp_path / "desc", tmp_path / "reference_data")
    nodes = {n["alias"]: n for n in models["Monument"]["nodes"]}
    assert nodes["heritage_status"]["datatype"] == "reference"
    assert set(nodes["heritage_status"]["values"]) == {"Listed", "Grade II", "Candidate"}
    assert set(nodes["phase_type"]["values"]) == {"Construction", "Destruction"}


def test_a_controlled_lists_skos_altlabels_are_values(data, tmp_path):
    # HER 2.0's lists carry altLabels, some a single letter ("S" for Statutory)
    import shutil
    root, _, S, _ = data
    copy = tmp_path / "copy"
    shutil.copytree(root, copy)
    xml = copy / "vocabularies" / "status.xml"
    listed = '<skos:prefLabel xml:lang="en">Listed</skos:prefLabel>'
    xml.write_text(xml.read_text().replace(listed, listed
        + '<skos:altLabel xml:lang="en">Protected</skos:altLabel>'
        + '<skos:altLabel xml:lang="en">S</skos:altLabel>'))
    v = ArchesVocabulary.from_data_dir(copy)
    phrases = {(x.phrase, x.field): x.value for x in v.values()}
    assert phrases[("protected", "heritage_status")] == S["Listed"][0]
    assert narrate(interpret(v, "which protected monuments are there?").plan) == \
        "Find Monuments whose heritage status is Listed."
    m = interpret(v, "what's the monument's status, protected?")
    assert [x.phrase for x in m.grounding.values] == ["protected"]
