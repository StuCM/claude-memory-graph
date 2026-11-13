"""The vocabulary bundle: everything question time needs about a project's
models, in one file built once, offline.

    {"format": "ceist.vocab/2",
     "built": {"graphs_sha256": "…", "models": 16, "entries": 1301, "phrasings": 7392, "groups": 2},
     "extra_type_words": {"stories": "Tale", …},                          # optional
     "models": {
       "Monument": {
         "graphid": "…",
         "nodes": {"<alias>": {"kind": "date|link|property", "label": "…", "targets": [...]}},
         "entries": [
           {"phrases": ["built", "put up", …], "kind": "date",
            "node": "construction_phase_start_date",
            "end_node": "construction_phase_end_date",                     # dates: the event's other end
            "qualifier": {"node": "role_type", "value": "Architect"}},     # v1: read as a combo
           …],
         "groups": {"<nodegroup alias>": {                                # v2
           "phrases": ["construction phase"],                             # name the group itself
           "nodes": {"<alias>": {"role": "type|date|actor|…", "end_node": "<alias>"}},
           "combos": [{"phrases": ["burnt down"], "node": "<alias meant, for a link or date>",
                       "set": {"<alias>": "<value label>", …}}],
           "answers": {"when": "<alias>", …}}}}}}

A v1 bundle still loads.

How it is made (`ceist vocab …`):

    describe   read the models (Alizarin) → one description per model
    prompt     the instruction an LLM follows to write a model's entries, with the
               model's description inline (the LLM sees the schema, never a path
               into the project or a record)
    save       the LLM's JSON reply → vocab/<Model>.json, validated
    split      vocab/<Model>.json → vocab/<Model>/<nodegroup alias>.json, plus
               vocab/manifest.json: each nodegroup's id, parent and a hash of its
               description, so `check --vocab` finds the groups that went stale
    assemble   validate the entries against the descriptions and write the bundle,
               with a hash of the graph files so a stale bundle is caught (`check`)
    slice      (ceist.slicing) cut a bundle down to what one dataset uses

A vocabulary directory holds either layout; with a manifest.json it is read
as the split one. A group file is {"model", "nodegroup", "entries", "group"}: the
group's own block (docs/tasks/ceist-group-grounding.md §2).

In layers (`layered`): a base per graph, `vocabularies/base/<graph id>/` (split
by nodegroup, from the schema alone), and a client layer the site owns that may
only add to it, unless its manifest confirms an override or a renamed node.
"""

import hashlib
import json
from pathlib import Path

FORMAT = "ceist.vocab/3"
READS = {"ceist.vocab/1", "ceist.vocab/2", FORMAT}
LAYOUT = "ceist.vocab-groups/1"
MANIFEST = "manifest.json"
DATE = {"date", "edtf"}
ROLES = {"date", "actor", "place", "type", "cause", "name", "identifier", "description",
         "measure", "unit", "link", "other"}


def kind_of(node: dict) -> str:
    if node["datatype"] in DATE:
        return "date"
    if node["datatype"].startswith("resource-instance"):
        return "link"
    return "property"


def graphs_hash(graphs_dir: str | Path) -> str:
    h = hashlib.sha256()
    for p in sorted(Path(graphs_dir).glob("*.json")):
        h.update(p.name.encode())
        h.update(p.read_bytes())
    return h.hexdigest()


def validate(description: dict, entries: list[dict]) -> tuple[list[str], list[str]]:
    """(errors, warnings) for one model's entries against its description."""
    nodes = {n["alias"]: n for n in description["nodes"]}
    errors, warnings = [], []
    if not isinstance(entries, list):
        return [f"{description['name']}: entries is not a list"], []
    shaped = list(entries)          # malformed entries blanked, so shared_phrases can read them
    for i, e in enumerate(entries):
        if not isinstance(e, dict) or not isinstance(e.get("node"), str):
            errors.append(f"{description['name']} entry {i}: not an object with a node")
            shaped[i] = {}
            continue
        where = f"{description['name']} entry {i} ({e.get('node')})"
        n = nodes.get(e.get("node"))
        if n is None:
            errors.append(f"{where}: no node '{e.get('node')}'")
            continue
        phrases = e.get("phrases")
        if not isinstance(phrases, list) or not all(isinstance(p, str) for p in phrases):
            errors.append(f"{where}: phrases is not a list of strings")
            shaped[i] = {}
            continue
        if not phrases:
            errors.append(f"{where}: no phrases")
        if e.get("end_node"):
            end = nodes.get(e["end_node"]) if isinstance(e["end_node"], str) else None
            if end is None or kind_of(end) != "date":
                errors.append(f"{where}: end_node {e['end_node']!r} is not a date of this model")
            elif kind_of(n) != "date":
                errors.append(f"{where}: end_node on a node that is not a date")
        q = e.get("qualifier")
        if q and not (isinstance(q, dict) and isinstance(q.get("node"), str)
                      and isinstance(q.get("value"), str)):
            errors.append(f"{where}: qualifier {q!r} is not {{\"node\", \"value\"}}")
        elif q:
            qn = nodes.get(q.get("node"))
            if qn is None:
                errors.append(f"{where}: qualifier node '{q.get('node')}' not in the model")
            elif isinstance(qn.get("values"), list) and q.get("value") not in qn["values"]:
                errors.append(f"{where}: '{q.get('value')}' is not a value of {q['node']}")
    for key, owners in shared_phrases(shaped).items():
        for i in owners[1:]:
            warnings.append(f"{description['name']}: '{key}' is a phrasing of two entries "
                            f"({entries[owners[0]]['node']}, {entries[i]['node']}) — ambiguous on purpose?")
    return errors, warnings


def validate_group(description: dict, group: str, block: dict) -> list[str]:
    """The errors in one nodegroup's block: every node on that tile, every
    value in its node's list, every role known."""
    nodes = {n["alias"]: n for n in description["nodes"]}
    where = f"{description['name']}.{group}"
    if group not in (description.get("nodegroups") or {group: None}):
        return [f"{where}: no nodegroup '{group}'"]

    def on_tile(a) -> bool:
        return isinstance(a, str) and a in nodes and nodes[a].get("nodegroup", group) == group

    errors = []
    if not _strings(block.get("phrases", [])):
        errors.append(f"{where}: phrases is not a list of strings")
    for a, n in (block.get("nodes") or {}).items():
        if not on_tile(a):
            errors.append(f"{where}: '{a}' is not a node of this group")
        elif not isinstance(n, dict) or n.get("role") not in ROLES:
            errors.append(f"{where}.{a}: role {n.get('role') if isinstance(n, dict) else n!r} "
                          f"is not one of {', '.join(sorted(ROLES))}")
        elif n.get("end_node") and not (on_tile(n["end_node"])
                                        and kind_of(nodes[n["end_node"]]) == "date"):
            errors.append(f"{where}.{a}: end_node {n['end_node']!r} is not a date of this group")
    for i, c in enumerate(block.get("combos") or []):
        if not (isinstance(c, dict) and _strings(c.get("phrases")) and c["phrases"]
                and isinstance(c.get("set"), dict) and c["set"]):
            errors.append(f"{where} combo {i}: needs phrases and a non-empty set")
            continue
        if "node" in c and not on_tile(c["node"]):
            errors.append(f"{where} combo {i}: node '{c['node']}' is not a node of this group")
        for a, v in c["set"].items():
            values = (nodes.get(a) or {}).get("values")
            if not on_tile(a):
                errors.append(f"{where} combo {i}: '{a}' is not a node of this group")
            elif isinstance(values, list) and v not in values:
                errors.append(f"{where} combo {i}: '{v}' is not a value of {a}")
    for want, a in (block.get("answers") or {}).items():
        if not on_tile(a):
            errors.append(f"{where}: answers.{want} '{a}' is not a node of this group")
    return errors


def _strings(x) -> bool:
    return isinstance(x, list) and all(isinstance(s, str) for s in x)


def shared_phrases(entries: list[dict]) -> dict[str, list[int]]:
    """Each phrase that belongs to more than one entry, with those entries' indices."""
    owners: dict[str, list[int]] = {}
    for i, e in enumerate(entries):
        for ph in e.get("phrases", []):
            seen = owners.setdefault(ph.strip().lower(), [])
            if i not in seen:
                seen.append(i)
    return {k: v for k, v in owners.items() if len(v) > 1}


def nodegroups(graph: dict) -> tuple[dict[str, dict], dict[str, str]]:
    """A graph's nodegroups, {alias: {"id", "parent"}}, and each node's nodegroup
    alias. A nodegroup is named by its top node, whose id it shares."""
    alias = {n["nodeid"]: n.get("alias") or n["nodeid"] for n in graph["nodes"]}
    groups = {alias.get(g["nodegroupid"], g["nodegroupid"]):
              {"id": g["nodegroupid"], "parent": alias.get(g.get("parentnodegroup_id"))}
              for g in graph.get("nodegroups", [])}
    node_group = {n["alias"]: alias.get(n["nodegroup_id"], n["nodegroup_id"])
                  for n in graph["nodes"] if n.get("alias") and n.get("nodegroup_id")}
    return groups, node_group


def group_hash(description: dict, group: str) -> str:
    nodes = [n for n in description["nodes"] if n.get("nodegroup") == group]
    return hashlib.sha256(json.dumps(nodes, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _descriptions(descriptions_dir: str | Path) -> dict:
    out = {}
    for p in sorted(Path(descriptions_dir).glob("*.json")):
        d = json.loads(p.read_text())
        out[d["name"]] = d
    return out


def read_vocab(vocab_dir: str | Path) -> tuple[list[dict], list[str]]:
    """Each model's {"model", "entries", "groups"} from either layout, plus warnings.
    Split layout: a model's entries in the order of its group files' names."""
    root = Path(vocab_dir)
    files = sorted((p for p in root.glob("*.json") if p.name != MANIFEST), key=lambda p: p.stem)
    if not (root / MANIFEST).exists():
        split = sorted(d.name for d in root.iterdir() if d.is_dir() and any(d.glob("*.json"))) if root.is_dir() else []
        if split:
            raise ValueError(f"{root}: model folders ({', '.join(split)}) but no {MANIFEST}, so they would not be "
                             f'read; write {{"format": "{LAYOUT}", "models": {{}}}} to {root / MANIFEST}')
        return [dict({"groups": {}}, **json.loads(p.read_text())) for p in files], []
    listed = json.loads((root / MANIFEST).read_text()).get("models") or {}
    out = []
    for d in sorted(p for p in root.iterdir() if p.is_dir()):
        v = _model_dir(d)
        if v:
            out.append(dict(v, type_words=(listed.get(d.name) or {}).get("type_words") or []))
    warnings = [f"{p.name} not read: {MANIFEST} says the split layout is read" for p in files]
    return out, warnings


def _model_dir(d: Path) -> dict | None:
    """One model's group files, as {"model": <folder name>, "entries", "groups"}."""
    groups = [json.loads(g.read_text()) for g in sorted(d.glob("*.json"), key=lambda p: p.stem)
              if g.name != MANIFEST]
    if not groups:
        return None
    return {"model": d.name, "entries": [e for g in groups for e in g["entries"]],
            "groups": {g["nodegroup"]: g["group"] for g in groups if g.get("group")}}


def layered(graphs: list[dict], base_dir: str | Path, client_dir: str | Path | None = None,
            language: str = "en", ontology_dir: str | Path | None = None,
            records: list[dict] | None = None) -> tuple[dict, list[str]]:
    """A bundle for these graphs from the base layer (base_dir/<graph id>/, split by
    nodegroup) plus an optional client layer (a vocabulary directory keyed by model
    name; its manifest's "base" names the base graph id when the client's differs).
    The client only adds: each phrase, role, answer or type word that would change
    the base's is left out and listed in the merge report returned with the bundle,
    unless the manifest confirms it ("overrides": [{phrase, node, was}]). A base entry
    whose node the client's graph lacks or holds as another kind is dropped and
    reported; "renamed": {old: new} carries the base phrases over to a renamed node.
    Beneath the base, the ontology layer (ontology_dir, by default ontology/cidoc-crm
    beside base_dir) gives phrases by CIDOC-CRM path; a base phrase wins over it. The bundle's
    "links" catalogue is built when `records` is given (an empty list: graphs and CRM only)."""
    from . import crm
    ontology_dir = Path(ontology_dir) if ontology_dir else Path(base_dir).parent / "ontology" / "cidoc-crm"
    ontology = {"entries": [e for p in sorted(ontology_dir.glob("*.json"))
                            for e in json.loads(p.read_text()).get("entries", [])]}
    client = {v["model"]: v for v in read_vocab(client_dir)[0]} if client_dir is not None else {}
    listed = (_manifest(Path(client_dir)).get("models") or {}) if client_dir is not None else {}
    models, report, type_words = {}, [], {}
    for g in graphs:
        name = g.get("name") or g["graphid"]
        if isinstance(name, dict):
            name = name.get(language) or next(iter(name.values()))
        gid = (listed.get(name) or {}).get("base") or g["graphid"]
        base = _model_dir(Path(base_dir) / gid) or {"entries": [], "groups": {}}
        for w in _manifest(Path(base_dir) / gid).get("type_words") or []:
            type_words[w] = name
        nodes = {n["alias"]: {"kind": kind_of(n)} for n in g["nodes"] if n.get("alias")}
        entries, dropped = _fit(name, base["entries"], nodes, (listed.get(name) or {}).get("renamed") or {})
        report += dropped
        models[name] = {"graphid": g["graphid"], "nodes": nodes, "entries": entries,
                        "groups": {a: _block(b) for a, b in base["groups"].items()}}
        report += _add_ontology(name, models[name], crm.ontology_entries(g, ontology))
    for name, model in models.items():
        mine = client.get(name) or {}
        if mine:
            report += _add_client(name, model, mine, (listed.get(name) or {}).get("overrides") or [])
        for w in (listed.get(name) or mine).get("type_words") or []:
            if type_words.setdefault(w, name) != name:
                report.append(f"type word '{w}' names {type_words[w]} already, {name} in the client; "
                              "not applied")
    report += _add_class_words(graphs, models, ontology, type_words)
    bundle = {"format": FORMAT, "models": models}
    if records is not None:
        bundle["links"] = _catalogue(graphs, records)
    if type_words:
        bundle["extra_type_words"] = type_words
    return bundle, report


def _catalogue(graphs: list[dict], records) -> dict:
    from . import catalogue
    from .arches import ArchesVocabulary
    return catalogue.build(ArchesVocabulary(graphs, resources=records))


def _add_ontology(name: str, model: dict, entries: list[dict]) -> list[str]:
    """Add the ontology layer's entries beneath a model's base, marked "layer": "ontology":
    a phrase the base already uses for something else is the base's; one that fits
    several nodes is left out, as a guess."""
    taken, report = _meanings(model), []
    nodes_of: dict[str, set] = {}
    for e in entries:
        for p in e["phrases"]:
            nodes_of.setdefault(p.strip().lower(), set()).add(e["node"])
    for e in entries:
        phrases = [p for p in e["phrases"] if len(nodes_of[p.strip().lower()]) == 1
                   and taken.get(p.strip().lower(), _entry_meaning(e)) == _entry_meaning(e)]
        if phrases:
            model["entries"].append(dict(e, phrases=phrases, layer="ontology"))
    for p, nodes in sorted(nodes_of.items()):
        if len(nodes) > 1 and p not in taken:
            report.append(f"{name}: ontology phrase '{p}' fits {', '.join(sorted(nodes))}; not applied")
    return report


def _add_class_words(graphs: list[dict], models: dict, ontology: dict, type_words: dict) -> list[str]:
    """The ontology layer's class words ("class" entries) as type words of the one model whose
    root is that class; under the base's and client's, and never another model's own name."""
    from . import crm
    from .text import plurals
    roots: dict[str, list[str]] = {}
    for g, name in zip(graphs, models):
        roots.setdefault(crm.root_class(g), []).append(name)
    names = {w for name in models for w in plurals(name)}
    report = []
    for e in ontology["entries"]:
        if e["kind"] != "class" or e["path"] not in roots:
            continue
        owners = roots[e["path"]]
        if len(owners) > 1:
            report.append(f"class words {', '.join(e['phrases'])} ({e['path']}) fit {', '.join(owners)}; not applied")
            continue
        for w in e["phrases"]:
            if w not in names:
                type_words.setdefault(w, owners[0])
    return report


def _fit(name: str, entries: list[dict], nodes: dict, renamed: dict) -> tuple[list[dict], list[str]]:
    """The base entries this client's graph can hold, after its renames; the report for the rest."""
    used = {e["node"] for e in entries}
    report = [f"{name}: node {old} renamed (confirmed) to {new}" if old in used else
              f"{name}: rename of {old} to {new} is stale, the base has no phrase for {old}; not applied"
              for old, new in renamed.items()]
    out = []
    for e in entries:
        node = renamed.get(e["node"], e["node"])
        phrases = ", ".join(f"'{p}'" for p in e["phrases"])
        if node not in nodes:
            report.append(f"{name}: base phrase {phrases} targets node {node}, which this client's graph lacks; "
                          "dropped")
        elif nodes[node]["kind"] != e["kind"]:
            report.append(f"{name}: base phrase {phrases} targets node {node}, which this client's graph has as "
                          f"{nodes[node]['kind']}; dropped")
        else:
            out.append(dict(e, node=node))
    return out, report


def _manifest(d: Path) -> dict:
    return json.loads((d / MANIFEST).read_text()) if (d / MANIFEST).exists() else {}


def _block(b: dict) -> dict:
    """A copy of a group block with every part present, for adding to."""
    return dict(b, phrases=list(b.get("phrases") or []), nodes=dict(b.get("nodes") or {}),
                combos=list(b.get("combos") or []), answers=dict(b.get("answers") or {}))


def _meanings(model: dict) -> dict[str, tuple]:
    """Each phrase of a model's entries and group blocks, with what it means."""
    out = {}
    for e in model["entries"]:
        for p in e["phrases"]:
            out.setdefault(p.strip().lower(), _entry_meaning(e))
    for a, b in model["groups"].items():
        for p in b["phrases"]:
            out.setdefault(p.strip().lower(), ("group", a))
        for c in b["combos"]:
            for p in c["phrases"]:
                out.setdefault(p.strip().lower(), _combo_meaning(a, c))
    return out


def _entry_meaning(e: dict) -> tuple:
    return ("entry", e["node"], json.dumps(e.get("qualifier"), sort_keys=True))


def _combo_meaning(group: str, c: dict) -> tuple:
    return ("combo", group, c.get("node"), json.dumps(c["set"], sort_keys=True))


def _add_client(name: str, model: dict, client: dict, overrides: list[dict]) -> list[str]:
    """Add a client layer's entries and group blocks to one model of the bundle;
    the merge report for what it would have changed, or changed as confirmed."""
    base, report = _meanings(model), []

    def new(phrases: list[str], meaning: tuple) -> list[str]:
        kept = []
        for p in phrases:
            key = p.strip().lower()
            was = base.get(key, meaning)
            if was == meaning:
                kept.append(p)
                continue
            clash = f"'{p}' means {_said(was)} in the base, {_said(meaning)} in the client"
            confirmed = next((o for o in overrides if o["phrase"].strip().lower() == key
                              and o["node"] == _said(meaning)), None)
            if confirmed is None:
                report.append(f"{name}: {clash}; not applied")
            elif confirmed["was"] != _said(was):
                report.append(f"{name}: {clash}; confirmation is stale (it was {confirmed['was']}); not applied")
            else:
                report.append(f"{name}: overridden (confirmed): {clash}")
                _forget(model, key)
                base[key] = meaning
                kept.append(p)
        return kept

    for e in client["entries"]:
        phrases = new(e["phrases"], _entry_meaning(e))
        if phrases:
            model["entries"].append(dict(e, phrases=phrases))
    for a, b in client["groups"].items():
        mine = model["groups"].setdefault(a, _block({}))
        mine["phrases"] += new(b.get("phrases") or [], ("group", a))
        for part in ("nodes", "answers"):
            for k, v in (b.get(part) or {}).items():
                if mine[part].setdefault(k, v) != v:
                    report.append(f"{name}.{a}: {part} {k} is {mine[part][k]} in the base, "
                                  f"{v} in the client; not applied")
        for c in b.get("combos") or []:
            phrases = new(c["phrases"], _combo_meaning(a, c))
            if phrases:
                mine["combos"].append(dict(c, phrases=phrases))
    return report


def _forget(model: dict, phrase: str) -> None:
    """Take a phrase out of a model's entries and group blocks."""
    def other(phrases: list[str]) -> list[str]:
        return [p for p in phrases if p.strip().lower() != phrase]

    model["entries"] = [dict(e, phrases=other(e["phrases"])) for e in model["entries"] if other(e["phrases"])]
    for b in model["groups"].values():
        b["phrases"] = other(b["phrases"])
        b["combos"] = [dict(c, phrases=other(c["phrases"])) for c in b["combos"] if other(c["phrases"])]


def _said(meaning: tuple) -> str:
    return " ".join(str(x) for x in meaning[1:] if x not in (None, "null"))


def assemble(descriptions_dir: str | Path, vocab_dir: str | Path,
             graphs_dir: str | Path | None = None,
             records: list[dict] | None = None) -> tuple[dict, list[str], list[str]]:
    """The bundle, plus (errors, warnings). A bundle with errors shouldn't ship. With `records`,
    the link catalogue is built from the graphs in graphs_dir and them.
    A model's entries are ordered by nodegroup, so both layouts give the same bundle."""
    descriptions = _descriptions(descriptions_dir)
    models, errors, type_words = {}, [], {}
    vocab, warnings = read_vocab(vocab_dir)
    for v in vocab:
        d = descriptions.get(v["model"])
        if d is None:
            errors.append(f"{v['model']}: no description for model '{v['model']}'")
            continue
        for w in v.get("type_words") or []:
            if type_words.setdefault(w, v["model"]) != v["model"]:
                errors.append(f"type word '{w}' names both {type_words[w]} and {v['model']}")
        err, warn = validate(d, v["entries"])
        errors += err + [e for a, b in v["groups"].items() for e in validate_group(d, a, b)]
        warnings += warn
        group_of = {n["alias"]: n.get("nodegroup") or "" for n in d["nodes"]}
        models[v["model"]] = {
            "graphid": d.get("graphid"),
            "nodes": {n["alias"]: {k: x for k, x in (("kind", kind_of(n)),
                                                      ("label", n.get("label") or n["name"]),
                                                      ("targets", n.get("targets"))) if x}
                      for n in d["nodes"]},
            "entries": [dict(e, phrases=sorted({x.strip().lower() for x in e["phrases"] if x.strip()}))
                        for e in sorted(v["entries"], key=lambda e: group_of.get(e.get("node"), ""))],
            "groups": {a: b for a, b in sorted(v["groups"].items()) if not b.get("skip")},
        }
    missing = sorted(set(descriptions) - set(models))
    if missing:
        warnings.append("no vocabulary for: " + ", ".join(missing))
    bundle = {"format": FORMAT,
              "built": {"graphs_sha256": graphs_hash(graphs_dir) if graphs_dir else None,
                        "models": len(models),
                        "entries": sum(len(m["entries"]) for m in models.values()),
                        "phrasings": sum(len(e["phrases"]) for m in models.values()
                                         for e in m["entries"]),
                        "groups": sum(len(m["groups"]) for m in models.values())},
             "models": models}
    if records is not None and graphs_dir:
        from .arches import graph_doc
        bundle["links"] = _catalogue([graph_doc(p) for p in sorted(Path(graphs_dir).glob("*.json"))], records)
    if type_words:
        bundle["extra_type_words"] = type_words
    return bundle, errors, warnings


def manifest(descriptions: dict) -> dict:
    return {"format": LAYOUT, "models": {
        name: {"graphid": d.get("graphid"),
               "nodegroups": {a: dict(g, description_sha256=group_hash(d, a))
                              for a, g in sorted((d.get("nodegroups") or {}).items())}}
        for name, d in sorted(descriptions.items())}}


def split(descriptions_dir: str | Path, vocab_dir: str | Path,
          out_dir: str | Path) -> tuple[list[str], list[str]]:
    """vocab/<Model>.json → <out>/<Model>/<nodegroup alias>.json and <out>/manifest.json;
    (files written, errors). A model with errors is not written."""
    descriptions = _descriptions(descriptions_dir)
    out = Path(out_dir)
    written, errors, done = [], [], {}
    for p in sorted((p for p in Path(vocab_dir).glob("*.json") if p.name != MANIFEST),
                    key=lambda p: p.stem):
        v = json.loads(p.read_text())
        d = descriptions.get(v["model"])
        if d is None or "nodegroups" not in d:
            errors.append(f"{p.name}: no description of {v['model']}'s nodegroups "
                          "(run `ceist vocab describe` again)")
            continue
        group_of = {n["alias"]: n.get("nodegroup") for n in d["nodes"]}
        by_group: dict[str, list] = {}
        for e in v["entries"]:
            g = group_of.get(e.get("node"))
            if g is None:
                errors.append(f"{v['model']}: '{e.get('node')}' is in no nodegroup")
            by_group.setdefault(g, []).append(e)
        if None in by_group:
            continue
        blocks = v.get("groups") or {}
        model_dir = out / v["model"]
        model_dir.mkdir(parents=True, exist_ok=True)
        for old in model_dir.glob("*.json"):
            old.unlink()
        for g in sorted(by_group.keys() | blocks.keys()):
            path = model_dir / f"{g}.json"
            f = {"model": v["model"], "nodegroup": g, "entries": by_group.get(g, [])}
            if g in blocks:
                f["group"] = blocks[g]
            path.write_text(json.dumps(f, indent=1, ensure_ascii=False) + "\n")
            written.append(str(path))
        done[v["model"]] = d
    if done:
        (out / MANIFEST).write_text(json.dumps(manifest(done), indent=1) + "\n")
    return written, errors


def stale_groups(vocab_dir: str | Path, descriptions_dir: str | Path) -> list[str]:
    """The nodegroups whose description changed since the split vocabulary was written."""
    m = json.loads((Path(vocab_dir) / MANIFEST).read_text())
    descriptions = _descriptions(descriptions_dir)
    out = []
    for name, model in m["models"].items():
        d = descriptions.get(name)
        if d is None:
            out.append(f"{name}: no longer described")
            continue
        now = manifest({name: d})["models"][name]["nodegroups"]
        for a, g in model["nodegroups"].items():
            if a not in now:
                out.append(f"{name}.{a}: no longer in the model")
            elif now[a]["description_sha256"] != g["description_sha256"]:
                out.append(f"{name}.{a}: its description changed")
        out += [f"{name}.{a}: new nodegroup" for a in now if a not in model["nodegroups"]]
    return out


def load(path: str | Path) -> dict:
    b = json.loads(Path(path).read_text())
    if b.get("format") not in READS:
        raise ValueError(f"{path}: not a {FORMAT} bundle")
    return b


def stale(bundle: dict, graphs_dir: str | Path) -> bool:
    built = (bundle.get("built") or {}).get("graphs_sha256")
    return built is not None and built != graphs_hash(graphs_dir)


PROMPT = """You are the offline "vocabulary build" step for a no-LLM natural-language search over \
Arches data. At query time only exact phrase lookup and static word vectors run, so the everyday \
phrasings people use for each node must be written now, once.

The model description(s) are at the end of this message, inline. Use ONLY them: there are no files \
to read, and you must not look for any (no records, no test questions: this is a blind build that \
sees the schema, never the data). Each description lists the model's searchable nodes: alias, \
name, datatype, card (the UI card it's on), path (its place in the model tree), label (the UI \
widget label, if different), crm (its CIDOC-CRM context), targets (for links: which models it \
points to), values (labels of a small controlled list or concept collection) or values_count (a \
large one).

Reply with ONLY one JSON object, keyed by model name, with each model's entries:
{{"<Model>": {{"model": "<Model>",
 "entries": [
   {{"phrases": ["...", ...],          // lowercase everyday phrasings
    "kind": "date" | "link" | "property",
    "node": "<alias>",                // the node a question means
    "end_node": "<alias>",            // dates only: the END date of the same timespan, when node is its start
    "qualifier": {{"node": "<alias>", "value": "<label from values>"}}   // optional: when the meaning needs a concept value too
   }}, ...]}}, ...}}

Guidance:
- Think like the people who will ask: members of the public, researchers, officers. Spend effort \
on what they ask about (events and their dates, people/organisations and their roles, types, \
periods, condition, protection, materials, location, dimensions, names, descriptions). Record-\
keeping metadata needs only a few phrases.
- Dates: give ONE entry per event with node = start date and end_node = end date, with the \
event's verbs and phrases (built, constructed, erected, put up, ...). Don't let two events share \
a phrase.
- Links to people/organisations are often generic (an actor link plus a role type). Where the \
role values list roles, write entries with node = the actor link and qualifier = the role for \
commonly asked roles (designed by → Architect, built by → Builder, ...), plus one entry without \
a qualifier for generic involvement. Use only labels in the values list. Likewise typed events \
(a phase type of Construction / Alteration / Destruction).
- Properties: nouns, adjectives and question forms (how tall → height; made of → material).
- Include direction words where they matter ("sailing from" vs "sailing to").
- Keep a model's entries distinguishable; 3–20 phrases per entry; skip nodes nobody would ask \
about by name.
Check that your reply parses as JSON.

Model descriptions:
{descriptions}
"""


def prompt(descriptions_dir: str | Path, models: list[str]) -> str:
    """The build instruction with the models' descriptions inline: the LLM is
    handed the schema itself, never a path into the project (where the
    records live). One model per prompt keeps it small (HER: 20–130 KB each)."""
    blocks = []
    for m in models:
        d = json.loads((Path(descriptions_dir) / f"{m}.json").read_text())
        blocks.append(json.dumps(d, ensure_ascii=False, separators=(",", ":")))
    return PROMPT.format(descriptions="\n\n".join(blocks))


def parse_reply(text: str) -> dict:
    """An LLM's JSON reply, with any ```json fence around it removed."""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else ""
        t = t.rsplit("```", 1)[0]
    return json.loads(t)


def save(reply: str, descriptions_dir: str | Path, vocab_dir: str | Path) -> tuple[list[str], list[str], list[str]]:
    """Write a build reply ({Model: {"model", "entries"}}) as <vocab dir>/<Model>.json,
    validated against each model's description; (written, errors, warnings).
    A model with errors is not written."""
    out = Path(vocab_dir)
    out.mkdir(parents=True, exist_ok=True)
    written, errors, warnings = [], [], []
    try:
        models = parse_reply(reply)
    except ValueError as e:
        return [], [f"the reply is not JSON: {e}"], []
    if not isinstance(models, dict):
        return [], [f"the reply is a JSON {type(models).__name__}, not an object keyed by model"], []
    for name, v in models.items():
        path = Path(descriptions_dir) / f"{name}.json"
        if not path.exists():
            errors.append(f"{name}: no description (not a model of this project)")
            continue
        v = {"model": name, "entries": v.get("entries", []) if isinstance(v, dict) else v}
        err, warn = validate(json.loads(path.read_text()), v["entries"])
        errors += err
        warnings += warn
        if err:
            continue
        (out / f"{name}.json").write_text(json.dumps(v, indent=1, ensure_ascii=False) + "\n")
        written.append(name)
    return written, errors, warnings
