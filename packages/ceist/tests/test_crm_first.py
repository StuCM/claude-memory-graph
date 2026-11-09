"""`ceist vocab crm-first`: which base phrasings a CIDOC-CRM path can carry, and the move that
takes them out of the base only when the layered bundle still gives the node that phrase."""

import json

from ceist import crm_first, vocab_rules

CRM = "http://www.cidoc-crm.org/cidoc-crm/"


def _graph(gid, name, *nodes):
    """(alias, class, property into it, parent alias, datatype); the first is the root."""
    g = {"graphid": gid, "name": name, "nodes": [], "edges": []}
    for alias, cls, prop, up, datatype in nodes:
        g["nodes"].append({"nodeid": f"{gid}/{alias}", "alias": alias, "datatype": datatype, "istopnode": up is None,
                           "ontologyclass": CRM + cls, "parentproperty": CRM + prop if prop else None})
        if up:
            g["edges"].append({"domainnode_id": f"{gid}/{up}", "rangenode_id": f"{gid}/{alias}"})
    return g


def _thing(gid, name):
    return _graph(gid, name, ("thing", "E22", None, None, "semantic"),
                  ("making", "E12", "P108i", "thing", "semantic"),
                  ("maker", "E39", "P14", "making", "resource-instance"),
                  ("span", "E52", "P4", "making", "semantic"),
                  ("made", "E61", "P82a", "span", "date"),
                  ("note", "E33", "P67i", "thing", "semantic"),
                  ("note_a", "E62", "P3", "note", "string"),
                  ("note_b", "E62", "P3", "note", "string"))


def _setup(tmp_path):
    graphs = tmp_path / "graphs"
    graphs.mkdir()
    for gid, name in (("g1", "Thing"), ("g2", "Other")):
        (graphs / f"{name}.json").write_text(json.dumps(_thing(gid, name)))
    base = tmp_path / "vocab" / "base" / "g1"
    base.mkdir(parents=True)
    (base / "making.json").write_text(json.dumps({"model": "Thing", "nodegroup": "making", "entries": [
        {"phrases": ["maker", "about"], "kind": "link", "node": "maker"},
        {"phrases": ["made", "fashioned"], "kind": "date", "node": "made", "end_node": "made_end"},
        {"phrases": ["first note"], "kind": "property", "node": "note_a"}],
        "group": {"phrases": [], "combos": [{"phrases": ["handmade"], "set": {"maker": "Hand"}}]}}))
    onto = tmp_path / "vocab" / "ontology" / "cidoc-crm"
    onto.mkdir(parents=True)
    (onto / "phrases.json").write_text(json.dumps({"format": "ceist.ontology/1", "entries": []}))
    (onto / "generic.json").write_text(json.dumps({"phrases": ["about"]}))
    return graphs, base.parent, onto


def test_each_phrasing_gets_the_shortest_path_that_means_one_node_or_a_reason(tmp_path):
    graphs, base, onto = _setup(tmp_path)
    units = crm_first.phrasings(base, None)
    crm_first.classify(units, crm_first.Sets([graphs]), {"entries": []}, {"about"})
    got = {u["phrase"]: (u["class"], u.get("path")) for u in units}
    assert got == {"maker": ("promotable", "P108i E12 P14"), "made": ("promotable", "P108i E12 P4"),
                   "fashioned": ("promotable", "P108i E12 P4"), "about": ("clash", None),
                   "first note": ("ambiguous path", None), "handmade": ("site-specific", None)}
    assert crm_first.candidates(units) == [
        {"layer": "ontology", "path": "P108i E12 P14", "kind": "link", "phrases": ["maker"]},
        {"layer": "ontology", "path": "P108i E12 P4", "kind": "date", "phrases": ["made", "fashioned"]}]


def test_the_move_takes_a_phrasing_out_only_when_the_ontology_gives_it_back(tmp_path):
    graphs, base, onto = _setup(tmp_path)
    units = crm_first.phrasings(base, None)
    sets = crm_first.Sets([graphs])
    crm_first.classify(units, sets, {"entries": []}, {"about"})
    # the gate passed both, but "fashioned" also names another node in the base, which wins over the ontology
    other = json.loads((base / "g1" / "making.json").read_text())
    other["entries"].append({"phrases": ["fashioned"], "kind": "link", "node": "maker"})
    (base / "g1" / "making.json").write_text(json.dumps(other))
    vocab_rules.apply(crm_first.candidates(units), onto, base, None)
    back = crm_first.move(units, sets, base, None, onto)
    assert [u["phrase"] for u in back] == ["fashioned"]
    entries = json.loads((base / "g1" / "making.json").read_text())["entries"]
    assert entries == [{"phrases": ["about"], "kind": "link", "node": "maker"},
                       {"phrases": ["first note"], "kind": "property", "node": "note_a"},
                       {"phrases": ["fashioned"], "kind": "link", "node": "maker"},
                       {"phrases": ["fashioned"], "kind": "date", "node": "made", "end_node": "made_end"}]
