"""A small Arches data_dir in the shared Alizarin / Rós Madair layout:
Sites, Buildings (site → Site, architect → Person, heritage status from a
SKOS thesaurus with a narrower concept, construction date), and People.

    Clock Tower      Listed     Leeds Dock  Ada Lovelace     1845   actors: Ada (Architect)
    Grain Warehouse  Grade II   Leeds Dock  Isambard Brunel  1872   actors: Ada (Builder),
                                                                            Isambard (Architect)
    Boat Shed        Candidate  Salts Mill  Ada Lovelace     1903

With `phases=True`, phases (type, cause and date on one tile each):
    Clock Tower      Destruction by Fire 1940
    Grain Warehouse  Destruction by Flood 1960 · Damage by Fire 1900

With `numbers=True`, Building has Height (m), Occupant capacity and Insured value:
    Clock Tower      30 m    200   50,000,000 (5 crore)
    Grain Warehouse  12.5 m  500   2,500,000
    Boat Shed        31 m    20    120,000
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


ROLES = """<?xml version="1.0" encoding="UTF-8"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:skos="http://www.w3.org/2004/02/skos/core#">
  <skos:ConceptScheme rdf:about="https://example.org/vocab/Roles">
    <skos:prefLabel xml:lang="en">Roles</skos:prefLabel>
  </skos:ConceptScheme>
  <skos:Concept rdf:about="https://example.org/vocab/Roles/architect">
    <skos:inScheme rdf:resource="https://example.org/vocab/Roles"/>
    <skos:prefLabel xml:lang="en">Architect</skos:prefLabel>
  </skos:Concept>
  <skos:Concept rdf:about="https://example.org/vocab/Roles/builder">
    <skos:inScheme rdf:resource="https://example.org/vocab/Roles"/>
    <skos:prefLabel xml:lang="en">Builder</skos:prefLabel>
  </skos:Concept>
</rdf:RDF>
"""


def _list(name: str, labels: list[str]) -> str:
    """A flat SKOS thesaurus."""
    scheme = f"https://example.org/vocab/{name}"
    concepts = "".join(f"""
  <skos:Concept rdf:about="{scheme}/{label.lower()}">
    <skos:inScheme rdf:resource="{scheme}"/>
    <skos:prefLabel xml:lang="en">{label}</skos:prefLabel>
  </skos:Concept>""" for label in labels)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:skos="http://www.w3.org/2004/02/skos/core#">
  <skos:ConceptScheme rdf:about="{scheme}">
    <skos:prefLabel xml:lang="en">{name}</skos:prefLabel>
  </skos:ConceptScheme>{concepts}
</rdf:RDF>
"""


PHASES = _list("PhaseType", ["Damage", "Destruction", "Alteration"])
CAUSES = _list("Cause", ["Fire", "Flood"])


def _id(name: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"https://example.org/fixture/{name}"))


def _node(graph, alias, name, datatype, config=None, root=False):
    nid = _id(f"{graph}/{alias}")
    n = {"nodeid": nid, "name": name, "alias": alias, "datatype": datatype, "graph_id": graph,
         "istopnode": root, "issearchable": True, "is_collector": not root,
         "nodegroup_id": None if root else nid, "config": config or {}}
    return n


def _graph(gid, name, children, nested=None):
    """`nested`: {parent semantic node alias: [its child nodes]} — nodes that
    share their parent's nodegroup (one tile holds them all)."""
    root = _node(gid, name.lower(), name, "semantic", root=True)
    nested = nested or {}
    inner = [n for kids in nested.values() for n in kids]
    by_alias = {n["alias"]: n for n in children}
    edges = [(root, n) for n in children] + [(by_alias[a], n) for a, kids in nested.items()
                                             for n in kids]
    return {"graph": [{
        "graphid": gid, "name": name, "root": root, "nodes": [root] + children + inner,
        "nodegroups": [{"nodegroupid": n["nodeid"],
                        "cardinality": "n" if n["alias"] in nested else "1",
                        "parentnodegroup_id": None} for n in children],
        "edges": [{"edgeid": _id(f"{gid}/edge/{b['alias']}"), "domainnode_id": a["nodeid"],
                   "rangenode_id": b["nodeid"], "graph_id": gid} for a, b in edges],
    }]}


def collection_ids(skos: str = SKOS):
    """(collection id, {label: concept id}, {label: prefLabel value id}) as Alizarin
    derives them from the SKOS — the same ids Rós Madair interns."""
    import alizarin
    cache = alizarin.RustRdmCache()
    cid = cache.add_from_skos_xml(skos, "http://example.org/")[0]
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


def _point(lng, lat):
    return {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {}, "geometry": {"type": "Point", "coordinates": [lng, lat]}}]}


def write(root: Path, phases: bool = False, places: bool = False, numbers: bool = False) -> dict:
    """`places`: a location node on Building and Site; Leeds Dock has none, Salts Mill
    is a polygon round the Boat Shed, the Warehouse is 1 km and the Shed 8 km from the Tower."""
    cid, concepts, values = collection_ids()
    rid_, roles, role_values = collection_ids(ROLES)
    concepts.update(roles)
    pid, phase_types, phase_values = collection_ids(PHASES)
    kid, causes, cause_values = collection_ids(CAUSES)
    concepts.update(phase_types)
    concepts.update(causes)
    # an "associated actor" entry: a link and a role in ONE nodegroup (one tile each)
    assoc = _node(BUILDING, "associated_actor", "Associated actor", "semantic")
    actor = dict(_node(BUILDING, "actor", "Actor", "resource-instance",
                       {"graphs": [{"graphid": PERSON}]}), nodegroup_id=assoc["nodeid"])
    actor_role = dict(_node(BUILDING, "actor_role", "Role", "concept",
                            {"rdmCollection": rid_}), nodegroup_id=assoc["nodeid"])
    # a phase entry: its type, cause and date on one tile
    phase = _node(BUILDING, "phase", "Phase", "semantic")
    phase_nodes = [dict(_node(BUILDING, alias, name, datatype, config), nodegroup_id=phase["nodeid"])
                   for alias, name, datatype, config in (
                       ("phase_type", "Phase type", "concept", {"rdmCollection": pid}),
                       ("phase_cause", "Phase cause", "concept", {"rdmCollection": kid}),
                       ("phase_date", "Phase date", "date", {"dateFormat": "YYYY-MM-DD"}))]
    graphs = {
        SITE: _graph(SITE, "Site", [_node(SITE, "name", "Name", "string"),
                                    *([_node(SITE, "location", "Location",
                                             "geojson-feature-collection")] if places else [])]),
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
            assoc,
            *([phase] if phases else []),
            *([_node(BUILDING, "location", "Location", "geojson-feature-collection")]
              if places else []),
            *([_node(BUILDING, "height_m", "Height (m)", "number"),
               _node(BUILDING, "capacity", "Occupant capacity", "number"),
               _node(BUILDING, "insured_value", "Insured value", "number")] if numbers else []),
        ], nested={"associated_actor": [actor, actor_role],
                   **({"phase": phase_nodes} if phases else {})}),
    }
    (root / "graphs").mkdir(parents=True)
    for gid, doc in graphs.items():
        (root / "graphs" / f"{gid}.json").write_text(json.dumps(doc))
    (root / "vocabularies").mkdir()
    (root / "vocabularies" / "heritage.xml").write_text(SKOS)
    (root / "vocabularies" / "roles.xml").write_text(ROLES)
    if phases:
        (root / "vocabularies" / "phases.xml").write_text(PHASES)
        (root / "vocabularies" / "causes.xml").write_text(CAUSES)

    node = {g: {n["alias"]: n["nodeid"] for n in doc["graph"][0]["nodes"]}
            for g, doc in graphs.items()}
    ids = {}

    def resource(gid, key, name, data, entries=()):
        """`entries`: (group alias, {alias: value, …}) — one multi-node tile each."""
        rid = _id(f"resource/{key}")
        ids[key] = rid
        tiles = [{"tileid": _id(f"tile/{key}/{alias}"), "nodegroup_id": node[gid][alias],
                  "parenttile_id": None, "resourceinstance_id": rid, "sortorder": 0,
                  "provisionaledits": None, "data": {node[gid][alias]: value}}
                 for alias, value in data.items()]
        tiles += [{"tileid": _id(f"tile/{key}/{group}/{i}"), "nodegroup_id": node[gid][group],
                   "parenttile_id": None, "resourceinstance_id": rid, "sortorder": i,
                   "provisionaledits": None,
                   "data": {node[gid][a]: v for a, v in vals.items()}}
                  for i, (group, vals) in enumerate(entries)]
        return {"resourceinstance": {"resourceinstanceid": rid, "graph_id": gid, "name": name,
                                     "legacyid": None,
                                     "descriptors": {"en": {"name": name, "description": "",
                                                            "map_popup": ""}}},
                "tiles": tiles}

    def text(v):
        return {"en": {"value": v, "direction": "ltr"}}

    def link(key):
        return [{"resourceId": ids[key], "ontologyProperty": "", "inverseOntologyProperty": ""}]

    def phase_of(kind, cause, when):
        return [("phase", {"phase_type": phase_values[kind], "phase_cause": cause_values[cause],
                           "phase_date": when})] if phases else []

    def at(lng, lat):
        return {"location": _point(lng, lat)} if places else {}

    def sized(height, capacity, value):
        return {"height_m": height, "capacity": capacity, "insured_value": value} if numbers else {}

    mill_area = {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {},
                 "geometry": {"type": "Polygon", "coordinates": [[[-1.51, 53.865], [-1.49, 53.865],
                                                                  [-1.49, 53.88], [-1.51, 53.88],
                                                                  [-1.51, 53.865]]]}}]}
    sites = [resource(SITE, "dock", "Leeds Dock", {"name": text("Leeds Dock")}),
             resource(SITE, "mill", "Salts Mill", {"name": text("Salts Mill"),
                                                   **({"location": mill_area} if places else {})})]
    people = [resource(PERSON, "ada", "Ada Lovelace", {"name": text("Ada Lovelace")}),
              resource(PERSON, "isambard", "Isambard Brunel", {"name": text("Isambard Brunel")})]
    buildings = [
        resource(BUILDING, "tower", "Clock Tower", {
            "name": text("Clock Tower"), "heritage_status": values["Listed"],
            "site": link("dock"), "architect": link("ada"), "construction_date": "1845-06-01", **at(-1.5, 53.8),
            **sized(30, 200, 50000000)},
            entries=[("associated_actor", {"actor": link("ada"),
                                           "actor_role": role_values["Architect"]}),
                     *phase_of("Destruction", "Fire", "1940-05-01")]),
        # Ada built it and Isambard designed it: "designed by Ada" must NOT match
        resource(BUILDING, "warehouse", "Grain Warehouse", {
            "name": text("Grain Warehouse"), "heritage_status": values["Grade II"],
            "site": link("dock"), "architect": link("isambard"),
            "construction_date": "1872-03-15", **at(-1.5, 53.809),
            **sized(12.5, 500, 2500000)},
            entries=[("associated_actor", {"actor": link("ada"),
                                           "actor_role": role_values["Builder"]}),
                     ("associated_actor", {"actor": link("isambard"),
                                           "actor_role": role_values["Architect"]}),
                     # Destruction and Fire, but on different tiles
                     *phase_of("Destruction", "Flood", "1960-01-01"),
                     *phase_of("Damage", "Fire", "1900-01-01")]),
        resource(BUILDING, "shed", "Boat Shed", {
            "name": text("Boat Shed"), "heritage_status": values["Candidate"],
            "site": link("mill"), "architect": link("ada"), "construction_date": "1903-09-30", **at(-1.5, 53.872),
            **sized(31, 20, 120000)}),
    ]
    for folder, items in (("site", sites), ("person", people), ("building", buildings)):
        (root / "resources" / folder).mkdir(parents=True)
        (root / "resources" / folder / "data.json").write_text(
            json.dumps({"business_data": {"resources": items}}))
    return {"collection": cid, "concepts": concepts, "ids": ids}
