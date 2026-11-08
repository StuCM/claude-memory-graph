"""Read Arches models through Alizarin into the node descriptions the
vocabulary build and the matchers use: each searchable node with its card and nodegroup,
its path through the model's tree, its datatype, its CIDOC-CRM context and
(for links) its targets.

    ceist vocab describe <graphs/resource_models dir> <out dir> [--reference <reference_data dir>]

writes <out dir>/<Model name>.json, one per model. Needs alizarin.

With reference_data (the package's controlled lists and thesauri: SKOS XML
or collection JSON under concepts/, collections/ or controlled_lists/,
loaded by Alizarin), each controlled node — a controlled list (`reference`)
or a legacy concept node — also lists its list's labels when the list is
small enough to read (≤ 120 items: roles, phase types, designation types);
large ones (monument types) give only their size — those are matched
through their own labels, not an LLM.

Skipped: semantic (structural) nodes, and the *_metatype concept nodes HER
models hang off every qualifier — they say what kind of qualifier a value
is, not something a question asks about.
"""

import json
from pathlib import Path

import alizarin

from .arches import CONTROLLED_TYPES, collection_of
from .bundle import nodegroups

SKIP_TYPES = {"semantic"}


def _text(v):
    return v.get("en") or next(iter(v.values()), "") if isinstance(v, dict) else (v or "")


SMALL = 120


def reference_files(ref_dir: str | Path) -> list[Path]:
    root = Path(ref_dir)
    return [p for d in ("concepts", "collections", "controlled_lists")
            for ext in ("*.xml", "*.json") for p in sorted((root / d).glob(ext))]


def load_rdm(ref_dir: str):
    from .arches import load_reference_data
    return load_reference_data(reference_files(ref_dir))[0]


def collection_labels(rdm, cid, small=None):
    if rdm is None or not cid or not rdm.has_collection(cid):
        return None
    col = rdm.get_collection(cid)
    ids = col.get_concept_ids()
    if len(ids) > (SMALL if small is None else small):
        return len(ids)
    return sorted({col.get_concept(i).get_label("en") or "" for i in ids} - {""})


def crm_label(uri: str | None) -> str:
    """'http://…/cidoc-crm/P14_carried_out_by' → 'carried out by';
    'E12_Production' → 'production'. CRM identifiers name themselves."""
    if not uri:
        return ""
    local = uri.rstrip("/").rsplit("/", 1)[-1].rsplit("#", 1)[-1]
    words = local.split("_")
    if words and words[0][:1] in "EP" and words[0][1:2].isdigit():
        words = words[1:]
    return " ".join(words).replace("-", " ").lower()


def describe_graph(doc: dict, graph_names: dict, rdm=None, small=None) -> dict:
    g = doc["graph"][0] if "graph" in doc else doc
    for n in g["nodes"]:
        if n.get("config") is None:   # Alizarin refuses a null config (arches-lingo has them)
            n["config"] = {}
    alizarin.register_graph(json.dumps(g))
    tree = alizarin.get_graph_schema(g["graphid"])
    nodes = {n["nodeid"]: n for n in g["nodes"]}
    groups = {ng["nodegroupid"]: ng for ng in g.get("nodegroups", [])}
    card_of = {c["nodegroup_id"]: _text(c["name"]) for c in g.get("cards", [])}
    label_of = {x["node_id"]: _text(x.get("label")) for x in g.get("cards_x_nodes_x_widgets", [])}
    by_alias, group_of = nodegroups(g)

    def card(ngid):
        while ngid:
            if ngid in card_of:
                return card_of[ngid]
            ngid = (groups.get(ngid) or {}).get("parentnodegroup_id")
        return ""

    out = []

    def walk(sub: dict, path: list[str], classes: list[str] = ()):
        for alias, info in sub.items():
            n = nodes.get(info.get("nodeid"))
            name = _text(n["name"]) if n else alias
            here = path + [name]
            cls = crm_label(n.get("ontologyclass")) if n else ""
            inside = list(classes) + ([cls] if cls and n and n["datatype"] == "semantic" else [])
            if n and n["datatype"] not in SKIP_TYPES and not alias.endswith("metatype"):
                entry = {"alias": alias, "name": name, "datatype": n["datatype"],
                         "card": card(n.get("nodegroup_id")),
                         "path": " > ".join(here[:-1]), "nodegroup": group_of.get(alias)}
                if label_of.get(n["nodeid"]) and label_of[n["nodeid"]] != name:
                    entry["label"] = label_of[n["nodeid"]]
                targets = [graph_names.get(x.get("graphid"), x.get("graphid"))
                           for x in (n.get("config") or {}).get("graphs") or []]
                if targets:
                    entry["targets"] = targets
                crm = [x for x in [crm_label(n.get("parentproperty"))] + inside[-2:] if x]
                if crm:
                    entry["crm"] = list(dict.fromkeys(crm))
                if n["datatype"] in CONTROLLED_TYPES:
                    labels = collection_labels(rdm, collection_of(n), small)
                    if isinstance(labels, list):
                        entry["values"] = labels
                    elif labels:
                        entry["values_count"] = labels
                out.append(entry)
            walk(info.get("children") or {}, here, inside)

    walk(tree, [])
    return {"name": _text(g["name"]), "graphid": g["graphid"],
            "description": _text(g.get("description")), "nodegroups": by_alias, "nodes": out}


def describe(src: str | Path, dest: str | Path, ref_dir: str | Path | None = None,
             small: float | None = None) -> dict:
    """Describe every model in `src` into `dest`/<Model>.json; returns {name: description}.
    `small` overrides SMALL, the longest list whose labels are listed."""
    rdm = load_rdm(ref_dir) if ref_dir else None
    docs = [json.loads(p.read_text()) for p in sorted(Path(src).glob("*.json"))]
    graph_names = {}
    for d in docs:
        g = d["graph"][0] if "graph" in d else d
        graph_names[g["graphid"]] = _text(g["name"])
    models = {}
    for d in docs:
        m = describe_graph(d, graph_names, rdm, small)
        models[m["name"]] = m
    out = Path(dest)
    out.mkdir(parents=True, exist_ok=True)
    for name, m in models.items():
        (out / f"{name}.json").write_text(json.dumps(m, indent=1))
    return models
