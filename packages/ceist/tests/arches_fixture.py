"""A small Arches data_dir in the shared Alizarin / Rós Madair layout:
Sites, Buildings (site → Site, architect → Person, heritage status from a
SKOS thesaurus with a narrower concept, construction date), and People.

    Clock Tower      Listed     Leeds Dock  Ada Lovelace     1845
    Grain Warehouse  Grade II   Leeds Dock  Isambard Brunel  1872
    Boat Shed        Candidate  Salts Mill  Ada Lovelace     1903
"""

import json
import uuid
from pathlib import Path

SITE, BUILDING, PERSON = (f"5e000000-0000-4000-8000-00000000000{i}" for i in (1, 2, 3))

SKOS = """<?xml version="1.0" encoding="UTF-8"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:skos="http://www.w3.org/2004/02/skos/core#">
  <skos:ConceptScheme rdf:about="https://example.org/vocab/HeritageStatus">
    <skos:prefLabel xml:lang="en">Heritage status</skos:prefLabel>
  </skos:ConceptScheme>
  <skos:Concept rdf:about="https://example.org/vocab/HeritageStatus/listed">
    <skos:inScheme rdf:resource="https://example.org/vocab/HeritageStatus"/>
    <skos:prefLabel xml:lang="en">Listed</skos:prefLabel>
    <skos:altLabel xml:lang="en">protected</skos:altLabel>
    <skos:narrower rdf:resource="https://example.org/vocab/HeritageStatus/grade_ii"/>
  </skos:Concept>
  <skos:Concept rdf:about="https://example.org/vocab/HeritageStatus/grade_ii">
    <skos:inScheme rdf:resource="https://example.org/vocab/HeritageStatus"/>
    <skos:prefLabel xml:lang="en">Grade II</skos:prefLabel>
    <skos:broader rdf:resource="https://example.org/vocab/HeritageStatus/listed"/>
  </skos:Concept>
  <skos:Concept rdf:about="https://example.org/vocab/HeritageStatus/candidate">
    <skos:inScheme rdf:resource="https://example.org/vocab/HeritageStatus"/>
    <skos:prefLabel xml:lang="en">Candidate</skos:prefLabel>
  </skos:Concept>
</rdf:RDF>
"""


def _id(name: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"https://example.org/fixture/{name}"))


def _node(graph, alias, name, datatype, config=None, root=False):
    nid = _id(f"{graph}/{alias}")
    n = {"nodeid": nid, "name": name, "alias": alias, "datatype": datatype, "graph_id": graph,
         "istopnode": root, "issearchable": True, "is_collector": not root,
         "nodegroup_id": None if root else nid, "config": config or {}}
    return n


def _graph(gid, name, children):
    root = _node(gid, name.lower(), name, "semantic", root=True)
    nodes = [root] + children
    return {"graph": [{
        "graphid": gid, "name": name, "root": root, "nodes": nodes,
        "nodegroups": [{"nodegroupid": n["nodeid"], "cardinality": "1",
                        "parentnodegroup_id": None} for n in children],
        "edges": [{"edgeid": _id(f"{gid}/edge/{n['alias']}"), "domainnode_id": root["nodeid"],
                   "rangenode_id": n["nodeid"], "graph_id": gid} for n in children],
    }]}


def collection_ids():
    """(collection id, {label: concept id}, {label: prefLabel value id}) as Alizarin
    derives them from the SKOS — the same ids Rós Madair interns."""
    import alizarin
    cache = alizarin.RustRdmCache()
    cid = cache.add_from_skos_xml(SKOS, "http://example.org/")[0]
    simple = json.loads(cache.get_collection(cid).to_simplified_json())
    concepts, values = {}, {}

    def walk(c):
        label = c["prefLabels"]["en"]["value"]
        concepts[label] = c["id"]
        values[label] = c["prefLabels"]["en"]["id"]
        for child in c.get("children") or c.get("narrower") or []:
            if isinstance(child, dict):
                walk(child)

    for c in (simple.get("concepts") or {}).values():
        walk(c)
    return cid, concepts, values


def write(root: Path) -> dict:
    cid, concepts, values = collection_ids()
    graphs = {
        SITE: _graph(SITE, "Site", [_node(SITE, "name", "Name", "string")]),
        PERSON: _graph(PERSON, "Person", [_node(PERSON, "name", "Name", "string")]),
        BUILDING: _graph(BUILDING, "Building", [
            _node(BUILDING, "name", "Name", "string"),
            _node(BUILDING, "heritage_status", "Heritage status", "concept",
                  {"rdmCollection": cid}),
            _node(BUILDING, "site", "Site", "resource-instance",
                  {"graphs": [{"graphid": SITE}]}),
            _node(BUILDING, "architect", "Architect", "resource-instance",
                  {"graphs": [{"graphid": PERSON}]}),
            _node(BUILDING, "construction_date", "Construction date", "date",
                  {"dateFormat": "YYYY-MM-DD"}),
        ]),
    }
    (root / "graphs").mkdir(parents=True)
    for gid, doc in graphs.items():
        (root / "graphs" / f"{gid}.json").write_text(json.dumps(doc))
    (root / "vocabularies").mkdir()
    (root / "vocabularies" / "heritage.xml").write_text(SKOS)

    node = {g: {n["alias"]: n["nodeid"] for n in doc["graph"][0]["nodes"]}
            for g, doc in graphs.items()}
    ids = {}

    def resource(gid, key, name, data):
        rid = _id(f"resource/{key}")
        ids[key] = rid
        tiles = [{"tileid": _id(f"tile/{key}/{alias}"), "nodegroup_id": node[gid][alias],
                  "parenttile_id": None, "resourceinstance_id": rid, "sortorder": 0,
                  "provisionaledits": None, "data": {node[gid][alias]: value}}
                 for alias, value in data.items()]
        return {"resourceinstance": {"resourceinstanceid": rid, "graph_id": gid, "name": name,
                                     "legacyid": None,
                                     "descriptors": {"en": {"name": name, "description": "",
                                                            "map_popup": ""}}},
                "tiles": tiles}

    def text(v):
        return {"en": {"value": v, "direction": "ltr"}}

    def link(key):
        return [{"resourceId": ids[key], "ontologyProperty": "", "inverseOntologyProperty": ""}]

    sites = [resource(SITE, "dock", "Leeds Dock", {"name": text("Leeds Dock")}),
             resource(SITE, "mill", "Salts Mill", {"name": text("Salts Mill")})]
    people = [resource(PERSON, "ada", "Ada Lovelace", {"name": text("Ada Lovelace")}),
              resource(PERSON, "isambard", "Isambard Brunel", {"name": text("Isambard Brunel")})]
    buildings = [
        resource(BUILDING, "tower", "Clock Tower", {
            "name": text("Clock Tower"), "heritage_status": values["Listed"],
            "site": link("dock"), "architect": link("ada"), "construction_date": "1845-06-01"}),
        resource(BUILDING, "warehouse", "Grain Warehouse", {
            "name": text("Grain Warehouse"), "heritage_status": values["Grade II"],
            "site": link("dock"), "architect": link("isambard"),
            "construction_date": "1872-03-15"}),
        resource(BUILDING, "shed", "Boat Shed", {
            "name": text("Boat Shed"), "heritage_status": values["Candidate"],
            "site": link("mill"), "architect": link("ada"), "construction_date": "1903-09-30"}),
    ]
    for folder, items in (("site", sites), ("person", people), ("building", buildings)):
        (root / "resources" / folder).mkdir(parents=True)
        (root / "resources" / folder / "data.json").write_text(
            json.dumps({"business_data": {"resources": items}}))
    return {"collection": cid, "concepts": concepts, "ids": ids}
