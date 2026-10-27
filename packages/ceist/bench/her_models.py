"""Read Arches models through Alizarin into the node descriptions the
vocabulary build and the matchers use: each searchable node with its card,
its path through the model's tree, its datatype and (for links) its targets.

    python her_models.py <graphs/resource_models dir> <out dir> [<reference_data dir>]

writes <out dir>/<Model name>.json, one per model.

With reference_data (the package's SKOS concepts and collections, loaded by
Alizarin), each concept node also lists its collection's labels when the
collection is small enough to read (≤ 120 terms: roles, phase types,
designation types); large thesauri (monument types) give only their size —
those are matched through their own SKOS labels, not an LLM.

Skipped: semantic (structural) nodes, and the *_metatype concept nodes HER
models hang off every qualifier — they say what kind of qualifier a value
is, not something a question asks about.
"""

import json
import sys
from pathlib import Path

import alizarin

SKIP_TYPES = {"semantic"}


def _text(v):
    return v.get("en") or next(iter(v.values()), "") if isinstance(v, dict) else (v or "")


SMALL = 120


def load_rdm(ref_dir: str):
    rdm = alizarin.RustRdmCache()
    root = Path(ref_dir)
    for p in sorted((root / "concepts").glob("*.xml")) + sorted((root / "collections").glob("*.xml")):
        rdm.add_from_skos_xml(p.read_text(), "http://www.archesproject.org/")
    return rdm


def collection_labels(rdm, cid):
    if rdm is None or not cid or not rdm.has_collection(cid):
        return None
    col = rdm.get_collection(cid)
    ids = col.get_concept_ids()
    if len(ids) > SMALL:
        return len(ids)
    return sorted({col.get_concept(i).get_label("en") or "" for i in ids} - {""})


def describe_graph(doc: dict, graph_names: dict, rdm=None) -> dict:
    g = doc["graph"][0] if "graph" in doc else doc
    alizarin.register_graph(json.dumps(g))
    tree = alizarin.get_graph_schema(g["graphid"])
    nodes = {n["nodeid"]: n for n in g["nodes"]}
    groups = {ng["nodegroupid"]: ng for ng in g.get("nodegroups", [])}
    card_of = {c["nodegroup_id"]: _text(c["name"]) for c in g.get("cards", [])}
    label_of = {x["node_id"]: _text(x.get("label")) for x in g.get("cards_x_nodes_x_widgets", [])}

    def card(ngid):
        while ngid:
            if ngid in card_of:
                return card_of[ngid]
            ngid = (groups.get(ngid) or {}).get("parentnodegroup_id")
        return ""

    out = []

    def walk(sub: dict, path: list[str]):
        for alias, info in sub.items():
            n = nodes.get(info.get("nodeid"))
            name = _text(n["name"]) if n else alias
            here = path + [name]
            if n and n["datatype"] not in SKIP_TYPES and not alias.endswith("metatype"):
                entry = {"alias": alias, "name": name, "datatype": n["datatype"],
                         "card": card(n.get("nodegroup_id")),
                         "path": " > ".join(here[:-1])}
                if label_of.get(n["nodeid"]) and label_of[n["nodeid"]] != name:
                    entry["label"] = label_of[n["nodeid"]]
                targets = [graph_names.get(x.get("graphid"), x.get("graphid"))
                           for x in (n.get("config") or {}).get("graphs") or []]
                if targets:
                    entry["targets"] = targets
                if n["datatype"] in ("concept", "concept-list"):
                    labels = collection_labels(rdm, (n.get("config") or {}).get("rdmCollection"))
                    if isinstance(labels, list):
                        entry["values"] = labels
                    elif labels:
                        entry["values_count"] = labels
                out.append(entry)
            walk(info.get("children") or {}, here)

    walk(tree, [])
    return {"name": _text(g["name"]), "graphid": g["graphid"],
            "description": _text(g.get("description")), "nodes": out}


def main(src: str, dest: str, ref_dir: str | None = None):
    rdm = load_rdm(ref_dir) if ref_dir else None
    files = sorted(Path(src).glob("*.json"))
    docs = [json.loads(p.read_text()) for p in files]
    graph_names = {}
    for d in docs:
        g = d["graph"][0]
        graph_names[g["graphid"]] = _text(g["name"])
    models = {}
    for d in docs:
        m = describe_graph(d, graph_names, rdm)
        models[m["name"]] = m
    out = Path(dest)
    out.mkdir(parents=True, exist_ok=True)
    for name, m in models.items():
        (out / f"{name}.json").write_text(json.dumps(m, indent=1))
    total = sum(len(m["nodes"]) for m in models.values())
    print(f"{len(models)} models, {total} searchable nodes → {dest}")
    for name, m in models.items():
        print(f"  {name:38s} {len(m['nodes'])}")


if __name__ == "__main__":
    main(*sys.argv[1:4])
