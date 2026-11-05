"""`ceist vocab slice`: a vocabulary cut down to the nodegroups, links and values a dataset uses."""

import json
import shutil

import pytest

pytest.importorskip("alizarin")

import arches_fixture as fx  # noqa: E402

from ceist.bundle import FORMAT, LAYOUT, MANIFEST  # noqa: E402
from ceist.cli import main  # noqa: E402
from ceist.slicing import Usage, slice_bundle, slice_vocab  # noqa: E402


def _edit(path, change):
    doc = json.loads(path.read_text())
    change(doc)
    path.write_text(json.dumps(doc))


def _bundle(models):
    return {"format": FORMAT, "models": {
        name: {"nodes": {e["node"]: {"kind": e["kind"]} for e in entries}, "entries": entries}
        for name, entries in models.items()}}


def _nid(alias):
    return fx._id(f"{fx.BUILDING}/{alias}")


@pytest.fixture
def visited(tmp_path):
    """The fixture, plus a visit date in a nodegroup under associated_actor. Only
    names, sites, architects and visits hold tiles, and there are no people."""
    root = tmp_path / "data"
    fx.write(root)
    visit = fx._node(fx.BUILDING, "visit_date", "Visit date", "date")

    def add_visit(doc):
        g = doc["graph"][0]
        g["nodes"].append(visit)
        g["nodegroups"].append({"nodegroupid": visit["nodeid"], "cardinality": "n",
                                "parentnodegroup_id": _nid("associated_actor")})
        g["edges"].append({"edgeid": fx._id("edge/visit"), "domainnode_id": _nid("associated_actor"),
                           "rangenode_id": visit["nodeid"], "graph_id": fx.BUILDING})

    def keep_some(doc):
        keep = {_nid(a) for a in ("name", "site", "architect")}
        for r in doc["business_data"]["resources"]:
            rid = r["resourceinstance"]["resourceinstanceid"]
            r["tiles"] = [t for t in r["tiles"] if t["nodegroup_id"] in keep]
            r["tiles"].append({"tileid": fx._id(f"tile/{rid}/visit"), "nodegroup_id": visit["nodeid"],
                               "parenttile_id": None, "resourceinstance_id": rid, "sortorder": 0,
                               "data": {visit["nodeid"]: "2001-01-01"}})

    _edit(root / "graphs" / f"{fx.BUILDING}.json", add_visit)
    _edit(root / "resources" / "building" / "data.json", keep_some)
    shutil.rmtree(root / "resources" / "person")
    return root


ENTRIES = {
    "Building": [{"phrases": ["built"], "kind": "date", "node": "construction_date"},
                 {"phrases": ["on site"], "kind": "link", "node": "site"},
                 {"phrases": ["designed by"], "kind": "link", "node": "architect"},
                 {"phrases": ["visited"], "kind": "date", "node": "visit_date"},
                 {"phrases": ["role"], "kind": "property", "node": "actor_role"}],
    "Person": [{"phrases": ["called"], "kind": "property", "node": "name"}]}
CUT = {"models": ["Person"], "groups": {"Building": ["construction_date", "heritage_status"]},
       "links": {"Building": ["architect"]}, "values": {}}


def test_slice_keeps_used_groups_their_ancestors_and_links(visited, tmp_path, capsys):
    src, out = tmp_path / "b.json", tmp_path / "sliced.json"
    src.write_text(json.dumps(_bundle(ENTRIES)))
    assert main(["vocab", "slice", str(src), "--data", str(visited / "resources"),
                 "--graphs", str(visited / "graphs"), "-o", str(out)]) == 0
    printed = capsys.readouterr().out
    assert "Building: 3 records; 5 of 7 nodegroups kept" in printed
    assert "values not checked" in printed
    b = json.loads(out.read_text())
    # visit_date holds tiles; associated_actor (actor_role's group) is its parent
    assert [e["node"] for e in b["models"]["Building"]["entries"]] == ["site", "visit_date", "actor_role"]
    assert sorted(b["models"]["Building"]["nodes"]) == ["actor_role", "architect", "site", "visit_date"]
    assert list(b["models"]) == ["Building"]
    assert b["built"]["entries"] == 3
    assert b["sliced"] == CUT


def test_slice_a_split_vocabulary(visited, tmp_path):
    use = Usage(visited / "graphs", visited / "resources")
    src, out = tmp_path / "vocab", tmp_path / "sliced"
    for model, entries in ENTRIES.items():
        for e in entries:
            group = use.group_of[model][e["node"]]
            (src / model).mkdir(parents=True, exist_ok=True)
            (src / model / f"{group}.json").write_text(
                json.dumps({"model": model, "nodegroup": group, "entries": [e]}))
    (src / MANIFEST).write_text(json.dumps({"format": LAYOUT, "models": {}}))
    assert slice_vocab(src, out, use) == CUT
    assert sorted(p.name for p in (out / "Building").iterdir()) == [
        "associated_actor.json", "site.json", "visit_date.json"]
    assert not (out / "Person").exists()
    assert json.loads((out / MANIFEST).read_text())["sliced"] == CUT


def test_slice_keeps_values_in_the_data_and_the_broader_ones(tmp_path):
    root = tmp_path / "data"
    fx.write(root)
    ref = tmp_path / "ref" / "concepts"
    ref.mkdir(parents=True)
    for p in (root / "vocabularies").glob("*.xml"):
        shutil.copy(p, ref)
    builder = fx._id("tile/warehouse/associated_actor/0")

    def warehouse_only(doc):
        # Grade II (narrower than Listed), and an Architect but no Builder
        w = next(r for r in doc["business_data"]["resources"]
                 if r["resourceinstance"]["name"] == "Grain Warehouse")
        w["tiles"] = [t for t in w["tiles"] if t["tileid"] != builder]
        doc["business_data"]["resources"] = [w]

    _edit(root / "resources" / "building" / "data.json", warehouse_only)
    b = _bundle({"Building": [
        {"phrases": ["designed by"], "kind": "link", "node": "actor",
         "qualifier": {"node": "actor_role", "value": "Architect"}},
        {"phrases": ["built by"], "kind": "link", "node": "actor",
         "qualifier": {"node": "actor_role", "value": "Builder"}},
        {"phrases": ["listed"], "kind": "property", "node": "heritage_status",
         "qualifier": {"node": "heritage_status", "value": "Listed"}},
        {"phrases": ["candidate"], "kind": "property", "node": "heritage_status",
         "qualifier": {"node": "heritage_status", "value": "Candidate"}}]})
    b["models"]["Building"]["groups"] = {"associated_actor": {"combos": [
        {"phrases": ["drew"], "node": "actor", "set": {"actor_role": "Architect"}},
        {"phrases": ["made"], "node": "actor", "set": {"actor_role": "Builder"}}]}}
    sliced = slice_bundle(b, Usage(root / "graphs", root / "resources", tmp_path / "ref"))
    assert [e["phrases"][0] for e in sliced["models"]["Building"]["entries"]] == ["designed by", "listed"]
    assert sliced["models"]["Building"]["groups"]["associated_actor"]["combos"] == [
        {"phrases": ["drew"], "node": "actor", "set": {"actor_role": "Architect"}}]
    assert sliced["sliced"]["values"] == {"Building": ["actor_role = Builder",
                                                       "heritage_status = Candidate",
                                                       "actor_role = Builder"]}
    unchecked = slice_bundle(b, Usage(root / "graphs", root / "resources"))
    assert len(unchecked["models"]["Building"]["entries"]) == 4
